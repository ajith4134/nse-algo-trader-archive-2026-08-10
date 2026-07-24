"""Proper scoring rules — hand-computed values (vendored python-prediction-scorer)."""
import math
from nse_algo_trader.paper_trading.prediction_lab.proper_scoring_rules import (
    probability_assigned_to_outcome, logarithmic_score, quadratic_score,
    brier_score_two_class, calibration_cross_entropy_bits,
)


def test_probability_assigned_to_outcome():
    assert probability_assigned_to_outcome(0.8, True) == 0.8
    assert abs(probability_assigned_to_outcome(0.8, False) - 0.2) < 1e-9


def test_logarithmic_score_reference_points():
    assert abs(logarithmic_score(0.5) - 1.0) < 1e-9      # coin-flip = 1 bit
    assert abs(logarithmic_score(1.0) - 0.0) < 1e-6      # certainty = 0
    assert logarithmic_score(0.1) > logarithmic_score(0.4)  # confident-wrong worse


def test_quadratic_score_reference_points():
    assert abs(quadratic_score(1.0) - 1.0) < 1e-9        # best +1
    assert abs(quadratic_score(0.0) + 1.0) < 1e-9        # worst -1


def test_brier_two_class_reference_points():
    assert abs(brier_score_two_class(1.0)) < 1e-9        # best 0
    assert abs(brier_score_two_class(0.0) - 2.0) < 1e-9  # worst 2


def test_cross_entropy_confidently_wrong_exceeds_coinflip():
    # predicted 0.85, actual 0.15 -> confidently wrong -> well above 1 bit
    assert calibration_cross_entropy_bits(0.15, 0.85) > 2.0
    # well-calibrated confident cohort -> below 1 bit
    assert calibration_cross_entropy_bits(0.85, 0.85) < 1.0
