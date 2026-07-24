"""Proper scoring rules for probabilistic predictions.

Provenance: the three scoring formulas are adapted from python-prediction-scorer
(github.com/yhoiseth/python-prediction-scorer, MIT), deep-scanned from its
`rules.py`/`_common.py`. What we changed vs that reference (see docs/research/48):
its rules use `Decimal` and an OO `Prediction`/`Category` API and take `p` = the
probability the prediction assigned to the outcome that HAPPENED; we keep the same
math as plain float functions with self-describing names, add a `p_outcome` mapper
for our single-probability binary trade predictions, and add a cohort
cross-entropy (the mean log-score derivable from a mechanism's predicted/actual
win rates, so the antibody can use log-score without a storage-schema change).

Why add these beyond Brier: the Brier score saturates on a bounded scale, so a
*confidently* wrong call barely stands out; the logarithmic score punishes
confident-wrong toward infinity, which the antibody tripwire uses to catch an
over-confident thesis fast.
"""

import math

# p is clamped away from 0/1 before the logarithm — a prediction can never earn an
# infinite reward or penalty, and log(0) is undefined.
_PROBABILITY_EPSILON = 1e-9


def probability_assigned_to_outcome(
    win_probability: float, trade_actually_won: bool
) -> float:
    """The probability the prediction assigned to the outcome that ACTUALLY
    happened — `win_probability` if the trade won, its complement if it lost.
    This is the `p` every proper scoring rule below consumes."""
    return win_probability if trade_actually_won else 1.0 - win_probability


def _clamp_probability(probability: float) -> float:
    return min(1.0 - _PROBABILITY_EPSILON, max(_PROBABILITY_EPSILON, probability))


def logarithmic_score(probability_of_outcome: float) -> float:
    """−log₂(p): 0 is best (certainty in what happened), rising toward large
    values as the prediction assigned less probability to the actual outcome.
    Punishes confident-wrong far harder than Brier (which saturates)."""
    return -math.log2(_clamp_probability(probability_of_outcome))


def quadratic_score(probability_of_outcome: float) -> float:
    """p·(2−p) − (1−p)²: +1 best, −1 worst (a bounded reward-form proper score)."""
    inverse = 1.0 - probability_of_outcome
    return probability_of_outcome * (2.0 - probability_of_outcome) - inverse**2


def brier_score_two_class(probability_of_outcome: float) -> float:
    """2·(1−p)²: 0 best, 2 worst — the two-class Brier in the reference library's
    convention (equals 2× our single-term `brier_contribution`)."""
    return 2.0 * (1.0 - probability_of_outcome) ** 2


def calibration_cross_entropy_bits(
    actual_win_rate: float, predicted_win_rate: float
) -> float:
    """A cohort's mean logarithmic score (bits) = the calibration cross-entropy
    H(ā, p̄) = −[ā·log₂(p̄) + (1−ā)·log₂(1−p̄)] between its actual win rate ā and
    predicted win rate p̄. Derivable from the two aggregates already on the
    calibration board, so the antibody gets a log-score signal with no
    per-experiment storage change. A confidently-wrong cohort (p̄=0.85, ā=0.15)
    scores ≈2.36 bits; an always-0.5 predictor scores 1.0 bit."""
    predicted = _clamp_probability(predicted_win_rate)
    return -(
        actual_win_rate * math.log2(predicted)
        + (1.0 - actual_win_rate) * math.log2(1.0 - predicted)
    )
