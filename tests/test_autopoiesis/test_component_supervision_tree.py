"""Tests for the OTP supervision tree (research/170 §2/§3, research/172 §5.5 acceptance bars).

Four layers:

  1. **Acceptance bars (research/172 §5.5)** — the restart-intensity limiter trips after MaxR
     restarts in MaxT seconds and ESCALATES, and the CrashLoopBackOff delays follow the kubelet
     schedule 10 → 20 → 40 → 80 → 160 → 300 (capped) and reset after sustained health.
  2. **OTP semantics** — `permanent`/`transient`/`temporary` restart types, and strategy selection
     (ONE_FOR_ONE / REST_FOR_ONE / ONE_FOR_ALL) from the blast radius of the dependency graph.
  3. **Real-registry wiring (Rule F-adjacent)** — dependency edges derived from the PRODUCTION
     `component_registry` maintains-overlay, and the persisted lifetime events landing in a real
     SQLite store (always under `tmp_path`, never `~/.nse_algo_trader/`).
  4. **Adversarial / degenerate (Rule O.4)** — a child that always fails to restart, a liveness probe
     that raises, an empty tree, concurrent reconcile passes from many threads, and a clock that runs
     backwards.

Rule J: `FakeSupervisedComponent` is the hermetic DI-seam fake. It lives ONLY here — production
selects real adapters over threads/engines through the same `SupervisedComponent` Protocol.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from nse_algo_trader.autopoiesis.autopoiesis_state_store import AutopoiesisStateStore
from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    ComponentCriticality,
    ComponentMembership,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.component_supervision_tree import (
    CRASH_LOOP_BACKOFF_RESET_AFTER_HEALTHY_SECONDS,
    INITIAL_CRASH_LOOP_BACKOFF_SECONDS,
    MAXIMUM_CRASH_LOOP_BACKOFF_SECONDS,
    ChildLivenessObservation,
    ChildRestartType,
    ComponentSupervisionTree,
    CrashLoopBackOffPolicy,
    RestartIntensityLimiter,
    RestartIntensityPolicy,
    SupervisionChildSpecification,
    SupervisionTreeConfigurationError,
    SupervisorRestartStrategy,
    build_supervision_tree_for_registered_components,
    crash_loop_backoff_delay_seconds,
    derive_child_dependency_edges_from_registry,
    restart_type_for_registered_component,
)

BASE_MOMENT = datetime(2026, 7, 27, 4, 30, tzinfo=UTC)


class FakeSupervisedComponent:
    """Hermetic Rule-J fake behind the `SupervisedComponent` seam — tests only, never production."""

    def __init__(
        self,
        component_id: str,
        is_initially_alive: bool = True,
        restart_always_fails: bool = False,
        restart_revives: bool = True,
        liveness_probe_error: Exception | None = None,
    ) -> None:
        self._component_id = component_id
        self._is_alive = is_initially_alive
        self.restart_always_fails = restart_always_fails
        self.restart_revives = restart_revives
        self.liveness_probe_error = liveness_probe_error
        self.restart_call_count = 0

    @property
    def component_id(self) -> str:
        return self._component_id

    def is_alive(self) -> bool:
        if self.liveness_probe_error is not None:
            raise self.liveness_probe_error
        return self._is_alive

    def restart(self) -> None:
        self.restart_call_count += 1
        if self.restart_always_fails:
            raise RuntimeError(f"{self._component_id} cannot be restarted")
        if self.restart_revives:
            self._is_alive = True

    def kill(self) -> None:
        self._is_alive = False


def make_child(
    child_id: str,
    component: FakeSupervisedComponent | None = None,
    restart_type: ChildRestartType = ChildRestartType.PERMANENT,
    depends_on_child_ids: tuple[str, ...] = (),
) -> SupervisionChildSpecification:
    return SupervisionChildSpecification(
        child_id=child_id,
        supervised_component=component or FakeSupervisedComponent(child_id),
        restart_type=restart_type,
        depends_on_child_ids=depends_on_child_ids,
    )


# ===================================================================================================
# 1 · ACCEPTANCE BAR — the restart-intensity limiter (research/172 §5.5, research/170 §2.3)
# ===================================================================================================


def test_restart_intensity_limiter_trips_after_max_restarts_in_period_and_escalates() -> None:
    """MaxR restarts inside MaxT seconds -> the supervisor gives up on the child and escalates."""
    component = FakeSupervisedComponent("flapper", restart_revives=True)
    tree = ComponentSupervisionTree(
        [make_child("flapper", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=3, period_seconds=60.0),
        backoff_policy=CrashLoopBackOffPolicy(
            initial_backoff_seconds=0.001, maximum_backoff_seconds=0.001,
            reset_after_healthy_seconds=600.0,
        ),
    )

    escalations = []
    for pass_index in range(6):
        component.kill()
        report = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=pass_index))
        escalations.extend(report.escalations)

    assert component.restart_call_count == 3, "the limiter must cap restarts at MaxR"
    assert len(escalations) == 1, "the give-up escalates exactly once, then the child is left alone"
    escalation = escalations[0]
    assert escalation.child_id == "flapper"
    assert escalation.maximum_restarts == 3
    assert escalation.period_seconds == 60.0
    assert escalation.restarts_within_period >= 3
    assert "gives up" in escalation.reason
    assert tree.has_given_up_on_child("flapper")


def test_restart_intensity_window_slides_so_spread_out_restarts_never_trip() -> None:
    """The counter is a SLIDING window, not a lifetime total (erlang.org: MaxR *within* MaxT)."""
    component = FakeSupervisedComponent("slow_flapper")
    tree = ComponentSupervisionTree(
        [make_child("slow_flapper", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=2, period_seconds=30.0),
        backoff_policy=CrashLoopBackOffPolicy(
            initial_backoff_seconds=0.001, maximum_backoff_seconds=0.001,
            reset_after_healthy_seconds=1e9,
        ),
    )
    for pass_index in range(6):
        component.kill()
        report = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=60 * pass_index))
        assert not report.escalations

    assert component.restart_call_count == 6
    assert not tree.has_given_up_on_child("slow_flapper")


def test_restart_intensity_limiter_counts_per_child_not_globally() -> None:
    first, second = FakeSupervisedComponent("first"), FakeSupervisedComponent("second")
    limiter = RestartIntensityLimiter(RestartIntensityPolicy(maximum_restarts=2, period_seconds=10.0))
    limiter.record_restart(first.component_id, BASE_MOMENT)
    limiter.record_restart(first.component_id, BASE_MOMENT)
    assert limiter.would_exceed_intensity(first.component_id, BASE_MOMENT)
    assert not limiter.would_exceed_intensity(second.component_id, BASE_MOMENT)
    limiter.forget_child(first.component_id)
    assert not limiter.would_exceed_intensity(first.component_id, BASE_MOMENT)


def test_clearing_the_give_up_resumes_supervision() -> None:
    component = FakeSupervisedComponent("flapper")
    tree = ComponentSupervisionTree(
        [make_child("flapper", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=1, period_seconds=600.0),
        backoff_policy=CrashLoopBackOffPolicy(initial_backoff_seconds=0.001,
                                              maximum_backoff_seconds=0.001),
    )
    component.kill()
    tree.reconcile_supervised_children(BASE_MOMENT)
    component.kill()
    tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=1))
    assert tree.has_given_up_on_child("flapper")

    tree.clear_supervisor_give_up("flapper")
    assert not tree.has_given_up_on_child("flapper")
    component.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=2))
    assert report.restarted_child_ids == ("flapper",)


# ===================================================================================================
# 2 · ACCEPTANCE BAR — the Kubernetes CrashLoopBackOff schedule (research/170 §3.2)
# ===================================================================================================


def test_crash_loop_backoff_delays_follow_the_kubelet_schedule() -> None:
    """10 -> 20 -> 40 -> 80 -> 160 -> 300 (capped), and 0 before the first restart."""
    expected_schedule = [10.0, 20.0, 40.0, 80.0, 160.0, 300.0, 300.0, 300.0]
    assert crash_loop_backoff_delay_seconds(0) == 0.0
    for restarts_so_far, expected_delay in enumerate(expected_schedule, start=1):
        assert crash_loop_backoff_delay_seconds(restarts_so_far) == pytest.approx(expected_delay)
    assert INITIAL_CRASH_LOOP_BACKOFF_SECONDS == 10.0
    assert MAXIMUM_CRASH_LOOP_BACKOFF_SECONDS == 300.0
    assert CRASH_LOOP_BACKOFF_RESET_AFTER_HEALTHY_SECONDS == 600.0


def test_crash_loop_backoff_never_exceeds_the_cap_for_absurd_restart_counts() -> None:
    assert crash_loop_backoff_delay_seconds(500) == MAXIMUM_CRASH_LOOP_BACKOFF_SECONDS
    assert crash_loop_backoff_delay_seconds(-7) == 0.0


def test_backoff_defers_a_restart_until_the_delay_has_elapsed() -> None:
    component = FakeSupervisedComponent("backing_off")
    tree = ComponentSupervisionTree(
        [make_child("backing_off", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=100, period_seconds=1e6),
    )
    component.kill()
    first = tree.reconcile_supervised_children(BASE_MOMENT)
    assert first.restarted_child_ids == ("backing_off",)

    # 5 s later the 10 s backoff has not elapsed: the restart is DEFERRED, not attempted.
    component.kill()
    deferred = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=5))
    assert deferred.restart_outcomes == ()
    assert [child_id for child_id, _ in deferred.deferred_by_backoff] == ["backing_off"]
    assert component.restart_call_count == 1

    # 11 s in, it is due again.
    resumed = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=11))
    assert resumed.restarted_child_ids == ("backing_off",)
    assert component.restart_call_count == 2


def test_sustained_health_resets_the_crash_loop_backoff_to_the_floor() -> None:
    """kubelet's reset condition: 10 minutes clean -> the timer returns to the 10 s floor."""
    component = FakeSupervisedComponent("recovering")
    tree = ComponentSupervisionTree(
        [make_child("recovering", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=100, period_seconds=1e6),
    )
    for restart_index in range(3):
        component.kill()
        tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=1000 * restart_index))
    assert tree.child_supervision_status("recovering").consecutive_restart_count == 3

    healthy_start = BASE_MOMENT + timedelta(seconds=3000)
    tree.reconcile_supervised_children(healthy_start)
    tree.reconcile_supervised_children(healthy_start + timedelta(seconds=601))
    status = tree.child_supervision_status("recovering")
    assert status.consecutive_restart_count == 0
    assert status.last_observation is ChildLivenessObservation.ALIVE

    component.kill()
    report = tree.reconcile_supervised_children(healthy_start + timedelta(seconds=602))
    assert report.restarted_child_ids == ("recovering",), "reset means the next restart is immediate"


# ===================================================================================================
# 3 · OTP restart types (research/170 §2.2)
# ===================================================================================================


def test_permanent_child_is_always_restarted() -> None:
    component = FakeSupervisedComponent("permanent_child")
    tree = ComponentSupervisionTree([make_child("permanent_child", component)])
    component.kill()
    tree.mark_child_terminated_normally("permanent_child")  # irrelevant for PERMANENT
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.restarted_child_ids == ("permanent_child",)


def test_transient_child_is_restarted_only_on_abnormal_termination() -> None:
    component = FakeSupervisedComponent("transient_child")
    tree = ComponentSupervisionTree(
        [make_child("transient_child", component, restart_type=ChildRestartType.TRANSIENT)]
    )
    component.kill()
    tree.mark_child_terminated_normally("transient_child")
    normal = tree.reconcile_supervised_children(BASE_MOMENT)
    assert normal.dead_child_ids == ("transient_child",)
    assert normal.restart_outcomes == ()
    assert component.restart_call_count == 0

    tree.mark_child_terminated_abnormally("transient_child")
    abnormal = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=1))
    assert abnormal.restarted_child_ids == ("transient_child",)


def test_temporary_child_is_never_restarted_even_under_one_for_all() -> None:
    """erlang.org: temporary children are "never restarted (not even ... `one_for_all`)"."""
    first = FakeSupervisedComponent("first")
    temporary = FakeSupervisedComponent("temporary_child")
    last = FakeSupervisedComponent("last")
    tree = ComponentSupervisionTree(
        [
            # Mutual dependency forces ONE_FOR_ALL, whose blast radius covers every child.
            make_child("first", first, depends_on_child_ids=("last",)),
            make_child("temporary_child", temporary, restart_type=ChildRestartType.TEMPORARY),
            make_child("last", last, depends_on_child_ids=("first",)),
        ]
    )
    last.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.strategies_selected[0][1] is SupervisorRestartStrategy.ONE_FOR_ALL
    assert "temporary_child" not in report.restarted_child_ids
    assert temporary.restart_call_count == 0


# ===================================================================================================
# 4 · ACCEPTANCE BAR — blast radius selects the restart strategy (research/172 §3)
# ===================================================================================================


def test_blast_radius_selects_one_for_one_when_nothing_depends_on_the_dead_child() -> None:
    leaf = FakeSupervisedComponent("leaf")
    tree = ComponentSupervisionTree(
        [make_child("root"), make_child("leaf", leaf, depends_on_child_ids=("root",))]
    )
    leaf.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.strategies_selected == (("leaf", SupervisorRestartStrategy.ONE_FOR_ONE),)
    assert report.restarted_child_ids == ("leaf",)


def test_blast_radius_selects_rest_for_one_for_a_forward_dependency_chain() -> None:
    """A -> B -> C in start order: killing B taints the SUFFIX, which is exactly `rest_for_one`."""
    upstream = FakeSupervisedComponent("upstream")
    middle = FakeSupervisedComponent("middle")
    downstream = FakeSupervisedComponent("downstream")
    tree = ComponentSupervisionTree(
        [
            make_child("upstream", upstream),
            make_child("middle", middle, depends_on_child_ids=("upstream",)),
            make_child("downstream", downstream, depends_on_child_ids=("middle",)),
        ]
    )
    middle.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.strategies_selected == (("middle", SupervisorRestartStrategy.REST_FOR_ONE),)
    assert set(report.restarted_child_ids) == {"middle", "downstream"}
    assert upstream.restart_call_count == 0, "rest_for_one never touches children started earlier"


def test_blast_radius_selects_one_for_all_for_a_cyclic_dependency() -> None:
    """When a dependent starts BEFORE the failure, no suffix contains the damage -> `one_for_all`."""
    first = FakeSupervisedComponent("first")
    second = FakeSupervisedComponent("second")
    tree = ComponentSupervisionTree(
        [
            make_child("first", first, depends_on_child_ids=("second",)),
            make_child("second", second, depends_on_child_ids=("first",)),
        ]
    )
    second.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.strategies_selected == (("second", SupervisorRestartStrategy.ONE_FOR_ALL),)
    assert set(report.restarted_child_ids) == {"first", "second"}


def test_blast_radius_ceiling_withholds_restarts_beyond_the_per_pass_cap() -> None:
    """PodDisruptionBudget analogue (research/170 §3.4): the actuator must not become the stampede."""
    children = [FakeSupervisedComponent(f"child_{index}") for index in range(5)]
    tree = ComponentSupervisionTree(
        [
            make_child(
                component.component_id, component,
                depends_on_child_ids=(f"child_{index - 1}",) if index else (),
            )
            for index, component in enumerate(children)
        ],
        maximum_children_restarted_per_pass=2,
    )
    children[0].kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert len(report.restart_outcomes) == 2
    assert len(report.withheld_by_blast_radius_ceiling) == 3


def test_strategy_selection_rejects_an_unregistered_child() -> None:
    from nse_algo_trader.autopoiesis.component_supervision_tree import (
        select_restart_strategy_for_blast_radius,
    )

    with pytest.raises(SupervisionTreeConfigurationError):
        select_restart_strategy_for_blast_radius("ghost", ("a", "b"), {})


# ===================================================================================================
# 5 · Level-triggered reconciliation + the real registry
# ===================================================================================================


def test_reconciliation_is_level_triggered_and_needs_no_crash_event() -> None:
    """Nothing tells the supervisor the child died — it re-derives the whole truth every pass."""
    component = FakeSupervisedComponent("silent_death")
    tree = ComponentSupervisionTree([make_child("silent_death", component)])
    quiet = tree.reconcile_supervised_children(BASE_MOMENT)
    assert quiet.is_quiescent
    assert quiet.alive_child_ids == ("silent_death",)

    component.kill()  # no event, no exception, no notification
    acted = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=30))
    assert acted.dead_child_ids == ("silent_death",)
    assert acted.restarted_child_ids == ("silent_death",)
    assert "restarted" in acted.headline


def test_empty_supervision_tree_reconciles_without_error() -> None:
    report = ComponentSupervisionTree().reconcile_supervised_children(BASE_MOMENT)
    assert report.is_quiescent
    assert report.alive_child_ids == ()


def test_dependency_edges_are_derived_from_the_real_maintains_overlay() -> None:
    registry = build_default_component_registry()
    child_ids = ["thread.live_paper_loop", "store.market_data", "engine.autopoiesis_homeostat"]
    edges = derive_child_dependency_edges_from_registry(child_ids, registry)
    # `store.market_data` is declared maintained_by ("thread.live_paper_loop",) in the real registry.
    assert edges["store.market_data"] == ("thread.live_paper_loop",)
    # The homeostat's declared maintainers (operator.human / platform.systemd) are not supervised
    # children, so they drop out rather than becoming phantom edges.
    assert edges["engine.autopoiesis_homeostat"] == ()


def test_restart_type_is_derived_from_the_registry_declaration() -> None:
    registry = build_default_component_registry()
    live_loop = registry.find("thread.live_paper_loop")
    curiosity_engine = registry.find("engine.curiosity")
    assert live_loop is not None and curiosity_engine is not None
    assert restart_type_for_registered_component(live_loop) is ChildRestartType.PERMANENT
    assert restart_type_for_registered_component(curiosity_engine) is ChildRestartType.TRANSIENT
    ancillary = RegisteredComponent(
        "ancillary.thing", ComponentClass.BACKGROUND_THREAD, ComponentCriticality.ANCILLARY
    )
    assert restart_type_for_registered_component(ancillary) is ChildRestartType.TEMPORARY


def test_production_constructor_builds_the_tree_off_the_real_registry() -> None:
    components = [
        FakeSupervisedComponent("thread.live_paper_loop"),
        FakeSupervisedComponent("store.market_data"),
    ]
    tree = build_supervision_tree_for_registered_components(components)
    assert tree.supervised_child_ids() == ("thread.live_paper_loop", "store.market_data")
    market_data_specification = tree.child_specification("store.market_data")
    assert market_data_specification is not None
    assert market_data_specification.component_class is ComponentClass.PERSISTENT_STORE
    assert market_data_specification.depends_on_child_ids == ("thread.live_paper_loop",)

    components[0].kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.strategies_selected[0][1] is SupervisorRestartStrategy.REST_FOR_ONE


def test_unregistered_component_is_still_supervised_with_defaults() -> None:
    tree = build_supervision_tree_for_registered_components(
        [FakeSupervisedComponent("thread.not_in_registry")]
    )
    specification = tree.child_specification("thread.not_in_registry")
    assert specification is not None
    assert specification.restart_type is ChildRestartType.PERMANENT


def test_restarts_are_persisted_as_censored_survival_lifetime_events(tmp_path) -> None:
    store = AutopoiesisStateStore(tmp_path / "supervision.sqlite3")
    try:
        component = FakeSupervisedComponent("thread.news_acquisition")
        tree = ComponentSupervisionTree(
            [
                SupervisionChildSpecification(
                    child_id="thread.news_acquisition",
                    supervised_component=component,
                    component_class=ComponentClass.BACKGROUND_THREAD,
                )
            ],
            state_store=store,
        )
        component.kill()
        tree.reconcile_supervised_children(BASE_MOMENT)
        events = store.read_lifetime_events(ComponentClass.BACKGROUND_THREAD)
        assert len(events) == 1
        assert events[0].component_id == "thread.news_acquisition"
        assert events[0].observed_failure is True
        assert tree.state_store_write_failure_count == 0
    finally:
        store.close()


def test_state_store_write_failure_is_counted_not_swallowed(tmp_path) -> None:
    """Rule O.3: a broken ledger must be visible, and must not stop the supervisor from restarting."""
    store = AutopoiesisStateStore(tmp_path / "supervision.sqlite3")
    store.close()  # every subsequent write now raises sqlite3.ProgrammingError
    component = FakeSupervisedComponent("broken_ledger_child")
    tree = ComponentSupervisionTree([make_child("broken_ledger_child", component)], state_store=store)
    component.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.restarted_child_ids == ("broken_ledger_child",)
    assert tree.state_store_write_failure_count == 1


# ===================================================================================================
# 6 · Adversarial / degenerate (Rule O.4)
# ===================================================================================================


def test_child_that_always_fails_to_restart_is_counted_and_eventually_escalates() -> None:
    component = FakeSupervisedComponent(
        "unrestartable", is_initially_alive=False, restart_always_fails=True
    )
    tree = ComponentSupervisionTree(
        [make_child("unrestartable", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=2, period_seconds=600.0),
        backoff_policy=CrashLoopBackOffPolicy(initial_backoff_seconds=0.001,
                                              maximum_backoff_seconds=0.001),
    )
    escalations = []
    for pass_index in range(5):
        report = tree.reconcile_supervised_children(BASE_MOMENT + timedelta(seconds=pass_index))
        escalations.extend(report.escalations)

    status = tree.child_supervision_status("unrestartable")
    assert status.failed_restart_attempt_count == 2
    assert status.total_restart_count == 0, "a raising restart is never counted as a success"
    assert len(escalations) == 1
    assert tree.has_given_up_on_child("unrestartable")
    failed_details = [
        outcome.detail
        for outcome in tree.reconcile_supervised_children(
            BASE_MOMENT + timedelta(seconds=99)
        ).restart_outcomes
    ]
    assert failed_details == [], "a given-up child is left alone"


def test_liveness_probe_that_raises_yields_unknown_and_the_supervisor_holds() -> None:
    """research/170 §7 (Google SRE Diskerase): "cannot determine state" is a reason to HOLD."""
    component = FakeSupervisedComponent(
        "unprobeable", liveness_probe_error=OSError("procfs unreadable")
    )
    tree = ComponentSupervisionTree([make_child("unprobeable", component)])
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.unknown_child_ids == ("unprobeable",)
    assert report.restart_outcomes == ()
    assert component.restart_call_count == 0
    assert report.liveness_probe_failures[0][0] == "unprobeable"
    assert "OSError" in report.liveness_probe_failures[0][1]


def test_clock_running_backwards_is_clamped_forward_and_counted() -> None:
    component = FakeSupervisedComponent("time_traveller")
    tree = ComponentSupervisionTree([make_child("time_traveller", component)])
    tree.reconcile_supervised_children(BASE_MOMENT)
    rewound = tree.reconcile_supervised_children(BASE_MOMENT - timedelta(hours=6))
    assert rewound.observed_at == BASE_MOMENT
    assert tree.backwards_clock_reading_count == 1


def test_naive_datetime_is_rejected() -> None:
    tree = ComponentSupervisionTree([make_child("child")])
    with pytest.raises(SupervisionTreeConfigurationError):
        tree.reconcile_supervised_children(datetime(2026, 7, 27, 4, 30))  # noqa: DTZ001


def test_concurrent_reconcile_passes_do_not_double_restart() -> None:
    component = FakeSupervisedComponent("contended", restart_revives=True)
    tree = ComponentSupervisionTree(
        [make_child("contended", component)],
        backoff_policy=CrashLoopBackOffPolicy(initial_backoff_seconds=600.0,
                                              maximum_backoff_seconds=600.0),
    )
    component.kill()
    barrier = threading.Barrier(8)

    def reconcile_once() -> None:
        barrier.wait()
        tree.reconcile_supervised_children(BASE_MOMENT)

    workers = [threading.Thread(target=reconcile_once) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert component.restart_call_count == 1, "the 10-minute backoff must serialise the restarts"


def test_degenerate_child_specifications_are_rejected() -> None:
    with pytest.raises(SupervisionTreeConfigurationError):
        SupervisionChildSpecification("   ", FakeSupervisedComponent("x"))
    with pytest.raises(SupervisionTreeConfigurationError):
        SupervisionChildSpecification("a", FakeSupervisedComponent("a"), shutdown_grace_seconds=-1.0)
    with pytest.raises(SupervisionTreeConfigurationError):
        SupervisionChildSpecification(
            "a", FakeSupervisedComponent("a"), depends_on_child_ids=("a",)
        )
    with pytest.raises(SupervisionTreeConfigurationError):
        RestartIntensityPolicy(maximum_restarts=0)
    with pytest.raises(SupervisionTreeConfigurationError):
        RestartIntensityPolicy(period_seconds=0.0)
    with pytest.raises(SupervisionTreeConfigurationError):
        CrashLoopBackOffPolicy(initial_backoff_seconds=10.0, maximum_backoff_seconds=5.0)
    with pytest.raises(SupervisionTreeConfigurationError):
        ComponentSupervisionTree(maximum_children_restarted_per_pass=0)


def test_unknown_child_operations_raise_rather_than_no_op() -> None:
    tree = ComponentSupervisionTree([make_child("known")])
    with pytest.raises(SupervisionTreeConfigurationError):
        tree.child_supervision_status("ghost")
    with pytest.raises(SupervisionTreeConfigurationError):
        tree.mark_child_terminated_normally("ghost")
    outcome = tree.restart_child_now("ghost", BASE_MOMENT)
    assert not outcome.succeeded
    assert "unknown supervised child" in outcome.detail


def test_re_registering_a_child_keeps_its_restart_history() -> None:
    component = FakeSupervisedComponent("child")
    tree = ComponentSupervisionTree([make_child("child", component)])
    component.kill()
    tree.reconcile_supervised_children(BASE_MOMENT)
    assert tree.child_supervision_status("child").total_restart_count == 1
    tree.register_supervised_child(make_child("child", component,
                                              restart_type=ChildRestartType.TRANSIENT))
    assert tree.supervised_child_ids() == ("child",)
    assert tree.child_supervision_status("child").total_restart_count == 1
    assert tree.child_supervision_status("child").restart_type is ChildRestartType.TRANSIENT


def test_quarantined_child_is_not_restarted_until_the_give_up_is_cleared() -> None:
    component = FakeSupervisedComponent("quarantined")
    tree = ComponentSupervisionTree([make_child("quarantined", component)])
    tree.quarantine_child("quarantined", "swapped to a healthy sibling")
    component.kill()
    report = tree.reconcile_supervised_children(BASE_MOMENT)
    assert report.restart_outcomes == ()
    assert component.restart_call_count == 0
    assert tree.child_supervision_status("quarantined").give_up_reason == (
        "swapped to a healthy sibling"
    )


def test_manual_restart_honours_the_intensity_limiter() -> None:
    """An autonomous actuator must not be able to out-restart the supervisor's own ceiling."""
    component = FakeSupervisedComponent("manual")
    tree = ComponentSupervisionTree(
        [make_child("manual", component)],
        intensity_policy=RestartIntensityPolicy(maximum_restarts=1, period_seconds=600.0),
        backoff_policy=CrashLoopBackOffPolicy(initial_backoff_seconds=0.001,
                                              maximum_backoff_seconds=0.001),
    )
    assert tree.restart_child_now("manual", BASE_MOMENT).succeeded
    blocked = tree.restart_child_now("manual", BASE_MOMENT + timedelta(seconds=1))
    assert not blocked.succeeded
    assert "gave up" in blocked.detail


def test_registry_with_only_exogenous_members_produces_no_supervised_edges() -> None:
    registry = OrganismComponentRegistry(
        components=(
            RegisteredComponent(
                "external.thing", ComponentClass.EXTERNAL_SERVICE, ComponentCriticality.VITAL,
                membership=ComponentMembership.EXOGENOUS,
            ),
        )
    )
    assert derive_child_dependency_edges_from_registry(["external.thing"], registry) == {
        "external.thing": ()
    }
