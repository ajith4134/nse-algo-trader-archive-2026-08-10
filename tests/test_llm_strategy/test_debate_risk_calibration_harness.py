"""Hermetic test for the debate risk_score earn-calibration harness (Layer 11 slice 2c,
research/101): the pure separation math + the conservative earned/not-earned thresholds.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.debate_risk_calibration_harness import (
    RiskOutcomeObservation,
    score_risk_calibration,
)


def _obs(risk_score, wins, losses):
    return [RiskOutcomeObservation(risk_score, True) for _ in range(wins)] + [
        RiskOutcomeObservation(risk_score, False) for _ in range(losses)
    ]


def test_insufficient_observations_are_not_earned():
    verdict = score_risk_calibration(_obs(0.2, 5, 1) + _obs(0.9, 1, 5))
    assert verdict.earned is False
    assert "observations" in verdict.note  # learning message


def test_one_sided_risk_distribution_is_not_earned():
    # plenty of data but ALL low-risk → no high cohort to compare
    verdict = score_risk_calibration(_obs(0.2, 40, 20))
    assert verdict.earned is False
    assert verdict.high_cohort_count == 0
    assert "one-sided" in verdict.note


def test_clear_separation_with_enough_data_is_earned():
    # low-risk wins 80%, high-risk wins 30% → separation 0.50, both cohorts large
    verdict = score_risk_calibration(_obs(0.2, 40, 10) + _obs(0.9, 15, 35))
    assert verdict.earned is True
    assert verdict.low_cohort_win_rate == 0.8
    assert verdict.high_cohort_win_rate == 0.3
    assert round(verdict.separation, 2) == 0.5
    assert "EARNED" in verdict.note


def test_too_small_a_separation_is_not_earned():
    # both cohorts ~50% → separation ~0, below the 5% floor
    verdict = score_risk_calibration(_obs(0.2, 25, 25) + _obs(0.9, 24, 26))
    assert verdict.earned is False
    assert "separation" in verdict.note
