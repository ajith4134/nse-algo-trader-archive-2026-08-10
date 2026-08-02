"""B18 steps 4-5 — the arm-selection posterior store and the adaptive selector.

The most important test in this file is `test_it_does_NOT_concentrate_when_there_is_no_edge`. A
selector that converges on a genuinely better arm but ALSO "converges" on pure noise is worse than
uniform allocation, because it is confidently wrong — and at 5-20%-of-noise edges that is the
default failure mode, not an edge case.

See `docs/research/b18_adaptive_arm_selector_design_2026-07-27.md`.
"""

import random
from collections import Counter
from datetime import datetime, timedelta

import pytest

from nse_algo_trader.paper_trading.adaptive_arm_selector import (
    AdaptiveArmSelector,
    shrink_toward_parent,
)
from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
    DEFAULT_EVIDENCE_HALF_LIFE_DAYS,
    ArmSelectionPosteriorStore,
    evidence_decay_factor,
)

ARMS = ("iv_rank", "adx_router", "trained_model")
CONTEXT = "NIFTY|trending"
START = datetime(2026, 7, 27, 10, 0)


@pytest.fixture
def store(tmp_path):
    store = ArmSelectionPosteriorStore(tmp_path / "arm_posterior.sqlite3")
    yield store
    store.close()


def _selector(store, seed=20260727, floor=None):
    return AdaptiveArmSelector(
        store, ARMS, random_source=random.Random(seed),
        **({"exploration_floor": floor} if floor is not None else {}),
    )


def _feed(store, arm, rewards, context=CONTEXT, start=START):
    for index, reward in enumerate(rewards):
        store.record_reward(arm, context, reward, start + timedelta(hours=index))


class TestTimeBasedForgetting:
    def test_evidence_halves_over_one_half_life(self):
        assert evidence_decay_factor(DEFAULT_EVIDENCE_HALF_LIFE_DAYS) == pytest.approx(0.5)
        assert evidence_decay_factor(0.0) == 1.0
        assert evidence_decay_factor(2 * DEFAULT_EVIDENCE_HALF_LIFE_DAYS) == pytest.approx(0.25)

    def test_a_cell_untouched_for_a_half_life_carries_half_its_weight(self, store):
        _feed(store, "adx_router", [100.0] * 10)
        fresh = store.load_cell("adx_router", CONTEXT, START + timedelta(hours=9))
        later = store.load_cell(
            "adx_router", CONTEXT,
            START + timedelta(hours=9, days=DEFAULT_EVIDENCE_HALF_LIFE_DAYS),
        )
        assert later.effective_sample_count == pytest.approx(
            fresh.effective_sample_count * 0.5, rel=0.01
        )

    def test_forgetting_is_TIME_based_not_observation_based(self, store):
        """A busy week must not forget faster than a quiet one — that is backwards."""
        _feed(store, "adx_router", [100.0] * 50, context="busy")       # 50 obs, ~2 days
        _feed(store, "adx_router", [100.0] * 5, context="quiet",
              start=START + timedelta(hours=1))                        # 5 obs, same window
        as_of = START + timedelta(days=3)
        busy = store.load_cell("adx_router", "busy", as_of)
        quiet = store.load_cell("adx_router", "quiet", as_of)
        # The decay factor applied is a function of elapsed time only, so the busy cell keeps its
        # larger sample count rather than being punished for trading more.
        assert busy.effective_sample_count > quiet.effective_sample_count

    def test_the_mean_survives_decay_even_as_the_count_shrinks(self, store):
        _feed(store, "adx_router", [250.0] * 12)
        decayed = store.load_cell(
            "adx_router", CONTEXT, START + timedelta(days=60)
        )
        # The MEAN is preserved exactly (decay scales sum and count together); only the WEIGHT
        # falls — 12 observations across ~2.8 half-lives keep ~12 * 0.5**2.8 ~= 1.7 of their weight.
        assert decayed.mean_reward == pytest.approx(250.0, rel=1e-6)
        assert decayed.effective_sample_count < 2.5
        assert decayed.effective_sample_count < 0.25 * 12


class TestDurabilityAndDelayedRewards:
    def test_evidence_survives_a_restart(self, tmp_path):
        path = tmp_path / "arm_posterior.sqlite3"
        first = ArmSelectionPosteriorStore(path)
        _feed(first, "iv_rank", [50.0] * 20)
        first.close()

        reopened = ArmSelectionPosteriorStore(path)
        try:
            cell = reopened.load_cell("iv_rank", CONTEXT, START + timedelta(hours=20))
            assert cell.effective_sample_count > 15.0
            assert cell.mean_reward == pytest.approx(50.0)
        finally:
            reopened.close()

    def test_a_delayed_reward_lands_on_the_cell_that_opened_the_trade(self, store):
        store.record_pending_trade("T1", "iv_rank", CONTEXT, START)
        assert store.pending_trade_count() == 1
        assert store.resolve_pending_trade("T1", 800.0, START + timedelta(hours=4))
        assert store.pending_trade_count() == 0
        cell = store.load_cell("iv_rank", CONTEXT, START + timedelta(hours=4))
        assert cell.mean_reward == pytest.approx(800.0)

    def test_an_unknown_trade_id_is_refused_not_credited_to_the_wrong_cell(self, store):
        assert not store.resolve_pending_trade("GHOST", 800.0, START)

    def test_selection_never_blocks_on_open_trades(self, store):
        for index in range(25):
            store.record_pending_trade(f"T{index}", "iv_rank", CONTEXT, START)
        assert _selector(store).select_arm(CONTEXT, START).chosen_arm in ARMS


class TestHierarchicalShrinkage:
    def test_a_cell_with_no_evidence_inherits_the_parent_not_zero(self):
        assert shrink_toward_parent(0.0, 0.0, parent_mean=420.0) == pytest.approx(420.0)

    def test_abundant_evidence_overwhelms_the_parent(self):
        shrunk = shrink_toward_parent(100.0, 10_000.0, parent_mean=-500.0)
        assert shrunk == pytest.approx(100.0, rel=0.02)

    def test_shrinkage_beats_raw_cell_means_on_noisy_cells_with_known_truth(self):
        """The James-Stein claim, TESTED rather than asserted."""
        rng = random.Random(7)
        true_mean, noise, samples_per_cell = 100.0, 400.0, 6
        raw_error = shrunk_error = 0.0
        for _ in range(400):
            observations = [rng.gauss(true_mean, noise) for _ in range(samples_per_cell)]
            raw = sum(observations) / samples_per_cell
            shrunk = shrink_toward_parent(raw, samples_per_cell, parent_mean=true_mean)
            raw_error += (raw - true_mean) ** 2
            shrunk_error += (shrunk - true_mean) ** 2
        assert shrunk_error < raw_error, "shrinkage must reduce total squared error"


class TestSelectionPolicy:
    def test_burn_in_spreads_uniformly_while_arms_are_thin(self, store):
        picks = Counter(
            _selector(store, seed=index).select_arm(CONTEXT, START).chosen_arm
            for index in range(600)
        )
        assert set(picks) == set(ARMS)
        for arm in ARMS:
            assert picks[arm] > 120, f"{arm} starved during burn-in: {picks}"

    def test_a_selection_during_burn_in_says_so(self, store):
        selection = _selector(store).select_arm(CONTEXT, START)
        assert selection.was_burn_in
        assert "burn-in" in selection.selection_reason

    def test_it_concentrates_on_a_genuinely_better_arm(self, store):
        """Criterion 7 — a real edge must eventually be found."""
        _feed(store, "iv_rank", [900.0] * 60)
        _feed(store, "adx_router", [-300.0] * 60)
        _feed(store, "trained_model", [-250.0] * 60)
        as_of = START + timedelta(hours=61)
        picks = Counter(
            _selector(store, seed=index).select_arm(CONTEXT, as_of).chosen_arm
            for index in range(400)
        )
        assert picks["iv_rank"] > 250, f"failed to find the real edge: {picks}"

    def test_it_does_NOT_concentrate_when_there_is_no_edge(self, store):
        """THE test that matters. All arms drawn from the same distribution — allocation must stay
        near uniform. A selector that 'converges' here is a confidently-wrong noise chaser."""
        rng = random.Random(99)
        for arm in ARMS:
            _feed(store, arm, [rng.gauss(0.0, 500.0) for _ in range(60)])
        as_of = START + timedelta(hours=61)
        picks = Counter(
            _selector(store, seed=index).select_arm(CONTEXT, as_of).chosen_arm
            for index in range(600)
        )
        # With no true edge, no arm may run away with the allocation.
        assert max(picks.values()) < 0.60 * 600, f"concentrated on noise: {picks}"
        assert min(picks.values()) > 0.10 * 600, f"starved an arm on noise: {picks}"

    def test_the_permanent_floor_never_starves_a_losing_arm(self, store):
        """Criterion 6 — 'it lost' must stay falsifiable, forever."""
        _feed(store, "iv_rank", [1500.0] * 80)
        _feed(store, "adx_router", [-900.0] * 80)
        _feed(store, "trained_model", [-900.0] * 80)
        as_of = START + timedelta(hours=81)
        picks = Counter(
            _selector(store, seed=index).select_arm(CONTEXT, as_of).chosen_arm
            for index in range(1500)
        )
        for arm in ("adx_router", "trained_model"):
            assert picks[arm] > 0, f"{arm} was permanently starved — unfalsifiable"

    def test_every_selection_is_auditable(self, store):
        _feed(store, "iv_rank", [100.0] * 40)
        selection = _selector(store).select_arm(CONTEXT, START + timedelta(hours=41))
        assert selection.chosen_arm in ARMS
        assert math_is_finite(selection.posterior_mean_reward)
        assert selection.posterior_standard_deviation > 0.0
        assert selection.effective_sample_count >= 0.0
        assert selection.selection_reason

    def test_contexts_are_independent(self, store):
        _feed(store, "iv_rank", [900.0] * 60, context="NIFTY|trending")
        as_of = START + timedelta(hours=61)
        other = store.load_cell("iv_rank", "BANKNIFTY|range_bound", as_of)
        assert other.effective_sample_count == 0.0

    def test_a_selector_needs_at_least_one_arm(self, store):
        with pytest.raises(ValueError):
            AdaptiveArmSelector(store, ())


def math_is_finite(value: float) -> bool:
    import math

    return math.isfinite(value)


class TestEvidenceSummaryForTheDashboard:
    """B18 step 7 — the read behind the `arm_selector` surface."""

    def test_an_arm_with_no_evidence_still_appears(self, store):
        """A never-selected arm must be VISIBLE as 0, not silently absent from the panel."""
        from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
            summarise_arm_evidence,
        )

        summaries = summarise_arm_evidence(store.load_all_cells(START), ARMS)
        assert {s.arm_name for s in summaries} == set(ARMS)
        assert all(s.context_count == 0 and not s.is_armed for s in summaries)

    def test_armed_contexts_are_counted_against_the_burn_in_floor(self, store):
        from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
            summarise_arm_evidence,
        )

        _feed(store, "iv_rank", [100.0] * 30, context="NIFTY|trending")
        _feed(store, "iv_rank", [100.0] * 3, context="NIFTY|range_bound")  # still thin
        as_of = START + timedelta(hours=31)
        summary = next(
            s for s in summarise_arm_evidence(store.load_all_cells(as_of), ARMS)
            if s.arm_name == "iv_rank"
        )
        assert summary.context_count == 2
        assert summary.contexts_past_burn_in == 1
        assert summary.is_armed

    def test_the_summary_mean_matches_the_pooled_reward(self, store):
        from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
            summarise_arm_evidence,
        )

        _feed(store, "adx_router", [200.0] * 20)
        as_of = START + timedelta(hours=21)
        summary = next(
            s for s in summarise_arm_evidence(store.load_all_cells(as_of), ARMS)
            if s.arm_name == "adx_router"
        )
        assert summary.mean_reward == pytest.approx(200.0)


class TestCrossThreadAccess:
    """The service constructs the store on the MAIN thread; the loop thread writes to it and the
    publish path reads it. SQLite refuses that by default — and the failure is SILENT for the
    reward path (it is caught and logged), so it would have quietly broken learning."""

    def test_the_store_is_usable_from_another_thread(self, store):
        import threading

        errors = []

        def _write_from_another_thread():
            try:
                store.record_reward("iv_rank", CONTEXT, 100.0, START)
                store.load_all_cells(START)
            except Exception as failure:  # noqa: BLE001
                errors.append(failure)

        worker = threading.Thread(target=_write_from_another_thread)
        worker.start()
        worker.join(timeout=10)
        assert not errors, f"cross-thread use failed: {errors}"
        assert store.load_cell("iv_rank", CONTEXT, START).effective_sample_count == 1.0
