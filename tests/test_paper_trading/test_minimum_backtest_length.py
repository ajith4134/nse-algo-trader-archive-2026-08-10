"""Tests for the MinBTL gate and the CSCV Probability of Backtest Overfitting.

Covers: MinBTL monotonicity in trial count and target Sharpe, the
sufficiency-gate boundary flip, degenerate conventions, consistency with the
Deflated-Sharpe promotion-gate benchmark, and PBO on constructed matrices where
the answer is known (random OOS ⇒ PBO ≈ 0.5; genuinely-best OOS ⇒ PBO ≈ 0;
worst OOS ⇒ PBO ≈ 1).
"""

import math
import random

import pytest

from nse_algo_trader.paper_trading.minimum_backtest_length import (
    backtest_length_is_sufficient,
    combinatorially_symmetric_cross_validation,
    estimate_probability_of_backtest_overfitting_via_cscv,
    expected_maximum_sharpe_coefficient,
    minimum_backtest_length,
    probability_of_backtest_overfitting,
)
from nse_algo_trader.paper_trading.strategy_promotion_gate import (
    estimate_deflated_sharpe_benchmark,
)

# ---------------------------------------------------------------------------
# MinBTL — units, values, monotonicity
# ---------------------------------------------------------------------------


def test_minbtl_years_matches_closed_form() -> None:
    coefficient = expected_maximum_sharpe_coefficient(100)
    expected_years = (coefficient / 1.5) ** 2
    assert minimum_backtest_length(100, 1.5) == pytest.approx(expected_years)


def test_minbtl_consistent_with_promotion_gate_benchmark() -> None:
    """The MinBTL coefficient IS the promotion gate's expected-max benchmark at
    unit cross-trial Sharpe dispersion — reused, not re-derived."""
    for number_of_trials in (2, 5, 50, 500):
        assert expected_maximum_sharpe_coefficient(
            number_of_trials
        ) == pytest.approx(
            estimate_deflated_sharpe_benchmark(1.0, number_of_trials)
        )


def test_minbtl_monotonic_increasing_in_number_of_trials() -> None:
    lengths = [
        minimum_backtest_length(n, target_annual_sharpe=1.0)
        for n in (2, 3, 5, 10, 50, 100, 1000, 10000)
    ]
    assert all(earlier < later for earlier, later in zip(lengths, lengths[1:]))


def test_minbtl_decreases_as_target_sharpe_rises() -> None:
    lengths = [
        minimum_backtest_length(100, target_annual_sharpe=t)
        for t in (0.5, 1.0, 1.5, 2.0, 3.0)
    ]
    assert all(earlier > later for earlier, later in zip(lengths, lengths[1:]))


def test_minbtl_observations_per_year_scales_linearly() -> None:
    years = minimum_backtest_length(200, 1.2, observations_per_year=1.0)
    daily = minimum_backtest_length(200, 1.2, observations_per_year=252.0)
    assert daily == pytest.approx(years * 252.0)


def test_minbtl_more_trials_need_a_longer_backtest_example() -> None:
    # A concrete sanity anchor: 10x more trials strictly lengthens MinBTL.
    assert minimum_backtest_length(1000, 1.0) > minimum_backtest_length(100, 1.0)


# ---------------------------------------------------------------------------
# MinBTL — degenerate conventions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("number_of_trials", [-5, 0, 1])
def test_minbtl_single_or_no_trial_is_zero(number_of_trials: int) -> None:
    assert minimum_backtest_length(number_of_trials, 1.0) == 0.0


@pytest.mark.parametrize("target", [0.0, -0.5, -10.0])
def test_minbtl_nonpositive_target_is_infinite(target: float) -> None:
    assert minimum_backtest_length(100, target) == math.inf


def test_minbtl_nonpositive_target_but_no_trials_is_still_zero() -> None:
    # N<2 short-circuits before the target check: no multiple testing at all.
    assert minimum_backtest_length(1, -1.0) == 0.0


def test_minbtl_nonpositive_observations_per_year_raises() -> None:
    with pytest.raises(ValueError):
        minimum_backtest_length(100, 1.0, observations_per_year=0.0)


# ---------------------------------------------------------------------------
# Sufficiency gate — boundary flip
# ---------------------------------------------------------------------------


def test_backtest_length_is_sufficient_flips_at_the_boundary() -> None:
    number_of_trials, target = 100, 1.0
    required = minimum_backtest_length(
        number_of_trials, target, observations_per_year=252.0
    )
    required_ceiling = math.ceil(required)

    sufficient_above, margin_above = backtest_length_is_sufficient(
        required_ceiling + 5, number_of_trials, target
    )
    assert sufficient_above is True
    assert margin_above > 0

    sufficient_below, margin_below = backtest_length_is_sufficient(
        int(required) - 5, number_of_trials, target
    )
    assert sufficient_below is False
    assert margin_below < 0


def test_backtest_length_is_sufficient_exact_boundary_is_sufficient() -> None:
    # observations_per_year=1 lets us hit an integer MinBTL exactly.
    number_of_trials, target = 50, 1.0
    required = minimum_backtest_length(number_of_trials, target)
    at_boundary = math.ceil(required)
    sufficient, margin = backtest_length_is_sufficient(
        at_boundary, number_of_trials, target, observations_per_year=1.0
    )
    assert sufficient is True
    assert margin >= 0


def test_backtest_length_sufficient_for_single_trial_always() -> None:
    # N<2 ⇒ MinBTL 0 ⇒ any non-negative observation count is sufficient.
    sufficient, margin = backtest_length_is_sufficient(1, 1, 2.0)
    assert sufficient is True
    assert margin == pytest.approx(1.0)


def test_backtest_length_nonpositive_target_never_sufficient() -> None:
    sufficient, margin = backtest_length_is_sufficient(10_000_000, 100, 0.0)
    assert sufficient is False
    assert margin == -math.inf


# ---------------------------------------------------------------------------
# PBO — constructed matrices with known answers
# ---------------------------------------------------------------------------


def _paired_matrices(
    is_matrix: list[list[float]], oos_matrix: list[list[float]]
) -> tuple[list[list[float]], list[list[float]]]:
    return is_matrix, oos_matrix


def test_pbo_is_best_genuinely_best_oos_is_near_zero() -> None:
    # Configuration 0 is best both IS and OOS on every split ⇒ never below the
    # OOS median ⇒ PBO ≈ 0.
    splits = 200
    is_matrix = [[10.0, 5.0, 1.0, -3.0] for _ in range(splits)]
    oos_matrix = [[9.0, 4.0, 0.5, -2.5] for _ in range(splits)]
    result = probability_of_backtest_overfitting(is_matrix, oos_matrix)
    assert result.is_estimable is True
    assert result.probability_of_backtest_overfitting == pytest.approx(0.0)


def test_pbo_is_best_is_worst_oos_is_near_one() -> None:
    # The IS-best configuration is deliberately the OOS-worst ⇒ always below the
    # median ⇒ PBO ≈ 1 (severe overfitting).
    splits = 200
    is_matrix = [[10.0, 5.0, 1.0, -3.0] for _ in range(splits)]
    oos_matrix = [[-3.0, 1.0, 5.0, 10.0] for _ in range(splits)]
    result = probability_of_backtest_overfitting(is_matrix, oos_matrix)
    assert result.is_estimable is True
    assert result.probability_of_backtest_overfitting == pytest.approx(1.0)


def test_pbo_random_oos_is_near_half() -> None:
    # OOS performance independent of IS ⇒ the IS-best config's OOS rank is
    # uniform ⇒ PBO ≈ 0.5.
    rng = random.Random(20260803)
    splits, configs = 4000, 12
    is_matrix = [[rng.gauss(0.0, 1.0) for _ in range(configs)] for _ in range(splits)]
    oos_matrix = [[rng.gauss(0.0, 1.0) for _ in range(configs)] for _ in range(splits)]
    result = probability_of_backtest_overfitting(is_matrix, oos_matrix)
    assert result.is_estimable is True
    assert result.probability_of_backtest_overfitting == pytest.approx(0.5, abs=0.05)


def test_pbo_logits_sign_matches_overfitting() -> None:
    is_matrix = [[10.0, 5.0, 1.0]]
    oos_matrix = [[-1.0, 5.0, 10.0]]  # IS-best (idx0) is OOS-worst
    result = probability_of_backtest_overfitting(is_matrix, oos_matrix)
    assert result.per_split_logits[0] < 0.0
    assert result.probability_of_backtest_overfitting == pytest.approx(1.0)


def test_pbo_handles_ties_in_oos_ranks() -> None:
    # All OOS values identical ⇒ mid-rank ⇒ ω = 0.5 ⇒ logit 0 ⇒ not < 0.
    is_matrix = [[3.0, 2.0, 1.0], [1.0, 2.0, 3.0]]
    oos_matrix = [[7.0, 7.0, 7.0], [7.0, 7.0, 7.0]]
    result = probability_of_backtest_overfitting(is_matrix, oos_matrix)
    assert result.is_estimable is True
    assert all(abs(logit) < 1e-9 for logit in result.per_split_logits)
    assert result.probability_of_backtest_overfitting == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# PBO — degenerate guards
# ---------------------------------------------------------------------------


def test_pbo_empty_matrices_are_not_estimable_and_conservative() -> None:
    result = probability_of_backtest_overfitting([], [])
    assert result.is_estimable is False
    assert result.probability_of_backtest_overfitting == 1.0
    assert result.split_count == 0


def test_pbo_single_configuration_is_not_estimable() -> None:
    result = probability_of_backtest_overfitting([[1.0], [2.0]], [[1.0], [2.0]])
    assert result.is_estimable is False
    assert result.probability_of_backtest_overfitting == 1.0


def test_pbo_mismatched_split_count_raises() -> None:
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting([[1.0, 2.0]], [[1.0, 2.0], [3.0, 4.0]])


def test_pbo_ragged_rows_raise() -> None:
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting([[1.0, 2.0]], [[1.0, 2.0, 3.0]])


# ---------------------------------------------------------------------------
# CSCV builder + end-to-end
# ---------------------------------------------------------------------------


def test_cscv_builds_correct_split_shapes() -> None:
    rng = random.Random(1)
    periods, configs, split_count = 240, 5, 6
    matrix = [[rng.gauss(0.0, 1.0) for _ in range(configs)] for _ in range(periods)]
    is_matrix, oos_matrix = combinatorially_symmetric_cross_validation(
        matrix, split_count
    )
    expected_combos = math.comb(split_count, split_count // 2)
    assert len(is_matrix) == expected_combos
    assert len(oos_matrix) == expected_combos
    assert all(len(row) == configs for row in is_matrix)
    assert all(len(row) == configs for row in oos_matrix)


def test_cscv_odd_split_count_raises() -> None:
    with pytest.raises(ValueError):
        combinatorially_symmetric_cross_validation([[1.0, 2.0]] * 10, split_count=5)


def test_cscv_too_few_rows_raises() -> None:
    with pytest.raises(ValueError):
        combinatorially_symmetric_cross_validation([[1.0, 2.0]] * 3, split_count=6)


def test_end_to_end_cscv_overfit_signal() -> None:
    # Configuration whose IS edge is pure in-sample noise that reverses OOS.
    # Build a T x N matrix where the "winner" is engineered to look good only on
    # the first half and bad on the second, so CSCV catches the reversal.
    rng = random.Random(7)
    periods, configs, split_count = 200, 8, 8
    matrix: list[list[float]] = []
    for t in range(periods):
        first_half = t < periods // 2
        row = []
        for c in range(configs):
            # config 0 spikes positive early, negative late (overfit trap).
            if c == 0:
                row.append(2.0 if first_half else -2.0)
            else:
                row.append(rng.gauss(0.0, 1.0))
        matrix.append(row)
    result = estimate_probability_of_backtest_overfitting_via_cscv(matrix, split_count)
    assert result.is_estimable is True
    assert 0.0 <= result.probability_of_backtest_overfitting <= 1.0
    assert result.split_count == math.comb(split_count, split_count // 2)
