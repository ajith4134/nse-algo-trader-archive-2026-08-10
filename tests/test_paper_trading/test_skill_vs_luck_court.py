"""Hermetic test for the SHADOW-REJECTED arm + skill-vs-luck court (Layer 7.5 slice 2;
research/106): the calibration board splits into taken vs vetoed arms with correct weighted
aggregates + rejection verdict, and the court combines the RANDOM-CONTROL edge + the
shadow-rejected verdict into the right overall judgment. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.memory_reflection.experience_memory import CalibrationBoardRow
from nse_algo_trader.paper_trading.control_arm_comparison import (
    ControlArmComparison,
    ControlArmStats,
)
from nse_algo_trader.paper_trading.shadow_rejected_arm import (
    analyze_shadow_rejected_arm,
)
from nse_algo_trader.paper_trading.skill_vs_luck_court import (
    convene_skill_vs_luck_court,
)


class _BoardStub:
    """Minimal ExperienceMemory: a calibration board with a strong TAKEN mechanism and a poor
    VETOED one."""

    def calibration_board(self, minimum_experiments=1, limit=50, **_):
        return [
            CalibrationBoardRow(
                strategy_tag="orb", mechanism_name="good_taken", experiment_count=40,
                predicted_win_rate=0.6, actual_win_rate=0.6, mean_brier=0.2,
                mean_return_fraction=0.01, mean_log_score=0.9,
            ),
            CalibrationBoardRow(
                strategy_tag="orb", mechanism_name="bad_vetoed", experiment_count=20,
                predicted_win_rate=0.8, actual_win_rate=0.2, mean_brier=0.4,
                mean_return_fraction=-0.03, mean_log_score=2.0,
            ),
        ]


def _comparison(has_edge: bool) -> ControlArmComparison:
    real = ControlArmStats("real", 15, 0.7, 0.01, 0.15, 0.9 if has_edge else 0.05)
    rnd = ControlArmStats("random", 15, 0.5, 0.0, 0.0, 0.4)
    return ControlArmComparison(real=real, random_control=rnd, has_edge=has_edge, verdict="v")


def test_shadow_rejected_split_and_rejection_verdict():
    analysis = analyze_shadow_rejected_arm(_BoardStub(), vetoed={"bad_vetoed"})
    assert analysis.taken.mechanisms == 1 and analysis.taken.experiments == 40
    assert analysis.taken.mean_return == 0.01
    assert analysis.shadow_rejected.mechanisms == 1 and analysis.shadow_rejected.experiments == 20
    assert analysis.shadow_rejected.mean_return == -0.03
    # refused mechanism did worse → the gate's rejection adds skill
    assert analysis.rejection_adds_skill is True
    assert "adds skill" in analysis.detail


def test_nothing_vetoed_yields_no_rejection_verdict():
    analysis = analyze_shadow_rejected_arm(_BoardStub(), vetoed=set())
    assert analysis.rejection_adds_skill is None
    assert analysis.shadow_rejected.experiments == 0
    assert "nothing vetoed" in analysis.detail


def test_court_reports_skill_when_directional_and_rejection_both_hold():
    analysis = analyze_shadow_rejected_arm(_BoardStub(), vetoed={"bad_vetoed"})
    verdict = convene_skill_vs_luck_court(_comparison(has_edge=True), analysis)
    assert verdict.directional_skill is True and verdict.rejection_skill is True
    assert verdict.overall_verdict.startswith("SKILL")
    assert "refuses the worse trades" in verdict.overall_verdict
    assert "SKILL DIAGONAL" in verdict.skill_diagonal_note


def test_court_reports_no_skill_when_random_control_not_beaten():
    analysis = analyze_shadow_rejected_arm(_BoardStub(), vetoed={"bad_vetoed"})
    verdict = convene_skill_vs_luck_court(_comparison(has_edge=False), analysis)
    assert verdict.directional_skill is False
    assert "NO demonstrated skill" in verdict.overall_verdict


def test_court_flags_over_rejection_when_gate_refuses_winners():
    # vetoed mechanism actually did BETTER than taken → over-rejecting
    class _InvertedBoard(_BoardStub):
        def calibration_board(self, minimum_experiments=1, limit=50, **_):
            rows = super().calibration_board()
            # swap returns so the vetoed one is the better performer
            rows[0] = CalibrationBoardRow(
                "orb", "good_taken", 40, 0.6, 0.6, 0.2, -0.03, 0.9)
            rows[1] = CalibrationBoardRow(
                "orb", "bad_vetoed", 20, 0.8, 0.2, 0.4, 0.02, 2.0)
            return rows

    analysis = analyze_shadow_rejected_arm(_InvertedBoard(), vetoed={"bad_vetoed"})
    assert analysis.rejection_adds_skill is False
    verdict = convene_skill_vs_luck_court(_comparison(has_edge=True), analysis)
    assert "OVER-REJECTING" in verdict.overall_verdict
