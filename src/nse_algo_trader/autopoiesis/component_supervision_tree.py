"""Trunk X AUTOPOIESIS — the OTP-style SUPERVISION TREE over the organism's living children.

Spec: research/172 §3 ("Supervision" row) + §5.5 acceptance bars + §8 decomposition.
Engineering source: research/170 §2 (Erlang/OTP supervisor semantics, fetched primary from
erlang.org), §3.2 (Kubernetes CrashLoopBackOff, from the kubelet source), §3.3 (level-triggered
reconciliation), §3.4 (PodDisruptionBudget blast-radius ceiling), §7 (safety of autonomous action).

--------------------------------------------------------------------------------------------------
WHAT THIS FIXES
--------------------------------------------------------------------------------------------------
research/170 §1 audited the real substrate: 6 daemon threads spawned ad hoc, `is_alive()` used at 3
sites purely as a re-entrancy guard, and **no restart counter anywhere** — so a permanently-crashing
thread would be silently re-spawned forever, and the three threads spawned without a guard have no
revival path at all. This module supplies the three things OTP gets for free from the BEAM VM and
Python does not (research/170 §2.5):

  1. an explicit **child registry** (`SupervisionChildSpecification`) instead of ad hoc
     `self._writer_thread = threading.Thread(...)` assignments;
  2. a **poll-based liveness watchdog** that actually respawns (`reconcile_supervised_children`),
     because Python threads do not "link" to a supervisor the way BEAM processes do;
  3. a **restart-intensity counter per child id** — the MaxR-in-MaxT ring buffer that makes the
     supervisor itself GIVE UP and escalate instead of crash-looping forever.

--------------------------------------------------------------------------------------------------
THE SEMANTICS COPIED, EXACTLY
--------------------------------------------------------------------------------------------------
**Restart types** (research/170 §2.2, quoting erlang.org):
  · `PERMANENT` — "always restarted".
  · `TRANSIENT` — "restarted only if it terminates abnormally"; a child that reports a normal
    completion (`mark_child_terminated_normally`) is left alone.
  · `TEMPORARY` — "never restarted (not even when the supervisor restart strategy is `rest_for_one`
    or `one_for_all`)". The parenthetical is load-bearing and is enforced in `_blast_radius_children`.

**Restart strategies** (research/170 §2.1), selected by BLAST RADIUS off the dependency graph rather
than declared per-supervisor, because the organism's dependency structure is data (the registry's
`maintained_by` overlay) and not a hand-set constant — see `select_restart_strategy_for_blast_radius`:
  · `ONE_FOR_ONE` — nothing depends on the dead child; restart only it.
  · `REST_FOR_ONE` — everything that depends on it starts AFTER it, so the failure taints a suffix of
    the start order: restart the dead child and every child after it.
  · `ONE_FOR_ALL` — a dependent starts BEFORE the dead child (mutual/cyclic dependency), so no
    suffix contains the damage: restart every child.

**Restart intensity** (research/170 §2.3 — "the single most important primitive"): erlang.org states
"if more than MaxR restarts occur within MaxT seconds, the supervisor terminates all the child
processes and then itself", defaulting to MaxR=1 / MaxT=5s. We keep the sliding-window shape exactly
and deliberately loosen the defaults to MaxR=3 / MaxT=60s (`DEFAULT_RESTART_INTENSITY_*`), because
OTP's 1-in-5 is tuned to exit-signal-driven supervision that reacts in microseconds while this
watchdog is POLL-driven at cadence granularity — a single reconcile pass could otherwise trip it. The
OTP defaults are kept as named constants so the difference is visible, not hidden. Our "terminate all
children and then itself" is deliberately softened to *give up on that child and escalate* (research/
170 §7: never kill the whole trading process over one flapping cadence).

**CrashLoopBackOff** (research/170 §3.2, kubelet source): a restarted child is not restarted again
until `min(300s, 10s * 2**(restarts_so_far - 1))` has elapsed — 10 → 20 → 40 → 80 → 160 → 300 → 300 —
and the counter resets to zero once the child has been continuously healthy for 10 minutes. The first
restart after a clean period is immediate, matching kubelet (backoff is for *repeated* crashes).

**Level-triggered, not edge-triggered** (research/170 §3.3): `reconcile_supervised_children` probes
EVERY registered child every pass and acts on the diff between desired ("this child should be alive")
and observed state. It is never called "because something crashed" — there is no crash event to miss,
no exception path to wire correctly at 37 call sites, and a supervisor that was itself down for ten
passes simply re-derives the whole truth on its next pass.

**Blast-radius ceiling** (research/170 §3.4, PodDisruptionBudget): at most
`maximum_children_restarted_per_pass` distinct children may be restarted in ONE pass, so a shared root
cause (disk full) tripping many children at once cannot turn the supervisor itself into a stampede.

--------------------------------------------------------------------------------------------------
DEPENDENCY-INJECTION SEAM (Rule J)
--------------------------------------------------------------------------------------------------
`SupervisedComponent` is a Protocol with `component_id` / `is_alive()` / `restart()`. Production
supplies real adapters over `threading.Thread` objects and cadence engines; the hermetic fake used to
drive restart-intensity trips and always-fails-to-restart paths lives ONLY under `tests/` and is never
selectable from production code.

Rule G — consumers: `component_repair_executor.SupervisionTreeRepairActuator` (built alongside this
module) actuates REPAIR/REPLACE/QUARANTINE decisions through this tree, and the queued
`autopoiesis_orchestrator` drives `reconcile_supervised_children` from the MAPE-K cycle.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Protocol

from nse_algo_trader.autopoiesis.autopoiesis_state_store import (
    AutopoiesisStateStore,
    PersistedLifetimeEvent,
)
from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    ComponentCriticality,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)

LOGGER = logging.getLogger(__name__)

# -- OTP restart intensity (research/170 §2.3) ------------------------------------------------------
# erlang.org's stock defaults, kept named so the deviation below is explicit rather than silent.
OTP_DEFAULT_RESTART_INTENSITY_MAX_RESTARTS = 1
OTP_DEFAULT_RESTART_INTENSITY_PERIOD_SECONDS = 5.0
# Ours: poll-driven supervision needs a window wider than one reconcile cadence.
DEFAULT_RESTART_INTENSITY_MAX_RESTARTS = 3
DEFAULT_RESTART_INTENSITY_PERIOD_SECONDS = 60.0

# -- Kubernetes CrashLoopBackOff (research/170 §3.2, kubelet `flowcontrol.NewBackOff`) ---------------
INITIAL_CRASH_LOOP_BACKOFF_SECONDS = 10.0
CRASH_LOOP_BACKOFF_MULTIPLIER = 2.0
MAXIMUM_CRASH_LOOP_BACKOFF_SECONDS = 300.0
CRASH_LOOP_BACKOFF_RESET_AFTER_HEALTHY_SECONDS = 600.0

# -- PodDisruptionBudget-style blast-radius ceiling (research/170 §3.4) -----------------------------
DEFAULT_MAXIMUM_CHILDREN_RESTARTED_PER_PASS = 3

_SECONDS_PER_HOUR = 3600.0


class SupervisionTreeConfigurationError(ValueError):
    """A child specification or supervisor policy that cannot be honoured (Rule O.4 degenerate input)."""


class ChildRestartType(str, Enum):
    """When a dead child is restarted (research/170 §2.2 — erlang.org child-spec `restart` field)."""

    PERMANENT = "permanent"    # always restarted
    TRANSIENT = "transient"    # restarted only on ABNORMAL termination
    TEMPORARY = "temporary"    # never restarted, not even under one_for_all / rest_for_one


class SupervisorRestartStrategy(str, Enum):
    """How far the restart spreads (research/170 §2.1)."""

    ONE_FOR_ONE = "one_for_one"
    ONE_FOR_ALL = "one_for_all"
    REST_FOR_ONE = "rest_for_one"


class ChildLivenessObservation(str, Enum):
    """The outcome of one level-triggered liveness probe.

    `UNKNOWN` exists because research/170 §7 (Google SRE's Diskerase post-mortem) is explicit that
    "no data / can't determine current state" must never be treated as licence to act: an
    `is_alive()` that RAISES yields UNKNOWN and the supervisor holds rather than restarting blind.
    """

    ALIVE = "alive"
    DEAD = "dead"
    UNKNOWN = "unknown"


class SupervisedComponent(Protocol):
    """The DI seam (Rule J). Production adapts real threads/engines onto it; the fake lives in tests."""

    @property
    def component_id(self) -> str:
        """Stable identity — must match the `component_registry` id when the child is registered."""

    def is_alive(self) -> bool:
        """True when the child is still doing its job. May raise; a raise is reported as UNKNOWN."""

    def restart(self) -> None:
        """Bring the child back. Raising means the restart FAILED (counted, logged, surfaced)."""


@dataclass(frozen=True)
class RestartIntensityPolicy:
    """OTP's `#{intensity => MaxR, period => MaxT}` supervisor flags (research/170 §2.3)."""

    maximum_restarts: int = DEFAULT_RESTART_INTENSITY_MAX_RESTARTS
    period_seconds: float = DEFAULT_RESTART_INTENSITY_PERIOD_SECONDS

    def __post_init__(self) -> None:
        if self.maximum_restarts < 1:
            raise SupervisionTreeConfigurationError(
                f"maximum_restarts must be >= 1, got {self.maximum_restarts}"
            )
        if not self.period_seconds > 0.0:
            raise SupervisionTreeConfigurationError(
                f"period_seconds must be > 0, got {self.period_seconds}"
            )


@dataclass(frozen=True)
class CrashLoopBackOffPolicy:
    """kubelet's CrashLoopBackOff schedule (research/170 §3.2), parameterised but defaulted to stock."""

    initial_backoff_seconds: float = INITIAL_CRASH_LOOP_BACKOFF_SECONDS
    backoff_multiplier: float = CRASH_LOOP_BACKOFF_MULTIPLIER
    maximum_backoff_seconds: float = MAXIMUM_CRASH_LOOP_BACKOFF_SECONDS
    reset_after_healthy_seconds: float = CRASH_LOOP_BACKOFF_RESET_AFTER_HEALTHY_SECONDS

    def __post_init__(self) -> None:
        if not self.initial_backoff_seconds > 0.0:
            raise SupervisionTreeConfigurationError(
                f"initial_backoff_seconds must be > 0, got {self.initial_backoff_seconds}"
            )
        if self.backoff_multiplier < 1.0:
            raise SupervisionTreeConfigurationError(
                f"backoff_multiplier must be >= 1, got {self.backoff_multiplier}"
            )
        if self.maximum_backoff_seconds < self.initial_backoff_seconds:
            raise SupervisionTreeConfigurationError(
                "maximum_backoff_seconds must be >= initial_backoff_seconds, got "
                f"{self.maximum_backoff_seconds} < {self.initial_backoff_seconds}"
            )
        if not self.reset_after_healthy_seconds > 0.0:
            raise SupervisionTreeConfigurationError(
                f"reset_after_healthy_seconds must be > 0, got {self.reset_after_healthy_seconds}"
            )


def crash_loop_backoff_delay_seconds(
    consecutive_restart_count: int, policy: CrashLoopBackOffPolicy | None = None
) -> float:
    """Delay owed BEFORE the next restart, given how many restarts have already happened in this loop.

    kubelet semantics (research/170 §3.2): the first restart after a clean period is immediate, then
    the delay doubles from 10 s and saturates at 300 s. So the delay owed after N restarts is
    `min(cap, 10 * 2**(N-1))` for N >= 1 and 0 for N <= 0, producing 10 / 20 / 40 / 80 / 160 / 300 /
    300 ... for N = 1, 2, 3, ...
    """
    effective_policy = policy or CrashLoopBackOffPolicy()
    if consecutive_restart_count <= 0:
        return 0.0
    unbounded_delay = effective_policy.initial_backoff_seconds * (
        effective_policy.backoff_multiplier ** (consecutive_restart_count - 1)
    )
    return float(min(effective_policy.maximum_backoff_seconds, unbounded_delay))


@dataclass(frozen=True)
class SupervisionChildSpecification:
    """One OTP child spec (research/170 §2.2), specialised to in-process children.

    `depends_on_child_ids` is what makes strategy selection data-driven: it is normally derived from
    the registry's curated `maintained_by` overlay via `derive_child_dependency_edges_from_registry`,
    never guessed from the Python import graph (`component_registry` explains why those differ).
    """

    child_id: str
    supervised_component: SupervisedComponent
    restart_type: ChildRestartType = ChildRestartType.PERMANENT
    component_class: ComponentClass = ComponentClass.BACKGROUND_THREAD
    shutdown_grace_seconds: float = 5.0
    depends_on_child_ids: tuple[str, ...] = ()
    role_description: str = ""

    def __post_init__(self) -> None:
        if not self.child_id or not self.child_id.strip():
            raise SupervisionTreeConfigurationError("child_id must be a non-blank identifier")
        if self.shutdown_grace_seconds < 0.0:
            raise SupervisionTreeConfigurationError(
                f"shutdown_grace_seconds must be >= 0, got {self.shutdown_grace_seconds}"
            )
        if self.child_id in self.depends_on_child_ids:
            raise SupervisionTreeConfigurationError(
                f"child {self.child_id!r} declares a dependency on itself"
            )


@dataclass(frozen=True)
class ChildRestartOutcome:
    """One restart attempt, whether or not it worked. A failure is DATA here, never a swallowed error."""

    child_id: str
    triggering_child_id: str
    restart_strategy: SupervisorRestartStrategy
    succeeded: bool
    detail: str
    consecutive_restart_count: int
    total_restart_count: int
    attempted_at: datetime


@dataclass(frozen=True)
class SupervisionEscalation:
    """The supervisor GIVING UP on a child — OTP's "terminate", softened to "escalate" (research/170 §7)."""

    child_id: str
    reason: str
    restarts_within_period: int
    maximum_restarts: int
    period_seconds: float
    escalated_at: datetime

    @property
    def headline(self) -> str:
        return (
            f"supervisor gave up on {self.child_id}: {self.restarts_within_period} restarts within "
            f"{self.period_seconds:.0f}s exceeds MaxR={self.maximum_restarts} — {self.reason}"
        )


@dataclass(frozen=True)
class ChildSupervisionStatus:
    """Per-child supervisory state, for the dashboard surface and the MAPE-K Analyze stage."""

    child_id: str
    restart_type: ChildRestartType
    last_observation: ChildLivenessObservation
    consecutive_restart_count: int
    total_restart_count: int
    failed_restart_attempt_count: int
    has_given_up: bool
    give_up_reason: str
    last_restart_at: datetime | None
    healthy_since: datetime | None
    next_restart_allowed_at: datetime | None


@dataclass(frozen=True)
class SupervisionReconciliationReport:
    """The result of ONE level-triggered pass — the diff observed and everything acted on."""

    observed_at: datetime
    alive_child_ids: tuple[str, ...] = ()
    dead_child_ids: tuple[str, ...] = ()
    unknown_child_ids: tuple[str, ...] = ()
    restart_outcomes: tuple[ChildRestartOutcome, ...] = ()
    escalations: tuple[SupervisionEscalation, ...] = ()
    deferred_by_backoff: tuple[tuple[str, float], ...] = ()
    withheld_by_blast_radius_ceiling: tuple[str, ...] = ()
    liveness_probe_failures: tuple[tuple[str, str], ...] = ()
    strategies_selected: tuple[tuple[str, SupervisorRestartStrategy], ...] = ()

    @property
    def restarted_child_ids(self) -> tuple[str, ...]:
        return tuple(outcome.child_id for outcome in self.restart_outcomes if outcome.succeeded)

    @property
    def failed_restart_child_ids(self) -> tuple[str, ...]:
        return tuple(outcome.child_id for outcome in self.restart_outcomes if not outcome.succeeded)

    @property
    def is_quiescent(self) -> bool:
        """Nothing needed doing: every child alive, nothing deferred, nothing escalated."""
        return not (
            self.dead_child_ids
            or self.restart_outcomes
            or self.escalations
            or self.deferred_by_backoff
            or self.unknown_child_ids
        )

    @property
    def headline(self) -> str:
        if self.is_quiescent:
            return f"{len(self.alive_child_ids)} supervised children alive — nothing to reconcile"
        return (
            f"{len(self.alive_child_ids)} alive · {len(self.dead_child_ids)} dead · "
            f"{len(self.restarted_child_ids)} restarted · {len(self.failed_restart_child_ids)} "
            f"restart-failures · {len(self.escalations)} escalated · "
            f"{len(self.deferred_by_backoff)} backing off"
        )


class RestartIntensityLimiter:
    """The MaxR-in-MaxT sliding ring buffer, per child id (research/170 §2.3 / §2.5 point 3).

    This is what stops a permanently-broken child being respawned forever. `would_exceed_intensity`
    is asked BEFORE each restart: once MaxR restarts already sit inside the window, the next one
    would be the (MaxR+1)-th — exactly erlang.org's "more than MaxR restarts within MaxT seconds" —
    so the supervisor escalates instead.
    """

    def __init__(self, policy: RestartIntensityPolicy | None = None) -> None:
        self._policy = policy or RestartIntensityPolicy()
        self._restart_timestamps: dict[str, deque[datetime]] = {}
        self._lock = threading.RLock()

    @property
    def policy(self) -> RestartIntensityPolicy:
        return self._policy

    def record_restart(self, child_id: str, restarted_at: datetime) -> None:
        with self._lock:
            timestamps = self._restart_timestamps.setdefault(child_id, deque())
            timestamps.append(restarted_at)
            self._evict_expired(timestamps, restarted_at)

    def restart_count_within_period(self, child_id: str, now: datetime) -> int:
        with self._lock:
            timestamps = self._restart_timestamps.get(child_id)
            if not timestamps:
                return 0
            self._evict_expired(timestamps, now)
            return len(timestamps)

    def would_exceed_intensity(self, child_id: str, now: datetime) -> bool:
        return self.restart_count_within_period(child_id, now) >= self._policy.maximum_restarts

    def forget_child(self, child_id: str) -> None:
        """Clear a child's restart history — used when a human clears an escalation (research/170 §7)."""
        with self._lock:
            self._restart_timestamps.pop(child_id, None)

    def _evict_expired(self, timestamps: deque[datetime], now: datetime) -> None:
        while timestamps and (now - timestamps[0]).total_seconds() > self._policy.period_seconds:
            timestamps.popleft()


def select_restart_strategy_for_blast_radius(
    failed_child_id: str,
    child_start_order: Sequence[str],
    dependency_edges: Mapping[str, Sequence[str]],
) -> tuple[SupervisorRestartStrategy, tuple[str, ...]]:
    """Pick the OTP strategy from the failed child's BLAST RADIUS (research/172 §3 supervision row).

    `dependency_edges[child] = (ids this child depends on, ...)`. The dependents of the failed child
    are computed transitively; the strategy then follows from where those dependents sit in start
    order:

      · no dependents                          -> ONE_FOR_ONE, blast radius = {failed}
      · all dependents start AFTER the failure  -> REST_FOR_ONE, blast radius = start-order suffix
      · some dependent starts BEFORE it         -> ONE_FOR_ALL, blast radius = every child

    The last case is the honest one: if A depends on C and C depends on A, no suffix of the start
    order contains the damage, which is precisely the situation OTP's `one_for_all` exists for.
    """
    ordered_children = tuple(child_start_order)
    if failed_child_id not in ordered_children:
        raise SupervisionTreeConfigurationError(
            f"{failed_child_id!r} is not in the supervised start order {ordered_children!r}"
        )
    dependents_of: dict[str, set[str]] = {child_id: set() for child_id in ordered_children}
    for child_id in ordered_children:
        for dependency_id in dependency_edges.get(child_id, ()):
            if dependency_id in dependents_of:
                dependents_of[dependency_id].add(child_id)

    transitive_dependents: set[str] = set()
    frontier = list(dependents_of.get(failed_child_id, set()))
    while frontier:
        dependent_id = frontier.pop()
        if dependent_id in transitive_dependents or dependent_id == failed_child_id:
            continue
        transitive_dependents.add(dependent_id)
        frontier.extend(dependents_of.get(dependent_id, set()))

    if not transitive_dependents:
        return SupervisorRestartStrategy.ONE_FOR_ONE, (failed_child_id,)

    failed_index = ordered_children.index(failed_child_id)
    if all(ordered_children.index(dependent) > failed_index for dependent in transitive_dependents):
        return SupervisorRestartStrategy.REST_FOR_ONE, ordered_children[failed_index:]
    return SupervisorRestartStrategy.ONE_FOR_ALL, ordered_children


def derive_child_dependency_edges_from_registry(
    child_ids: Sequence[str], registry: OrganismComponentRegistry | None = None
) -> dict[str, tuple[str, ...]]:
    """Read dependency edges off the curated `G_maintains` overlay, restricted to supervised children.

    `component_registry` declares `maintained_by` as "u is maintained by v", i.e. u DEPENDS ON v, so
    the edge direction carries over unchanged. Maintainers that are not themselves supervised children
    (the human operator, systemd, the exchange) drop out — they are outside this supervisor's reach.
    """
    effective_registry = registry or build_default_component_registry()
    supervised = set(child_ids)
    edges: dict[str, tuple[str, ...]] = {}
    for child_id in child_ids:
        component = effective_registry.find(child_id)
        if component is None:
            edges[child_id] = ()
            continue
        edges[child_id] = tuple(
            maintainer_id
            for maintainer_id in component.maintained_by
            if maintainer_id in supervised and maintainer_id != child_id
        )
    return edges


def restart_type_for_registered_component(component: RegisteredComponent) -> ChildRestartType:
    """Map a registry component onto an OTP restart type — declared policy, not inference.

    Long-lived threads and the organism's own maintainers are `PERMANENT` ("always restarted").
    Cadence engines are `TRANSIENT`: a cadence that completes its work and stops has terminated
    NORMALLY and must not be respawned, whereas one that dies mid-pass must be. Anything ancillary
    (observability only) is `TEMPORARY` — restarting it can never repay a restart-storm risk.
    """
    if component.criticality is ComponentCriticality.ANCILLARY:
        return ChildRestartType.TEMPORARY
    if component.component_class is ComponentClass.CADENCE_ENGINE:
        return ChildRestartType.TRANSIENT
    return ChildRestartType.PERMANENT


@dataclass
class _SupervisedChildRuntimeState:
    """Mutable per-child bookkeeping. Deliberately NOT frozen — this is the supervisor's carried state."""

    child_id: str
    last_observation: ChildLivenessObservation = ChildLivenessObservation.UNKNOWN
    consecutive_restart_count: int = 0
    total_restart_count: int = 0
    failed_restart_attempt_count: int = 0
    last_restart_at: datetime | None = None
    healthy_since: datetime | None = None
    last_observed_dead_at: datetime | None = None
    terminated_normally: bool = False
    has_given_up: bool = False
    give_up_reason: str = ""


class ComponentSupervisionTree:
    """A level-triggered OTP supervisor over `SupervisedComponent` children.

    Thread-safe: every public mutation holds one re-entrant lock, because the reconcile cadence, the
    repair executor and a human-triggered restart can all touch the same child concurrently.
    """

    def __init__(
        self,
        child_specifications: Iterable[SupervisionChildSpecification] = (),
        *,
        intensity_policy: RestartIntensityPolicy | None = None,
        backoff_policy: CrashLoopBackOffPolicy | None = None,
        maximum_children_restarted_per_pass: int = DEFAULT_MAXIMUM_CHILDREN_RESTARTED_PER_PASS,
        state_store: AutopoiesisStateStore | None = None,
    ) -> None:
        if maximum_children_restarted_per_pass < 1:
            raise SupervisionTreeConfigurationError(
                "maximum_children_restarted_per_pass must be >= 1, got "
                f"{maximum_children_restarted_per_pass}"
            )
        self._lock = threading.RLock()
        self._child_specifications: dict[str, SupervisionChildSpecification] = {}
        self._child_start_order: list[str] = []
        self._runtime_states: dict[str, _SupervisedChildRuntimeState] = {}
        self._intensity_limiter = RestartIntensityLimiter(intensity_policy)
        self._backoff_policy = backoff_policy or CrashLoopBackOffPolicy()
        self._maximum_children_restarted_per_pass = maximum_children_restarted_per_pass
        self._state_store = state_store
        self._latest_observed_at: datetime | None = None
        self._backwards_clock_reading_count = 0
        self._state_store_write_failure_count = 0
        for specification in child_specifications:
            self.register_supervised_child(specification)

    # -- registration ------------------------------------------------------------------------------

    def register_supervised_child(self, specification: SupervisionChildSpecification) -> None:
        """Add a child spec. Re-registering the same id replaces the spec but KEEPS its restart history."""
        with self._lock:
            if specification.child_id not in self._child_specifications:
                self._child_start_order.append(specification.child_id)
                self._runtime_states[specification.child_id] = _SupervisedChildRuntimeState(
                    child_id=specification.child_id
                )
            self._child_specifications[specification.child_id] = specification

    def supervised_child_ids(self) -> tuple[str, ...]:
        """Children in START ORDER — the order `rest_for_one` slices."""
        with self._lock:
            return tuple(self._child_start_order)

    def child_specification(self, child_id: str) -> SupervisionChildSpecification | None:
        with self._lock:
            return self._child_specifications.get(child_id)

    def dependency_edges(self) -> dict[str, tuple[str, ...]]:
        with self._lock:
            return {
                child_id: specification.depends_on_child_ids
                for child_id, specification in self._child_specifications.items()
            }

    @property
    def intensity_policy(self) -> RestartIntensityPolicy:
        return self._intensity_limiter.policy

    @property
    def backoff_policy(self) -> CrashLoopBackOffPolicy:
        return self._backoff_policy

    @property
    def backwards_clock_reading_count(self) -> int:
        """How often a caller handed us a timestamp older than the last one (surfaced, never hidden)."""
        return self._backwards_clock_reading_count

    @property
    def state_store_write_failure_count(self) -> int:
        """Ledger writes that failed. Non-zero means the survival model is missing observations."""
        return self._state_store_write_failure_count

    # -- child lifecycle signals -------------------------------------------------------------------

    def mark_child_terminated_normally(self, child_id: str) -> None:
        """Declare a NORMAL termination — the distinction `TRANSIENT` restart semantics turn on.

        erlang.org: a transient child is "restarted only if it terminates abnormally". Python threads
        carry no exit reason, so the child (or its owner) must say so explicitly; absent this call a
        dead transient child is assumed to have crashed, which is the fail-safe direction.
        """
        with self._lock:
            state = self._require_runtime_state(child_id)
            state.terminated_normally = True

    def mark_child_terminated_abnormally(self, child_id: str) -> None:
        """Undo a normal-termination declaration (the child was restarted / crashed since)."""
        with self._lock:
            state = self._require_runtime_state(child_id)
            state.terminated_normally = False

    def quarantine_child(self, child_id: str, reason: str) -> None:
        """Stop supervising a child without deleting it — the QUARANTINE lever's landing point.

        A quarantined child is never restarted by reconciliation until `clear_supervisor_give_up`.
        """
        with self._lock:
            state = self._require_runtime_state(child_id)
            state.has_given_up = True
            state.give_up_reason = reason or "quarantined"
        LOGGER.warning("supervision tree quarantined child %s: %s", child_id, reason)

    def clear_supervisor_give_up(self, child_id: str) -> None:
        """Human (or REPLACE action) clears an escalation: forget the restart history and resume."""
        with self._lock:
            state = self._require_runtime_state(child_id)
            state.has_given_up = False
            state.give_up_reason = ""
            state.consecutive_restart_count = 0
            state.terminated_normally = False
            self._intensity_limiter.forget_child(child_id)
        LOGGER.info("supervision give-up cleared for child %s — supervision resumed", child_id)

    def has_given_up_on_child(self, child_id: str) -> bool:
        with self._lock:
            return self._require_runtime_state(child_id).has_given_up

    def child_supervision_status(self, child_id: str) -> ChildSupervisionStatus:
        with self._lock:
            specification = self._child_specifications.get(child_id)
            if specification is None:
                raise SupervisionTreeConfigurationError(f"unknown supervised child {child_id!r}")
            state = self._require_runtime_state(child_id)
            return ChildSupervisionStatus(
                child_id=child_id,
                restart_type=specification.restart_type,
                last_observation=state.last_observation,
                consecutive_restart_count=state.consecutive_restart_count,
                total_restart_count=state.total_restart_count,
                failed_restart_attempt_count=state.failed_restart_attempt_count,
                has_given_up=state.has_given_up,
                give_up_reason=state.give_up_reason,
                last_restart_at=state.last_restart_at,
                healthy_since=state.healthy_since,
                next_restart_allowed_at=self._next_restart_allowed_at(state),
            )

    def all_child_supervision_statuses(self) -> tuple[ChildSupervisionStatus, ...]:
        with self._lock:
            return tuple(self.child_supervision_status(child_id) for child_id in self._child_start_order)

    # -- the level-triggered reconcile pass ---------------------------------------------------------

    def reconcile_supervised_children(
        self, observed_at: datetime | None = None
    ) -> SupervisionReconciliationReport:
        """ONE level-triggered pass: probe every child, diff against desired, act on the diff.

        Deliberately NOT edge-triggered (research/170 §3.3): nothing here reacts to a crash *event*.
        Every pass re-derives the whole truth, so a missed death, a supervisor that was itself down,
        or two deaths collapsed into one all self-heal on the next pass.
        """
        with self._lock:
            now = self._guarded_now(observed_at)
            if not self._child_start_order:
                return SupervisionReconciliationReport(observed_at=now)

            alive: list[str] = []
            dead: list[str] = []
            unknown: list[str] = []
            probe_failures: list[tuple[str, str]] = []

            # --- OBSERVE (the whole world, every pass) ------------------------------------------
            for child_id in self._child_start_order:
                observation, probe_error = self._probe_child_liveness(child_id)
                state = self._require_runtime_state(child_id)
                state.last_observation = observation
                if observation is ChildLivenessObservation.ALIVE:
                    alive.append(child_id)
                    self._register_healthy_observation(state, now)
                elif observation is ChildLivenessObservation.DEAD:
                    dead.append(child_id)
                    state.healthy_since = None
                    state.last_observed_dead_at = now
                else:
                    unknown.append(child_id)
                    probe_failures.append((child_id, probe_error))

            # --- ANALYZE + PLAN + EXECUTE (act only on the diff) --------------------------------
            outcomes: list[ChildRestartOutcome] = []
            escalations: list[SupervisionEscalation] = []
            deferred: list[tuple[str, float]] = []
            withheld: list[str] = []
            strategies: list[tuple[str, SupervisorRestartStrategy]] = []
            restarted_this_pass: set[str] = set()

            for triggering_child_id in dead:
                if not self._child_should_be_restarted(triggering_child_id):
                    continue
                strategy, blast_radius = select_restart_strategy_for_blast_radius(
                    triggering_child_id, self._child_start_order, self.dependency_edges()
                )
                strategies.append((triggering_child_id, strategy))
                for child_id in self._restartable_blast_radius(blast_radius, triggering_child_id):
                    if child_id in restarted_this_pass:
                        continue
                    if len(restarted_this_pass) >= self._maximum_children_restarted_per_pass:
                        # PodDisruptionBudget-style ceiling (research/170 §3.4): hold, do not stampede.
                        withheld.append(child_id)
                        continue
                    decision = self._restart_child_under_supervision(
                        child_id, triggering_child_id, strategy, now
                    )
                    if decision.escalation is not None:
                        escalations.append(decision.escalation)
                    if decision.backoff_seconds_remaining is not None:
                        deferred.append((child_id, decision.backoff_seconds_remaining))
                    if decision.outcome is not None:
                        outcomes.append(decision.outcome)
                        restarted_this_pass.add(child_id)

            report = SupervisionReconciliationReport(
                observed_at=now,
                alive_child_ids=tuple(alive),
                dead_child_ids=tuple(dead),
                unknown_child_ids=tuple(unknown),
                restart_outcomes=tuple(outcomes),
                escalations=tuple(escalations),
                deferred_by_backoff=tuple(deferred),
                withheld_by_blast_radius_ceiling=tuple(withheld),
                liveness_probe_failures=tuple(probe_failures),
                strategies_selected=tuple(strategies),
            )
            if not report.is_quiescent:
                LOGGER.info("supervision reconcile: %s", report.headline)
            return report

    def restart_child_now(
        self, child_id: str, now: datetime | None = None, *, ignore_backoff: bool = False
    ) -> ChildRestartOutcome:
        """Restart ONE child immediately, outside the reconcile cadence.

        This is the entry point the repair executor's REPAIR/REPLACE actuator uses. It still honours
        the intensity limiter (an autonomous actuator must not be able to out-restart the supervisor's
        own ceiling); `ignore_backoff` exists only for the REPLACE path, where the child is being
        rebuilt rather than retried, so the crash-loop delay does not apply.
        """
        with self._lock:
            moment = self._guarded_now(now)
            if child_id not in self._child_specifications:
                detail = f"unknown supervised child {child_id!r} — nothing to restart"
                LOGGER.warning("%s", detail)
                return ChildRestartOutcome(
                    child_id=child_id,
                    triggering_child_id=child_id,
                    restart_strategy=SupervisorRestartStrategy.ONE_FOR_ONE,
                    succeeded=False,
                    detail=detail,
                    consecutive_restart_count=0,
                    total_restart_count=0,
                    attempted_at=moment,
                )
            decision = self._restart_child_under_supervision(
                child_id,
                triggering_child_id=child_id,
                strategy=SupervisorRestartStrategy.ONE_FOR_ONE,
                now=moment,
                ignore_backoff=ignore_backoff,
            )
            if decision.outcome is not None:
                return decision.outcome
            state = self._require_runtime_state(child_id)
            if decision.escalation is not None:
                detail = decision.escalation.headline
            elif decision.backoff_seconds_remaining is not None:
                detail = (
                    f"crash-loop backoff: {decision.backoff_seconds_remaining:.1f}s remaining before "
                    f"{child_id} may be restarted again"
                )
            else:
                detail = decision.refusal_detail
            return ChildRestartOutcome(
                child_id=child_id,
                triggering_child_id=child_id,
                restart_strategy=SupervisorRestartStrategy.ONE_FOR_ONE,
                succeeded=False,
                detail=detail,
                consecutive_restart_count=state.consecutive_restart_count,
                total_restart_count=state.total_restart_count,
                attempted_at=moment,
            )

    # -- internals ---------------------------------------------------------------------------------

    @dataclass(frozen=True)
    class _RestartDecision:
        outcome: ChildRestartOutcome | None = None
        escalation: SupervisionEscalation | None = None
        backoff_seconds_remaining: float | None = None
        refusal_detail: str = ""

    def _require_runtime_state(self, child_id: str) -> _SupervisedChildRuntimeState:
        state = self._runtime_states.get(child_id)
        if state is None:
            raise SupervisionTreeConfigurationError(f"unknown supervised child {child_id!r}")
        return state

    def _guarded_now(self, observed_at: datetime | None) -> datetime:
        """Reject naive datetimes and refuse to let the clock run backwards (Rule O.4/O.5).

        A backwards jump (NTP step, a caller replaying a stale timestamp) would otherwise widen every
        sliding window and silently disarm the intensity limiter. We clamp forward and COUNT the
        event rather than trusting or discarding it silently.
        """
        moment = observed_at or datetime.now(UTC)
        if moment.tzinfo is None:
            raise SupervisionTreeConfigurationError(
                f"naive datetime rejected — supervision timestamps must be timezone-aware: {moment!r}"
            )
        moment = moment.astimezone(UTC)
        if self._latest_observed_at is not None and moment < self._latest_observed_at:
            self._backwards_clock_reading_count += 1
            LOGGER.warning(
                "supervision clock went backwards (%s < %s) — clamping forward, occurrence #%d",
                moment.isoformat(), self._latest_observed_at.isoformat(),
                self._backwards_clock_reading_count,
            )
            return self._latest_observed_at
        self._latest_observed_at = moment
        return moment

    def _probe_child_liveness(self, child_id: str) -> tuple[ChildLivenessObservation, str]:
        specification = self._child_specifications[child_id]
        try:
            is_alive = bool(specification.supervised_component.is_alive())
        except Exception as probe_error:  # noqa: BLE001 — surfaced as UNKNOWN, never swallowed
            LOGGER.exception("liveness probe for supervised child %s raised", child_id)
            return ChildLivenessObservation.UNKNOWN, f"{type(probe_error).__name__}: {probe_error}"
        return (
            ChildLivenessObservation.ALIVE if is_alive else ChildLivenessObservation.DEAD
        ), ""

    def _register_healthy_observation(
        self, state: _SupervisedChildRuntimeState, now: datetime
    ) -> None:
        """Sustained health resets the crash-loop backoff (research/170 §3.2 reset condition)."""
        if state.healthy_since is None:
            state.healthy_since = now
            return
        healthy_seconds = (now - state.healthy_since).total_seconds()
        if (
            state.consecutive_restart_count > 0
            and healthy_seconds >= self._backoff_policy.reset_after_healthy_seconds
        ):
            LOGGER.info(
                "child %s healthy for %.0fs — crash-loop backoff reset to the %ss floor",
                state.child_id, healthy_seconds, self._backoff_policy.initial_backoff_seconds,
            )
            state.consecutive_restart_count = 0
            self._intensity_limiter.forget_child(state.child_id)

    def _child_should_be_restarted(self, child_id: str) -> bool:
        specification = self._child_specifications[child_id]
        state = self._require_runtime_state(child_id)
        if state.has_given_up:
            return False
        if specification.restart_type is ChildRestartType.TEMPORARY:
            return False
        return not (
            specification.restart_type is ChildRestartType.TRANSIENT and state.terminated_normally
        )

    def _restartable_blast_radius(
        self, blast_radius: Sequence[str], triggering_child_id: str
    ) -> tuple[str, ...]:
        """Filter the blast radius by restart type.

        erlang.org, `temporary`: "never restarted (not even when the supervisor restart strategy is
        `rest_for_one` or `one_for_all`)" — that exclusion is enforced here, not left to the caller.
        """
        restartable: list[str] = []
        for child_id in blast_radius:
            specification = self._child_specifications.get(child_id)
            if specification is None:
                continue
            if specification.restart_type is ChildRestartType.TEMPORARY:
                continue
            state = self._require_runtime_state(child_id)
            if state.has_given_up:
                continue
            if (
                child_id != triggering_child_id
                and specification.restart_type is ChildRestartType.TRANSIENT
                and state.terminated_normally
            ):
                continue
            restartable.append(child_id)
        return tuple(restartable)

    def _next_restart_allowed_at(self, state: _SupervisedChildRuntimeState) -> datetime | None:
        if state.last_restart_at is None:
            return None
        delay_seconds = crash_loop_backoff_delay_seconds(
            state.consecutive_restart_count, self._backoff_policy
        )
        if delay_seconds <= 0.0:
            return state.last_restart_at
        return state.last_restart_at + timedelta(seconds=delay_seconds)

    def _restart_child_under_supervision(
        self,
        child_id: str,
        triggering_child_id: str,
        strategy: SupervisorRestartStrategy,
        now: datetime,
        *,
        ignore_backoff: bool = False,
    ) -> ComponentSupervisionTree._RestartDecision:
        specification = self._child_specifications.get(child_id)
        if specification is None:
            return ComponentSupervisionTree._RestartDecision(
                refusal_detail=f"unknown supervised child {child_id!r}"
            )
        state = self._require_runtime_state(child_id)
        if state.has_given_up:
            return ComponentSupervisionTree._RestartDecision(
                refusal_detail=f"supervisor has given up on {child_id}: {state.give_up_reason}"
            )
        if specification.restart_type is ChildRestartType.TEMPORARY:
            return ComponentSupervisionTree._RestartDecision(
                refusal_detail=f"{child_id} is TEMPORARY — never restarted (OTP child-spec semantics)"
            )

        # --- CrashLoopBackOff gate (research/170 §3.2) ------------------------------------------
        if not ignore_backoff:
            allowed_at = self._next_restart_allowed_at(state)
            if allowed_at is not None and now < allowed_at:
                return ComponentSupervisionTree._RestartDecision(
                    backoff_seconds_remaining=(allowed_at - now).total_seconds()
                )

        # --- Restart-intensity gate (research/170 §2.3) — the acceptance bar --------------------
        if self._intensity_limiter.would_exceed_intensity(child_id, now):
            policy = self._intensity_limiter.policy
            escalation = SupervisionEscalation(
                child_id=child_id,
                reason=(
                    "restart-intensity limiter tripped — supervisor gives up and escalates instead of "
                    "crash-looping forever"
                ),
                restarts_within_period=self._intensity_limiter.restart_count_within_period(
                    child_id, now
                ),
                maximum_restarts=policy.maximum_restarts,
                period_seconds=policy.period_seconds,
                escalated_at=now,
            )
            state.has_given_up = True
            state.give_up_reason = escalation.reason
            LOGGER.error("%s", escalation.headline)
            self._record_lifetime_event(specification, state, now, failure_reason=escalation.reason)
            return ComponentSupervisionTree._RestartDecision(escalation=escalation)

        # --- EXECUTE ----------------------------------------------------------------------------
        self._intensity_limiter.record_restart(child_id, now)
        state.last_restart_at = now
        state.consecutive_restart_count += 1
        state.terminated_normally = False
        state.healthy_since = None
        succeeded = True
        detail = f"restarted under {strategy.value} (triggered by {triggering_child_id})"
        try:
            specification.supervised_component.restart()
        except Exception as restart_error:  # noqa: BLE001 — counted + logged + surfaced (Rule O.3)
            succeeded = False
            state.failed_restart_attempt_count += 1
            detail = (
                f"restart FAILED under {strategy.value} (triggered by {triggering_child_id}): "
                f"{type(restart_error).__name__}: {restart_error}"
            )
            LOGGER.exception("restart of supervised child %s failed", child_id)
        else:
            state.total_restart_count += 1

        self._record_lifetime_event(
            specification,
            state,
            now,
            failure_reason="" if succeeded else detail,
        )
        return ComponentSupervisionTree._RestartDecision(
            outcome=ChildRestartOutcome(
                child_id=child_id,
                triggering_child_id=triggering_child_id,
                restart_strategy=strategy,
                succeeded=succeeded,
                detail=detail,
                consecutive_restart_count=state.consecutive_restart_count,
                total_restart_count=state.total_restart_count,
                attempted_at=now,
            )
        )

    def _record_lifetime_event(
        self,
        specification: SupervisionChildSpecification,
        state: _SupervisedChildRuntimeState,
        now: datetime,
        failure_reason: str,
    ) -> None:
        """Append the survival observation this death produced (the Weibull-AFT fit's only input).

        A restart is an OBSERVED FAILURE of the previous incarnation, so `observed_failure=True`;
        right-censored rows come from the telemetry collector, not from here.
        """
        if self._state_store is None:
            return
        uptime_hours = 0.0
        if state.last_observed_dead_at is not None and state.last_restart_at is not None:
            reference = state.healthy_since or state.last_restart_at
            uptime_hours = max(0.0, (now - reference).total_seconds() / _SECONDS_PER_HOUR)
        try:
            self._state_store.record_lifetime_event(
                PersistedLifetimeEvent(
                    component_id=specification.child_id,
                    component_class=specification.component_class,
                    recorded_at=now,
                    uptime_hours=uptime_hours,
                    observed_failure=True,
                    restart_count=state.total_restart_count,
                    degradation_trend=float(state.consecutive_restart_count),
                    failure_reason=failure_reason,
                )
            )
        except Exception as store_error:  # noqa: BLE001 — counted + logged, never silently dropped
            self._state_store_write_failure_count += 1
            LOGGER.exception(
                "failed to persist the lifetime event for %s (%s) — survival data lost for this "
                "observation; total write failures: %d",
                specification.child_id, store_error, self._state_store_write_failure_count,
            )


def build_supervision_tree_for_registered_components(
    supervised_components: Sequence[SupervisedComponent],
    *,
    registry: OrganismComponentRegistry | None = None,
    intensity_policy: RestartIntensityPolicy | None = None,
    backoff_policy: CrashLoopBackOffPolicy | None = None,
    maximum_children_restarted_per_pass: int = DEFAULT_MAXIMUM_CHILDREN_RESTARTED_PER_PASS,
    state_store: AutopoiesisStateStore | None = None,
) -> ComponentSupervisionTree:
    """The PRODUCTION constructor: derive every child spec from the organism registry.

    Restart type, component class and the dependency edges all come from the registry, so the
    supervision tree cannot drift from the organism's declared self-model. A supervised component
    whose id is not in the registry is still accepted — it is supervised with conservative defaults
    and logged, because refusing to supervise an unregistered thread would leave it with NO watchdog,
    which is strictly worse than supervising it imperfectly.
    """
    effective_registry = registry or build_default_component_registry()
    child_ids = [component.component_id for component in supervised_components]
    dependency_edges = derive_child_dependency_edges_from_registry(child_ids, effective_registry)
    specifications: list[SupervisionChildSpecification] = []
    for component in supervised_components:
        registered = effective_registry.find(component.component_id)
        if registered is None:
            LOGGER.warning(
                "supervising unregistered component %s with default child-spec settings — add it to "
                "component_registry so its class, criticality and maintainers are declared",
                component.component_id,
            )
        specifications.append(
            SupervisionChildSpecification(
                child_id=component.component_id,
                supervised_component=component,
                restart_type=(
                    restart_type_for_registered_component(registered)
                    if registered is not None
                    else ChildRestartType.PERMANENT
                ),
                component_class=(
                    registered.component_class
                    if registered is not None
                    else ComponentClass.BACKGROUND_THREAD
                ),
                depends_on_child_ids=dependency_edges.get(component.component_id, ()),
                role_description=registered.role_description if registered is not None else "",
            )
        )
    return ComponentSupervisionTree(
        specifications,
        intensity_policy=intensity_policy,
        backoff_policy=backoff_policy,
        maximum_children_restarted_per_pass=maximum_children_restarted_per_pass,
        state_store=state_store,
    )
