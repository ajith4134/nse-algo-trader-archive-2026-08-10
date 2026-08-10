"""Deterministic index-option policy — the transparent P1 baseline + training-data generator.

This is the forced-first path of the INDEX-OPTION bot (crypto Feature-Catalogue §03b: "the ordering is
forced"). It composes the vol-regime engine (slice 1) + IV-surface engine (slice 2) + structure selector
(slice 3) into a full, sized ``TradeProposal`` with NO learned model — a fully specified deterministic
policy that:

* is the **rollback target** and the **baseline the learned head (slice 4) must beat out-of-sample**, and
* **generates the labelled dataset** the learned head trains on (every proposal it emits is a logged trial
  with a later realised outcome).

Sizing, expectancy and tail estimates are all transparent functions of the surface/regime state, never a
black box; the maturity ladder (Rule Q) keeps size at zero until the bot's competency is earned.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolSurfaceState,
)
from nse_algo_trader.segment_bots.index_option_bot.structure_selector import (
    IndexOptionStructureSelector,
    StructureDecision,
)
from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeState,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    BotCompetency,
    MarketSegment,
    TradeProposal,
    TradeSide,
)

_SIGNAL_TTL_SECONDS = 5 * 60  # a proposal computed now must not fire 5 min later (crypto §03b signal-expiry)
_MAX_LOTS_AT_FULL_CONVICTION = 10


@dataclass(frozen=True)
class DeterministicPolicyConfig:
    max_lots: int = _MAX_LOTS_AT_FULL_CONVICTION
    signal_ttl_seconds: int = _SIGNAL_TTL_SECONDS
    min_conviction_to_trade: float = 0.30


class DeterministicIndexOptionPolicy:
    """Turns regime + surface into a sized, expiring ``TradeProposal`` with transparent economics."""

    def __init__(self, config: DeterministicPolicyConfig | None = None):
        self._config = config or DeterministicPolicyConfig()
        self._selector = IndexOptionStructureSelector()

    def propose(
        self,
        underlying: str,
        expiry: str,
        regime: VolatilityRegimeState,
        surface: ImpliedVolSurfaceState,
        competency: BotCompetency,
        now_epoch: float,
        is_expiry_day: bool = False,
        trend_side: TradeSide = TradeSide.NEUTRAL,
        trend_conviction: float = 0.0,
        vol_richness=None,
        opportunity_score=None,
    ) -> TradeProposal | None:
        """Emit a proposal, or None when the policy stands aside / conviction is too low / not yet earned.

        When ``opportunity_score`` is given (slice-2 scorer), selection is DISPATCHED to the highest-scoring
        profit engine (``select_for_engine``) rather than the first-match playbook; a None best-engine (no
        engine cleared the abstention floor) stands aside.
        """
        if opportunity_score is not None:
            if opportunity_score.best_engine is None:
                return None
            decision = self._selector.select_for_engine(
                opportunity_score.best_engine, underlying, expiry, regime, surface, is_expiry_day,
                trend_side, trend_conviction, vol_richness)
        else:
            decision = self._selector.select(underlying, expiry, regime, surface, is_expiry_day,
                                             trend_side, trend_conviction, vol_richness)
        # A directional debit spread is gated by the arbiter's directional edge (already earned + calibrated),
        # NOT the vol-structure conviction floor (which is calibrated for premium selling). Vol structures
        # still require the floor. Either way size scales with conviction, so a weak edge trades tiny.
        if decision.stand_aside:
            return None
        if not decision.directionally_earned and decision.conviction < self._config.min_conviction_to_trade:
            return None

        lots = self._size_lots(decision, competency)
        if lots <= 0:
            return None

        calibrated_prob = self._deterministic_win_probability(decision, surface)
        expectancy = self._expected_expectancy(decision, regime, surface)
        loss_tail = self._loss_tail(decision, surface)

        return TradeProposal(
            segment=MarketSegment.INDEX_OPTION,
            bot_name=f"index_option_deterministic:{underlying}",
            underlying=underlying,
            side=decision.side,
            structure=decision.plan,
            size_hint_lots=lots,
            conviction=decision.conviction,
            calibrated_prob=calibrated_prob,
            expected_expectancy=expectancy,
            loss_tail_estimate=loss_tail,
            signal_expiry_epoch=now_epoch + self._config.signal_ttl_seconds,
            regime_label=regime.regime_label,
            feature_provenance={
                "rationale": decision.rationale,
                "iv_rank": surface.iv_rank,
                "variance_risk_premium": regime.variance_risk_premium,
                "risk_reversal_25d": surface.risk_reversal_25d,
                "regime_probabilities": list(regime.regime_probabilities),
                "structure": decision.plan.kind.value,
            },
        )

    # -- transparent economics ------------------------------------------------------------------------
    def _size_lots(self, decision: StructureDecision, competency: BotCompetency) -> int:
        """Base size scaled by conviction, laddered by competency. Rule-Q cold-start: an unearned bot still
        takes a 1-lot PAPER floor so a track record can accrue (activation is laddered by SIZE, not silenced);
        LIVE capital is gated separately at the execution seam."""
        conviction_lots = decision.conviction * self._config.max_lots
        # earned bots ramp from a 1/6 floor up to full size as competency level climbs 0→5 (maturity ramp)
        competency_scale = (min(max(competency.level, 0), 5) + 1) / 6.0
        sized = int(max(0, round(conviction_lots * competency_scale)))
        if sized <= 0 and decision.conviction > 0.0:
            return 1  # cold-start / thin-conviction paper floor — one lot so the outcome accrues
        return sized

    @staticmethod
    def _deterministic_win_probability(decision: StructureDecision, surface: ImpliedVolSurfaceState) -> float:
        """A transparent P(win) proxy: premium-selling structures win more often (defined by their payoff)."""
        base = 0.55 if decision.plan.net_theta > 0 else 0.45  # theta-positive (short vol) wins more often, smaller
        rank_tilt = 0.10 * ((surface.iv_rank or 0.5) - 0.5) * (1 if decision.plan.net_theta > 0 else -1)
        return float(min(max(base + rank_tilt, 0.05), 0.95))

    @staticmethod
    def _expected_expectancy(
        decision: StructureDecision, regime: VolatilityRegimeState, surface: ImpliedVolSurfaceState
    ) -> float:
        """Expected net edge: for short-vol, proportional to the harvestable VRP; small for long-vol."""
        vrp = regime.variance_risk_premium or 0.0
        if decision.plan.net_theta > 0:  # premium seller monetises positive VRP
            return float(max(vrp, 0.0) * 0.5 * decision.conviction)
        return float(0.01 * decision.conviction)  # long-vol / directional: small modelled edge

    @staticmethod
    def _loss_tail(decision: StructureDecision, surface: ImpliedVolSurfaceState) -> float:
        """CVaR-style loss proxy: defined-risk structures cap the tail; undefined ones carry a fat tail."""
        if decision.plan.is_defined_risk:
            return 0.05  # capped by the wings
        return 0.25 * (1.0 + (surface.iv_rank or 0.5))  # naked short vol → larger, IV-scaled tail
