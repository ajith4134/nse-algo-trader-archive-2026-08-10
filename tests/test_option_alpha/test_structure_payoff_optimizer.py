"""Tests for the terminal-distribution model + structure payoff optimizer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.option_alpha.option_opportunity_scorer import ProfitEngine
from nse_algo_trader.option_alpha.structure_payoff_optimizer import StructurePayoffOptimizer
from nse_algo_trader.option_alpha.terminal_distribution_model import TerminalDistributionModel
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide


def _chain(spot=100.0, step=5.0, n=9):
    # realistic chain: time value DECAYS with distance from ATM (a real smile), so OTM wings are cheaper than
    # the inner legs — a short condor collects a genuine positive credit (a flat-premium chain would net ~0 and
    # be correctly rejected by the optimizer's trade-quality premium floor).
    rows = []
    for i in range(-n, n + 1):
        k = spot + i * step
        time_value = max(0.3, 3.0 - 0.35 * abs(i))  # ATM ≈ 3.0, decaying ~0.35/step, floored
        rows.append({"option_right_code": "CE", "strike_price": k, "close_price": max(spot - k, 0) + time_value,
                     "underlying_price": spot, "expiry_date": "2026-08-25", "open_interest": 5000,
                     "total_traded_volume": 1000})
        rows.append({"option_right_code": "PE", "strike_price": k, "close_price": max(k - spot, 0) + time_value,
                     "underlying_price": spot, "expiry_date": "2026-08-25", "open_interest": 5000,
                     "total_traded_volume": 1000})
    return pd.DataFrame(rows)


def _dist(spot=100.0, sigma=0.2, conviction=0.0, sign=0):
    return TerminalDistributionModel(n_samples=5000, seed=1).simulate(
        spot, 30 / 365, sigma, directional_conviction=conviction, directional_sign=sign)


# ---- terminal distribution ----
def test_distribution_centered_and_widens_with_sigma():
    narrow = _dist(sigma=0.1).samples
    wide = _dist(sigma=0.5).samples
    assert abs(float(np.median(narrow)) - 100.0) < 5.0
    assert float(np.std(wide)) > float(np.std(narrow))  # higher σ → wider terminal spread


def test_drift_shifts_distribution_with_conviction():
    up = _dist(conviction=1.0, sign=1)
    down = _dist(conviction=1.0, sign=-1)
    assert up.probability_above(100.0) > 0.5 > down.probability_above(100.0)


def test_same_day_tenor_is_floored_not_zero():
    d = TerminalDistributionModel(n_samples=1000).simulate(100.0, 0.0, 0.2)
    assert d.tenor_years > 0 and np.isfinite(d.samples).all()


# ---- payoff optimizer ----
def test_theta_returns_a_defined_risk_condor():
    opt = StructurePayoffOptimizer(max_loss_fraction=0.1)
    r = opt.optimize(_chain(), _dist(sigma=0.15), ProfitEngine.THETA, lot_size=50)
    assert r is not None and len(r.legs) == 4  # iron condor
    assert {leg.side for leg in r.legs} == {"buy", "sell"}  # has protective wings → defined risk
    assert np.isfinite(r.max_loss) and r.max_loss > 0
    assert 0.0 <= r.p_profit <= 1.0


def test_delta_long_builds_call_debit_spread():
    opt = StructurePayoffOptimizer(max_loss_fraction=0.1)
    r = opt.optimize(_chain(), _dist(conviction=0.8, sign=1), ProfitEngine.DELTA, lot_size=50,
                     trend_side=TradeSide.LONG)
    assert r is not None
    assert all(leg.right == "CE" for leg in r.legs)  # call structure for a long view
    assert any(leg.side == "buy" for leg in r.legs) and any(leg.side == "sell" for leg in r.legs)


def test_vega_builds_long_convexity():
    opt = StructurePayoffOptimizer(max_loss_fraction=0.2)
    r = opt.optimize(_chain(), _dist(sigma=0.3), ProfitEngine.VEGA, lot_size=50)
    assert r is not None and all(leg.side == "buy" for leg in r.legs)  # long straddle/strangle


def test_max_loss_cap_rejects_undefined_risk():
    # a tiny cap → even a defined-risk condor's max loss exceeds it → nothing returned
    opt = StructurePayoffOptimizer(max_loss_fraction=0.0)
    assert opt.optimize(_chain(), _dist(), ProfitEngine.THETA, lot_size=50) is None


def test_expected_pnl_is_finite_and_priced():
    opt = StructurePayoffOptimizer(max_loss_fraction=0.5)
    r = opt.optimize(_chain(), _dist(sigma=0.2), ProfitEngine.THETA, lot_size=50)
    assert r is not None and np.isfinite(r.expected_pnl) and np.isfinite(r.cvar)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
