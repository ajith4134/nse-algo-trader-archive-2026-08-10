"""Hermetic tests for Trunk XIV AXIOLOGY — explicit utility + value drift (research/153)."""

from nse_algo_trader.axiology.explicit_utility_function import (
    ValueWeights,
    evaluate_utility,
)
from nse_algo_trader.axiology.value_drift_monitor import detect_value_drift


def test_utility_decomposition_sums_to_utility():
    returns = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, -0.015]
    u = evaluate_utility(returns)
    assert abs((u.return_term + u.risk_term + u.drawdown_term + u.tail_term) - u.utility) < 1e-9
    assert u.sample_size == len(returns)
    assert u.volatility > 0 and u.max_drawdown >= 0 and u.tail_loss_cvar5 >= 0


def test_steady_gains_score_higher_than_volatile_wash():
    steady = [0.01] * 20
    volatile = [0.20, -0.19, 0.21, -0.20] * 5   # same-ish mean, far more risk/drawdown
    assert evaluate_utility(steady).utility > evaluate_utility(volatile).utility


def test_weights_change_the_penalty():
    returns = [0.05, -0.10, 0.04, -0.12, 0.03]
    tail_averse = evaluate_utility(returns, ValueWeights(w_tail=5.0))
    tail_neutral = evaluate_utility(returns, ValueWeights(w_tail=0.0))
    assert tail_averse.utility < tail_neutral.utility  # caring about the tail lowers a tail-heavy series


def test_empty_returns_safe():
    u = evaluate_utility([])
    assert u.utility == 0.0 and u.sample_size == 0


def test_drift_flagged_when_recent_risk_spikes():
    calm = [0.005, -0.004, 0.006, -0.005] * 5           # 20-trade calm baseline
    wild = [0.15, -0.18, 0.20, -0.22, 0.17, -0.19] * 3  # 18-trade much-riskier recent window
    report = detect_value_drift(calm + wild, recent_fraction=0.45)  # recent ≈ 17 ≥ 10
    assert report.is_drifting
    assert "volatility" in report.drifting_components


def test_no_drift_when_stable():
    stable = [0.005, -0.004, 0.006, -0.005] * 10  # 40 stable trades
    report = detect_value_drift(stable, recent_fraction=0.4)
    assert not report.is_drifting


def test_insufficient_history_no_false_verdict():
    report = detect_value_drift([0.01, -0.01, 0.02], recent_fraction=0.4)
    assert not report.is_drifting and "insufficient" in report.summary
