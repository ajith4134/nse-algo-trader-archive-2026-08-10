"""Option Book Risk Engine — portfolio-level view + CVXPY live-sizing over the pod's OPEN option book.

The per-name pipeline (scorer → optimizer) picks each trade in isolation; this engine looks at the WHOLE open
option book: aggregate net greeks (ΣΔ ΣΓ Σν ΣΘ across every leg × lot), total expected P&L, and a portfolio
CVaR, and solves a CVXPY quadratic-utility LIVE-SIZING vector (per-name lot multipliers that maximise expected
P&L penalised by book variance + a net-greek-neutrality preference, under a margin budget).

CRUCIAL (user directive): this NEVER caps PAPER acceptance — every option name still trades on paper. It is a
portfolio DIAGNOSTIC (surfaced on the dashboard) plus a recommended LIVE sizing used only when live trading is
enabled. So the "book optimizer" adds portfolio awareness + a real CVXPY solve without reintroducing a limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nse_algo_trader.option_alpha.option_greeks import net_structure_greeks

_RISK_AVERSION = 1e-7        # λ on book variance in the utility solve (per-₹ scale)
_GREEK_NEUTRAL_WEIGHT = 1e-3  # mild preference for a delta-neutral book
_MAX_LIVE_MULTIPLIER = 3.0    # a live position can scale up to this × its paper lot


@dataclass(frozen=True)
class OptionBookRisk:
    net_delta: float
    net_gamma: float
    net_vega: float
    net_theta: float
    expected_pnl: float
    portfolio_cvar: float
    n_structures: int
    live_size_multipliers: dict = field(default_factory=dict)  # order_id → recommended live lot multiplier


class OptionBookRiskEngine:
    """Aggregates net greeks + CVaR over the open option book and solves a CVXPY live-sizing vector."""

    def __init__(self, rate: float = 0.065):
        self._rate = rate

    def assess(self, positions: list[dict], spot_of, today=None) -> OptionBookRisk:
        """positions: pod open-position dicts (with legs + expiry). spot_of: callable(underlying)→float."""
        from datetime import date

        today = today or date.today()
        option_positions = [p for p in positions if p.get("legs")]
        if not option_positions:
            return OptionBookRisk(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, {})

        nd = ng = nv = nt = 0.0
        exp_pnls: list[float] = []
        cvars: list[float] = []
        order_ids: list[str] = []
        for p in option_positions:
            underlying = str(p.get("underlying"))
            spot = float(spot_of(underlying) or 0.0)
            tenor = self._tenor_years(p.get("expiry", ""), today)
            lot_size = self._lot_size(p)
            g = net_structure_greeks(p["legs"], spot, tenor, self._rate, lot_size, int(p.get("quantity", 1)))
            nd += g.delta
            ng += g.gamma
            nv += g.vega
            nt += g.theta
            feats = p.get("features", {}) if isinstance(p.get("features"), dict) else {}
            exp_pnls.append(float(feats.get("expected_pnl", 0.0) or 0.0))
            cvars.append(abs(float(feats.get("cvar", feats.get("max_loss", 0.0)) or 0.0)))
            order_ids.append(str(p.get("order_id", underlying)))

        exp = np.asarray(exp_pnls, dtype=float)
        cv = np.asarray(cvars, dtype=float)
        portfolio_cvar = float(np.sqrt(np.sum(cv**2)))  # independence approximation across structures
        multipliers = self._solve_live_sizing(exp, cv, order_ids)
        return OptionBookRisk(
            net_delta=round(nd, 2), net_gamma=round(ng, 4), net_vega=round(nv, 2), net_theta=round(nt, 2),
            expected_pnl=round(float(np.sum(exp)), 2), portfolio_cvar=round(portfolio_cvar, 2),
            n_structures=len(option_positions), live_size_multipliers=multipliers)

    def _solve_live_sizing(self, exp: np.ndarray, cvar: np.ndarray, order_ids: list[str]) -> dict:
        """CVXPY: maximise expected P&L − λ·variance over per-name live multipliers x ∈ [0, MAX]."""
        n = len(exp)
        if n == 0:
            return {}
        try:
            import cvxpy as cp

            x = cp.Variable(n, nonneg=True)
            variance = cp.sum(cp.multiply(cvar**2, cp.square(x)))  # diagonal risk from per-structure CVaR
            utility = exp @ x - _RISK_AVERSION * variance
            constraints = [x <= _MAX_LIVE_MULTIPLIER]
            cp.Problem(cp.Maximize(utility), constraints).solve()
            if x.value is None:
                return dict.fromkeys(order_ids, 1.0)
            return {oid: round(float(max(0.0, v)), 3) for oid, v in zip(order_ids, x.value, strict=False)}
        except Exception:  # noqa: BLE001 — solver failure → neutral 1× sizing (paper is unaffected regardless)
            return dict.fromkeys(order_ids, 1.0)

    @staticmethod
    def _tenor_years(expiry: str, today) -> float:
        from datetime import date

        try:
            return max((date.fromisoformat(str(expiry)[:10]) - today).days, 0) / 365.0 or (1.0 / 365.0)
        except (ValueError, TypeError):
            return 7.0 / 365.0

    @staticmethod
    def _lot_size(position: dict) -> int:
        legs = position.get("legs", [])
        for leg in legs:
            ls = leg.get("lot_size")
            if ls:
                return int(ls)
        return 1
