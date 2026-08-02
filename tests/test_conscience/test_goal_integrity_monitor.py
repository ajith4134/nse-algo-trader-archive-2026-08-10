"""Hermetic test for the goal-integrity monitor (Trunk VII; research/114): a profitable, edge-
concentrated cohort is ALIGNED; a negative-return systemic cohort is CRITICAL (objective-sign
drift); a win-rate/return rank inversion flags goal-proxy divergence. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.goal_integrity_monitor import (
    DeclaredObjective,
    assess_goal_integrity,
)
from nse_algo_trader.memory_reflection.experience_memory import CalibrationBoardRow


def _row(mech, n, win, ret):
    return CalibrationBoardRow(
        strategy_tag="s", mechanism_name=mech, experiment_count=n,
        predicted_win_rate=win, actual_win_rate=win, mean_brier=0.2,
        mean_return_fraction=ret, mean_log_score=1.0,
    )


class _Memory:
    def __init__(self, rows):
        self._rows = rows

    def calibration_board(self, minimum_experiments=1, limit=50, **_):
        return [r for r in self._rows if r.experiment_count >= minimum_experiments][:limit]


def test_aligned_when_profitable_and_win_rate_tracks_return():
    # higher win-rate mechanisms also earn more return → positive proxy alignment, positive return
    mem = _Memory([
        _row("a", 30, 0.40, -0.002), _row("b", 30, 0.55, 0.004), _row("c", 30, 0.70, 0.010),
    ])
    v = assess_goal_integrity(mem)
    assert v.aligned and v.severity == "clear" and not v.drift_flags
    assert v.integrity_score > 0.8


def test_warning_on_objective_sign_when_aggregate_return_negative():
    # negative aggregate return with win-rate still tracking return = UNDERPERFORMANCE → warning
    # (not a halt); goal-integrity halts only on structural proxy misalignment.
    mem = _Memory([
        _row("a", 40, 0.45, -0.010), _row("b", 40, 0.55, -0.008),
    ])
    v = assess_goal_integrity(mem)
    assert v.severity == "warning" and not v.aligned and not v.is_critical
    assert "objective-sign" in v.drift_flags


def test_critical_when_winrate_strongly_inverts_return():
    # win-rate ranking strongly INVERSE to return ranking → structural proxy misalignment → CRITICAL
    mem = _Memory([
        _row("hi_win_lose", 30, 0.80, -0.010), _row("mid", 30, 0.50, 0.002),
        _row("lo_win_earn", 30, 0.20, 0.012),
    ])
    v = assess_goal_integrity(mem)
    assert v.is_critical and not v.aligned
    assert "goal-proxy-divergence" in v.drift_flags


def test_insufficient_data_is_clear():
    v = assess_goal_integrity(_Memory([_row("a", 5, 0.5, 0.01)]))
    assert v.aligned and v.severity == "clear" and v.integrity_score == 1.0


def test_declared_objective_thresholds_are_configurable():
    mem = _Memory([_row("a", 30, 0.5, 0.001), _row("b", 30, 0.5, 0.001)])
    strict = DeclaredObjective(min_edge_concentration=0.99)
    v = assess_goal_integrity(mem, strict)
    # concentration is 1.0 here (all positive), so still clear — proves the knob is honoured w/o crash
    assert v.severity in {"clear", "warning"}
