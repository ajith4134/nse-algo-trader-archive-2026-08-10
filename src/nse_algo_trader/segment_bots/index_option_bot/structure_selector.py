"""Index-option structure selector — turns the vol/regime + IV-surface state into a concrete trade plan.

This is the decision core that fuses the two upstream engines (slice 1 volatility-regime, slice 2 IV
surface) into an ``OptionStructurePlan`` + side + conviction, using the institutional index-vol playbook:

* **Never sell vol into stress.** A high-variance Markov regime (stressed) → stand aside or, at most, a
  small DEFINED-RISK long-vol structure. Selling premium in the wrong regime is the classic account-ender.
* **Sell premium when it is rich.** Calm/elevated regime + high IV-rank + positive variance-risk-premium →
  short premium: an iron condor (defined risk) when IV-rank is very high, a short strangle when moderate.
* **Buy vol when it is cheap.** Calm regime + low IV-rank → long straddle/strangle (or a directional debit
  structure when a trend is present).
* **Trade the skew.** A rich 25Δ risk-reversal (expensive puts) → sell the expensive wing via a put credit
  spread rather than a symmetric structure.
* **Expiry day → 0DTE gamma/theta.** On the expiring contract, a short-premium iron-fly in calm conditions.

The output is decision-grade: strikes are expressed as moneyness offsets (portable across underlyings/spot),
with estimated net greeks and a conviction in [0,1] that blends how strongly the conditions align — the
downstream policy/head turn this into a sized ``TradeProposal``.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolSurfaceState,
)
from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeState,
)
from nse_algo_trader.option_alpha.option_opportunity_scorer import ProfitEngine
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    OptionStructureKind,
    OptionStructurePlan,
    TradeSide,
)

# thresholds are self-calibrating handles, not magic prices: IV-rank / skew are already normalised [0,1]/vol-pts
_HIGH_IV_RANK = 0.60
_VERY_HIGH_IV_RANK = 0.80
_LOW_IV_RANK = 0.30
_RICH_SKEW_VOL_PTS = 0.03  # 25Δ risk-reversal above this = pay-to-sell-the-put-wing rich
_STRESSED_REGIME_PROB = 0.55


@dataclass(frozen=True)
class StructureDecision:
    """A decision-grade structure choice with its rationale and conviction."""

    plan: OptionStructurePlan
    side: TradeSide
    conviction: float  # [0,1]
    rationale: str
    stand_aside: bool
    directionally_earned: bool = False  # True = gated by the arbiter's directional edge, not the vol-conviction floor


def _leg(right: str, moneyness_offset: float, side: str, lots: int = 1) -> dict:
    """A structure leg expressed as a moneyness offset (strike = round(spot*(1+offset)) downstream)."""
    return {"right": right, "moneyness_offset": moneyness_offset, "side": side, "lots": lots}


class IndexOptionStructureSelector:
    """Maps (volatility-regime state, IV-surface state, is-expiry) → an OptionStructurePlan + conviction."""

    def select(
        self,
        underlying: str,
        expiry: str,
        regime: VolatilityRegimeState,
        surface: ImpliedVolSurfaceState,
        is_expiry_day: bool = False,
        trend_side: TradeSide = TradeSide.NEUTRAL,
        trend_conviction: float = 0.0,
        vol_richness=None,
    ) -> StructureDecision:
        """Choose the structure. Abstains (stand_aside) when the regime forbids the only fitting trade.

        ``vol_richness`` (VolRichnessState) is the cross-sectional VRP richness that replaces the perpetually
        -None IV-rank: rich → sell premium, cheap → buy vol. IV-rank stays a legacy fallback once it earns.
        """

        stressed_prob = self._stressed_probability(regime)
        iv_rank = surface.iv_rank
        vrp = regime.variance_risk_premium or 0.0
        skew = surface.risk_reversal_25d
        rich_vol = (iv_rank is not None and iv_rank >= _HIGH_IV_RANK) or (
            vol_richness is not None and vol_richness.is_rich())
        very_rich_vol = (iv_rank is not None and iv_rank >= _VERY_HIGH_IV_RANK) or (
            vol_richness is not None and vol_richness.is_rich(high=0.85))
        cheap_vol = (iv_rank is not None and iv_rank <= _LOW_IV_RANK) or (
            vol_richness is not None and vol_richness.is_cheap())
        # effective richness rank ∈ [0,1] for conviction blending: prefer earned IV-rank, else VRP richness
        eff_rank = iv_rank if iv_rank is not None else (
            vol_richness.richness if (vol_richness is not None and vol_richness.richness is not None) else 0.5)

        # 1) STRESS GATE — never a naked vol sale in a stressed regime
        if stressed_prob >= _STRESSED_REGIME_PROB:
            if rich_vol:
                # vol rich AND stressed → small DEFINED-RISK long-vol (own the tail, capped cost)
                plan = self._iron_condor(underlying, expiry, wing=0.04, body=0.015, sell=False)
                return StructureDecision(plan, TradeSide.NEUTRAL, 0.35,
                                         "stressed regime + rich vol → defined-risk long vol", False)
            return StructureDecision(self._empty(underlying, expiry), TradeSide.NEUTRAL, 0.0,
                                     "stressed regime, no favourable structure → stand aside", True)

        # 2) EXPIRY DAY → 0DTE gamma/theta on the expiring contract
        if is_expiry_day:
            if trend_side in (TradeSide.LONG, TradeSide.SHORT):
                plan = self._directional(underlying, expiry, trend_side, kind=OptionStructureKind.ZERO_DTE_GAMMA)
                return StructureDecision(plan, trend_side, 0.5, "0DTE directional gamma with the trend", False)
            plan = self._iron_fly(underlying, expiry)
            return StructureDecision(plan, TradeSide.NEUTRAL, 0.45, "0DTE short-premium iron-fly (calm expiry)", False)

        # 3) SELL PREMIUM when rich (calm/elevated + rich vol + positive VRP). "Rich" is IV-rank when earned,
        #    else the cross-sectional VRP richness — this is the Θ/premium-harvest engine of FLAT markets.
        if rich_vol and vrp > 0.0:
            src = "IV-rank" if iv_rank is not None else "VRP-richness"
            if skew >= _RICH_SKEW_VOL_PTS:
                plan = self._put_credit_spread(underlying, expiry)
                conviction = self._blend(eff_rank, vrp, extra=min(skew / 0.06, 1.0))
                return StructureDecision(plan, TradeSide.NEUTRAL, conviction,
                                         f"rich {src} + positive VRP + rich put skew → put credit spread", False)
            plan = (self._iron_condor(underlying, expiry, wing=0.05, body=0.02, sell=True)
                    if very_rich_vol else self._short_strangle(underlying, expiry))
            conviction = self._blend(eff_rank, vrp)
            return StructureDecision(plan, TradeSide.NEUTRAL, conviction,
                                     f"rich {src} + positive VRP → {'iron condor' if very_rich_vol else 'short strangle'}",
                                     False)

        # 4) BUY VOL when cheap (low IV-rank or low cross-sectional VRP richness)
        if cheap_vol:
            if trend_side in (TradeSide.LONG, TradeSide.SHORT):
                plan = self._directional(underlying, expiry, trend_side, kind=OptionStructureKind.VERTICAL_DEBIT_SPREAD)
                return StructureDecision(plan, trend_side, 0.4, "cheap vol + trend → directional debit spread", False)
            plan = self._long_strangle(underlying, expiry)
            return StructureDecision(plan, TradeSide.NEUTRAL, 0.4, "cheap vol, no trend → long strangle", False)

        # 5) mid/gathering IV-rank but an EARNED directional trend → express it with a DEFINED-RISK directional
        #    debit spread. Directional BUYING (capped risk) does not need a vol edge the way premium SELLING
        #    does; the trend conviction (already the arbiter's calibrated, earned strength) both gates this via
        #    the policy's min-conviction and scales the size. This is how the bot trades on the one dimension
        #    it CAN earn on thin IV history — its directional read — instead of standing aside indefinitely.
        if trend_side in (TradeSide.LONG, TradeSide.SHORT) and trend_conviction > 0.0:
            plan = self._directional(underlying, expiry, trend_side, kind=OptionStructureKind.VERTICAL_DEBIT_SPREAD)
            return StructureDecision(plan, trend_side, trend_conviction,
                                     f"earned {trend_side.value} trend (gathering IV) → defined-risk debit spread",
                                     False, directionally_earned=True)

        # 6) no vol edge AND no earned directional trend → stand aside
        return StructureDecision(self._empty(underlying, expiry), TradeSide.NEUTRAL, 0.0,
                                 "no vol edge (mid IV-rank) and no earned trend → stand aside", True)

    def select_for_engine(
        self,
        engine: ProfitEngine,
        underlying: str,
        expiry: str,
        regime: VolatilityRegimeState,
        surface: ImpliedVolSurfaceState,
        is_expiry_day: bool = False,
        trend_side: TradeSide = TradeSide.NEUTRAL,
        trend_conviction: float = 0.0,
        vol_richness=None,
    ) -> StructureDecision:
        """Build the structure for a SCORED-chosen profit engine (slice-2 dispatch — replaces first-match).

        The opportunity scorer already decided WHICH engine has the edge for this name; this maps that engine
        to its structure, so selection is driven by the strongest score, not by branch order.
        """
        stressed = self._stressed_probability(regime) >= _STRESSED_REGIME_PROB
        vrp = regime.variance_risk_premium or 0.0
        skew = surface.risk_reversal_25d
        eff_rank = surface.iv_rank if surface.iv_rank is not None else (
            vol_richness.richness if (vol_richness is not None and vol_richness.richness is not None) else 0.5)
        very_rich = eff_rank >= _VERY_HIGH_IV_RANK or (vol_richness is not None and vol_richness.is_rich(high=0.85))

        if engine is ProfitEngine.THETA:
            # premium harvest — defined-risk in stress, else credit spread on rich skew / condor / strangle
            if stressed:
                plan = self._iron_condor(underlying, expiry, wing=0.04, body=0.015, sell=False)
                return StructureDecision(plan, TradeSide.NEUTRAL, 0.35, "Θ engine (stressed) → defined-risk long vol", False)
            if skew >= _RICH_SKEW_VOL_PTS:
                return StructureDecision(self._put_credit_spread(underlying, expiry), TradeSide.NEUTRAL,
                                         self._blend(eff_rank, vrp, extra=min(skew / 0.06, 1.0)),
                                         "Θ engine → put credit spread (rich put skew)", False)
            plan = (self._iron_condor(underlying, expiry, wing=0.05, body=0.02, sell=True)
                    if very_rich else self._short_strangle(underlying, expiry))
            return StructureDecision(plan, TradeSide.NEUTRAL, self._blend(eff_rank, vrp),
                                     f"Θ engine → {'iron condor' if very_rich else 'short strangle'}", False)

        if engine is ProfitEngine.DELTA:
            if trend_side in (TradeSide.LONG, TradeSide.SHORT) and trend_conviction > 0.0:
                plan = self._directional(underlying, expiry, trend_side, kind=OptionStructureKind.VERTICAL_DEBIT_SPREAD)
                return StructureDecision(plan, trend_side, trend_conviction,
                                         f"Δ engine → {trend_side.value} defined-risk debit spread", False,
                                         directionally_earned=True)
            return StructureDecision(self._empty(underlying, expiry), TradeSide.NEUTRAL, 0.0,
                                     "Δ engine but no earned side → stand aside", True)

        if engine is ProfitEngine.VEGA:
            return StructureDecision(self._long_strangle(underlying, expiry), TradeSide.NEUTRAL, 0.4,
                                     "ν engine → long strangle (cheap vol)", False)

        if engine is ProfitEngine.GAMMA:
            if is_expiry_day and trend_side in (TradeSide.LONG, TradeSide.SHORT):
                plan = self._directional(underlying, expiry, trend_side, kind=OptionStructureKind.ZERO_DTE_GAMMA)
                return StructureDecision(plan, trend_side, 0.5, "Γ engine → 0DTE directional gamma", False)
            if is_expiry_day:
                return StructureDecision(self._iron_fly(underlying, expiry), TradeSide.NEUTRAL, 0.45,
                                         "Γ engine → 0DTE iron fly", False)
            return StructureDecision(self._long_strangle(underlying, expiry), TradeSide.NEUTRAL, 0.4,
                                     "Γ engine → long strangle (own convexity)", False)

        # RELVALUE — express the surface-shape dislocation: rich put skew → put credit spread, else condor
        if skew >= _RICH_SKEW_VOL_PTS:
            return StructureDecision(self._put_credit_spread(underlying, expiry), TradeSide.NEUTRAL,
                                     min(1.0, skew / 0.06), "RV engine → put credit spread (skew RV)", False)
        return StructureDecision(self._iron_condor(underlying, expiry, wing=0.05, body=0.02, sell=True),
                                 TradeSide.NEUTRAL, 0.4, "RV engine → defined-risk condor (term/skew RV)", False)

    # -- conviction + regime helpers ------------------------------------------------------------------
    @staticmethod
    def _stressed_probability(regime: VolatilityRegimeState) -> float:
        if regime.maturity != "earned" or len(regime.regime_probabilities) < 2:
            return 0.0  # immature regime never triggers the stress gate on its own
        return float(regime.regime_probabilities[-1])  # highest-variance regime is last (calm=0)

    @staticmethod
    def _blend(iv_rank: float, vrp: float, extra: float = 0.0) -> float:
        base = 0.5 * iv_rank + 0.4 * min(max(vrp / 0.10, 0.0), 1.0) + 0.1 * extra
        return float(min(max(base, 0.0), 1.0))

    # -- structure builders (moneyness-offset legs; sign conventions per protocol) ---------------------
    def _empty(self, underlying: str, expiry: str) -> OptionStructurePlan:
        return OptionStructurePlan(OptionStructureKind.NONE, underlying, expiry)

    def _short_strangle(self, underlying: str, expiry: str) -> OptionStructurePlan:
        legs = (_leg("PE", -0.03, "sell"), _leg("CE", +0.03, "sell"))
        return OptionStructurePlan(OptionStructureKind.SHORT_STRANGLE, underlying, expiry, legs,
                                   is_defined_risk=False, net_delta=0.0, net_vega=-1.0, net_theta=1.0)

    def _long_strangle(self, underlying: str, expiry: str) -> OptionStructurePlan:
        legs = (_leg("PE", -0.03, "buy"), _leg("CE", +0.03, "buy"))
        return OptionStructurePlan(OptionStructureKind.SHORT_STRANGLE, underlying, expiry, legs,
                                   is_defined_risk=True, net_delta=0.0, net_vega=1.0, net_theta=-1.0)

    def _iron_condor(self, underlying: str, expiry: str, wing: float, body: float, sell: bool) -> OptionStructurePlan:
        s = "sell" if sell else "buy"
        b = "buy" if sell else "sell"
        legs = (_leg("PE", -(body + wing), b), _leg("PE", -body, s),
                _leg("CE", +body, s), _leg("CE", +(body + wing), b))
        return OptionStructurePlan(OptionStructureKind.IRON_CONDOR, underlying, expiry, legs,
                                   is_defined_risk=True, net_delta=0.0,
                                   net_vega=-1.0 if sell else 1.0, net_theta=1.0 if sell else -1.0)

    def _iron_fly(self, underlying: str, expiry: str) -> OptionStructurePlan:
        legs = (_leg("PE", -0.03, "buy"), _leg("PE", 0.0, "sell"),
                _leg("CE", 0.0, "sell"), _leg("CE", +0.03, "buy"))
        return OptionStructurePlan(OptionStructureKind.IRON_FLY, underlying, expiry, legs,
                                   is_defined_risk=True, net_delta=0.0, net_vega=-1.0, net_theta=1.0)

    def _put_credit_spread(self, underlying: str, expiry: str) -> OptionStructurePlan:
        legs = (_leg("PE", -0.02, "sell"), _leg("PE", -0.05, "buy"))
        return OptionStructurePlan(OptionStructureKind.VERTICAL_CREDIT_SPREAD, underlying, expiry, legs,
                                   is_defined_risk=True, net_delta=0.15, net_vega=-0.5, net_theta=0.5)

    def _directional(self, underlying: str, expiry: str, side: TradeSide, kind: OptionStructureKind) -> OptionStructurePlan:
        right = "CE" if side == TradeSide.LONG else "PE"
        legs: tuple[dict, ...]
        if kind == OptionStructureKind.VERTICAL_DEBIT_SPREAD:
            legs = (_leg(right, 0.0, "buy"), _leg(right, 0.03 if side == TradeSide.LONG else -0.03, "sell"))
        else:  # single directional / 0DTE gamma
            legs = (_leg(right, 0.0, "buy"),)
        return OptionStructurePlan(kind, underlying, expiry, legs, is_defined_risk=True,
                                   net_delta=0.5 if side == TradeSide.LONG else -0.5, net_vega=0.3, net_theta=-0.3)
