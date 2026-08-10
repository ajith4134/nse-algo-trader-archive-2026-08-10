"""Single-stock option structure selector — fuses IV-rank + option-flow + event proximity into a trade.

Distinct from the index selector: it is EVENT- and FLOW-aware. The order of gates:

1. **Post-event** (vol crushed) → buy cheap vol if IV-rank is low, else stand aside.
2. **Pre-event** (rich IV, binary move ahead) → sell the rich premium but DEFINED-RISK ONLY (iron condor,
   never a naked strangle) and size-capped by the event gate.
3. **Bearish flow** (a PCR-shift up + net put buildup) → do NOT sell puts; sell call premium or stand aside.
4. **Rich IV-rank, clear calendar** → sell premium (iron condor / short strangle).
5. **Unusual call activity + bullish flow** → a directional call debit tilt.

Conviction folds the event size-cap in, so positions naturally shrink into a binary event (Rule Q-style
risk scaling) without a separate size path.
"""

from __future__ import annotations

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolSurfaceState,
)
from nse_algo_trader.option_alpha.option_opportunity_scorer import ProfitEngine
from nse_algo_trader.segment_bots.index_option_bot.structure_selector import StructureDecision
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    OptionStructureKind,
    OptionStructurePlan,
    TradeSide,
)
from nse_algo_trader.segment_bots.stock_option_bot.event_calendar_gate import (
    EventPhase,
    EventProximity,
)
from nse_algo_trader.segment_bots.stock_option_bot.option_flow_signals import OptionFlowState

_HIGH_IV_RANK = 0.60
_VERY_HIGH_IV_RANK = 0.80
_LOW_IV_RANK = 0.30


def _leg(right: str, offset: float, side: str, lots: int = 1) -> dict:
    return {"right": right, "moneyness_offset": offset, "side": side, "lots": lots}


class StockOptionStructureSelector:
    """Maps (IV surface, option flow, event proximity) → an OptionStructurePlan + conviction for one name."""

    def select(
        self,
        underlying: str,
        expiry: str,
        surface: ImpliedVolSurfaceState,
        flow: OptionFlowState,
        event: EventProximity,
        trend: TradeSide = TradeSide.NEUTRAL,
        trend_conviction: float = 0.0,
        vol_richness=None,
    ) -> StructureDecision:
        iv_rank = surface.iv_rank
        cap = event.size_cap_fraction
        # cross-sectional VRP richness replaces the perpetually-None IV-rank (rich → sell, cheap → buy vol);
        # IV-rank stays a legacy fallback once it earns its ~60-session history.
        rich_vol = (iv_rank is not None and iv_rank >= _HIGH_IV_RANK) or (
            vol_richness is not None and vol_richness.is_rich())
        very_rich_vol = (iv_rank is not None and iv_rank >= _VERY_HIGH_IV_RANK) or (
            vol_richness is not None and vol_richness.is_rich(high=0.85))
        cheap_vol = (iv_rank is not None and iv_rank <= _LOW_IV_RANK) or (
            vol_richness is not None and vol_richness.is_cheap())
        eff_rank = iv_rank if iv_rank is not None else (
            vol_richness.richness if (vol_richness is not None and vol_richness.richness is not None) else 0.5)

        # 1) post-event: vol crushed → buy cheap vol or stand aside
        if event.phase == EventPhase.POST_EVENT:
            if cheap_vol:
                return self._decision(self._long_strangle(underlying, expiry), TradeSide.NEUTRAL,
                                      0.4 * cap, "post-event crushed vol → buy cheap vol")
            return self._aside(underlying, expiry, "post-event, vol not cheap → stand aside")

        # 2) pre-event: rich premium but DEFINED-RISK only, size-capped
        if event.blocks_naked_premium:
            if rich_vol:
                return self._decision(self._iron_condor(underlying, expiry, sell=True), TradeSide.NEUTRAL,
                                      self._blend(eff_rank) * cap,
                                      "pre-event rich vol → DEFINED-RISK iron condor (vol-crush), size-capped")
            return self._aside(underlying, expiry, "pre-event but vol not rich enough for a defined-risk sale")

        # 3) bearish flow guard: PCR shifting up + put buildup → don't sell puts
        if flow.is_bearish_flow():
            if rich_vol:
                return self._decision(self._call_credit_spread(underlying, expiry), TradeSide.SHORT,
                                      self._blend(eff_rank) * 0.9 * cap,
                                      "bearish flow + rich vol → sell CALL premium (avoid put side)")
            return self._aside(underlying, expiry, "bearish flow, vol not rich → stand aside")

        # 4) rich vol (VRP or IV-rank), clear calendar → sell premium
        if rich_vol:
            plan = (self._iron_condor(underlying, expiry, sell=True) if very_rich_vol
                    else self._short_strangle(underlying, expiry))
            return self._decision(plan, TradeSide.NEUTRAL, self._blend(eff_rank) * cap,
                                  f"clear calendar + rich vol → {'iron condor' if very_rich_vol else 'short strangle'}")

        # 5) unusual call activity + bullish flow → directional call debit
        if flow.net_flow_bias > 0.3 and flow.unusual_call_strikes and trend != TradeSide.SHORT:
            return self._decision(self._call_debit_spread(underlying, expiry), TradeSide.LONG,
                                  0.4 * cap, "bullish unusual call flow → directional call debit")

        # 6) cheap vol (VRP or IV-rank), no flow edge → buy vol
        if cheap_vol:
            return self._decision(self._long_strangle(underlying, expiry), TradeSide.NEUTRAL,
                                  0.35 * cap, "cheap vol, no flow edge → long strangle")

        # 7) an EARNED directional trend (arbiter-calibrated) → express it with a DEFINED-RISK directional
        #    debit spread (call for a LONG read, put for SHORT). Directional BUYING needs no vol edge, so this
        #    lets the name trade on the one dimension earnable from thin per-name IV history — its trend.
        if trend in (TradeSide.LONG, TradeSide.SHORT) and trend_conviction > 0.0:
            plan = (self._call_debit_spread(underlying, expiry) if trend == TradeSide.LONG
                    else self._put_debit_spread(underlying, expiry))
            return StructureDecision(plan, trend, float(min(max(trend_conviction, 0.0), 1.0)),
                                     f"earned {trend.value} trend (gathering IV) → defined-risk debit spread",
                                     False, directionally_earned=True)

        return self._aside(underlying, expiry, "no IV/flow/event edge and no earned trend → stand aside")

    def select_for_engine(
        self,
        engine: ProfitEngine,
        underlying: str,
        expiry: str,
        surface: ImpliedVolSurfaceState,
        flow: OptionFlowState,
        event: EventProximity,
        trend: TradeSide = TradeSide.NEUTRAL,
        trend_conviction: float = 0.0,
        vol_richness=None,
    ) -> StructureDecision:
        """Build the structure for a SCORED-chosen profit engine (slice-2 dispatch — replaces first-match)."""
        cap = event.size_cap_fraction
        eff_rank = surface.iv_rank if surface.iv_rank is not None else (
            vol_richness.richness if (vol_richness is not None and vol_richness.richness is not None) else 0.5)
        very_rich = eff_rank >= _VERY_HIGH_IV_RANK or (vol_richness is not None and vol_richness.is_rich(high=0.85))

        if engine is ProfitEngine.THETA:
            if event.phase == EventPhase.POST_EVENT:  # premium already crushed post-event → don't sell into it
                return self._aside(underlying, expiry, "Θ engine but post-event crush → stand aside")
            if event.blocks_naked_premium:  # pre-event → defined-risk only, size-capped
                return self._decision(self._iron_condor(underlying, expiry, sell=True), TradeSide.NEUTRAL,
                                      self._blend(eff_rank) * cap, "Θ engine (pre-event) → defined-risk condor")
            if flow.is_bearish_flow():  # bearish flow → sell CALL side, avoid puts
                return self._decision(self._call_credit_spread(underlying, expiry), TradeSide.SHORT,
                                      self._blend(eff_rank) * 0.9 * cap, "Θ engine + bearish flow → call credit spread")
            plan = (self._iron_condor(underlying, expiry, sell=True) if very_rich
                    else self._short_strangle(underlying, expiry))
            return self._decision(plan, TradeSide.NEUTRAL, self._blend(eff_rank) * cap,
                                  f"Θ engine → {'iron condor' if very_rich else 'short strangle'}")

        if engine is ProfitEngine.DELTA:
            if trend in (TradeSide.LONG, TradeSide.SHORT) and trend_conviction > 0.0:
                plan = (self._call_debit_spread(underlying, expiry) if trend == TradeSide.LONG
                        else self._put_debit_spread(underlying, expiry))
                return StructureDecision(plan, trend, float(min(max(trend_conviction, 0.0), 1.0)),
                                         f"Δ engine → {trend.value} defined-risk debit spread", False,
                                         directionally_earned=True)
            return self._aside(underlying, expiry, "Δ engine but no earned side → stand aside")

        if engine in (ProfitEngine.VEGA, ProfitEngine.GAMMA):  # long vol / convexity → long strangle
            return self._decision(self._long_strangle(underlying, expiry), TradeSide.NEUTRAL, 0.4 * cap,
                                  f"{'ν' if engine is ProfitEngine.VEGA else 'Γ'} engine → long strangle")

        # RELVALUE — skew RV: sell the rich call side (defined-risk) as the surface-shape expression
        return self._decision(self._iron_condor(underlying, expiry, sell=True), TradeSide.NEUTRAL,
                              self._blend(eff_rank) * cap, "RV engine → defined-risk condor (skew RV)")

    # -- helpers --------------------------------------------------------------------------------------
    @staticmethod
    def _blend(iv_rank: float) -> float:
        return float(min(max(0.4 + 0.6 * iv_rank, 0.0), 1.0))

    @staticmethod
    def _decision(plan, side, conviction, rationale) -> StructureDecision:
        return StructureDecision(plan, side, float(min(max(conviction, 0.0), 1.0)), rationale, False)

    def _aside(self, underlying, expiry, why) -> StructureDecision:
        return StructureDecision(OptionStructurePlan(OptionStructureKind.NONE, underlying, expiry),
                                 TradeSide.NEUTRAL, 0.0, why, True)

    def _short_strangle(self, u, e) -> OptionStructurePlan:
        return OptionStructurePlan(OptionStructureKind.SHORT_STRANGLE, u, e,
                                   (_leg("PE", -0.05, "sell"), _leg("CE", +0.05, "sell")),
                                   is_defined_risk=False, net_delta=0.0, net_vega=-1.0, net_theta=1.0)

    def _long_strangle(self, u, e) -> OptionStructurePlan:
        return OptionStructurePlan(OptionStructureKind.SHORT_STRANGLE, u, e,
                                   (_leg("PE", -0.05, "buy"), _leg("CE", +0.05, "buy")),
                                   is_defined_risk=True, net_delta=0.0, net_vega=1.0, net_theta=-1.0)

    def _iron_condor(self, u, e, sell: bool) -> OptionStructurePlan:
        s, b = ("sell", "buy") if sell else ("buy", "sell")
        legs = (_leg("PE", -0.07, b), _leg("PE", -0.03, s), _leg("CE", +0.03, s), _leg("CE", +0.07, b))
        return OptionStructurePlan(OptionStructureKind.IRON_CONDOR, u, e, legs, is_defined_risk=True,
                                   net_delta=0.0, net_vega=-1.0 if sell else 1.0, net_theta=1.0 if sell else -1.0)

    def _call_credit_spread(self, u, e) -> OptionStructurePlan:
        return OptionStructurePlan(OptionStructureKind.VERTICAL_CREDIT_SPREAD, u, e,
                                   (_leg("CE", +0.02, "sell"), _leg("CE", +0.05, "buy")),
                                   is_defined_risk=True, net_delta=-0.15, net_vega=-0.5, net_theta=0.5)

    def _call_debit_spread(self, u, e) -> OptionStructurePlan:
        return OptionStructurePlan(OptionStructureKind.VERTICAL_DEBIT_SPREAD, u, e,
                                   (_leg("CE", 0.0, "buy"), _leg("CE", +0.05, "sell")),
                                   is_defined_risk=True, net_delta=0.4, net_vega=0.3, net_theta=-0.3)

    def _put_debit_spread(self, u, e) -> OptionStructurePlan:
        """Bearish defined-risk directional: buy the ATM put, sell a further-OTM put (capped-cost SHORT bet)."""
        return OptionStructurePlan(OptionStructureKind.VERTICAL_DEBIT_SPREAD, u, e,
                                   (_leg("PE", 0.0, "buy"), _leg("PE", -0.05, "sell")),
                                   is_defined_risk=True, net_delta=-0.4, net_vega=0.3, net_theta=-0.3)
