"""The assembled STOCK-OPTION bot — a ``SegmentBot`` over the full NSE single-stock option universe (slice).

Reuses the index bot's engines with its OWN instances + stores (choice-B independence at the model level):
volatility-regime + IV-surface + learned win-probability head. Adds the single-name brains: the option-flow
engine, the event-proximity gate, and the stock structure selector. Per underlying each cycle:

  prices → regime · chain → IV surface + option flow · calendar → event proximity
  → stock structure selector → sized TradeProposal (event-capped) → head refinement (if earned)

Proposes only (crypto §03b) into the portfolio supervisor. Owns its data via an injected
``StockOptionDataAdapter`` seam (Rule J), its competency/track-record store, and its self-learning loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import pandas as pd

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolRankStore,
    ImpliedVolSurfaceEngine,
    ImpliedVolSurfaceState,
)
from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import (
    BotTrackRecordStore,
    ClosedTrade,
)
from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeEngine,
    VolatilityRegimeState,
    VolatilityRegimeStore,
)
from nse_algo_trader.segment_bots.index_option_bot.win_probability_head import (
    IndexOptionWinProbabilityHead,
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
from nse_algo_trader.segment_bots.stock_option_bot.event_calendar_gate import (
    EventCalendarSource,
    EventProximity,
    EventProximityGate,
)
from nse_algo_trader.segment_bots.stock_option_bot.option_flow_signals import (
    OptionFlowEngine,
    OptionFlowState,
    PcrHistoryStore,
)
from nse_algo_trader.segment_bots.stock_option_bot.stock_option_structure_selector import (
    StockOptionStructureSelector,
)

_SIGNAL_TTL_SECONDS = 5 * 60
_MAX_LOTS_AT_FULL_CONVICTION = 10
_MIN_CONVICTION_TO_TRADE = 0.30
_STOCK_OPTION_LOT_DEFAULT = 1  # per-name F&O lot varies (TODO source from the live instrument dump); paper-safe


def _stock_opportunity_features(g: _GatheredStockState, richness: VolRichnessState | None) -> OpportunityFeatures:
    """Assemble the scorer's feature vector for a stock name (adds the event-gate pre_event signal)."""
    regime = g.regime
    stressed_prob = (float(regime.regime_probabilities[-1])
                     if getattr(regime, "maturity", "") == "earned" and len(regime.regime_probabilities) >= 2
                     else 0.0)
    return OpportunityFeatures(
        underlying=g.underlying,
        richness=richness.richness if richness is not None else None,
        vrp=regime.variance_risk_premium,
        stressed_prob=stressed_prob,
        is_range_bound=g.trend_conviction < 0.15,
        trend_conviction=g.trend_conviction,
        abs_skew=abs(g.surface.risk_reversal_25d),
        abs_term_slope=abs(getattr(g.surface, "term_structure_slope", 0.0) or 0.0),
        is_expiry_day=False,  # stock adapter has no is_expiry_day; event gate handles proximity
        pre_event=g.event.blocks_naked_premium,  # pre-event blocks naked premium → Θ engine damped
    )


@dataclass(frozen=True)
class _GatheredStockState:
    """Pass-1 per-name state carried into the cross-sectional richness pass + selection."""

    underlying: str
    trade_date: str
    regime: VolatilityRegimeState
    surface: ImpliedVolSurfaceState
    flow: OptionFlowState
    event: EventProximity
    expiry: str
    trend: TradeSide
    trend_conviction: float
    chain: pd.DataFrame
    spot: float


_EARNED_MIN_CLOSED_TRADES = 30
_TRADES_PER_LEVEL = 40


class StockOptionDataAdapter(Protocol):
    """The bot's own data seam. Production wires real per-name F&O feeds + the event calendar; tests fake it."""

    def stock_underlyings(self) -> list[str]: ...
    def price_series(self, underlying: str) -> pd.Series: ...
    def option_chain(self, underlying: str) -> tuple[pd.DataFrame, str]: ...  # (chain_df, trade_date ISO)
    def implied_atm_vol(self, underlying: str) -> float | None: ...
    def nearest_expiry(self, underlying: str) -> str: ...
    def trend_side(self, underlying: str) -> TradeSide: ...
    def event_calendar(self) -> EventCalendarSource | None: ...


class StockOptionBot:
    """The STOCK-OPTION SegmentBot: proposes single-name option structures over the full F&O universe."""

    name = "stock_option_bot"
    segment = MarketSegment.STOCK_OPTION

    def __init__(self, data_adapter: StockOptionDataAdapter, store_dir: Path, risk_free_rate: float = 0.065,
                 risk_account_notional: float = 1_000_000.0):
        # per-structure defined-risk cap scales with ACCOUNT capital (not a hardcoded ₹1M); the supervisor's
        # per-trade min/max-capital sizing is the true position limit downstream.
        self._adapter = data_adapter
        self._regime_store = VolatilityRegimeStore(store_dir / "regime")
        self._iv_store = ImpliedVolRankStore(store_dir / "iv_rank")
        self._pcr_store = PcrHistoryStore(store_dir / "pcr")
        self._head_store = WinProbabilityHeadStore(store_dir / "head")
        self._track_store = BotTrackRecordStore(store_dir / "track_record")
        self._selector = StockOptionStructureSelector()
        self._event_gate = EventProximityGate()
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
        closed = self._track_store.closed_count()
        return BotCompetency(
            level=min(5, closed // _TRADES_PER_LEVEL),
            closed_trades=closed,
            rolling_sharpe=None,
            calibration_error=None,
            is_earned=closed >= _EARNED_MIN_CLOSED_TRADES,
        )

    def propose(self, now_epoch: float) -> list[TradeProposal]:
        # Rule-Q cold-start: propose from birth (paper floor size); LIVE weight gated in the supervisor/seam.
        # Two passes: gather each name's engines → cross-sectional VRP richness → build (wakes premium selling
        # across the F&O universe ranked by VRP, the Θ engine of flat markets).
        competency = self.competency()
        source = self._adapter.event_calendar()
        self._brain.begin_cycle()  # reset the per-cycle directional-training budget (cold-start throttle)
        gathered = [g for u in self._adapter.stock_underlyings() if (g := self._gather(u, source)) is not None]
        richness = self._vrp_engine.assess_universe([
            VolRichnessInput(g.underlying, g.trade_date, g.regime.variance_risk_premium, g.regime.realized_vol)
            for g in gathered
        ])
        # slice-2: score every profit engine per name + rank the universe → the winning engine drives selection
        trade_date = gathered[0].trade_date if gathered else None
        opportunity = self._scorer.rank_universe(
            [_stock_opportunity_features(g, richness.get(g.underlying)) for g in gathered], trade_date,
            engine_weights=self._learner.engine_weights())  # slice 5: tilt toward engines that have paid
        proposals: list[TradeProposal] = []
        for g in gathered:
            p = self._build_proposal(g, richness.get(g.underlying), opportunity.get(g.underlying),
                                     competency, now_epoch)
            if p is not None:
                proposals.append(p)
        return proposals

    def _gather(self, underlying, source) -> _GatheredStockState | None:
        prices = self._adapter.price_series(underlying)
        chain, trade_date = self._adapter.option_chain(underlying)
        if prices is None or len(prices) == 0 or chain is None or len(chain) == 0:
            return None
        regime = VolatilityRegimeEngine(underlying, self._regime_store).fit_and_state(
            prices, implied_vol=self._adapter.implied_atm_vol(underlying))
        surface = ImpliedVolSurfaceEngine(underlying, self._iv_store, self._rate).fit_and_state(chain, trade_date)
        flow = OptionFlowEngine(underlying, self._pcr_store).compute(chain, trade_date)
        event = self._event_gate.assess(underlying, date.fromisoformat(trade_date), source)
        # the bot's OWN directional brain computes call-vs-put side from its price history (wakes the
        # directional selector branch); adapter.trend_side survives only as an optional live-feed override.
        verdict = self._brain.verdict_for(underlying, prices)
        trend = verdict.side if verdict.side != TradeSide.NEUTRAL else self._adapter.trend_side(underlying)
        spot = float(chain["underlying_price"].iloc[0]) if len(chain) else 0.0
        return _GatheredStockState(
            underlying=underlying, trade_date=trade_date, regime=regime, surface=surface, flow=flow,
            event=event, expiry=self._adapter.nearest_expiry(underlying),
            trend=trend, trend_conviction=verdict.conviction, chain=chain, spot=spot,
        )

    def _build_proposal(self, g: _GatheredStockState, vol_richness: VolRichnessState | None,
                        opportunity: OpportunityScore | None, competency, now_epoch) -> TradeProposal | None:
        underlying, regime, surface, flow, event = g.underlying, g.regime, g.surface, g.flow, g.event
        trend, trend_conviction, expiry = g.trend, g.trend_conviction, g.expiry
        # dispatch selection to the scored best engine; abstain if no engine cleared the floor; fall back to
        # first-match when no score is available (e.g. tiny universe).
        if opportunity is not None:
            if opportunity.best_engine is None:
                return None
            decision = self._selector.select_for_engine(
                opportunity.best_engine, underlying, expiry, surface, flow, event, trend, trend_conviction,
                vol_richness)
        else:
            decision = self._selector.select(underlying, expiry, surface, flow, event, trend, trend_conviction,
                                             vol_richness)
        if decision.stand_aside:
            return None
        # a directional debit spread is gated by the arbiter's directional edge (already earned); vol/flow
        # structures still require the conviction floor.
        if not decision.directionally_earned and decision.conviction < _MIN_CONVICTION_TO_TRADE:
            return None

        lots = self._size_lots(decision.conviction, competency)
        if lots <= 0:
            return None

        features = engineer_features(regime, surface, decision)
        learned = self._head.calibrated_win_probability(features)
        calibrated_prob = learned if learned is not None else self._deterministic_prob(decision, surface)
        proposal = TradeProposal(
            segment=MarketSegment.STOCK_OPTION,
            bot_name=f"stock_option_bot:{underlying}",
            underlying=underlying,
            side=decision.side,
            structure=decision.plan,
            size_hint_lots=lots,
            conviction=decision.conviction,
            calibrated_prob=calibrated_prob,
            expected_expectancy=self._expectancy(decision, regime),
            loss_tail_estimate=(0.05 if decision.plan.is_defined_risk else 0.25),
            signal_expiry_epoch=now_epoch + _SIGNAL_TTL_SECONDS,
            regime_label=regime.regime_label,
            feature_provenance={
                "rationale": decision.rationale, "iv_rank": surface.iv_rank,
                "pcr_oi": flow.pcr_open_interest, "pcr_shift_z": flow.pcr_shift_z,
                "net_flow_bias": flow.net_flow_bias, "event_phase": event.phase.value,
                "event_days": event.signed_days_to_event, "structure": decision.plan.kind.value,
                "features": features,
            },
        )
        # slice-3: swap the template for the max-EV real-strike structure synthesized on the live chain.
        # None = a live chain was present but no structure cleared the trade-quality floor → stand aside
        # (never emit a proof-less template trade).
        return self._synthesize_structure(g, opportunity, proposal)

    def _synthesize_structure(self, g: _GatheredStockState, opportunity: OpportunityScore | None,
                             proposal: TradeProposal) -> TradeProposal | None:
        """Replace the template with the optimizer's max-EV real-strike structure (live chain + forecast).

        Returns the synthesized proposal on success; the untouched template only when there is NO live chain
        to optimize over; ``None`` (abstain) when a live chain WAS present but no candidate cleared the
        trade-quality floor — the honest "no good trade" outcome, never a proof-less trade.
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
            directional_conviction=g.trend_conviction, directional_sign=sign)
        lot = _live_lot_size(g.chain) or _STOCK_OPTION_LOT_DEFAULT  # real per-name lot from the live dump
        # try the best engine; if it can't synthesize a floor-passing structure, fall back to the next-best
        # engine that clears the edge floor — abstain only when NONE can (never a proof-less trade).
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

    @staticmethod
    def _size_lots(conviction: float, competency: BotCompetency) -> int:
        # Rule-Q cold-start: unearned → a 1-lot PAPER floor so the outcome accrues (activation laddered by
        # SIZE, not silenced); LIVE capital gated separately at the execution seam.
        scale = (min(max(competency.level, 0), 5) + 1) / 6.0
        sized = int(max(0, round(conviction * _MAX_LOTS_AT_FULL_CONVICTION * scale)))
        if sized <= 0 and conviction > 0.0:
            return 1
        return sized

    @staticmethod
    def _deterministic_prob(decision, surface) -> float:
        base = 0.55 if decision.plan.net_theta > 0 else 0.45
        tilt = 0.10 * ((surface.iv_rank or 0.5) - 0.5) * (1 if decision.plan.net_theta > 0 else -1)
        return float(min(max(base + tilt, 0.05), 0.95))

    @staticmethod
    def _expectancy(decision, regime) -> float:
        vrp = regime.variance_risk_premium or 0.0
        if decision.plan.net_theta > 0:
            return float(max(vrp, 0.0) * 0.5 * decision.conviction)
        return float(0.01 * decision.conviction)

    def learn_from_closed_trades(self) -> None:
        trials = self._track_store.labelled_trials()
        if trials:
            self._head.train(trials)

    def record_closed_trade(self, trade: ClosedTrade) -> None:
        self._track_store.record(trade)
        if self._head.observe_outcome(trade.calibrated_prob_at_entry, trade.won):
            self.learn_from_closed_trades()
