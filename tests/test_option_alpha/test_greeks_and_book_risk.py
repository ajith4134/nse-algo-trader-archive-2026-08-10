"""Tests for per-leg greeks + the option book risk engine."""

from __future__ import annotations

import pytest

from nse_algo_trader.option_alpha.option_greeks import leg_greeks
from nse_algo_trader.option_alpha.option_book_risk_engine import OptionBookRiskEngine


def test_atm_call_delta_near_half():
    g = leg_greeks("CE", 100.0, 100.0, 30 / 365, 0.065, 3.0)
    assert 0.4 <= g.delta <= 0.65 and g.gamma > 0 and g.vega > 0  # ATM call ~0.5 delta, long gamma/vega


def test_atm_put_delta_negative():
    g = leg_greeks("PE", 100.0, 100.0, 30 / 365, 0.065, 3.0)
    assert -0.65 <= g.delta <= -0.35


def test_uninvertible_premium_is_zeroed():
    assert leg_greeks("CE", 100.0, 100.0, 30 / 365, 0.065, 0.0).delta == 0.0  # zero premium → safe zeros


def _condor(underlying="NIFTY"):
    # a short iron condor: sell inner CE+PE, buy outer wings — net short vega, positive theta
    return {"underlying": underlying, "quantity": 1, "expiry": "2026-09-25",
            "features": {"expected_pnl": 500.0, "cvar": 2000.0}, "order_id": f"{underlying}|IC",
            "legs": [
                {"right": "CE", "strike": 105, "side": "sell", "current_price": 4, "lot_size": 50},
                {"right": "CE", "strike": 110, "side": "buy", "current_price": 2, "lot_size": 50},
                {"right": "PE", "strike": 95, "side": "sell", "current_price": 4, "lot_size": 50},
                {"right": "PE", "strike": 90, "side": "buy", "current_price": 2, "lot_size": 50}]}


def test_book_net_greeks_and_sizing():
    eng = OptionBookRiskEngine()
    risk = eng.assess([_condor("NIFTY"), _condor("BANKNIFTY")], spot_of=lambda u: 100.0)
    assert risk.n_structures == 2
    assert risk.net_vega < 0 and risk.net_theta > 0  # short-premium book: short vega, earns theta
    assert risk.expected_pnl == pytest.approx(1000.0)  # 500 × 2
    assert risk.portfolio_cvar > 0
    assert all(0.0 <= m <= 3.0 for m in risk.live_size_multipliers.values())  # CVXPY sizing bounded


def test_empty_book_is_zero():
    r = OptionBookRiskEngine().assess([], spot_of=lambda u: 100.0)
    assert r.n_structures == 0 and r.expected_pnl == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
