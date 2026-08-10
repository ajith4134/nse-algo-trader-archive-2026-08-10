"""The assembled INDEX-OPTION bot — composes the four engines into one ``SegmentBot`` (slice 5).

Pipeline per index underlying, each cycle:
  raw prices  → volatility-regime engine (slice 1) → regime + VRP
  option chain → IV-surface engine     (slice 2) → IV-rank + skew + term structure
  (regime, surface) → structure selector (slice 3) → structure + conviction
  → deterministic policy (slice 3) → sized TradeProposal
  → learned head (slice 4), if earned → refine calibrated_prob (else deterministic passthrough)

The bot PROPOSES only (crypto §03b) — its proposals flow to the portfolio supervisor (slice 6). It owns its
own data (via an injected ``IndexOptionDataAdapter`` — a DI seam so production feeds and test fakes swap
without touching the bot, Rule J), its own competency/track-record store, and its own self-learning loop
(feeds realised outcomes to the head + drift monitor). Each emitted proposal is logged as a labelled trial,
which is exactly the dataset the learned head trains on once outcomes accrue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from nse_algo_trader.segment_bots.index_option_bot.deterministic_index_option_policy import (
    DeterministicIndexOptionPolicy,
)
from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolRankStore,
    ImpliedVolSurfaceEngine,
    ImpliedVolSurfaceState,
)
from nse_algo_trader.segment_bots.index_option_bot.structure_selector import (
    IndexOptionStructureSelector,
)
from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeEngine,
    VolatilityRegimeState,
    VolatilityRegimeStore,
)
from nse_algo_trader.segment_bots.index_option_bot.win_probability_head import (
    IndexOptionWinProbabilityHead,
    LabelledTrial,
    WinProbabilityHeadStore,
    engineer_features,
)
from nse_algo_trader.segment_bots.directional_ai.directional_side_brain import DirectionalSideBrain
from nse_algo_trader.option_alpha.vol_risk_premium_richness_engine import (
    VolRichnessInput,
    VolRichnessState,
    VolRiskPremiumRichnessEngine,
    VrpHistoryStore,
)
from nse_algo_trader.option_alpha.option_opportunity_scorer import (
    OpportunityFeatures,
    OpportunityScore,
    OpportunityScoreLedger,
    OptionOpportunityScorer,
)
from nse_algo_trader.option_alpha.engine_performance_learner import (
    EnginePerformanceLearner,
    EnginePerformanceStore,
)
from nse_algo_trader.option_alpha.terminal_distribution_model import TerminalDistributionModel
from nse_algo_trader.option_alpha.structure_payoff_optimizer import (
    StructurePayoffOptimizer,
    build_plan_from_optimized_structure,
    live_lot_size as _live_lot_size,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    BotCompetency,
    MarketSegment,
    TradeProposal,
    TradeSide,
)

_EARNED_MIN_CLOSED_TRADES = 30  # bot competency ladder: below this, size is gated to 0 (Rule Q)
_COMPETENCY_TRADES_PER_LEVEL = 40  # closed trades per competency level (0..5)
# exchange-set contract lot sizes (revised quarterly by NSE/BSE — TODO source from the live instrument dump)
_INDEX_LOT_SIZES = {"NIFTY": 75, "BANKNIFTY": 35, "FINNIFTY": 65, "MIDCPNIFTY": 140, "NIFTYNXT50": 120,
                    "SENSEX": 20, "BANKEX": 30}


def _opportunity_features(g: _GatheredIndexState, richness: VolRichnessState | None) -> OpportunityFeatures:
    """Assemble the scorer's per-name feature vector from the gathered engine states + cross-sectional richness."""
    regime = g.regime
    stressed_prob = (float(regime.regime_probabilities[-1])
                     if getattr(regime, "maturity", "") == "earned" and len(regime.regime_probabilities) >= 2
                     else 0.0)
    return OpportunityFeatures(
        underlying=g.underlying,
        richness=richness.richness if richness is not None else None,
        vrp=regime.variance_risk_premium,
        stressed_prob=stressed_prob,
        is_range_bound=g.trend_conviction < 0.15,  # weak directional read → range-bound (Θ-friendly)
        trend_conviction=g.trend_conviction,
        abs_skew=abs(g.surface.risk_reversal_25d),
        abs_term_slope=abs(getattr(g.surface, "term_structure_slope", 0.0) or 0.0),
        is_expiry_day=g.is_expiry,
        pre_event=False,  # index options have no single-name event gate
    )


@dataclass(frozen=True)
class _GatheredIndexState:
    """Pass-1 per-name state (fitted engines) carried into the cross-sectional richness pass + selection."""

    underlying: str
    trade_date: str
    regime: VolatilityRegimeState
    surface: ImpliedVolSurfaceState
    expiry: str
    is_expiry: bool
    trend: TradeSide
    trend_conviction: float
    chain: pd.DataFrame
    spot: float


class IndexOptionDataAdapter(Protocol):
    """The bot's own data seam — production wires real feeds; tests inject a fake (Rule J). No DB in the bot."""

    def index_underlyings(self) -> list[str]: ...
    def price_series(self, underlying: str) -> pd.Series: ...
    def option_chain(self, underlying: str) -> tuple[pd.DataFrame, str]: ...  # (chain_df, trade_date ISO)
    def implied_atm_vol(self, underlying: str) -> float | None: ...
    def nearest_expiry(self, underlying: str) -> str: ...
    def is_expiry_day(self, underlying: str) -> bool: ...
    def trend_side(self, underlying: str) -> TradeSide: ...


@dataclass
class ClosedTrade:
    """A realised outcome for one of the bot's proposals — the raw material of competency + head training."""

    features: dict
    won: bool
    entry_epoch: float
    calibrated_prob_at_entry: float


class BotTrackRecordStore:
    """Persists the bot's closed trades → competency + the labelled trials the learned head trains on."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "index_option_bot_closed_trades.json"

    def record(self, trade: ClosedTrade) -> None:
        rows = self._load_raw()
        rows.append(
            {
                "features": trade.features,
                "won": trade.won,
                "entry_epoch": trade.entry_epoch,
                "calibrated_prob_at_entry": trade.calibrated_prob_at_entry,
            }
        )
        self._path.write_text(json.dumps(rows[-5000:], indent=0))

    def _load_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def labelled_trials(self) -> list[LabelledTrial]:
        return [
            LabelledTrial(features=r["features"], won=bool(r["won"]), entry_epoch=float(r["entry_epoch"]))
            for r in self._load_raw()
        ]

    def closed_count(self) -> int:
        return len(self._load_raw())


class IndexOptionBot:
    """The INDEX-OPTION SegmentBot: proposes structured option trades over the full index universe."""

    name = "index_option_bot"
    segment = MarketSegment.INDEX_OPTION

    def __init__(
        self,
        data_adapter: IndexOptionDataAdapter,
        store_dir: Path,
        risk_free_rate: float = 0.065,
        risk_account_notional: float = 1_000_000.0,
    ):
        # the optimizer's per-structure defined-risk cap is a fraction of the ACCOUNT capital (not a hardcoded
        # ₹1M) so it scales with real capital; the supervisor's per-trade min/max-capital sizing is the true
        # position limit downstream.
        self._adapter = data_adapter
        self._regime_store = VolatilityRegimeStore(store_dir / "regime")
        self._iv_store = ImpliedVolRankStore(store_dir / "iv_rank")
        self._head_store = WinProbabilityHeadStore(store_dir / "head")
        self._track_store = BotTrackRecordStore(store_dir / "track_record")
        self._selector = IndexOptionStructureSelector()
        self._policy = DeterministicIndexOptionPolicy()
        self._head = IndexOptionWinProbabilityHead(self._head_store)
        self._brain = DirectionalSideBrain(store_dir / "directional")
        self._vrp_engine = VolRiskPremiumRichnessEngine(VrpHistoryStore(store_dir / "vrp"))
        self._scorer = OptionOpportunityScorer(OpportunityScoreLedger(store_dir / "opportunity"))
        self._distribution = TerminalDistributionModel()
        self._optimizer = StructurePayoffOptimizer(account_notional=risk_account_notional)
        self._engine_perf = EnginePerformanceStore(store_dir / "engine_perf")
        self._learner = EnginePerformanceLearner(self._engine_perf)
        self._rate = risk_free_rate

    def record_engine_outcome(self, engine: str, won: bool, realized_pnl: float) -> None:
        """Feed a closed trade's engine + outcome to the learner → re-weights the scorer next cycle (slice 5)."""
        self._engine_perf.record(engine, won, realized_pnl)

    def competency(self) -> BotCompetency:
        """Earned track record → drives the supervisor's competency-weighted allocation (maturity ladder)."""
        closed = self._track_store.closed_count()
        level = min(5, closed // _COMPETENCY_TRADES_PER_LEVEL)
        return BotCompetency(
            level=level,
            closed_trades=closed,
            rolling_sharpe=None,
            calibration_error=None,
            is_earned=closed >= _EARNED_MIN_CLOSED_TRADES,
        )

    def propose(self, now_epoch: float) -> list[TradeProposal]:
        """Run the full pipeline over every index underlying and return this cycle's proposals.

        Two passes: (1) GATHER each name's regime + IV surface + directional verdict, so the vol-richness
        engine can rank the whole universe's Variance Risk Premium CROSS-SECTIONALLY this cycle; (2) BUILD a
        proposal per name using its richness (rich → sell premium, cheap → buy vol) — the path that wakes the
        Θ/premium-harvest engine in flat markets where the old None-IV-rank gate stood aside.

        Rule-Q cold-start: proposes from birth at a competency floor (never silenced); LIVE weight gates
        separately (supervisor warm-up + execution seam).
        """
        competency = self.competency()
        self._brain.begin_cycle()  # reset the per-cycle directional-training budget (cold-start throttle)
        gathered = [g for u in self._adapter.index_underlyings() if (g := self._gather(u)) is not None]
        richness = self._vrp_engine.assess_universe([
            VolRichnessInput(g.underlying, g.trade_date, g.regime.variance_risk_premium, g.regime.realized_vol)
            for g in gathered
        ])
        # slice-2: score every profit engine per name + rank the universe → the winning engine drives selection
        trade_date = gathered[0].trade_date if gathered else None
        opportunity = self._scorer.rank_universe(
            [_opportunity_features(g, richness.get(g.underlying)) for g in gathered], trade_date,
            engine_weights=self._learner.engine_weights())  # slice 5: tilt toward engines that have paid
        proposals: list[TradeProposal] = []
        for g in gathered:
            proposal = self._build_proposal(
                g, richness.get(g.underlying), opportunity.get(g.underlying), competency, now_epoch)
            if proposal is not None:
                proposals.append(proposal)
        return proposals

    def _gather(self, underlying: str) -> _GatheredIndexState | None:
        """Pass 1: fit the per-name engines needed for both the cross-sectional richness pass and selection."""
        prices = self._adapter.price_series(underlying)
        chain, trade_date = self._adapter.option_chain(underlying)
        if prices is None or len(prices) == 0 or chain is None or len(chain) == 0:
            return None
        regime = VolatilityRegimeEngine(underlying, self._regime_store).fit_and_state(
            prices, implied_vol=self._adapter.implied_atm_vol(underlying)
        )
        surface = ImpliedVolSurfaceEngine(underlying, self._iv_store, self._rate).fit_and_state(chain, trade_date)
        # the bot's OWN directional brain computes the side + conviction from its price history (wakes the
        # CE/PE branches); the passive adapter.trend_side survives only as an optional live-trend override.
        verdict = self._brain.verdict_for(underlying, prices)
        trend = verdict.side if verdict.side != TradeSide.NEUTRAL else self._adapter.trend_side(underlying)
        spot = float(chain["underlying_price"].iloc[0]) if len(chain) else 0.0
        return _GatheredIndexState(
            underlying=underlying, trade_date=trade_date, regime=regime, surface=surface,
            expiry=self._adapter.nearest_expiry(underlying), is_expiry=self._adapter.is_expiry_day(underlying),
            trend=trend, trend_conviction=verdict.conviction, chain=chain, spot=spot,
        )

    def _build_proposal(self, g: _GatheredIndexState, vol_richness: VolRichnessState | None,
                        opportunity: OpportunityScore | None, competency: BotCompetency,
                        now_epoch: float) -> TradeProposal | None:
        """Pass 2: turn one gathered name (+ richness + opportunity score) into a sized proposal."""
        proposal = self._policy.propose(
            g.underlying, g.expiry, g.regime, g.surface, competency, now_epoch, g.is_expiry,
            g.trend, g.trend_conviction, vol_richness, opportunity,
        )
        if proposal is None:
            return None

        # slice-3: SYNTHESIZE the structure — price real-strike candidates over the regime-conditioned terminal
        # distribution and swap in the max-EV defined-risk one (the bot inventing its own trade). Falls back to
        # the template structure when the optimizer can't (no live chain / too few strikes).
        proposal = self._synthesize_structure(g, opportunity, proposal)
        if proposal is None:
            return None  # a live chain was present but NO structure cleared the trade-quality floor → stand aside
                         # (never emit a proof-less template trade; the honest "no good trade" outcome)

        # slice-4 refinement: if the learned head is earned, replace the deterministic prob with the model's.
        # Selection is dispatched to the scored best engine (falls back to first-match if no score).
        decision = (self._selector.select_for_engine(opportunity.best_engine, g.underlying, g.expiry, g.regime,
                                                     g.surface, g.is_expiry, g.trend, g.trend_conviction, vol_richness)
                    if opportunity is not None and opportunity.best_engine is not None
                    else self._selector.select(g.underlying, g.expiry, g.regime, g.surface, g.is_expiry,
                                               g.trend, g.trend_conviction, vol_richness))
        features = engineer_features(g.regime, g.surface, decision)
        learned = self._head.calibrated_win_probability(features)
        if learned is not None:
            proposal = _with_calibrated_prob(proposal, learned, features)
        else:
            proposal = _with_features(proposal, features)
        return proposal

    def _synthesize_structure(self, g: _GatheredIndexState, opportunity: OpportunityScore | None,
                             proposal: TradeProposal) -> TradeProposal | None:
        """Replace the template structure with the max-EV real-strike structure the optimizer synthesizes.

        Returns the synthesized proposal on success; the untouched template proposal only when there is NO live
        chain to optimize over (stored-data fallback); and ``None`` (abstain) when a live chain WAS present but
        no candidate cleared the trade-quality floor — the honest "no good trade here" outcome, never a
        proof-less trade.
        """
        if opportunity is None or opportunity.best_engine is None or g.chain is None or len(g.chain) == 0:
            return proposal
        import dataclasses
        from datetime import date

        try:
            tenor = max((date.fromisoformat(g.expiry) - date.today()).days, 0) / 365.0
        except (ValueError, TypeError):
            tenor = 7.0 / 365.0
        sign = 1 if g.trend == TradeSide.LONG else (-1 if g.trend == TradeSide.SHORT else 0)
        distribution = self._distribution.simulate(
            g.spot, tenor, g.regime.blended_forecast_sigma,
            regime_probabilities=tuple(g.regime.regime_probabilities),
            directional_conviction=g.trend_conviction, directional_sign=sign,
        )
        lot = _live_lot_size(g.chain) or _INDEX_LOT_SIZES.get(g.underlying, 1)  # real lot from the live dump
        # try the best engine; if its optimizer can't synthesize a floor-passing structure, fall back to the
        # next-best engine that clears the edge floor — abstain only when NONE can (never a proof-less trade).
        optimized = None
        for engine in opportunity.tradeable_engines() or [opportunity.best_engine]:
            optimized = self._optimizer.optimize(g.chain, distribution, engine, lot, g.trend)
            if optimized is not None:
                break
        if optimized is None:
            return None  # live chain present but no floor-passing structure on any engine → abstain
        plan = build_plan_from_optimized_structure(optimized, g.underlying, g.expiry, g.spot)
        provenance = {**proposal.feature_provenance, "synthesized": True, "engine": optimized.engine.value,
                      "expected_pnl": optimized.expected_pnl, "cvar": optimized.cvar,
                      "p_profit": optimized.p_profit, "max_loss": optimized.max_loss,
                      "rationale": optimized.rationale}
        return dataclasses.replace(proposal, structure=plan, feature_provenance=provenance)

    def learn_from_closed_trades(self) -> None:
        """Advance self-learning: (re)train the head on accrued labelled trials + reset if drift is detected."""
        trials = self._track_store.labelled_trials()
        if len(trials) >= 1:
            self._head.train(trials)

    def record_closed_trade(self, trade: ClosedTrade) -> None:
        """Feed a realised outcome back in — accrues competency + the head's training set + drift signal."""
        self._track_store.record(trade)
        drifted = self._head.observe_outcome(trade.calibrated_prob_at_entry, trade.won)
        if drifted:
            self.learn_from_closed_trades()


def _with_calibrated_prob(proposal: TradeProposal, prob: float, features: dict) -> TradeProposal:
    provenance = {**proposal.feature_provenance, "learned_calibrated_prob": prob, "features": features}
    return _replace_proposal(proposal, calibrated_prob=prob, provenance=provenance)


def _with_features(proposal: TradeProposal, features: dict) -> TradeProposal:
    return _replace_proposal(proposal, provenance={**proposal.feature_provenance, "features": features})


def _replace_proposal(proposal: TradeProposal, calibrated_prob: float | None = None, provenance: dict | None = None) -> TradeProposal:
    import dataclasses

    return dataclasses.replace(
        proposal,
        calibrated_prob=calibrated_prob if calibrated_prob is not None else proposal.calibrated_prob,
        feature_provenance=provenance if provenance is not None else proposal.feature_provenance,
    )
