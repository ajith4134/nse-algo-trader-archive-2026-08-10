"""Unit tests for the curiosity engine's component layers (research/164; Trunk XII)."""

from __future__ import annotations

import pytest

from nse_algo_trader.intrinsic_motivation.curiosity_experience_reader import (
    build_curiosity_observation,
)
from nse_algo_trader.intrinsic_motivation.learning_progress_estimator import (
    MIN_WINDOW,
    CellLearningState,
    compute_learning_progress,
    update_cell_learning_state,
)
from nse_algo_trader.intrinsic_motivation.count_based_novelty import (
    enumerate_cell_novelties,
    novelty_bonus,
)


def _row(strategy, regime, brier, outcome="loss"):
    return {"strategy_tag": strategy, "market_regime": regime, "brier_contribution": brier,
            "actual_outcome": outcome, "win_probability": 0.5, "occurred_at": "2026-07-24T10:00:00+05:30"}


# -- reader ---------------------------------------------------------------------------------------

def test_reader_groups_by_cell_and_preserves_time_order():
    rows = [_row("orb", "indecisive", 0.1), _row("orb", "indecisive", 0.2), _row("orb", "trending", 0.3)]
    obs = build_curiosity_observation(rows)
    assert obs.total_samples == 3
    assert obs.cells_by_key[("orb", "indecisive")].errors_in_time_order == (0.1, 0.2)
    assert obs.strategies_seen == frozenset({"orb"})
    assert obs.regimes_seen == frozenset({"indecisive", "trending"})


def test_reader_recomputes_brier_when_absent():
    row = {"strategy_tag": "orb", "market_regime": "indecisive", "win_probability": 0.8,
           "actual_outcome": "loss", "occurred_at": "t"}  # no brier_contribution
    obs = build_curiosity_observation([row])
    # (0.8 - 0)^2 = 0.64
    assert obs.cells_by_key[("orb", "indecisive")].errors_in_time_order[0] == pytest.approx(0.64)


def test_reader_drops_rows_without_derivable_error():
    rows = [{"strategy_tag": "orb", "market_regime": "indecisive"}]  # no brier, no win_prob
    obs = build_curiosity_observation(rows)
    assert obs.total_samples == 0


# -- learning progress ----------------------------------------------------------------------------

def test_lp_none_below_trust_gate():
    assert compute_learning_progress(tuple([0.1] * (2 * MIN_WINDOW - 1))) is None


def test_lp_positive_when_error_decreasing():
    # prior window high error, recent window low error → positive LP (learning)
    errors = tuple([0.4] * MIN_WINDOW + [0.1] * MIN_WINDOW)
    lp = compute_learning_progress(errors)
    assert lp == pytest.approx(0.3)


def test_lp_negative_when_error_rising():
    errors = tuple([0.1] * MIN_WINDOW + [0.4] * MIN_WINDOW)
    assert compute_learning_progress(errors) == pytest.approx(-0.3)


def test_q_lp_tracks_absolute_progress_and_boredom_increments():
    from nse_algo_trader.intrinsic_motivation.curiosity_experience_reader import CellErrorSeries
    # flat error (no learning) → |LP|≈0 → a bored window
    errors = tuple([0.2] * (2 * MIN_WINDOW))
    cell = CellErrorSeries("orb", "indecisive", errors, tuple([0] * len(errors)), len(errors))
    reading = update_cell_learning_state(cell, CellLearningState(samples_at_last_update=0))
    assert reading.is_trusted is True
    assert reading.new_state.consecutive_bored_windows == 1
    assert reading.new_state.boredom_multiplier < 1.0


def test_no_double_count_without_new_samples():
    from nse_algo_trader.intrinsic_motivation.curiosity_experience_reader import CellErrorSeries
    errors = tuple([0.4] * MIN_WINDOW + [0.1] * MIN_WINDOW)
    cell = CellErrorSeries("orb", "indecisive", errors, tuple([1] * len(errors)), len(errors))
    first = update_cell_learning_state(cell, CellLearningState(samples_at_last_update=0))
    # same sample_count → state unchanged (no re-fold)
    second = update_cell_learning_state(cell, first.new_state)
    assert second.new_state == first.new_state


# -- novelty --------------------------------------------------------------------------------------

def test_novelty_max_at_zero_and_decays():
    assert novelty_bonus(0) == pytest.approx(1.0)
    assert novelty_bonus(3) == pytest.approx(0.5)
    assert novelty_bonus(99) < novelty_bonus(10)


def test_enumerate_includes_unobserved_regime_combinations():
    rows = [_row("orb", "indecisive", 0.2)]
    obs = build_curiosity_observation(rows)
    novelties = enumerate_cell_novelties(obs)
    unobserved = [c for c in novelties if c.is_unobserved]
    # orb seen only in indecisive → trending + range_bound are unobserved (N=0, max novelty)
    assert {c.market_regime for c in unobserved} == {"trending", "range_bound"}
    assert all(c.novelty == pytest.approx(1.0) for c in unobserved)
