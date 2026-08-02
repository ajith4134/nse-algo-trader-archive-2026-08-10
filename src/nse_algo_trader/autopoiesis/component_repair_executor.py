"""Trunk X AUTOPOIESIS — the repair EXECUTOR: the organism's actuator hand.

Spec: research/172 §3 ("Reactive front line" row), §5.5 acceptance bars, §8 decomposition, §9 wiring.
Engineering source: research/170 §4 (resilience4j CLOSED→OPEN→HALF_OPEN, fetched primary),
§5.1 (AWS exponential-backoff-and-jitter formulas, fetched primary), §5.2 (Envoy `RetryBudget`
`budget_percent` 20% / `min_retry_concurrency` 3, fetched primary), §5.3 (idempotency is a
precondition), §7 (Google SRE — action budgets, blast-radius ceilings, dry-run, audit trail).

--------------------------------------------------------------------------------------------------
WHAT THIS IS
--------------------------------------------------------------------------------------------------
`maintenance_policy_solver` decides WHAT should happen to a component (MONITOR / REPAIR / REPLACE /
QUARANTINE, from a Bellman-solved control-limit policy). This module is the only thing in the package
that actually DOES it. The user's granted authority is explicit and narrow (research/172 §1 header):
**autonomous, budgeted, conscience-checked**. Each of those three words is a mechanism here:

  · **autonomous** — no human approval gate on the cheap, reversible actions; the executor acts.
  · **budgeted**   — a hard ceiling on repair actions per rolling hour, read from the append-only
                     ledger via `AutopoiesisStateStore.count_repairs_since`, with an ESCALATING
                     backoff once exhausted. Exhaustion BLOCKS; it never degrades into "try anyway".
  · **conscience-checked** — before every single action, the corrigibility off-switch is consulted
                     (`CorrigibilitySwitch.permits_trading()`); if it is engaged, NOTHING proceeds.
                     Severity-escalated actions additionally go past the `ConstitutionalReferee`.

Three further guardrails sit on top, all from research/170 §4/§5/§7:

  · a **pybreaker** circuit breaker per component (CLOSED → OPEN → HALF_OPEN), whose state is
    PERSISTED, so a process restart does not silently re-close every breaker and re-attack a
    dependency the organism had just isolated;
  · **tenacity** retries using AWS's **decorrelated jitter** — `sleep = min(cap, U(base, prev*3))`,
    transcribed verbatim from research/170 §5.1 — behind an **Envoy-style retry budget** so N
    independently-retrying components cannot collectively re-create the retry storm backoff exists
    to prevent;
  · **dry-run** (`plan_only=True`) that returns the full plan, including every pre-check verdict,
    without touching the organism (research/170 §7 mechanism 3).

--------------------------------------------------------------------------------------------------
THINGS THAT ARE DELIBERATE, NOT OVERSIGHTS
--------------------------------------------------------------------------------------------------
1. **A REFUSAL is not written to the repair ledger.** `count_repairs_since` counts every row in
   `component_repair_action`, so persisting refusals would let a jammed off-switch or an OPEN
   breaker silently drain the repair budget for the actions that ARE allowed. Refusals are instead
   counted (`refused_action_count`), logged at WARNING, returned in the outcome, and — for critical
   components — written as a forensic `SafetyIncident`. Nothing is swallowed (Rule O.3).
2. **MONITOR is recorded but never blocked.** The spec calls MONITOR "a no-op that still records";
   it is therefore a ledger row and it does consume a slot of the rolling meter, but it can never be
   REFUSED for budget reasons — a homeostat that cannot even observe itself is worse than one that
   observes too often. `RepairBudgetPolicy.records_monitor_observations=False` turns the row off for
   an orchestrator that runs MONITOR every cycle.
3. **QUARANTINE requires a fallback.** A VITAL component with no `fallback_component_id` may not be
   quarantined: doing so would remove organism function rather than protect it, which inverts the
   purpose of the lever. The refusal is reported with its reason, never silently downgraded.
4. **Retry is only ever applied to idempotent repair actions** (research/170 §5.3). Restarting a
   supervised child, rebuilding a cache and swapping to a fallback sibling are idempotent by
   construction; nothing in this module may be pointed at order placement or position mutation.

Rule G — consumers: `SupervisionTreeRepairActuator` (below) binds this executor to
`component_supervision_tree`, and the queued `autopoiesis_orchestrator` calls
`execute_maintenance_action` with the decision `maintenance_policy_solver.select_action_for_component`
returned. Rule N — `RepairExecutionOutcome` / `RepairBudgetStatus` are the dashboard surface's
"repairs today vs budget" metric.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

import pybreaker
from tenacity import RetryCallState, Retrying, stop_after_attempt
from tenacity.retry import retry_base
from tenacity.wait import wait_base

from nse_algo_trader.autopoiesis.autopoiesis_state_store import (
    AutopoiesisStateStore,
    PersistedRepairAction,
)
from nse_algo_trader.autopoiesis.component_registry import (
    ComponentCriticality,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.component_supervision_tree import ComponentSupervisionTree
from nse_algo_trader.autopoiesis.maintenance_policy_solver import MaintenanceActionKind

if TYPE_CHECKING:  # imported lazily at runtime — see `_load_conscience_organs` (no import cycle)
    from nse_algo_trader.conscience.constitutional_core import ProposedTradingAction
    from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
    from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
    from nse_algo_trader.conscience.incident_post_mortem import SafetyIncident

LOGGER = logging.getLogger(__name__)

# -- repair budget (research/170 §7 mechanism 1: OTP MaxR/MaxT generalised past process restart) ----
DEFAULT_REPAIR_BUDGET_MAXIMUM_ACTIONS_PER_WINDOW = 12
DEFAULT_REPAIR_BUDGET_WINDOW_HOURS = 1.0
DEFAULT_BUDGET_EXHAUSTION_BACKOFF_SECONDS = 300.0
DEFAULT_BUDGET_EXHAUSTION_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAXIMUM_BUDGET_EXHAUSTION_BACKOFF_SECONDS = 3600.0

# -- circuit breaker (research/170 §4.1/§4.2 — resilience4j semantics, pybreaker implementation) ----
# resilience4j ships slidingWindowSize=100 / minimumNumberOfCalls=100; those defaults suit a
# high-frequency RPC path. Repair actions are RARE (a handful per hour by the budget above), so a
# 100-call window would never fill and the breaker would never open. pybreaker's consecutive-failure
# counter is the correct shape for this call frequency; the threshold is set to 3 consecutive failed
# repairs, and the wait-in-open keeps resilience4j's 60 s default.
DEFAULT_BREAKER_CONSECUTIVE_FAILURE_MAXIMUM = 3
DEFAULT_BREAKER_RESET_TIMEOUT_SECONDS = 60.0
DEFAULT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD = 1

# -- retry with decorrelated jitter (research/170 §5.1, AWS Architecture Blog) ----------------------
DEFAULT_DECORRELATED_JITTER_BASE_SECONDS = 0.5
DEFAULT_DECORRELATED_JITTER_CAP_SECONDS = 20.0
DECORRELATED_JITTER_GROWTH_FACTOR = 3.0  # `sleep = min(cap, random_between(base, sleep_prev * 3))`
DEFAULT_REPAIR_ATTEMPT_MAXIMUM = 3

# -- retry budget (research/170 §5.2, Envoy `RetryBudget` proto defaults) ---------------------------
DEFAULT_RETRY_BUDGET_PERCENT = 0.20
DEFAULT_MINIMUM_RETRY_CONCURRENCY = 3

# -- forensic record -------------------------------------------------------------------------------
INCIDENT_TYPE_AUTONOMOUS_COMPONENT_REPAIR = "autonomous_component_repair"
CRITICAL_INCIDENT_SEVERITY = "critical"      # matches incident_post_mortem._CRITICAL_SEVERITIES
WARNING_INCIDENT_SEVERITY = "warning"
_FORENSIC_INCIDENTS_KEPT = 50

# -- refusal reasons (self-describing constants, never bare strings at call sites) ------------------
REFUSAL_OFF_SWITCH_ENGAGED = "off_switch_engaged"
REFUSAL_CONSTITUTION_BLOCKED = "constitution_blocked"
REFUSAL_REPAIR_BUDGET_EXHAUSTED = "repair_budget_exhausted"
REFUSAL_CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
REFUSAL_QUARANTINE_WITHOUT_FALLBACK = "quarantine_without_fallback"
REFUSAL_QUARANTINE_FALLBACK_UNKNOWN = "quarantine_fallback_not_in_registry"
REFUSAL_UNKNOWN_COMPONENT = "component_not_in_registry"
REFUSAL_EXOGENOUS_COMPONENT = "component_is_outside_the_organism_boundary"
REFUSAL_BLANK_COMPONENT_ID = "blank_component_id"


class RepairExecutionConfigurationError(ValueError):
    """A policy the executor cannot honour (Rule O.4 degenerate-input guard)."""


class ComponentRepairFailedError(RuntimeError):
    """The actuator tried and could not repair/replace/quarantine. Retryable; never swallowed."""


# ---------------------------------------------------------------------------------------------------
# The actuation seam
# ---------------------------------------------------------------------------------------------------


class ComponentRepairActuator(Protocol):
    """What "doing the repair" means, injected so the executor stays policy-only.

    Every method returns a human-readable detail for the forensic ledger and raises
    `ComponentRepairFailedError` (or any exception) when the action did not take effect. All three
    MUST be idempotent — research/170 §5.3 makes idempotency a precondition of auto-retry, not an
    optimisation.
    """

    def repair_component(self, component_id: str) -> str:
        """Restore the component in place (restart the child, refresh the session, rebuild a cache)."""

    def replace_component(self, component_id: str) -> str:
        """Discard the accumulated incarnation and stand a fresh one up from scratch."""

    def quarantine_component(self, component_id: str, fallback_component_id: str | None) -> str:
        """Take the component out of service and hand its consumers to `fallback_component_id`."""


class SupervisionTreeRepairActuator:
    """The PRODUCTION actuator: repair actions land on the OTP supervision tree (Rule G wiring).

    · REPAIR    -> `restart_child_now` (crash-loop backoff and the MaxR/MaxT limiter still apply, so
                   an autonomous actuator can never out-restart the supervisor's own ceiling).
    · REPLACE   -> clear the accumulated give-up/restart history, then restart ignoring the backoff:
                   a replacement is a fresh incarnation, not another retry of the old one.
    · QUARANTINE-> `quarantine_child`, plus a notification to `quarantine_sink` so the data path can
                   switch consumers to the declared fallback sibling.
    """

    def __init__(
        self,
        supervision_tree: ComponentSupervisionTree,
        quarantine_sink: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self._supervision_tree = supervision_tree
        self._quarantine_sink = quarantine_sink

    def repair_component(self, component_id: str) -> str:
        outcome = self._supervision_tree.restart_child_now(component_id)
        if not outcome.succeeded:
            raise ComponentRepairFailedError(outcome.detail)
        return outcome.detail

    def replace_component(self, component_id: str) -> str:
        self._supervision_tree.clear_supervisor_give_up(component_id)
        outcome = self._supervision_tree.restart_child_now(component_id, ignore_backoff=True)
        if not outcome.succeeded:
            raise ComponentRepairFailedError(outcome.detail)
        return f"replaced (history cleared): {outcome.detail}"

    def quarantine_component(self, component_id: str, fallback_component_id: str | None) -> str:
        reason = (
            f"quarantined by the homeostat; consumers fall back to {fallback_component_id}"
            if fallback_component_id
            else "quarantined by the homeostat (non-vital, no fallback needed)"
        )
        self._supervision_tree.quarantine_child(component_id, reason)
        if self._quarantine_sink is not None:
            self._quarantine_sink(component_id, fallback_component_id)
        return reason


# ---------------------------------------------------------------------------------------------------
# Retry: decorrelated jitter + an Envoy-style budget
# ---------------------------------------------------------------------------------------------------


class DecorrelatedJitterWait(wait_base):
    """AWS decorrelated jitter as a tenacity wait strategy (research/170 §5.1, verbatim formula).

        sleep = min(cap, random_between(base, sleep_prev * 3))

    Decorrelated jitter is the one AWS formula that needs the PREVIOUS sleep threaded through, which
    is why it is stateful and why one instance must be used for exactly one retry sequence — the
    executor builds a fresh instance per action. `random_source` exists so tests are deterministic
    without monkeypatching the global RNG.
    """

    def __init__(
        self,
        base_seconds: float = DEFAULT_DECORRELATED_JITTER_BASE_SECONDS,
        cap_seconds: float = DEFAULT_DECORRELATED_JITTER_CAP_SECONDS,
        growth_factor: float = DECORRELATED_JITTER_GROWTH_FACTOR,
        random_source: random.Random | None = None,
    ) -> None:
        if not base_seconds > 0.0:
            raise RepairExecutionConfigurationError(
                f"base_seconds must be > 0, got {base_seconds}"
            )
        if cap_seconds < base_seconds:
            raise RepairExecutionConfigurationError(
                f"cap_seconds must be >= base_seconds, got {cap_seconds} < {base_seconds}"
            )
        if growth_factor <= 1.0:
            raise RepairExecutionConfigurationError(
                f"growth_factor must be > 1, got {growth_factor}"
            )
        self.base_seconds = float(base_seconds)
        self.cap_seconds = float(cap_seconds)
        self.growth_factor = float(growth_factor)
        self._random_source = random_source or random.Random()
        self._previous_sleep_seconds = float(base_seconds)
        self.sleep_history_seconds: list[float] = []

    def reset(self) -> None:
        self._previous_sleep_seconds = self.base_seconds
        self.sleep_history_seconds.clear()

    def __call__(self, retry_state: RetryCallState) -> float:
        upper_bound = max(self.base_seconds, self._previous_sleep_seconds * self.growth_factor)
        sleep_seconds = min(
            self.cap_seconds, self._random_source.uniform(self.base_seconds, upper_bound)
        )
        self._previous_sleep_seconds = sleep_seconds
        self.sleep_history_seconds.append(sleep_seconds)
        return sleep_seconds


class EnvoyStyleRetryBudget:
    """Concurrent-retry ceiling, Envoy's `RetryBudget` (research/170 §5.2, primary-fetched defaults).

        permitted = max(min_retry_concurrency, ceil(budget_percent * active_action_count))

    `budget_percent` defaults to 20% and `min_retry_concurrency` to 3, exactly as the Envoy proto
    documents. The minimum matters: without it a quiet period rounds the percentage to zero and a
    lone failing component could never retry at all.
    """

    def __init__(
        self,
        budget_percent: float = DEFAULT_RETRY_BUDGET_PERCENT,
        minimum_retry_concurrency: int = DEFAULT_MINIMUM_RETRY_CONCURRENCY,
    ) -> None:
        if not 0.0 < budget_percent <= 1.0:
            raise RepairExecutionConfigurationError(
                f"budget_percent must be in (0, 1], got {budget_percent}"
            )
        if minimum_retry_concurrency < 0:
            raise RepairExecutionConfigurationError(
                f"minimum_retry_concurrency must be >= 0, got {minimum_retry_concurrency}"
            )
        self.budget_percent = float(budget_percent)
        self.minimum_retry_concurrency = int(minimum_retry_concurrency)
        self._active_retry_count = 0
        self._active_action_count = 0
        self._denied_retry_count = 0
        self._lock = threading.RLock()

    @property
    def active_retry_count(self) -> int:
        return self._active_retry_count

    @property
    def denied_retry_count(self) -> int:
        """Retries the budget refused — a repair-storm signal, surfaced rather than hidden."""
        return self._denied_retry_count

    def permitted_retry_concurrency(self, active_action_count: int) -> int:
        return max(
            self.minimum_retry_concurrency,
            int(math.ceil(self.budget_percent * max(0, active_action_count))),
        )

    def register_action_started(self) -> None:
        with self._lock:
            self._active_action_count += 1

    def register_action_finished(self) -> None:
        with self._lock:
            self._active_action_count = max(0, self._active_action_count - 1)

    def try_acquire_retry_permit(self) -> bool:
        with self._lock:
            ceiling = self.permitted_retry_concurrency(self._active_action_count)
            if self._active_retry_count >= ceiling:
                self._denied_retry_count += 1
                LOGGER.warning(
                    "retry budget denied a repair retry: %d concurrent retries already active, "
                    "ceiling %d (budget_percent=%.2f, min_retry_concurrency=%d)",
                    self._active_retry_count, ceiling, self.budget_percent,
                    self.minimum_retry_concurrency,
                )
                return False
            self._active_retry_count += 1
            return True

    def release_retry_permits(self, permit_count: int) -> None:
        if permit_count <= 0:
            return
        with self._lock:
            self._active_retry_count = max(0, self._active_retry_count - permit_count)


class _RetryPermittedByBudget(retry_base):
    """tenacity retry predicate: retry a failure only while the Envoy budget still has room."""

    def __init__(
        self,
        retry_budget: EnvoyStyleRetryBudget,
        permit_counter: list[int],
        non_retryable_exception_types: tuple[type[BaseException], ...],
    ) -> None:
        self._retry_budget = retry_budget
        self._permit_counter = permit_counter
        self._non_retryable_exception_types = non_retryable_exception_types

    def __call__(self, retry_state: RetryCallState) -> bool:
        outcome = retry_state.outcome
        if outcome is None or not outcome.failed:
            return False
        raised = outcome.exception()
        if raised is not None and isinstance(raised, self._non_retryable_exception_types):
            return False
        if not self._retry_budget.try_acquire_retry_permit():
            return False
        self._permit_counter[0] += 1
        return True


# ---------------------------------------------------------------------------------------------------
# Circuit breakers with PERSISTED state
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """pybreaker configuration per component (research/170 §4.1 state machine)."""

    consecutive_failure_maximum: int = DEFAULT_BREAKER_CONSECUTIVE_FAILURE_MAXIMUM
    reset_timeout_seconds: float = DEFAULT_BREAKER_RESET_TIMEOUT_SECONDS
    half_open_success_threshold: int = DEFAULT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD

    def __post_init__(self) -> None:
        if self.consecutive_failure_maximum < 1:
            raise RepairExecutionConfigurationError(
                f"consecutive_failure_maximum must be >= 1, got {self.consecutive_failure_maximum}"
            )
        if not self.reset_timeout_seconds > 0.0:
            raise RepairExecutionConfigurationError(
                f"reset_timeout_seconds must be > 0, got {self.reset_timeout_seconds}"
            )
        if self.half_open_success_threshold < 1:
            raise RepairExecutionConfigurationError(
                f"half_open_success_threshold must be >= 1, got {self.half_open_success_threshold}"
            )


class _BreakerStatePersistingListener(pybreaker.CircuitBreakerListener):
    """Writes every breaker transition through to the append-only store.

    Without this, a process restart re-closes every breaker from scratch and the organism immediately
    re-attacks the failing dependency it had just isolated (`autopoiesis_state_store` names this as
    one of the three reasons that store exists).
    """

    def __init__(self, component_id: str, registry: PersistentComponentBreakerRegistry) -> None:
        self._component_id = component_id
        self._registry = registry

    def state_change(
        self,
        cb: pybreaker.CircuitBreaker,
        old_state: pybreaker.CircuitBreakerState | None,
        new_state: pybreaker.CircuitBreakerState,
    ) -> None:
        # `new_state.name` — NOT `cb.current_state`. pybreaker's `open()` assigns the cached state
        # object before the storage string (`self.state = self._state_storage.state = STATE_OPEN`
        # assigns left-to-right), so at listener time `cb.current_state` still reports the OLD state.
        # Persisting that would durably record "closed" for a breaker that had just tripped open.
        self._registry.persist_breaker_state(
            self._component_id, cb, breaker_state=str(new_state.name)
        )

    def failure(self, cb: pybreaker.CircuitBreaker, exc: BaseException) -> None:
        self._registry.persist_breaker_state(self._component_id, cb)

    def success(self, cb: pybreaker.CircuitBreaker) -> None:
        self._registry.persist_breaker_state(self._component_id, cb)


class PersistentComponentBreakerRegistry:
    """One `pybreaker.CircuitBreaker` per component, rehydrated from and written back to the store."""

    def __init__(
        self,
        state_store: AutopoiesisStateStore,
        policy: CircuitBreakerPolicy | None = None,
    ) -> None:
        self._state_store = state_store
        self._policy = policy or CircuitBreakerPolicy()
        self._breakers: dict[str, pybreaker.CircuitBreaker] = {}
        self._lock = threading.RLock()
        self.persistence_failure_count = 0

    @property
    def policy(self) -> CircuitBreakerPolicy:
        return self._policy

    def breaker_for_component(self, component_id: str) -> pybreaker.CircuitBreaker:
        with self._lock:
            existing = self._breakers.get(component_id)
            if existing is not None:
                return existing
            breaker = self._build_rehydrated_breaker(component_id)
            self._breakers[component_id] = breaker
            return breaker

    def current_breaker_state(self, component_id: str) -> str:
        return str(self.breaker_for_component(component_id).current_state)

    def is_short_circuiting(self, component_id: str, now: datetime) -> bool:
        """True while the breaker is OPEN *and* its wait-in-open window has not yet elapsed.

        pybreaker moves OPEN → HALF_OPEN lazily inside the next call, so asking `current_state`
        alone would keep reporting "open" forever and the breaker could never be probed.
        """
        breaker = self.breaker_for_component(component_id)
        if breaker.current_state != pybreaker.STATE_OPEN:
            return False
        opened_at = breaker._state_storage.opened_at  # noqa: SLF001 — pybreaker exposes no public getter
        if opened_at is None:
            return False
        return now < opened_at + timedelta(seconds=self._policy.reset_timeout_seconds)

    def persist_breaker_state(
        self,
        component_id: str,
        breaker: pybreaker.CircuitBreaker,
        breaker_state: str | None = None,
    ) -> None:
        try:
            self._state_store.upsert_breaker_state(
                component_id=component_id,
                breaker_state=breaker_state or str(breaker.current_state),
                consecutive_failure_count=int(breaker.fail_counter),
                updated_at=datetime.now(UTC),
            )
        except Exception as store_error:  # noqa: BLE001 — counted + logged (Rule O.3)
            self.persistence_failure_count += 1
            LOGGER.exception(
                "failed to persist breaker state for %s (%s); a restart will lose this isolation. "
                "total persistence failures: %d",
                component_id, store_error, self.persistence_failure_count,
            )

    def _build_rehydrated_breaker(self, component_id: str) -> pybreaker.CircuitBreaker:
        persisted = None
        try:
            persisted = self._state_store.read_breaker_state(component_id)
        except Exception as store_error:  # noqa: BLE001 — degrade to CLOSED but SAY SO
            LOGGER.exception(
                "could not read the persisted breaker state for %s (%s) — starting CLOSED",
                component_id, store_error,
            )
        initial_state = pybreaker.STATE_CLOSED
        persisted_failure_count = 0
        if persisted is not None:
            initial_state, persisted_failure_count = persisted
            if initial_state not in (
                pybreaker.STATE_CLOSED, pybreaker.STATE_OPEN, pybreaker.STATE_HALF_OPEN
            ):
                LOGGER.warning(
                    "unrecognised persisted breaker state %r for %s — starting CLOSED",
                    initial_state, component_id,
                )
                initial_state = pybreaker.STATE_CLOSED
                persisted_failure_count = 0
        storage = pybreaker.CircuitMemoryStorage(initial_state)
        for _ in range(max(0, persisted_failure_count)):
            storage.increment_counter()
        if initial_state == pybreaker.STATE_OPEN:
            # Resume the wait-in-open window where the previous process left it, rather than
            # restarting the clock (which would extend every outage by a full reset timeout).
            storage.opened_at = datetime.now(UTC)
        breaker = pybreaker.CircuitBreaker(
            fail_max=self._policy.consecutive_failure_maximum,
            reset_timeout=self._policy.reset_timeout_seconds,
            success_threshold=self._policy.half_open_success_threshold,
            state_storage=storage,
            name=f"component_repair::{component_id}",
        )
        breaker.add_listener(_BreakerStatePersistingListener(component_id, self))
        return breaker


# ---------------------------------------------------------------------------------------------------
# Budget + result types
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairBudgetPolicy:
    """The self-imposed action-rate ceiling (research/170 §7 mechanism 1, Google SRE Diskerase fix)."""

    maximum_actions_per_window: int = DEFAULT_REPAIR_BUDGET_MAXIMUM_ACTIONS_PER_WINDOW
    window_hours: float = DEFAULT_REPAIR_BUDGET_WINDOW_HOURS
    exhaustion_backoff_seconds: float = DEFAULT_BUDGET_EXHAUSTION_BACKOFF_SECONDS
    exhaustion_backoff_multiplier: float = DEFAULT_BUDGET_EXHAUSTION_BACKOFF_MULTIPLIER
    maximum_exhaustion_backoff_seconds: float = DEFAULT_MAXIMUM_BUDGET_EXHAUSTION_BACKOFF_SECONDS
    records_monitor_observations: bool = True

    def __post_init__(self) -> None:
        if self.maximum_actions_per_window < 1:
            raise RepairExecutionConfigurationError(
                f"maximum_actions_per_window must be >= 1, got {self.maximum_actions_per_window}"
            )
        if not self.window_hours > 0.0:
            raise RepairExecutionConfigurationError(
                f"window_hours must be > 0, got {self.window_hours}"
            )
        if self.exhaustion_backoff_seconds < 0.0:
            raise RepairExecutionConfigurationError(
                f"exhaustion_backoff_seconds must be >= 0, got {self.exhaustion_backoff_seconds}"
            )
        if self.exhaustion_backoff_multiplier < 1.0:
            raise RepairExecutionConfigurationError(
                f"exhaustion_backoff_multiplier must be >= 1, got "
                f"{self.exhaustion_backoff_multiplier}"
            )
        if self.maximum_exhaustion_backoff_seconds < self.exhaustion_backoff_seconds:
            raise RepairExecutionConfigurationError(
                "maximum_exhaustion_backoff_seconds must be >= exhaustion_backoff_seconds"
            )


@dataclass(frozen=True)
class RepairBudgetStatus:
    """How much autonomous-action budget is left in the rolling window — a dashboard metric (Rule N)."""

    evaluated_at: datetime
    window_started_at: datetime
    actions_used: int
    maximum_actions: int
    is_exhausted: bool
    consecutive_exhaustion_count: int
    blocked_until: datetime | None

    @property
    def remaining_actions(self) -> int:
        return max(0, self.maximum_actions - self.actions_used)

    @property
    def is_blocked(self) -> bool:
        return self.blocked_until is not None and self.evaluated_at < self.blocked_until

    @property
    def headline(self) -> str:
        if self.is_blocked and self.blocked_until is not None:
            return (
                f"repair budget EXHAUSTED ({self.actions_used}/{self.maximum_actions}) — blocked "
                f"until {self.blocked_until.isoformat()}"
            )
        return f"repair budget {self.actions_used}/{self.maximum_actions} used in the rolling window"


@dataclass(frozen=True)
class RepairExecutionOutcome:
    """Everything that happened (or would have happened) for ONE maintenance decision."""

    component_id: str
    action_kind: MaintenanceActionKind
    decided_at: datetime
    plan_only: bool
    was_executed: bool
    succeeded: bool
    was_refused: bool
    refusal_reason: str
    detail: str
    attempt_count: int
    duration_seconds: float
    breaker_state_after: str
    budget_status: RepairBudgetStatus
    forensic_incident: SafetyIncident | None = None

    @property
    def headline(self) -> str:
        if self.plan_only:
            verb = "WOULD REFUSE" if self.was_refused else "WOULD EXECUTE"
        elif self.was_refused:
            verb = "REFUSED"
        else:
            verb = "EXECUTED (ok)" if self.succeeded else "EXECUTED (failed)"
        reason = f" [{self.refusal_reason}]" if self.refusal_reason else ""
        return f"{verb} {self.action_kind.value} on {self.component_id}{reason}: {self.detail}"


# ---------------------------------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------------------------------


class ComponentRepairExecutor:
    """Autonomous, budgeted, conscience-checked execution of `MaintenanceActionKind` decisions.

    Every public entry point is thread-safe: the reconcile cadence and an operator-triggered repair
    can arrive concurrently, and the budget meter, breaker registry and forensic ledger must all see
    a consistent ordering.
    """

    def __init__(
        self,
        state_store: AutopoiesisStateStore,
        repair_actuator: ComponentRepairActuator,
        *,
        registry: OrganismComponentRegistry | None = None,
        corrigibility_switch: CorrigibilitySwitch | None = None,
        constitutional_referee: ConstitutionalReferee | None = None,
        incident_recorder: Callable[[SafetyIncident], Any] | None = None,
        budget_policy: RepairBudgetPolicy | None = None,
        breaker_policy: CircuitBreakerPolicy | None = None,
        retry_budget: EnvoyStyleRetryBudget | None = None,
        maximum_repair_attempts: int = DEFAULT_REPAIR_ATTEMPT_MAXIMUM,
        jitter_base_seconds: float = DEFAULT_DECORRELATED_JITTER_BASE_SECONDS,
        jitter_cap_seconds: float = DEFAULT_DECORRELATED_JITTER_CAP_SECONDS,
        trading_footprint_under_repair: ProposedTradingAction | None = None,
        random_source: random.Random | None = None,
        retry_sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if maximum_repair_attempts < 1:
            raise RepairExecutionConfigurationError(
                f"maximum_repair_attempts must be >= 1, got {maximum_repair_attempts}"
            )
        self._state_store = state_store
        self._repair_actuator = repair_actuator
        self._registry = registry or build_default_component_registry()
        self._budget_policy = budget_policy or RepairBudgetPolicy()
        self._breaker_registry = PersistentComponentBreakerRegistry(state_store, breaker_policy)
        self._retry_budget = retry_budget or EnvoyStyleRetryBudget()
        self._maximum_repair_attempts = maximum_repair_attempts
        self._jitter_base_seconds = jitter_base_seconds
        self._jitter_cap_seconds = jitter_cap_seconds
        self._random_source = random_source or random.Random()
        self._retry_sleep = retry_sleep
        self._incident_recorder = incident_recorder
        self._recent_forensic_incidents: list[SafetyIncident] = []
        self._lock = threading.RLock()
        self._latest_decided_at: datetime | None = None
        self._backwards_clock_reading_count = 0
        self._consecutive_budget_exhaustion_count = 0
        self._budget_blocked_until: datetime | None = None
        self._ledger_write_failure_count = 0
        self.executed_action_count = 0
        self.failed_action_count = 0
        self.refused_action_count = 0

        switch, referee, footprint = _load_conscience_organs(
            corrigibility_switch, constitutional_referee, trading_footprint_under_repair
        )
        self._corrigibility_switch = switch
        self._constitutional_referee = referee
        self._trading_footprint_under_repair = footprint

    # -- introspection -----------------------------------------------------------------------------

    @property
    def corrigibility_switch(self) -> CorrigibilitySwitch:
        """The live off-switch this executor obeys. Exposed so the orchestrator can rebind the organism's."""
        return self._corrigibility_switch

    @property
    def constitutional_referee(self) -> ConstitutionalReferee:
        return self._constitutional_referee

    @property
    def breaker_registry(self) -> PersistentComponentBreakerRegistry:
        return self._breaker_registry

    @property
    def retry_budget(self) -> EnvoyStyleRetryBudget:
        return self._retry_budget

    @property
    def budget_policy(self) -> RepairBudgetPolicy:
        return self._budget_policy

    @property
    def backwards_clock_reading_count(self) -> int:
        return self._backwards_clock_reading_count

    @property
    def ledger_write_failure_count(self) -> int:
        """Forensic-ledger writes that failed — surfaced because a lost row is a lost audit trail."""
        return self._ledger_write_failure_count

    def breaker_state_for_component(self, component_id: str) -> str:
        return self._breaker_registry.current_breaker_state(component_id)

    def recent_forensic_incidents(self) -> tuple[SafetyIncident, ...]:
        with self._lock:
            return tuple(self._recent_forensic_incidents)

    # -- budget ------------------------------------------------------------------------------------

    def current_repair_budget_status(self, now: datetime | None = None) -> RepairBudgetStatus:
        """Read the rolling-window meter straight off the append-only ledger (never an in-memory guess)."""
        with self._lock:
            moment = self._guarded_now(now)
            return self._budget_status_unlocked(moment)

    def _budget_status_unlocked(self, now: datetime) -> RepairBudgetStatus:
        window_started_at = now - timedelta(hours=self._budget_policy.window_hours)
        try:
            actions_used = self._state_store.count_repairs_since(window_started_at)
        except Exception as store_error:  # noqa: BLE001 — fail SAFE: unreadable meter = exhausted
            LOGGER.exception(
                "could not read the repair ledger to meter the budget (%s) — treating the budget as "
                "EXHAUSTED, because an unmeasurable actuator must not act (research/170 §7)",
                store_error,
            )
            actions_used = self._budget_policy.maximum_actions_per_window
        return RepairBudgetStatus(
            evaluated_at=now,
            window_started_at=window_started_at,
            actions_used=actions_used,
            maximum_actions=self._budget_policy.maximum_actions_per_window,
            is_exhausted=actions_used >= self._budget_policy.maximum_actions_per_window,
            consecutive_exhaustion_count=self._consecutive_budget_exhaustion_count,
            blocked_until=self._budget_blocked_until,
        )

    def _budget_exhaustion_backoff_seconds(self, exhaustion_count: int) -> float:
        return min(
            self._budget_policy.maximum_exhaustion_backoff_seconds,
            self._budget_policy.exhaustion_backoff_seconds
            * (self._budget_policy.exhaustion_backoff_multiplier ** max(0, exhaustion_count - 1)),
        )

    def _projected_budget_block_expiry(self, now: datetime) -> datetime:
        """What the block WOULD be, for the dry-run path — computed without mutating any counter."""
        return now + timedelta(
            seconds=self._budget_exhaustion_backoff_seconds(
                self._consecutive_budget_exhaustion_count + 1
            )
        )

    def _escalate_budget_exhaustion_backoff(self, now: datetime) -> datetime:
        """Each successive exhaustion doubles the block, capped — an actuator that keeps hitting the
        ceiling backs further off rather than hammering the ceiling itself."""
        self._consecutive_budget_exhaustion_count += 1
        backoff_seconds = self._budget_exhaustion_backoff_seconds(
            self._consecutive_budget_exhaustion_count
        )
        self._budget_blocked_until = now + timedelta(seconds=backoff_seconds)
        LOGGER.error(
            "repair budget exhausted (%d consecutive) — blocking every repair action until %s",
            self._consecutive_budget_exhaustion_count, self._budget_blocked_until.isoformat(),
        )
        return self._budget_blocked_until

    # -- the one entry point -----------------------------------------------------------------------

    def plan_maintenance_action(
        self,
        component_id: str,
        action_kind: MaintenanceActionKind,
        now: datetime | None = None,
    ) -> RepairExecutionOutcome:
        """DRY RUN (research/170 §7 mechanism 3): every pre-check runs, nothing touches the organism."""
        return self.execute_maintenance_action(component_id, action_kind, now, plan_only=True)

    def execute_maintenance_action(
        self,
        component_id: str,
        action_kind: MaintenanceActionKind,
        now: datetime | None = None,
        plan_only: bool = False,
    ) -> RepairExecutionOutcome:
        """Run the full pre-check ladder, then (unless `plan_only`) actuate and record the action.

        Pre-check order is deliberate — cheapest and most absolute first:
          1. degenerate input (blank id) · 2. membership (unknown / exogenous) ·
          3. CONSCIENCE off-switch · 4. constitutional referee (severity-escalated actions) ·
          5. QUARANTINE fallback requirement · 6. repair budget · 7. circuit breaker.
        The off-switch sits above everything an operator can tune, because corrigibility is a VALUE:
        it must never be outranked by a budget or a breaker setting.
        """
        with self._lock:
            decided_at = self._guarded_now(now)
            component = self._registry.find(component_id)

            refusal = self._first_refusal_reason(
                component_id, component, action_kind, decided_at, plan_only
            )
            if refusal is not None:
                return self._refuse(
                    component_id, component, action_kind, decided_at, plan_only, *refusal
                )

            budget_status = self._budget_status_unlocked(decided_at)
            if plan_only:
                return RepairExecutionOutcome(
                    component_id=component_id,
                    action_kind=action_kind,
                    decided_at=decided_at,
                    plan_only=True,
                    was_executed=False,
                    succeeded=False,
                    was_refused=False,
                    refusal_reason="",
                    detail=(
                        f"dry run: every pre-check passed; {action_kind.value} on {component_id} "
                        f"would be executed now ({budget_status.headline})"
                    ),
                    attempt_count=0,
                    duration_seconds=0.0,
                    breaker_state_after=self._breaker_registry.current_breaker_state(component_id),
                    budget_status=budget_status,
                )
            return self._execute_and_record(
                component_id, component, action_kind, decided_at, budget_status
            )

    def execute_maintenance_actions(
        self,
        requested_actions: Sequence[tuple[str, MaintenanceActionKind]],
        now: datetime | None = None,
        plan_only: bool = False,
        maximum_components_acted_on: int | None = None,
    ) -> tuple[RepairExecutionOutcome, ...]:
        """Batch form with a PodDisruptionBudget-style ceiling (research/170 §3.4 / §7 mechanism 2).

        A shared root cause (disk full) marks many components unhealthy in the same cycle; without a
        ceiling the actuator itself becomes the stampede. Components beyond the ceiling are simply
        not attempted this pass — level-triggered reconciliation will re-derive them next pass.
        """
        ceiling = (
            maximum_components_acted_on
            if maximum_components_acted_on is not None
            else self._budget_policy.maximum_actions_per_window
        )
        if ceiling < 1:
            raise RepairExecutionConfigurationError(
                f"maximum_components_acted_on must be >= 1, got {ceiling}"
            )
        outcomes: list[RepairExecutionOutcome] = []
        acted_on = 0
        for component_id, action_kind in requested_actions:
            if acted_on >= ceiling and action_kind is not MaintenanceActionKind.MONITOR:
                LOGGER.warning(
                    "blast-radius ceiling reached (%d components acted on this pass) — %s on %s "
                    "withheld until the next reconcile pass", ceiling, action_kind.value, component_id,
                )
                continue
            outcome = self.execute_maintenance_action(component_id, action_kind, now, plan_only)
            outcomes.append(outcome)
            if outcome.was_executed and action_kind is not MaintenanceActionKind.MONITOR:
                acted_on += 1
        return tuple(outcomes)

    # -- pre-checks --------------------------------------------------------------------------------

    def _first_refusal_reason(
        self,
        component_id: str,
        component: RegisteredComponent | None,
        action_kind: MaintenanceActionKind,
        now: datetime,
        plan_only: bool = False,
    ) -> tuple[str, str] | None:
        """Return `(refusal_reason, detail)` for the FIRST failed pre-check, else None.

        `plan_only` makes the ladder side-effect-free: a dry run must not escalate the budget
        backoff, or merely ASKING what would happen would change what happens (research/170 §7).
        """
        if not component_id or not component_id.strip():
            return REFUSAL_BLANK_COMPONENT_ID, "a blank component id cannot be acted on"
        if component is None:
            return (
                REFUSAL_UNKNOWN_COMPONENT,
                f"{component_id!r} is not a registered member of the organism — the actuator refuses "
                "to act on anything outside its own self-model",
            )
        if not component.is_self:
            return (
                REFUSAL_EXOGENOUS_COMPONENT,
                f"{component_id} is declared EXOGENOUS (the broker API, the exchange, the human) — "
                "the organism cannot repair what is outside its boundary",
            )

        # --- 3. CONSCIENCE: the off-switch outranks everything ---------------------------------
        if not self._corrigibility_switch.permits_trading():
            return (
                REFUSAL_OFF_SWITCH_ENGAGED,
                "the corrigibility off-switch is ENGAGED"
                + (
                    f" ({self._corrigibility_switch.reason})"
                    if getattr(self._corrigibility_switch, "reason", "")
                    else ""
                )
                + " — no autonomous repair may proceed while the organism is halted",
            )

        # --- 4. CONSCIENCE: the constitutional referee, for severity-escalated actions ----------
        if self._action_requires_referee_review(component, action_kind) and (
            not self._constitutional_referee.adjudicate_order(
                self._trading_footprint_under_repair
            )
        ):
            return (
                REFUSAL_CONSTITUTION_BLOCKED,
                "the constitutional referee blocked the trading footprint this repair would "
                "restore — an autonomous action must not re-enable a non-compliant path",
            )

        # --- 5. QUARANTINE needs somewhere for the consumers to go -----------------------------
        if action_kind is MaintenanceActionKind.QUARANTINE:
            quarantine_refusal = self._quarantine_refusal_reason(component)
            if quarantine_refusal is not None:
                return quarantine_refusal

        # --- 6. the repair budget (MONITOR is exempt — see the module docstring) ---------------
        if action_kind is not MaintenanceActionKind.MONITOR:
            if self._budget_blocked_until is not None and now < self._budget_blocked_until:
                return (
                    REFUSAL_REPAIR_BUDGET_EXHAUSTED,
                    f"repair budget exhausted — blocked until "
                    f"{self._budget_blocked_until.isoformat()} "
                    f"(exhaustion #{self._consecutive_budget_exhaustion_count})",
                )
            budget_status = self._budget_status_unlocked(now)
            if budget_status.is_exhausted:
                blocked_until = (
                    self._projected_budget_block_expiry(now)
                    if plan_only
                    else self._escalate_budget_exhaustion_backoff(now)
                )
                return (
                    REFUSAL_REPAIR_BUDGET_EXHAUSTED,
                    f"repair budget exhausted: {budget_status.actions_used}/"
                    f"{budget_status.maximum_actions} actions in the last "
                    f"{self._budget_policy.window_hours:g}h — blocked until "
                    f"{blocked_until.isoformat()}",
                )

        # --- 7. the circuit breaker -------------------------------------------------------------
        if action_kind is not MaintenanceActionKind.MONITOR and (
            self._breaker_registry.is_short_circuiting(component_id, now)
        ):
            return (
                REFUSAL_CIRCUIT_BREAKER_OPEN,
                f"the circuit breaker for {component_id} is OPEN — repeated repairs failed, so the "
                "organism stops attacking it until the wait-in-open window elapses",
            )
        return None

    def _action_requires_referee_review(
        self, component: RegisteredComponent, action_kind: MaintenanceActionKind
    ) -> bool:
        """Referee review is reserved for actions that change what the organism can trade with.

        The Referee's real subject is a `ProposedTradingAction`, so the question asked of it is a
        real one: "is the trading footprint this repair would restore constitutionally permitted?"
        The default footprint is the phase-1 paper-trading configuration (compliant by construction);
        an orchestrator that passes the LIVE footprint gets a genuine veto out of this check.
        """
        if action_kind in (MaintenanceActionKind.REPLACE, MaintenanceActionKind.QUARANTINE):
            return True
        return (
            action_kind is MaintenanceActionKind.REPAIR
            and component.criticality is ComponentCriticality.VITAL
        )

    def _quarantine_refusal_reason(
        self, component: RegisteredComponent
    ) -> tuple[str, str] | None:
        fallback_id = component.fallback_component_id
        if fallback_id is None:
            if component.criticality is ComponentCriticality.VITAL:
                return (
                    REFUSAL_QUARANTINE_WITHOUT_FALLBACK,
                    f"{component.component_id} is VITAL and declares no fallback_component_id — "
                    "quarantining it would remove organism function rather than protect it",
                )
            return None
        if self._registry.find(fallback_id) is None:
            return (
                REFUSAL_QUARANTINE_FALLBACK_UNKNOWN,
                f"{component.component_id} declares fallback {fallback_id!r}, which is not a "
                "registered component — the consumers would have nowhere to go",
            )
        return None

    # -- execution ---------------------------------------------------------------------------------

    def _execute_and_record(
        self,
        component_id: str,
        component: RegisteredComponent | None,
        action_kind: MaintenanceActionKind,
        decided_at: datetime,
        budget_status: RepairBudgetStatus,
    ) -> RepairExecutionOutcome:
        if action_kind is MaintenanceActionKind.MONITOR:
            return self._record_monitor_observation(
                component_id, action_kind, decided_at, budget_status
            )

        started_at = time.monotonic()
        attempt_counter = [0]
        permit_counter = [0]
        actuator_was_invoked = [False]
        jitter_wait = DecorrelatedJitterWait(
            base_seconds=self._jitter_base_seconds,
            cap_seconds=self._jitter_cap_seconds,
            random_source=self._random_source,
        )
        breaker = self._breaker_registry.breaker_for_component(component_id)
        breaker_state_before = str(breaker.current_state)

        def invoke_actuator_through_breaker() -> str:
            attempt_counter[0] += 1

            def actuate() -> str:
                actuator_was_invoked[0] = True
                return self._dispatch_action(component_id, component, action_kind)

            # Breaker INSIDE, retry OUTSIDE (resilience4j's recommended composition, research/170
            # §4): every attempt is recorded by the breaker, so a genuinely dead component trips it
            # instead of being retried forever.
            return str(breaker.call(actuate))

        self._retry_budget.register_action_started()
        succeeded = False
        detail = ""
        refusal_reason = ""
        try:
            retrying = Retrying(
                sleep=self._retry_sleep,
                stop=stop_after_attempt(self._maximum_repair_attempts),
                wait=jitter_wait,
                retry=_RetryPermittedByBudget(
                    self._retry_budget, permit_counter, (pybreaker.CircuitBreakerError,)
                ),
                reraise=True,
            )
            detail = str(retrying(invoke_actuator_through_breaker))
            succeeded = True
        except pybreaker.CircuitBreakerError as breaker_error:
            if not actuator_was_invoked[0]:
                refusal_reason = REFUSAL_CIRCUIT_BREAKER_OPEN
                detail = f"short-circuited by the open breaker: {breaker_error}"
            elif breaker_state_before == pybreaker.STATE_HALF_OPEN:
                detail = (
                    f"the half-open trial repair failed and re-opened the breaker: {breaker_error}"
                )
            else:
                detail = (
                    f"the repair failed and TRIPPED the breaker open after "
                    f"{self._breaker_registry.policy.consecutive_failure_maximum} consecutive "
                    f"failures: {breaker_error}"
                )
        except Exception as action_error:  # noqa: BLE001 — counted, logged, surfaced (Rule O.3)
            detail = f"{type(action_error).__name__}: {action_error}"
            LOGGER.exception(
                "autonomous %s of %s failed after %d attempt(s)",
                action_kind.value, component_id, attempt_counter[0],
            )
        finally:
            self._retry_budget.release_retry_permits(permit_counter[0])
            self._retry_budget.register_action_finished()

        duration_seconds = max(0.0, time.monotonic() - started_at)
        # Explicit write-through after the action settles, so the durable state matches the final
        # breaker state even if a listener fired mid-transition.
        self._breaker_registry.persist_breaker_state(component_id, breaker)

        if refusal_reason:
            # The breaker short-circuited before the actuator ran: nothing happened to the organism,
            # so this is a REFUSAL and must not consume a ledger row (see the module docstring).
            return self._refuse(
                component_id, component, action_kind, decided_at, False, refusal_reason, detail
            )

        if succeeded:
            self.executed_action_count += 1
            self._consecutive_budget_exhaustion_count = 0
            self._budget_blocked_until = None
        else:
            self.failed_action_count += 1

        self._append_repair_ledger_row(
            component_id, action_kind, decided_at, succeeded, detail, duration_seconds
        )
        incident = self._record_forensic_incident_if_critical(
            component_id, component, action_kind, decided_at, succeeded, refused=False, detail=detail
        )
        outcome = RepairExecutionOutcome(
            component_id=component_id,
            action_kind=action_kind,
            decided_at=decided_at,
            plan_only=False,
            was_executed=True,
            succeeded=succeeded,
            was_refused=False,
            refusal_reason="",
            detail=detail,
            attempt_count=attempt_counter[0],
            duration_seconds=duration_seconds,
            breaker_state_after=self._breaker_registry.current_breaker_state(component_id),
            budget_status=replace(
                budget_status, actions_used=budget_status.actions_used + 1
            ),
            forensic_incident=incident,
        )
        LOGGER.info("repair executor: %s", outcome.headline)
        return outcome

    def _dispatch_action(
        self,
        component_id: str,
        component: RegisteredComponent | None,
        action_kind: MaintenanceActionKind,
    ) -> str:
        if action_kind is MaintenanceActionKind.REPAIR:
            return self._repair_actuator.repair_component(component_id)
        if action_kind is MaintenanceActionKind.REPLACE:
            return self._repair_actuator.replace_component(component_id)
        if action_kind is MaintenanceActionKind.QUARANTINE:
            fallback_id = component.fallback_component_id if component is not None else None
            return self._repair_actuator.quarantine_component(component_id, fallback_id)
        raise RepairExecutionConfigurationError(
            f"no actuation path for maintenance action {action_kind!r}"
        )

    def _record_monitor_observation(
        self,
        component_id: str,
        action_kind: MaintenanceActionKind,
        decided_at: datetime,
        budget_status: RepairBudgetStatus,
    ) -> RepairExecutionOutcome:
        """MONITOR does nothing to the organism but still leaves a row (spec §3 action set)."""
        detail = f"monitored {component_id} — no intervention taken"
        if self._budget_policy.records_monitor_observations:
            self._append_repair_ledger_row(
                component_id, action_kind, decided_at, True, detail, 0.0
            )
        self.executed_action_count += 1
        return RepairExecutionOutcome(
            component_id=component_id,
            action_kind=action_kind,
            decided_at=decided_at,
            plan_only=False,
            was_executed=True,
            succeeded=True,
            was_refused=False,
            refusal_reason="",
            detail=detail,
            attempt_count=0,
            duration_seconds=0.0,
            breaker_state_after=self._breaker_registry.current_breaker_state(component_id),
            budget_status=budget_status,
        )

    def _refuse(
        self,
        component_id: str,
        component: RegisteredComponent | None,
        action_kind: MaintenanceActionKind,
        decided_at: datetime,
        plan_only: bool,
        refusal_reason: str,
        detail: str,
    ) -> RepairExecutionOutcome:
        if not plan_only:
            self.refused_action_count += 1
            LOGGER.warning(
                "repair executor REFUSED %s on %s [%s]: %s",
                action_kind.value, component_id, refusal_reason, detail,
            )
        incident = (
            None
            if plan_only
            else self._record_forensic_incident_if_critical(
                component_id, component, action_kind, decided_at,
                succeeded=False, refused=True, detail=f"{refusal_reason}: {detail}",
            )
        )
        return RepairExecutionOutcome(
            component_id=component_id,
            action_kind=action_kind,
            decided_at=decided_at,
            plan_only=plan_only,
            was_executed=False,
            succeeded=False,
            was_refused=True,
            refusal_reason=refusal_reason,
            detail=detail,
            attempt_count=0,
            duration_seconds=0.0,
            breaker_state_after=self._breaker_registry.current_breaker_state(component_id)
            if component_id
            else pybreaker.STATE_CLOSED,
            budget_status=self._budget_status_unlocked(decided_at),
            forensic_incident=incident,
        )

    # -- persistence + forensics -------------------------------------------------------------------

    def _append_repair_ledger_row(
        self,
        component_id: str,
        action_kind: MaintenanceActionKind,
        attempted_at: datetime,
        succeeded: bool,
        detail: str,
        duration_seconds: float,
    ) -> None:
        try:
            self._state_store.record_repair_action(
                PersistedRepairAction(
                    component_id=component_id,
                    attempted_at=attempted_at,
                    action_kind=action_kind.value,
                    succeeded=succeeded,
                    detail=detail[:2000],
                    duration_seconds=duration_seconds,
                )
            )
        except Exception as store_error:  # noqa: BLE001 — counted + logged (Rule O.3)
            self._ledger_write_failure_count += 1
            LOGGER.exception(
                "failed to append the repair-ledger row for %s/%s (%s) — the budget meter and the "
                "audit trail are now both short one row; total ledger write failures: %d",
                component_id, action_kind.value, store_error, self._ledger_write_failure_count,
            )

    def _record_forensic_incident_if_critical(
        self,
        component_id: str,
        component: RegisteredComponent | None,
        action_kind: MaintenanceActionKind,
        occurred_at: datetime,
        succeeded: bool,
        refused: bool,
        detail: str,
    ) -> SafetyIncident | None:
        """Write a `SafetyIncident` for anything a human would want to find after the fact.

        Critical = an irreversible-ish lever (REPLACE/QUARANTINE), or anything that went wrong or was
        refused on a VITAL component. Ordinary successful repairs stay in the repair ledger only.
        """
        is_vital = component is not None and component.criticality is ComponentCriticality.VITAL
        is_escalated_lever = action_kind in (
            MaintenanceActionKind.REPLACE, MaintenanceActionKind.QUARANTINE
        )
        went_wrong = refused or not succeeded
        if not (is_escalated_lever or (is_vital and went_wrong)):
            return None

        from nse_algo_trader.conscience.incident_post_mortem import SafetyIncident

        severity = (
            CRITICAL_INCIDENT_SEVERITY
            if (is_vital and went_wrong) or action_kind is MaintenanceActionKind.QUARANTINE
            else WARNING_INCIDENT_SEVERITY
        )
        incident = SafetyIncident(
            incident_type=INCIDENT_TYPE_AUTONOMOUS_COMPONENT_REPAIR,
            severity=severity,
            occurred_at=occurred_at.isoformat(),
            subject=component_id,
            detail=(
                f"{'REFUSED' if refused else ('ok' if succeeded else 'FAILED')} "
                f"{action_kind.value}: {detail}"
            )[:2000],
            trace_id=(
                f"autopoiesis_repair::{component_id}::{action_kind.value}::"
                f"{occurred_at.isoformat()}"
            ),
        )
        self._recent_forensic_incidents.append(incident)
        del self._recent_forensic_incidents[:-_FORENSIC_INCIDENTS_KEPT]
        if self._incident_recorder is not None:
            try:
                self._incident_recorder(incident)
            except Exception as recorder_error:  # noqa: BLE001 — counted + logged (Rule O.3)
                LOGGER.exception(
                    "the forensic incident recorder rejected the repair incident for %s (%s) — the "
                    "incident is still held in memory and returned in the outcome",
                    component_id, recorder_error,
                )
        return incident

    # -- clock -------------------------------------------------------------------------------------

    def _guarded_now(self, now: datetime | None) -> datetime:
        """Timezone-aware UTC only, and never allowed to move backwards (Rule O.4/O.5).

        A backwards jump would widen the rolling budget window and silently hand the actuator free
        repairs, so the reading is clamped forward and COUNTED rather than trusted.
        """
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise RepairExecutionConfigurationError(
                f"naive datetime rejected — repair timestamps must be timezone-aware: {moment!r}"
            )
        moment = moment.astimezone(UTC)
        if self._latest_decided_at is not None and moment < self._latest_decided_at:
            self._backwards_clock_reading_count += 1
            LOGGER.warning(
                "repair-executor clock went backwards (%s < %s) — clamping forward, occurrence #%d",
                moment.isoformat(), self._latest_decided_at.isoformat(),
                self._backwards_clock_reading_count,
            )
            return self._latest_decided_at
        self._latest_decided_at = moment
        return moment


def _load_conscience_organs(
    corrigibility_switch: CorrigibilitySwitch | None,
    constitutional_referee: ConstitutionalReferee | None,
    trading_footprint_under_repair: ProposedTradingAction | None,
) -> tuple[CorrigibilitySwitch, ConstitutionalReferee, ProposedTradingAction]:
    """Resolve the conscience organs with LAZY imports (no hard `autopoiesis -> conscience` edge).

    When an organ is not supplied the executor builds a private one and says so loudly: a private
    off-switch is NOT wired to the operator's dashboard toggle, so an executor running with one is
    autonomous without being corrigible — exactly the condition the warning exists to make visible.
    """
    from nse_algo_trader.conscience.constitutional_core import ProposedTradingAction
    from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
    from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch

    if corrigibility_switch is None:
        LOGGER.warning(
            "ComponentRepairExecutor built WITHOUT the organism's corrigibility switch — using a "
            "private one. Autonomous repairs will not be stopped by the operator's off-switch until "
            "the orchestrator passes the live switch in."
        )
        corrigibility_switch = CorrigibilitySwitch()
    if constitutional_referee is None:
        constitutional_referee = ConstitutionalReferee()
    if trading_footprint_under_repair is None:
        # Phase-1 paper configuration: intraday, broker-routed, defined-risk, in-scope segment. It is
        # compliant by construction, so the default check passes; the value of the gate is that an
        # orchestrator passing the LIVE footprint gets a real veto.
        trading_footprint_under_repair = ProposedTradingAction(
            segment="nse_cash_equity",
            is_live=False,
            is_option=False,
            is_overnight_carry=False,
            option_risk_defined=True,
            is_atomic_multi_leg=True,
            routes_through_broker=True,
            has_algo_id=True,
        )
    return corrigibility_switch, constitutional_referee, trading_footprint_under_repair
