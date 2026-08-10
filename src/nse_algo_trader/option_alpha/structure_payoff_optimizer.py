"""Structure Payoff Optimizer — the bot SYNTHESIZES its own trade from the live chain + the forecast.

Instead of picking a fixed template, this enumerates candidate structures built from REAL strikes on the live
chain, prices each one's P&L across the regime-conditioned terminal distribution (entry cashflow from live
premiums + terminal intrinsic value per Monte-Carlo sample), and returns the structure that MAXIMISES expected
value subject to a defined-risk cap, a per-leg liquidity floor, and the target profit-engine's greek sign.
This is the "come up with its own ideas" capability: the engine searches the real strike grid and composes the
trade — including non-template shapes (broken-wing condors) — that the distribution says pays best.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nse_algo_trader.option_alpha.option_opportunity_scorer import ProfitEngine
from nse_algo_trader.option_alpha.terminal_distribution_model import TerminalDistribution
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    OptionStructureKind,
    OptionStructurePlan,
    TradeSide,
)

_ENGINE_TO_KIND = {
    ProfitEngine.THETA: OptionStructureKind.IRON_CONDOR,
    ProfitEngine.RELVALUE: OptionStructureKind.IRON_CONDOR,
    ProfitEngine.DELTA: OptionStructureKind.VERTICAL_DEBIT_SPREAD,
    ProfitEngine.VEGA: OptionStructureKind.SHORT_STRANGLE,  # kind label; long-vol legs (buys) → long strangle
    ProfitEngine.GAMMA: OptionStructureKind.SHORT_STRANGLE,
}

_MIN_LIQUIDITY_OI = 0.0  # per-leg open-interest floor (0 until real OI is trusted; raised via calibration)
_CVAR_PCT = 5.0


@dataclass(frozen=True)
class OptimizedLeg:
    right: str          # CE | PE
    strike: float
    side: str           # buy | sell
    price: float        # live premium


@dataclass(frozen=True)
class OptimizedStructure:
    """A synthesized structure: concrete real-strike legs + its distribution-priced economics."""

    engine: ProfitEngine
    legs: tuple[OptimizedLeg, ...]
    expected_pnl: float
    max_loss: float
    cvar: float
    p_profit: float
    entry_cashflow: float  # net credit(+)/debit(−) per lot at entry
    rationale: str


def _intrinsic(right: str, strike: float, s_t: np.ndarray) -> np.ndarray:
    return np.maximum(s_t - strike, 0.0) if right == "CE" else np.maximum(strike - s_t, 0.0)


class StructurePayoffOptimizer:
    """Prices candidate real-strike structures over the terminal distribution and returns the max-EV one."""

    def __init__(self, max_loss_fraction: float = 0.02, account_notional: float = 1_000_000.0,
                 min_premium_fraction: float = 0.0005, min_return_on_risk: float = 0.03):
        self._max_loss_cap = max_loss_fraction * account_notional
        self._liq_floor = _MIN_LIQUIDITY_OI
        # trade-quality floors (relative, no magic ₹): a structure must collect/pay a MEANINGFUL premium
        # (≥ min_premium_fraction of the per-lot notional) AND clear a NON-TRIVIAL edge (E[P&L] > 0 and
        # ≥ min_return_on_risk of the capital at risk) — kills near-worthless-premium / tiny-edge trades on
        # near-expiry chains (e.g. the ₹0.05-leg condor with E[P&L] ₹3). Calibrated from the realised track
        # record once trades accrue (slice-5 learning; docs/BACKLOG.md).
        self._min_premium_fraction = min_premium_fraction
        self._min_return_on_risk = min_return_on_risk

    def optimize(
        self,
        chain: pd.DataFrame,
        distribution: TerminalDistribution,
        engine: ProfitEngine,
        lot_size: int,
        trend_side: TradeSide = TradeSide.NEUTRAL,
    ) -> OptimizedStructure | None:
        """Search the live chain's real strikes for the max-EV defined-risk structure for this engine."""
        grid = self._strike_grid(chain)
        if len(grid) < 3:
            return None
        spot = distribution.spot
        candidates = self._candidates(engine, grid, spot, trend_side)
        best: OptimizedStructure | None = None
        for legs in candidates:
            evaluated = self._evaluate(legs, distribution, engine, lot_size)
            if evaluated is None:
                continue
            if best is None or evaluated.expected_pnl > best.expected_pnl:
                best = evaluated
        return best

    def _strike_grid(self, chain: pd.DataFrame) -> dict[float, dict[str, tuple[float, float]]]:
        """{strike: {"CE": (price, oi), "PE": (price, oi)}} from the live chain's priced legs."""
        grid: dict[float, dict[str, tuple[float, float]]] = {}
        for _, row in chain.iterrows():
            right = str(row["option_right_code"]).upper()
            right = "CE" if right.startswith("C") else "PE"
            price = float(row["close_price"])
            if price <= 0:
                continue
            oi = float(row.get("open_interest", 0.0) or 0.0)
            grid.setdefault(float(row["strike_price"]), {})[right] = (price, oi)
        return {k: v for k, v in grid.items() if "CE" in v and "PE" in v}

    def _candidates(self, engine, grid, spot, trend_side) -> list[list[OptimizedLeg]]:
        strikes = sorted(grid)
        atm = min(strikes, key=lambda k: abs(k - spot))
        ai = strikes.index(atm)

        def leg(strike, right, side):
            price = grid[strike][right][0]
            return OptimizedLeg(right, strike, side, price)

        out: list[list[OptimizedLeg]] = []
        if engine is ProfitEngine.THETA or engine is ProfitEngine.RELVALUE:
            # iron condors at several widths: sell inner CE+PE, buy outer wings (defined risk)
            for inner in (1, 2, 3):
                for wing in (2, 3, 4):
                    ci, pi = ai + inner, ai - inner
                    co, po = ai + inner + wing, ai - inner - wing
                    if po < 0 or co >= len(strikes):
                        continue
                    out.append([
                        leg(strikes[ci], "CE", "sell"), leg(strikes[co], "CE", "buy"),
                        leg(strikes[pi], "PE", "sell"), leg(strikes[po], "PE", "buy"),
                    ])
        elif engine is ProfitEngine.DELTA and trend_side in (TradeSide.LONG, TradeSide.SHORT):
            for width in (1, 2, 3):
                if trend_side == TradeSide.LONG and ai + width < len(strikes):
                    out.append([leg(atm, "CE", "buy"), leg(strikes[ai + width], "CE", "sell")])
                if trend_side == TradeSide.SHORT and ai - width >= 0:
                    out.append([leg(atm, "PE", "buy"), leg(strikes[ai - width], "PE", "sell")])
        else:  # VEGA / GAMMA — long convexity: long straddle + long strangles
            out.append([leg(atm, "CE", "buy"), leg(atm, "PE", "buy")])
            for width in (2, 3):
                if ai + width < len(strikes) and ai - width >= 0:
                    out.append([leg(strikes[ai + width], "CE", "buy"), leg(strikes[ai - width], "PE", "buy")])
        return out

    def _evaluate(self, legs, distribution, engine, lot_size) -> OptimizedStructure | None:
        if any(leg.price <= 0 for leg in legs):
            return None
        s_t = distribution.samples
        lot = max(int(lot_size), 1)
        # entry cashflow per lot: sells receive premium (+), buys pay (−)
        entry = sum((leg.price if leg.side == "sell" else -leg.price) for leg in legs) * lot
        # terminal value per sample: hold buys (+intrinsic), owe sells (−intrinsic)
        terminal = np.zeros_like(s_t)
        for leg in legs:
            sign = 1.0 if leg.side == "buy" else -1.0
            terminal = terminal + sign * _intrinsic(leg.right, leg.strike, s_t) * lot
        pnl = entry + terminal
        expected = float(np.mean(pnl))
        max_loss = float(-np.min(pnl))
        cvar = float(-np.mean(np.sort(pnl)[: max(1, int(len(pnl) * _CVAR_PCT / 100.0))]))
        p_profit = float(np.mean(pnl > 0))

        if not np.isfinite(max_loss) or max_loss > self._max_loss_cap:
            return None  # not defined-risk within the cap
        # trade-quality floor 1 — meaningful premium: the net entry cashflow must be ≥ a fraction of the
        # per-lot notional; near-worthless-premium structures (₹0.05 legs on a near-expiry chain) are rejected.
        spot = float(distribution.spot)
        if spot > 0 and abs(entry) < self._min_premium_fraction * spot * lot:
            return None
        # trade-quality floor 2 — non-trivial positive edge: E[P&L] > 0 AND ≥ a fraction of the capital at
        # risk (return-on-risk floor); kills negative-EV and tiny-edge picks even if best of a weak field.
        if expected <= 0.0 or (max_loss > 0 and expected < self._min_return_on_risk * max_loss):
            return None
        return OptimizedStructure(
            engine=engine, legs=tuple(legs), expected_pnl=round(expected, 2), max_loss=round(max_loss, 2),
            cvar=round(cvar, 2), p_profit=round(p_profit, 4), entry_cashflow=round(entry, 2),
            rationale=(f"{engine.value}: E[P&L] {expected:.0f}, maxloss {max_loss:.0f}, "
                       f"P(profit) {p_profit:.0%}, {len(legs)} real-strike legs"))


def build_plan_from_optimized_structure(
    structure: OptimizedStructure, underlying: str, expiry: str, spot: float,
) -> OptionStructurePlan:
    """Convert a synthesized real-strike structure into the pipeline's ``OptionStructurePlan``.

    Legs carry both the exact ``strike`` and a ``moneyness_offset`` (strike/spot − 1) so the paper router can
    resolve them today and a future live router can use the exact strike. Net greeks are signed from the leg
    mix (buys long, sells short). Defined risk = the optimizer already capped max loss.
    """
    legs = []
    net_vega = 0.0
    net_theta = 0.0
    for leg in structure.legs:
        long = leg.side == "buy"
        legs.append({
            "right": leg.right,
            "strike": leg.strike,
            "moneyness_offset": (leg.strike / spot - 1.0) if spot > 0 else 0.0,
            "side": leg.side,
            "lots": 1,
            "price": leg.price,
        })
        net_vega += (1.0 if long else -1.0)
        net_theta += (-1.0 if long else 1.0)  # long options bleed theta, short options earn it
    return OptionStructurePlan(
        kind=_ENGINE_TO_KIND.get(structure.engine, OptionStructureKind.IRON_CONDOR),
        underlying=underlying,
        expiry=expiry,
        legs=tuple(legs),
        is_defined_risk=True,
        net_delta=0.0,
        net_vega=net_vega,
        net_theta=net_theta,
    )


def live_lot_size(chain: pd.DataFrame) -> int:
    """The exchange contract lot from a LIVE chain (0 if absent, e.g. a stored bhavcopy chain → caller floors)."""
    if chain is None or "lot_size" not in chain.columns or len(chain) == 0:
        return 0
    try:
        return int(chain["lot_size"].iloc[0])
    except (ValueError, TypeError):
        return 0
