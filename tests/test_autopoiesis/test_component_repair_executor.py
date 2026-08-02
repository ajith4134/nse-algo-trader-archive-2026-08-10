"""Tests for the repair executor (research/170 §4/§5/§7, research/172 §5.5 acceptance bars).

Four layers:

  1. **Acceptance bars (research/172 §5.5)** — the breaker traverses CLOSED → OPEN → HALF_OPEN →
     CLOSED under induced failures and its state SURVIVES a simulated process restart via the store;
     repair-budget exhaustion BLOCKS further repairs.
  2. **Safety, non-negotiable** — the corrigibility off-switch stops every action dead; a VITAL
     component with no fallback may not be quarantined; the constitutional referee can veto; the
     dry-run path never touches the organism.
  3. **The engineering primitives** — AWS decorrelated-jitter bounds, the Envoy retry-budget ceiling
     formula (20% / min 3), and the real supervision-tree actuator end to end.
  4. **Adversarial / degenerate (Rule O.4)** — an actuator that raises, a repair on an unknown or
     EXOGENOUS component, concurrent repair requests from many threads, a clock running backwards,
     and a broken ledger.

Every store lives under `tmp_path` — never `~/.nse_algo_trader/`.
"""

from __future__ import annotations

import random
import threading
import time
from datetime import UTC, datetime, timedelta

import pybreaker
import pytest

from nse_algo_trader.autopoiesis.autopoiesis_state_store import AutopoiesisStateStore
from nse_algo_trader.autopoiesis.component_repair_executor import (
    DECORRELATED_JITTER_GROWTH_FACTOR,
    DEFAULT_MINIMUM_RETRY_CONCURRENCY,
    DEFAULT_RETRY_BUDGET_PERCENT,
    INCIDENT_TYPE_AUTONOMOUS_COMPONENT_REPAIR,
    REFUSAL_BLANK_COMPONENT_ID,
    REFUSAL_CIRCUIT_BREAKER_OPEN,
    REFUSAL_CONSTITUTION_BLOCKED,
    REFUSAL_EXOGENOUS_COMPONENT,
    REFUSAL_OFF_SWITCH_ENGAGED,
    REFUSAL_QUARANTINE_WITHOUT_FALLBACK,
    REFUSAL_REPAIR_BUDGET_EXHAUSTED,
    REFUSAL_UNKNOWN_COMPONENT,
    CircuitBreakerPolicy,
    ComponentRepairExecutor,
    ComponentRepairFailedError,
    DecorrelatedJitterWait,
    EnvoyStyleRetryBudget,
    RepairBudgetPolicy,
    RepairExecutionConfigurationError,
    SupervisionTreeRepairActuator,
)
from nse_algo_trader.autopoiesis.component_supervision_tree import (
    ComponentSupervisionTree,
    SupervisionChildSpecification,
)
from nse_algo_trader.autopoiesis.maintenance_policy_solver import MaintenanceActionKind
from nse_algo_trader.conscience.constitutional_core import ProposedTradingAction
from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch

BASE_MOMENT = datetime(2026, 7, 27, 5, 15, tzinfo=UTC)

# Real ids from the production registry, chosen for their declared properties:
SUPPORTING_COMPONENT_ID = "store.news"                    # SUPPORTING, no fallback
VITAL_WITHOUT_FALLBACK_ID = "store.market_data"           # VITAL, fallback_component_id is None
VITAL_WITH_FALLBACK_ID = "session.kite"                   # VITAL, falls back to session.breeze
EXOGENOUS_COMPONENT_ID = "operator.human"                 # declared outside the boundary


class FakeRepairActuator:
    """Hermetic Rule-J actuation fake — lives only here; production uses SupervisionTreeRepairActuator."""

    def __init__(self, repair_should_fail: bool = False, raised_error: Exception | None = None) -> None:
        self.repair_should_fail = repair_should_fail
        self.raised_error = raised_error
        self.repair_call_count = 0
        self.replace_call_count = 0
        self.quarantine_call_count = 0
        self.quarantined_fallback_ids: list[str | None] = []

    def repair_component(self, component_id: str) -> str:
        self.repair_call_count += 1
        if self.raised_error is not None:
            raise self.raised_error
        if self.repair_should_fail:
            raise ComponentRepairFailedError(f"{component_id} could not be repaired")
        return f"repaired {component_id}"

    def replace_component(self, component_id: str) -> str:
        self.replace_call_count += 1
        if self.repair_should_fail:
            raise ComponentRepairFailedError(f"{component_id} could not be replaced")
        return f"replaced {component_id}"

    def quarantine_component(self, component_id: str, fallback_component_id: str | None) -> str:
        self.quarantine_call_count += 1
        self.quarantined_fallback_ids.append(fallback_component_id)
        return f"quarantined {component_id} -> {fallback_component_id}"

    @property
    def total_call_count(self) -> int:
        return self.repair_call_count + self.replace_call_count + self.quarantine_call_count


def build_executor(
    store: AutopoiesisStateStore,
    actuator: FakeRepairActuator | None = None,
    **overrides,
) -> tuple[ComponentRepairExecutor, FakeRepairActuator, CorrigibilitySwitch]:
    """A fast, deterministic executor: sub-millisecond jitter and a no-op sleep."""
    effective_actuator = actuator or FakeRepairActuator()
    switch = overrides.pop("corrigibility_switch", None) or CorrigibilitySwitch()
    settings = {
        "corrigibility_switch": switch,
        "budget_policy": RepairBudgetPolicy(maximum_actions_per_window=50),
        "maximum_repair_attempts": 2,
        "jitter_base_seconds": 0.001,
        "jitter_cap_seconds": 0.002,
        "random_source": random.Random(20260727),
        "retry_sleep": lambda _seconds: None,
    }
    settings.update(overrides)
    executor = ComponentRepairExecutor(store, effective_actuator, **settings)
    return executor, effective_actuator, switch


@pytest.fixture()
def state_store(tmp_path):
    store = AutopoiesisStateStore(tmp_path / "autopoiesis_repair.sqlite3")
    yield store
    store.close()


# ===================================================================================================
# 1 · Happy path + the forensic ledger
# ===================================================================================================


def test_successful_repair_is_executed_and_appended_to_the_forensic_ledger(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.was_executed and outcome.succeeded and not outcome.was_refused
    assert actuator.repair_call_count == 1
    assert outcome.attempt_count == 1
    assert executor.executed_action_count == 1

    ledger = state_store.read_repair_history(SUPPORTING_COMPONENT_ID)
    assert len(ledger) == 1
    assert ledger[0].action_kind == MaintenanceActionKind.REPAIR.value
    assert ledger[0].succeeded is True
    assert "repaired" in ledger[0].detail


def test_monitor_is_a_no_op_that_still_records(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.MONITOR, BASE_MOMENT
    )
    assert outcome.was_executed and outcome.succeeded
    assert actuator.total_call_count == 0, "MONITOR must never touch the organism"
    assert state_store.count_repairs_since(BASE_MOMENT - timedelta(hours=1)) == 1


def test_monitor_row_can_be_switched_off(state_store) -> None:
    executor, _, _ = build_executor(
        state_store,
        budget_policy=RepairBudgetPolicy(
            maximum_actions_per_window=50, records_monitor_observations=False
        ),
    )
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.MONITOR, BASE_MOMENT
    )
    assert state_store.count_repairs_since(BASE_MOMENT - timedelta(hours=1)) == 0


def test_failed_repair_is_counted_logged_and_recorded_never_swallowed(state_store) -> None:
    executor, actuator, _ = build_executor(
        state_store, FakeRepairActuator(repair_should_fail=True)
    )
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.was_executed and not outcome.succeeded
    assert executor.failed_action_count == 1
    assert actuator.repair_call_count == 2, "the failure is retried up to maximum_repair_attempts"
    assert "could not be repaired" in outcome.detail
    assert state_store.read_repair_history(SUPPORTING_COMPONENT_ID)[0].succeeded is False


def test_an_actuator_raising_an_unexpected_error_is_surfaced_not_swallowed(state_store) -> None:
    executor, _, _ = build_executor(
        state_store, FakeRepairActuator(raised_error=MemoryError("out of memory"))
    )
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.was_executed and not outcome.succeeded
    assert "MemoryError" in outcome.detail
    assert executor.failed_action_count == 1


# ===================================================================================================
# 2 · ACCEPTANCE BAR — the repair budget (research/172 §5.5)
# ===================================================================================================


def test_repair_budget_exhaustion_blocks_further_repairs(state_store) -> None:
    executor, actuator, _ = build_executor(
        state_store, budget_policy=RepairBudgetPolicy(maximum_actions_per_window=2)
    )
    for offset in range(2):
        assert executor.execute_maintenance_action(
            SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR,
            BASE_MOMENT + timedelta(seconds=offset),
        ).succeeded

    blocked = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=2)
    )
    assert blocked.was_refused
    assert blocked.refusal_reason == REFUSAL_REPAIR_BUDGET_EXHAUSTED
    assert not blocked.was_executed
    assert actuator.repair_call_count == 2, "no actuation happens past the budget"
    assert executor.refused_action_count == 1
    assert blocked.budget_status.is_exhausted
    assert blocked.budget_status.remaining_actions == 0


def test_budget_exhaustion_backoff_escalates_and_the_refusal_does_not_drain_the_ledger(
    state_store,
) -> None:
    executor, _, _ = build_executor(
        state_store,
        budget_policy=RepairBudgetPolicy(
            maximum_actions_per_window=1,
            exhaustion_backoff_seconds=10.0,
            exhaustion_backoff_multiplier=2.0,
        ),
    )
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    first_refusal = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert first_refusal.budget_status.blocked_until == BASE_MOMENT + timedelta(seconds=11)

    # Still inside the block: refused without even re-reading the meter.
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=5)
    )
    # Past the first block, still over budget -> the backoff DOUBLES to 20 s.
    second_refusal = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=12)
    )
    assert second_refusal.refusal_reason == REFUSAL_REPAIR_BUDGET_EXHAUSTED
    assert second_refusal.budget_status.blocked_until == BASE_MOMENT + timedelta(seconds=32)

    # Refusals must never themselves consume budget rows.
    assert state_store.count_repairs_since(BASE_MOMENT - timedelta(hours=1)) == 1


def test_budget_window_rolls_forward_so_old_repairs_stop_counting(state_store) -> None:
    executor, _, _ = build_executor(
        state_store, budget_policy=RepairBudgetPolicy(maximum_actions_per_window=1, window_hours=1.0)
    )
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    much_later = BASE_MOMENT + timedelta(hours=3)
    assert executor.current_repair_budget_status(much_later).actions_used == 0
    assert executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, much_later
    ).succeeded


def test_monitor_is_never_blocked_by_an_exhausted_budget(state_store) -> None:
    executor, _, _ = build_executor(
        state_store, budget_policy=RepairBudgetPolicy(maximum_actions_per_window=1)
    )
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    monitored = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.MONITOR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert monitored.was_executed and not monitored.was_refused


def test_an_unreadable_ledger_fails_safe_by_treating_the_budget_as_exhausted(tmp_path) -> None:
    store = AutopoiesisStateStore(tmp_path / "broken.sqlite3")
    store.close()
    executor, actuator, _ = build_executor(store)
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.was_refused
    assert outcome.refusal_reason == REFUSAL_REPAIR_BUDGET_EXHAUSTED
    assert actuator.total_call_count == 0


# ===================================================================================================
# 3 · ACCEPTANCE BAR — the circuit breaker (research/170 §4, research/172 §5.5)
# ===================================================================================================


def test_breaker_traverses_closed_open_half_open_closed_under_induced_failures(state_store) -> None:
    actuator = FakeRepairActuator(repair_should_fail=True)
    executor, _, _ = build_executor(
        state_store,
        actuator,
        breaker_policy=CircuitBreakerPolicy(
            consecutive_failure_maximum=2,
            reset_timeout_seconds=0.15,
            # 2 successful trials required, so HALF_OPEN is observable rather than transient.
            half_open_success_threshold=2,
        ),
        maximum_repair_attempts=2,
    )
    assert executor.breaker_state_for_component(SUPPORTING_COMPONENT_ID) == pybreaker.STATE_CLOSED

    tripped = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert tripped.breaker_state_after == pybreaker.STATE_OPEN
    assert "TRIPPED the breaker open" in tripped.detail

    # OPEN: short-circuits without invoking the actuator at all.
    calls_before = actuator.repair_call_count
    short_circuited = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert short_circuited.was_refused
    assert short_circuited.refusal_reason == REFUSAL_CIRCUIT_BREAKER_OPEN
    assert actuator.repair_call_count == calls_before

    # After the wait-in-open window, the next call is a HALF_OPEN trial.
    time.sleep(0.2)
    actuator.repair_should_fail = False
    trial = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=2)
    )
    assert trial.succeeded
    assert trial.breaker_state_after == pybreaker.STATE_HALF_OPEN

    closed = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=3)
    )
    assert closed.succeeded
    assert closed.breaker_state_after == pybreaker.STATE_CLOSED


def test_breaker_state_survives_a_simulated_process_restart(state_store) -> None:
    """A restart must NOT silently re-close the breaker and re-attack the failing dependency."""
    actuator = FakeRepairActuator(repair_should_fail=True)
    breaker_policy = CircuitBreakerPolicy(
        consecutive_failure_maximum=2, reset_timeout_seconds=600.0
    )
    first_executor, _, _ = build_executor(state_store, actuator, breaker_policy=breaker_policy)
    first_executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert state_store.read_breaker_state(SUPPORTING_COMPONENT_ID)[0] == pybreaker.STATE_OPEN

    # Simulated restart: a brand-new executor object over the SAME durable store.
    fresh_actuator = FakeRepairActuator()
    second_executor, _, _ = build_executor(
        state_store, fresh_actuator, breaker_policy=breaker_policy
    )
    assert second_executor.breaker_state_for_component(SUPPORTING_COMPONENT_ID) == (
        pybreaker.STATE_OPEN
    )
    refused = second_executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert refused.refusal_reason == REFUSAL_CIRCUIT_BREAKER_OPEN
    assert fresh_actuator.total_call_count == 0


def test_a_corrupt_persisted_breaker_state_degrades_to_closed_and_says_so(state_store) -> None:
    state_store.upsert_breaker_state(
        SUPPORTING_COMPONENT_ID, "totally-not-a-state", 99, BASE_MOMENT
    )
    executor, _, _ = build_executor(state_store)
    assert executor.breaker_state_for_component(SUPPORTING_COMPONENT_ID) == pybreaker.STATE_CLOSED


# ===================================================================================================
# 4 · SAFETY — the conscience pre-checks (non-negotiable)
# ===================================================================================================


@pytest.mark.parametrize(
    "action_kind",
    [
        MaintenanceActionKind.MONITOR,
        MaintenanceActionKind.REPAIR,
        MaintenanceActionKind.REPLACE,
        MaintenanceActionKind.QUARANTINE,
    ],
)
def test_engaged_off_switch_blocks_every_action_kind(state_store, action_kind) -> None:
    executor, actuator, switch = build_executor(state_store)
    switch.halt("operator pulled the off-switch")

    outcome = executor.execute_maintenance_action(
        VITAL_WITH_FALLBACK_ID, action_kind, BASE_MOMENT
    )
    assert outcome.was_refused
    assert outcome.refusal_reason == REFUSAL_OFF_SWITCH_ENGAGED
    assert not outcome.was_executed
    assert actuator.total_call_count == 0
    assert state_store.count_repairs_since(BASE_MOMENT - timedelta(hours=1)) == 0
    assert "operator pulled the off-switch" in outcome.detail


def test_resuming_the_off_switch_re_enables_autonomous_repair(state_store) -> None:
    executor, actuator, switch = build_executor(state_store)
    switch.halt("halted")
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    switch.resume()
    resumed = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert resumed.succeeded
    assert actuator.repair_call_count == 1


def test_constitutional_referee_can_veto_a_severity_escalated_action(state_store) -> None:
    """The referee reviews the trading footprint the repair would restore; a non-compliant one vetoes."""
    non_compliant_footprint = ProposedTradingAction(
        segment="mcx_commodity_futures",   # out of phase-1 scope -> hard article A7 violation
        is_overnight_carry=True,           # hard article A1 violation
    )
    executor, actuator, _ = build_executor(
        state_store,
        constitutional_referee=ConstitutionalReferee(),
        trading_footprint_under_repair=non_compliant_footprint,
    )
    outcome = executor.execute_maintenance_action(
        VITAL_WITH_FALLBACK_ID, MaintenanceActionKind.REPLACE, BASE_MOMENT
    )
    assert outcome.was_refused
    assert outcome.refusal_reason == REFUSAL_CONSTITUTION_BLOCKED
    assert actuator.total_call_count == 0
    assert executor.constitutional_referee.blocked_count == 1


def test_referee_review_is_reserved_for_severity_escalated_actions(state_store) -> None:
    """A cheap REPAIR of a SUPPORTING component is autonomous — no referee round-trip."""
    executor, _, _ = build_executor(
        state_store,
        constitutional_referee=ConstitutionalReferee(),
        trading_footprint_under_repair=ProposedTradingAction(segment="mcx_commodity_futures"),
    )
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.succeeded
    assert executor.constitutional_referee.orders_adjudicated == 0


def test_quarantine_of_a_vital_component_without_a_fallback_is_refused(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    outcome = executor.execute_maintenance_action(
        VITAL_WITHOUT_FALLBACK_ID, MaintenanceActionKind.QUARANTINE, BASE_MOMENT
    )
    assert outcome.was_refused
    assert outcome.refusal_reason == REFUSAL_QUARANTINE_WITHOUT_FALLBACK
    assert "VITAL" in outcome.detail and "fallback_component_id" in outcome.detail
    assert actuator.quarantine_call_count == 0


def test_quarantine_of_a_vital_component_with_a_declared_fallback_is_permitted(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    outcome = executor.execute_maintenance_action(
        VITAL_WITH_FALLBACK_ID, MaintenanceActionKind.QUARANTINE, BASE_MOMENT
    )
    assert outcome.succeeded
    assert actuator.quarantined_fallback_ids == ["session.breeze"]


def test_quarantine_of_a_non_vital_component_without_a_fallback_is_permitted(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.QUARANTINE, BASE_MOMENT
    )
    assert outcome.succeeded
    assert actuator.quarantined_fallback_ids == [None]


def test_critical_actions_produce_a_forensic_incident(state_store) -> None:
    recorded = []
    executor, _, _ = build_executor(state_store, incident_recorder=recorded.append)
    outcome = executor.execute_maintenance_action(
        VITAL_WITH_FALLBACK_ID, MaintenanceActionKind.QUARANTINE, BASE_MOMENT
    )
    assert outcome.forensic_incident is not None
    incident = outcome.forensic_incident
    assert incident.incident_type == INCIDENT_TYPE_AUTONOMOUS_COMPONENT_REPAIR
    assert incident.is_critical
    assert incident.subject == VITAL_WITH_FALLBACK_ID
    assert recorded == [incident]
    assert executor.recent_forensic_incidents() == (incident,)


def test_a_refused_action_on_a_vital_component_is_also_forensically_recorded(state_store) -> None:
    recorded = []
    executor, _, switch = build_executor(state_store, incident_recorder=recorded.append)
    switch.halt("halted for the audit")
    executor.execute_maintenance_action(
        VITAL_WITHOUT_FALLBACK_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert len(recorded) == 1
    assert "REFUSED" in recorded[0].detail
    assert recorded[0].is_critical


def test_a_failing_incident_recorder_does_not_lose_the_incident(state_store) -> None:
    def rejecting_recorder(_incident) -> bool:
        raise OSError("incident store unavailable")

    executor, _, _ = build_executor(state_store, incident_recorder=rejecting_recorder)
    outcome = executor.execute_maintenance_action(
        VITAL_WITH_FALLBACK_ID, MaintenanceActionKind.QUARANTINE, BASE_MOMENT
    )
    assert outcome.forensic_incident is not None
    assert len(executor.recent_forensic_incidents()) == 1


# ===================================================================================================
# 5 · SAFETY — dry run (research/170 §7 mechanism 3)
# ===================================================================================================


def test_dry_run_returns_the_plan_without_touching_the_organism(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    plan = executor.plan_maintenance_action(
        VITAL_WITH_FALLBACK_ID, MaintenanceActionKind.QUARANTINE, BASE_MOMENT
    )
    assert plan.plan_only
    assert not plan.was_executed and not plan.was_refused
    assert "WOULD EXECUTE" in plan.headline
    assert actuator.total_call_count == 0
    assert state_store.count_repairs_since(BASE_MOMENT - timedelta(hours=1)) == 0
    assert executor.executed_action_count == 0


def test_dry_run_reports_a_refusal_without_counting_or_escalating_it(state_store) -> None:
    executor, _, switch = build_executor(state_store)
    switch.halt("halted")
    plan = executor.plan_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert plan.plan_only and plan.was_refused
    assert plan.refusal_reason == REFUSAL_OFF_SWITCH_ENGAGED
    assert "WOULD REFUSE" in plan.headline
    assert executor.refused_action_count == 0, "a dry run must not move any counter"


def test_dry_run_does_not_escalate_the_budget_backoff(state_store) -> None:
    executor, _, _ = build_executor(
        state_store, budget_policy=RepairBudgetPolicy(maximum_actions_per_window=1)
    )
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    plan = executor.plan_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert plan.refusal_reason == REFUSAL_REPAIR_BUDGET_EXHAUSTED
    assert executor.current_repair_budget_status(
        BASE_MOMENT + timedelta(seconds=2)
    ).consecutive_exhaustion_count == 0


# ===================================================================================================
# 6 · Decorrelated jitter + the Envoy retry budget (research/170 §5.1 / §5.2)
# ===================================================================================================


def test_decorrelated_jitter_follows_the_aws_formula_and_respects_base_and_cap() -> None:
    wait_strategy = DecorrelatedJitterWait(
        base_seconds=1.0, cap_seconds=20.0, random_source=random.Random(7)
    )
    previous = 1.0
    for _ in range(50):
        sleep_seconds = wait_strategy(None)  # type: ignore[arg-type]
        upper_bound = min(20.0, max(1.0, previous * DECORRELATED_JITTER_GROWTH_FACTOR))
        assert 1.0 <= sleep_seconds <= upper_bound + 1e-9
        previous = sleep_seconds
    assert len(wait_strategy.sleep_history_seconds) == 50
    assert max(wait_strategy.sleep_history_seconds) <= 20.0

    wait_strategy.reset()
    assert wait_strategy.sleep_history_seconds == []


def test_decorrelated_jitter_rejects_degenerate_parameters() -> None:
    with pytest.raises(RepairExecutionConfigurationError):
        DecorrelatedJitterWait(base_seconds=0.0)
    with pytest.raises(RepairExecutionConfigurationError):
        DecorrelatedJitterWait(base_seconds=5.0, cap_seconds=1.0)
    with pytest.raises(RepairExecutionConfigurationError):
        DecorrelatedJitterWait(growth_factor=1.0)


def test_envoy_retry_budget_ceiling_uses_the_documented_defaults() -> None:
    budget = EnvoyStyleRetryBudget()
    assert budget.budget_percent == DEFAULT_RETRY_BUDGET_PERCENT == 0.20
    assert budget.minimum_retry_concurrency == DEFAULT_MINIMUM_RETRY_CONCURRENCY == 3
    # The minimum floor dominates in quiet periods...
    assert budget.permitted_retry_concurrency(0) == 3
    assert budget.permitted_retry_concurrency(10) == 3
    # ...and the percentage takes over once traffic justifies it.
    assert budget.permitted_retry_concurrency(100) == 20
    assert budget.permitted_retry_concurrency(41) == 9  # ceil(0.2 * 41)


def test_envoy_retry_budget_denies_retries_past_the_ceiling() -> None:
    budget = EnvoyStyleRetryBudget(budget_percent=0.5, minimum_retry_concurrency=1)
    assert budget.try_acquire_retry_permit()
    assert not budget.try_acquire_retry_permit()
    assert budget.denied_retry_count == 1
    budget.release_retry_permits(1)
    assert budget.try_acquire_retry_permit()


def test_retry_budget_exhaustion_stops_repair_retries(state_store) -> None:
    """A drained budget must curtail retries rather than let a repair storm build."""
    saturated_budget = EnvoyStyleRetryBudget(budget_percent=0.01, minimum_retry_concurrency=1)
    assert saturated_budget.try_acquire_retry_permit(), "drain the single available permit first"
    executor, actuator, _ = build_executor(
        state_store,
        FakeRepairActuator(repair_should_fail=True),
        retry_budget=saturated_budget,
        maximum_repair_attempts=5,
    )
    outcome = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert not outcome.succeeded
    assert actuator.repair_call_count == 1, "no retry may be attempted with an empty retry budget"
    assert saturated_budget.denied_retry_count >= 1


def test_envoy_retry_budget_rejects_degenerate_parameters() -> None:
    with pytest.raises(RepairExecutionConfigurationError):
        EnvoyStyleRetryBudget(budget_percent=0.0)
    with pytest.raises(RepairExecutionConfigurationError):
        EnvoyStyleRetryBudget(budget_percent=1.5)
    with pytest.raises(RepairExecutionConfigurationError):
        EnvoyStyleRetryBudget(minimum_retry_concurrency=-1)


# ===================================================================================================
# 7 · The real supervision-tree actuator (Rule G wiring, end to end)
# ===================================================================================================


class FakeSupervisedThread:
    def __init__(self, component_id: str, restart_always_fails: bool = False) -> None:
        self._component_id = component_id
        self._is_alive = False
        self.restart_always_fails = restart_always_fails
        self.restart_call_count = 0

    @property
    def component_id(self) -> str:
        return self._component_id

    def is_alive(self) -> bool:
        return self._is_alive

    def restart(self) -> None:
        self.restart_call_count += 1
        if self.restart_always_fails:
            raise RuntimeError("cannot restart")
        self._is_alive = True


def test_supervision_tree_actuator_repairs_replaces_and_quarantines(state_store) -> None:
    thread = FakeSupervisedThread("thread.news_acquisition")
    tree = ComponentSupervisionTree(
        [SupervisionChildSpecification("thread.news_acquisition", thread)]
    )
    quarantined: list[tuple[str, str | None]] = []
    actuator = SupervisionTreeRepairActuator(
        tree, quarantine_sink=lambda cid, fb: quarantined.append((cid, fb))
    )
    executor = ComponentRepairExecutor(
        state_store,
        actuator,
        corrigibility_switch=CorrigibilitySwitch(),
        budget_policy=RepairBudgetPolicy(maximum_actions_per_window=50),
        retry_sleep=lambda _seconds: None,
        jitter_base_seconds=0.001,
        jitter_cap_seconds=0.002,
    )

    repaired = executor.execute_maintenance_action(
        "thread.news_acquisition", MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert repaired.succeeded
    assert thread.restart_call_count == 1

    replaced = executor.execute_maintenance_action(
        "thread.news_acquisition", MaintenanceActionKind.REPLACE, BASE_MOMENT + timedelta(seconds=1)
    )
    assert replaced.succeeded
    assert "replaced" in replaced.detail
    assert thread.restart_call_count == 2, "REPLACE ignores the crash-loop backoff"

    quarantine = executor.execute_maintenance_action(
        "thread.news_acquisition", MaintenanceActionKind.QUARANTINE,
        BASE_MOMENT + timedelta(seconds=2),
    )
    assert quarantine.succeeded
    assert quarantined == [("thread.news_acquisition", None)]
    assert tree.has_given_up_on_child("thread.news_acquisition")


def test_supervision_tree_actuator_surfaces_a_failed_restart_as_a_failed_repair(
    state_store,
) -> None:
    thread = FakeSupervisedThread("thread.news_acquisition", restart_always_fails=True)
    tree = ComponentSupervisionTree(
        [SupervisionChildSpecification("thread.news_acquisition", thread)]
    )
    executor = ComponentRepairExecutor(
        state_store,
        SupervisionTreeRepairActuator(tree),
        corrigibility_switch=CorrigibilitySwitch(),
        budget_policy=RepairBudgetPolicy(maximum_actions_per_window=50),
        maximum_repair_attempts=1,
        retry_sleep=lambda _seconds: None,
    )
    outcome = executor.execute_maintenance_action(
        "thread.news_acquisition", MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.was_executed and not outcome.succeeded
    assert "cannot restart" in outcome.detail


# ===================================================================================================
# 8 · Adversarial / degenerate (Rule O.4)
# ===================================================================================================


def test_unknown_and_exogenous_components_are_refused(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    unknown = executor.execute_maintenance_action(
        "component.that.does.not.exist", MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert unknown.refusal_reason == REFUSAL_UNKNOWN_COMPONENT

    exogenous = executor.execute_maintenance_action(
        EXOGENOUS_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT + timedelta(seconds=1)
    )
    assert exogenous.refusal_reason == REFUSAL_EXOGENOUS_COMPONENT
    assert actuator.total_call_count == 0


def test_blank_component_id_is_refused(state_store) -> None:
    executor, _, _ = build_executor(state_store)
    outcome = executor.execute_maintenance_action(
        "   ", MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    assert outcome.refusal_reason == REFUSAL_BLANK_COMPONENT_ID


def test_naive_datetime_is_rejected(state_store) -> None:
    executor, _, _ = build_executor(state_store)
    with pytest.raises(RepairExecutionConfigurationError):
        executor.execute_maintenance_action(
            SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR,
            datetime(2026, 7, 27, 5, 15),  # noqa: DTZ001
        )


def test_clock_running_backwards_is_clamped_and_counted(state_store) -> None:
    executor, _, _ = build_executor(state_store)
    executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
    )
    rewound = executor.execute_maintenance_action(
        SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT - timedelta(hours=12)
    )
    assert rewound.decided_at == BASE_MOMENT
    assert executor.backwards_clock_reading_count == 1


class ThreadSafeRepairLedgerDouble:
    """A hermetic, thread-safe stand-in for the parts of `AutopoiesisStateStore` the executor uses.

    Why it exists (Rule J + a real limitation worth naming): `AutopoiesisStateStore` opens one
    `sqlite3` connection with the stdlib default `check_same_thread=True`, so the REAL store can only
    be touched from the thread that created it — see
    `test_real_state_store_is_single_threaded_by_construction` below, which pins that fact. This
    double keeps the concurrency assertion focused on the executor's OWN locking of the budget meter,
    breaker registry and counters, without pretending sqlite3 is something it is not.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.repair_rows: list = []
        self.breaker_rows: dict[str, tuple[str, int]] = {}

    def count_repairs_since(self, since: datetime) -> int:
        with self._lock:
            return sum(1 for row in self.repair_rows if row.attempted_at >= since)

    def record_repair_action(self, action) -> None:
        with self._lock:
            self.repair_rows.append(action)

    def read_breaker_state(self, component_id: str):
        with self._lock:
            return self.breaker_rows.get(component_id)

    def upsert_breaker_state(self, component_id, breaker_state, consecutive_failure_count, updated_at):
        with self._lock:
            self.breaker_rows[component_id] = (breaker_state, int(consecutive_failure_count))


def test_concurrent_repair_requests_stay_within_the_budget() -> None:
    """16 threads racing on the same component must not slip past a budget of 4."""
    ledger = ThreadSafeRepairLedgerDouble()
    actuator = FakeRepairActuator()
    executor = ComponentRepairExecutor(
        ledger,  # type: ignore[arg-type]  # hermetic Rule-J double over the store's used surface
        actuator,
        corrigibility_switch=CorrigibilitySwitch(),
        budget_policy=RepairBudgetPolicy(maximum_actions_per_window=4),
        retry_sleep=lambda _seconds: None,
        jitter_base_seconds=0.001,
        jitter_cap_seconds=0.002,
    )
    barrier = threading.Barrier(16)
    outcomes: list = []
    outcomes_lock = threading.Lock()

    def request_repair(index: int) -> None:
        barrier.wait()
        outcome = executor.execute_maintenance_action(
            SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR,
            BASE_MOMENT + timedelta(milliseconds=index),
        )
        with outcomes_lock:
            outcomes.append(outcome)

    workers = [threading.Thread(target=request_repair, args=(index,)) for index in range(16)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)

    executed = [outcome for outcome in outcomes if outcome.was_executed]
    refused = [outcome for outcome in outcomes if outcome.was_refused]
    assert len(outcomes) == 16
    assert len(executed) == 4, "the budget ceiling must hold under concurrency"
    assert actuator.repair_call_count == 4
    assert all(o.refusal_reason == REFUSAL_REPAIR_BUDGET_EXHAUSTED for o in refused)


def test_real_state_store_is_single_threaded_by_construction(state_store) -> None:
    """Pins the constraint the double above exists for: the executor must be driven from ONE thread.

    `AutopoiesisStateStore` holds a single `sqlite3` connection created with the stdlib default
    `check_same_thread=True`. Reading the budget meter from another thread therefore RAISES — and the
    executor's fail-safe turns that into a budget refusal rather than an unmetered repair, which is
    the behaviour this test locks in.
    """
    executor, actuator, _ = build_executor(state_store)
    outcomes: list = []

    def request_repair_from_another_thread() -> None:
        outcomes.append(
            executor.execute_maintenance_action(
                SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR, BASE_MOMENT
            )
        )

    worker = threading.Thread(target=request_repair_from_another_thread)
    worker.start()
    worker.join(timeout=10)

    assert outcomes[0].was_refused
    assert outcomes[0].refusal_reason == REFUSAL_REPAIR_BUDGET_EXHAUSTED
    assert actuator.total_call_count == 0, "an unmeasurable budget must never permit a repair"


def test_batch_execution_honours_the_blast_radius_ceiling(state_store) -> None:
    executor, actuator, _ = build_executor(state_store)
    requests = [
        (SUPPORTING_COMPONENT_ID, MaintenanceActionKind.REPAIR),
        ("store.council_track_record", MaintenanceActionKind.REPAIR),
        ("store.replay_curriculum", MaintenanceActionKind.REPAIR),
        ("store.debate_risk_observations", MaintenanceActionKind.REPAIR),
    ]
    outcomes = executor.execute_maintenance_actions(
        requests, BASE_MOMENT, maximum_components_acted_on=2
    )
    assert len(outcomes) == 2
    assert actuator.repair_call_count == 2


def test_batch_execution_rejects_a_degenerate_ceiling(state_store) -> None:
    executor, _, _ = build_executor(state_store)
    with pytest.raises(RepairExecutionConfigurationError):
        executor.execute_maintenance_actions([], BASE_MOMENT, maximum_components_acted_on=0)


def test_degenerate_policies_are_rejected() -> None:
    with pytest.raises(RepairExecutionConfigurationError):
        RepairBudgetPolicy(maximum_actions_per_window=0)
    with pytest.raises(RepairExecutionConfigurationError):
        RepairBudgetPolicy(window_hours=0.0)
    with pytest.raises(RepairExecutionConfigurationError):
        RepairBudgetPolicy(exhaustion_backoff_multiplier=0.5)
    with pytest.raises(RepairExecutionConfigurationError):
        CircuitBreakerPolicy(consecutive_failure_maximum=0)
    with pytest.raises(RepairExecutionConfigurationError):
        CircuitBreakerPolicy(reset_timeout_seconds=0.0)
    with pytest.raises(RepairExecutionConfigurationError):
        CircuitBreakerPolicy(half_open_success_threshold=0)


def test_executor_rejects_a_degenerate_attempt_maximum(state_store) -> None:
    with pytest.raises(RepairExecutionConfigurationError):
        ComponentRepairExecutor(
            state_store, FakeRepairActuator(), maximum_repair_attempts=0,
            corrigibility_switch=CorrigibilitySwitch(),
        )


def test_executor_without_a_supplied_off_switch_builds_a_private_one_and_warns(
    state_store, caplog
) -> None:
    """Rule O.3: the un-wired off-switch is a loud condition, never a silent default."""
    with caplog.at_level("WARNING"):
        executor = ComponentRepairExecutor(state_store, FakeRepairActuator())
    assert isinstance(executor.corrigibility_switch, CorrigibilitySwitch)
    assert any("WITHOUT the organism's corrigibility switch" in r.message for r in caplog.records)
