"""Hermetic test for the per-trade pre-mortem Monte Carlo (Layer 7.5 slice 3; research/107):
deterministic synthetic paths drive target / stop / timeout outcomes, and the aggregate
probabilities, mean, CVaR, worst case + seeded reproducibility are asserted. Pure, no I/O.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.paper_trading.per_trade_pre_mortem import run_entry_pre_mortem
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection

# entry 100, stop 99, target 102 (RR 2 at 1% risk)
_ENTRY, _STOP, _TARGET = 100.0, 99.0, 102.0


def _run(paths, seed=0, trials=1000):
    return run_entry_pre_mortem(
        _ENTRY, _STOP, _TARGET, SignalDirection.LONG, paths, trials=trials, seed=seed
    )


def test_no_paths_returns_none():
    assert _run([]) is None


def test_a_winning_path_hits_target_every_trial():
    # +1.5% then +1% → crosses 102 → target on every resample
    forecast = _run([[0.015, 0.01]])
    assert forecast.probability_target == 1.0
    assert forecast.probability_stop == 0.0
    assert forecast.mean_return == pytest.approx((102 - 100) / 100)


def test_a_losing_path_hits_stop_every_trial():
    # -1.5% → crosses 99 → stop on every resample
    forecast = _run([[-0.015]])
    assert forecast.probability_stop == 1.0
    assert forecast.mean_return == pytest.approx((99 - 100) / 100)
    assert forecast.worst_case_return == pytest.approx(-0.01)


def test_timeout_path_exits_at_path_end():
    # drifts to +0.5% without touching stop/target → timeout at the last close
    forecast = _run([[0.003, 0.002]])
    assert forecast.probability_timeout == 1.0
    assert forecast.mean_return == pytest.approx(100.0 * 1.003 * 1.002 / 100 - 1.0, abs=1e-6)


def test_distribution_over_mixed_paths_and_reproducible():
    paths = [[0.015, 0.01], [-0.015], [0.003, 0.002]]  # win / loss / timeout
    a = _run(paths, seed=42)
    b = _run(paths, seed=42)
    assert a == b  # seeded → reproducible
    # all three outcomes appear, probabilities sum to 1
    assert a.probability_target > 0 and a.probability_stop > 0 and a.probability_timeout > 0
    assert a.probability_target + a.probability_stop + a.probability_timeout == pytest.approx(1.0)
    # CVaR (worst 5%) is at least as bad as the mean
    assert a.conditional_value_at_risk_5pct <= a.mean_return
