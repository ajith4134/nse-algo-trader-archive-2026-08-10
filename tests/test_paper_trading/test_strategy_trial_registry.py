"""Hermetic tests for the persistent strategy-trial registry (L2 validation
engine, docs/research/166) — the honest cumulative trial count `N` the Deflated
Sharpe Ratio deflates against.

Rule J: a temp `.db` path is injected through the same constructor seam
production uses; no fake leaks into prod. Covers register/count, dedup, family
scoping, persistence across two registry instances on the same file, empty
registry, NaN/inf handling, negative observation counts, statistical agreement
with `statistics`, and order-independence/stability of `stable_config_hash`.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime

import pytest

from nse_algo_trader.paper_trading.strategy_trial_registry import (
    StrategyTrialRegistry,
    stable_config_hash,
)


def _fixed_now() -> datetime:
    return datetime(2026, 8, 3, 10, 0, 0)


def _make_registry(tmp_path) -> StrategyTrialRegistry:
    return StrategyTrialRegistry(
        db_file_path=tmp_path / "strategy_trials.sqlite3",
        now_provider=_fixed_now,
    )


# ----- register / count ---------------------------------------------------


def test_register_one_trial_counts_one(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.5, 40, kept=True)
    assert registry.cumulative_trial_count() == 1


def test_distinct_configs_increment_the_honest_n(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.5, 40, kept=True)
    registry.register_trial("orb", "cfg_b", 0.3, 40, kept=False)
    registry.register_trial("orb", "cfg_c", 0.9, 40, kept=True)
    assert registry.cumulative_trial_count() == 3


def test_reregistering_same_config_hash_dedups_and_updates_row(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.5, 40, kept=False)
    # A re-run of the IDENTICAL config is NOT a new independent trial.
    registry.register_trial("orb", "cfg_a", 0.7, 55, kept=True)
    assert registry.cumulative_trial_count() == 1
    # The row was UPDATED to the latest Sharpe (0.7), not left at 0.5.
    assert registry.all_trial_sharpes() == [pytest.approx(0.7)]
    summary = registry.trial_summary()
    assert summary["count"] == 1
    assert summary["kept_count"] == 1


def test_same_config_hash_in_different_families_are_distinct_trials(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "shared_hash", 0.5, 40, kept=True)
    registry.register_trial("vwap", "shared_hash", 0.6, 40, kept=True)
    assert registry.cumulative_trial_count() == 2


# ----- family scoping -----------------------------------------------------


def test_family_scoping_of_count_and_std(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.2, 40, kept=True)
    registry.register_trial("orb", "cfg_b", 0.8, 40, kept=True)
    registry.register_trial("vwap", "cfg_c", 0.4, 40, kept=True)
    assert registry.cumulative_trial_count("orb") == 2
    assert registry.cumulative_trial_count("vwap") == 1
    assert registry.cumulative_trial_count() == 3
    assert registry.sharpe_std_across_trials("orb") == pytest.approx(
        statistics.pstdev([0.2, 0.8])
    )
    # vwap has a single trial -> std undefined -> 0.0
    assert registry.sharpe_std_across_trials("vwap") == 0.0


# ----- sharpe_std correctness ---------------------------------------------


def test_sharpe_std_matches_statistics_population_std(tmp_path):
    registry = _make_registry(tmp_path)
    sharpes = [0.1, -0.3, 0.55, 0.42, -0.18, 0.9]
    for index, sharpe in enumerate(sharpes):
        registry.register_trial("orb", f"cfg_{index}", sharpe, 40, kept=True)
    assert registry.sharpe_std_across_trials() == pytest.approx(
        statistics.pstdev(sharpes)
    )
    assert sorted(registry.all_trial_sharpes()) == pytest.approx(sorted(sharpes))


def test_trial_summary_fields(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.2, 40, kept=True)
    registry.register_trial("orb", "cfg_b", 0.8, 40, kept=True)
    registry.register_trial("orb", "cfg_c", -0.4, 40, kept=False)
    summary = registry.trial_summary()
    assert summary["count"] == 3
    assert summary["kept_count"] == 2
    assert summary["discarded_count"] == 1
    assert summary["sharpe_std"] == pytest.approx(
        statistics.pstdev([0.2, 0.8, -0.4])
    )
    assert summary["mean_sharpe"] == pytest.approx(
        statistics.fmean([0.2, 0.8, -0.4])
    )


# ----- persistence across instances (Rule J: same db file) ----------------


def test_persistence_across_two_registry_instances_on_same_db(tmp_path):
    db_path = tmp_path / "persist.sqlite3"
    first = StrategyTrialRegistry(db_file_path=db_path, now_provider=_fixed_now)
    first.register_trial("orb", "cfg_a", 0.5, 40, kept=True)
    first.register_trial("orb", "cfg_b", 0.7, 40, kept=False)

    # A fresh process/instance on the SAME file sees the accumulated trials —
    # this is exactly what makes N honest across restarts.
    second = StrategyTrialRegistry(db_file_path=db_path, now_provider=_fixed_now)
    assert second.cumulative_trial_count() == 2
    assert second.sharpe_std_across_trials() == pytest.approx(
        statistics.pstdev([0.5, 0.7])
    )

    # And a NEW config from the second instance accumulates, not resets.
    second.register_trial("orb", "cfg_c", 0.9, 40, kept=True)
    assert second.cumulative_trial_count() == 3


# ----- empty registry -----------------------------------------------------


def test_empty_registry_is_zero_and_zero(tmp_path):
    registry = _make_registry(tmp_path)
    assert registry.cumulative_trial_count() == 0
    assert registry.cumulative_trial_count("orb") == 0
    assert registry.sharpe_std_across_trials() == 0.0
    assert registry.all_trial_sharpes() == []
    summary = registry.trial_summary()
    assert summary == {
        "count": 0,
        "kept_count": 0,
        "discarded_count": 0,
        "sharpe_std": 0.0,
        "mean_sharpe": 0.0,
    }


def test_single_trial_has_zero_std(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.5, 40, kept=True)
    assert registry.sharpe_std_across_trials() == 0.0


# ----- adversarial: NaN / inf / negative counts ---------------------------


@pytest.mark.parametrize("bad_sharpe", [math.nan, math.inf, -math.inf])
def test_non_finite_sharpe_is_ignored_in_stats_but_trial_still_counts(
    tmp_path, bad_sharpe
):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_good_1", 0.4, 40, kept=True)
    registry.register_trial("orb", "cfg_good_2", 0.6, 40, kept=True)
    registry.register_trial("orb", "cfg_bad", bad_sharpe, 40, kept=True)

    # The bad-Sharpe config WAS trialed -> it counts toward the honest N.
    assert registry.cumulative_trial_count() == 3
    # ...but its non-finite Sharpe never poisons the dispersion sample.
    sharpes = registry.all_trial_sharpes()
    assert all(math.isfinite(value) for value in sharpes)
    assert sorted(sharpes) == pytest.approx([0.4, 0.6])
    std = registry.sharpe_std_across_trials()
    assert math.isfinite(std)
    assert std == pytest.approx(statistics.pstdev([0.4, 0.6]))
    assert math.isfinite(registry.trial_summary()["mean_sharpe"])


def test_negative_observation_count_is_clamped_and_does_not_raise(tmp_path):
    registry = _make_registry(tmp_path)
    registry.register_trial("orb", "cfg_a", 0.5, -17, kept=True)
    assert registry.cumulative_trial_count() == 1


def test_register_never_raises_on_bad_input(tmp_path):
    registry = _make_registry(tmp_path)
    # A non-numeric Sharpe would blow up math.isfinite; register must swallow it
    # (instrumentation must not break a trading pass) and leave N unchanged.
    registry.register_trial("orb", "cfg_a", "not-a-number", 40, kept=True)  # type: ignore[arg-type]
    assert registry.cumulative_trial_count() == 0


# ----- stable_config_hash: order-independent + stable ---------------------


def test_stable_config_hash_is_order_independent(tmp_path):
    assert stable_config_hash({"a": 1, "b": 2, "c": 3}) == stable_config_hash(
        {"c": 3, "a": 1, "b": 2}
    )


def test_stable_config_hash_is_order_independent_when_nested():
    left = {"outer": {"x": 1, "y": 2}, "z": [1, 2, 3]}
    right = {"z": [1, 2, 3], "outer": {"y": 2, "x": 1}}
    assert stable_config_hash(left) == stable_config_hash(right)


def test_stable_config_hash_is_stable_and_distinguishes_content():
    config = {"opening_range_minutes": 15, "target_r_multiple": 2.0}
    assert stable_config_hash(config) == stable_config_hash(dict(config))
    assert stable_config_hash(config) != stable_config_hash(
        {"opening_range_minutes": 30, "target_r_multiple": 2.0}
    )


def test_stable_config_hash_dedups_a_reregistered_identical_config(tmp_path):
    registry = _make_registry(tmp_path)
    config = {"opening_range_minutes": 15, "target_r_multiple": 2.0}
    hash_first = stable_config_hash(config)
    # Same content, different insertion order -> same hash -> dedup.
    hash_again = stable_config_hash(
        {"target_r_multiple": 2.0, "opening_range_minutes": 15}
    )
    registry.register_trial("orb", hash_first, 0.5, 40, kept=True)
    registry.register_trial("orb", hash_again, 0.6, 40, kept=True)
    assert registry.cumulative_trial_count() == 1
