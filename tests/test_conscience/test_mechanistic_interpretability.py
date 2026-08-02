"""Hermetic test for mechanistic interpretability (Trunk VII; research/115): decisions are
attributed to their driving mechanisms, graded by reliability, and an influential-but-unreliable
mechanism is a red flag. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.mechanistic_interpretability import (
    explain_decision_mechanisms,
)
from nse_algo_trader.memory_reflection.experience_memory import CalibrationBoardRow


def _row(mech, n, pred, actual, ret):
    return CalibrationBoardRow(
        strategy_tag="s", mechanism_name=mech, experiment_count=n,
        predicted_win_rate=pred, actual_win_rate=actual, mean_brier=0.2,
        mean_return_fraction=ret, mean_log_score=1.0,
    )


class _Memory:
    def __init__(self, rows):
        self._rows = rows

    def calibration_board(self, minimum_experiments=1, limit=50, **_):
        return [r for r in self._rows if r.experiment_count >= minimum_experiments][:limit]


def test_well_calibrated_positive_edge_has_no_red_flags():
    mem = _Memory([
        _row("a", 40, 0.55, 0.55, 0.004), _row("b", 30, 0.60, 0.58, 0.006),
    ])
    rep = explain_decision_mechanisms(mem)
    assert rep.is_transparent and not rep.red_flags
    assert rep.reliable_share > 0.9
    assert rep.top_mechanism == "a"  # most experiments = most influential


def test_influence_shares_sum_to_one_and_are_ranked():
    mem = _Memory([_row("a", 10, 0.5, 0.5, 0.01), _row("b", 30, 0.5, 0.5, 0.01)])
    rep = explain_decision_mechanisms(mem)
    assert abs(sum(a.influence_share for a in rep.attributions) - 1.0) < 1e-9
    assert rep.attributions[0].mechanism_name == "b"  # 30 > 10, ranked first
    assert rep.attributions[0].influence_share == 0.75


def test_influential_miscalibrated_mechanism_is_a_red_flag():
    # 'bad' drives 80% of decisions but predicts 0.80 win while actually 0.40 → miscalibrated
    mem = _Memory([
        _row("bad", 80, 0.80, 0.40, 0.002), _row("ok", 20, 0.50, 0.50, 0.004),
    ])
    rep = explain_decision_mechanisms(mem)
    assert "bad" in rep.red_flags and not rep.is_transparent


def test_influential_negative_edge_mechanism_is_a_red_flag():
    mem = _Memory([
        _row("loser", 60, 0.50, 0.50, -0.01), _row("ok", 40, 0.50, 0.50, 0.01),
    ])
    rep = explain_decision_mechanisms(mem)
    assert "loser" in rep.red_flags  # well-calibrated but negative edge + influential


def test_empty_memory_is_handled():
    rep = explain_decision_mechanisms(_Memory([]))
    assert rep.total_experiments == 0 and rep.top_mechanism is None and rep.is_transparent
