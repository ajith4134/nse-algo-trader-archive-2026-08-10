"""Trunk X AUTOPOIESIS — the MAPE-K cycle that binds the organism's self-maintenance into one loop.

This is the part that makes the other twelve modules an ORGANISM rather than twelve libraries. One
cycle, level-triggered like a Kubernetes controller (observe actual → diff against desired → act),
never edge-triggered — which is precisely the failure mode of the 37 `except Exception: pass` cadence
methods this engine exists to replace (research/170 §2).

    MONITOR   `component_telemetry_collector`  — read every vital sign off the real organism
    ANALYZE   `component_health_index`         — PCA T²/SPE + EWMA -> h(t) per component
              `operational_closure_auditor`    — who maintains whom; who is maintained by nobody
              `component_failure_hazard_model` — right-censored RUL (Weibull-AFT / Wiener / prior)
    PLAN      `maintenance_policy_solver`      — CBM control-limit lookup -> monitor/repair/replace/quarantine
              `homeostatic_setpoint_keeper`    — viability set -> how hard to throttle the organism
    EXECUTE   `component_supervision_tree`     — OTP-style restarts under a MaxR/MaxT intensity limiter
              `component_repair_executor`      — budgeted, breaker-guarded, conscience-checked repair
              `organism_vitality_gate`         — publish the entry-site lever for the trading loop
    KNOWLEDGE `autopoiesis_state_store`        — the append-only memory all of the above read and write

THREADING CONTRACT (a correctness fork, decided here deliberately — see docs/BACKLOG.md):
`AutopoiesisStateStore` holds ONE `sqlite3` connection created with the stdlib default
`check_same_thread=True`. `LivePaperTradingService` runs five-plus daemon threads. Therefore **this
orchestrator owns the store and every cycle runs on ONE thread** — the service's writer thread. Nothing
else may touch the store. The alternative (opening the connection with `check_same_thread=False` plus a
lock) was rejected: a single owning thread is simpler to reason about and cannot interleave a
half-written forensic ledger. The repair executor already fails SAFE if the store is unreachable
(budget unreadable ⇒ treated as exhausted ⇒ repair refused), so a violation of this contract degrades
to "performs no repairs" rather than to corruption — loud, not silent.

WHAT THIS CYCLE MAY DO ON ITS OWN, AND WHAT IT MAY NEVER DO:
It may restart threads, re-fit stale artifacts, quarantine failing sources, and throttle the organism's
own workload — all inside a repair budget, behind circuit breakers, and only after the corrigibility
off-switch and the constitutional referee have permitted the action (checked inside
`component_repair_executor`, not here). It may tighten or veto entries through the vitality gate. It may
NEVER up-size a trade: the vitality multiplier is structurally clamped to [0, 1].
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from nse_algo_trader.autopoiesis.autopoiesis_state_store import (
    AutopoiesisStateStore,
    PersistedLifetimeEvent,
)
from nse_algo_trader.autopoiesis.component_failure_hazard_model import (
    ComponentFailureHazardModel,
    ComponentLifetimeObservation,
    RemainingUsefulLifeEstimate,
)
from nse_algo_trader.autopoiesis.component_health_index import (
    ComponentHealthAssessment,
    ComponentHealthIndexEngine,
    DegradationState,
)
from nse_algo_trader.autopoiesis.component_registry import (
    OrganismComponentRegistry,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.component_repair_executor import (
    ComponentRepairExecutor,
    RepairExecutionOutcome,
)
from nse_algo_trader.autopoiesis.component_telemetry_collector import (
    ComponentTelemetryCollector,
    InjectedComponentObservation,
    OrganismTelemetryCollection,
    TelemetryCollectionDiagnostics,
)
from nse_algo_trader.autopoiesis.homeostatic_setpoint_keeper import (
    HomeostaticSetpointKeeper,
    HomeostaticThrottleDecision,
    build_default_setpoint_keeper,
)
from nse_algo_trader.autopoiesis.maintenance_policy_solver import (
    MaintenanceActionKind,
    MaintenancePolicyTable,
    select_action_for_component,
    solve_maintenance_policy_table,
)
from nse_algo_trader.autopoiesis.operational_closure_auditor import (
    OperationalClosureReport,
    audit_operational_closure,
)
from nse_algo_trader.autopoiesis.organism_vitality_gate import OrganismVitalityGate

LOGGER = logging.getLogger(__name__)

#: Re-solving the CBM policy is expensive (value iteration per cohort) and its inputs move slowly, so
#: it is solved on a cadence and looked up cheaply per cycle (research/168 §3c).
POLICY_RESOLVE_INTERVAL_HOURS: float = 6.0

#: Re-fitting the survival model is likewise slow and its input only changes as lifetime events accrue.
HAZARD_REFIT_INTERVAL_HOURS: float = 1.0

#: Degradation states at which the cycle will consider acting on a component at all. Everything
#: healthier is recorded and left alone — a homeostat that intervenes on noise is worse than none.
ACTIONABLE_DEGRADATION_STATES: frozenset[DegradationState] = frozenset(
    {DegradationState.DEGRADED, DegradationState.FAILING, DegradationState.FAILED}
)


@dataclass(frozen=True)
class MaintenanceCycleReport:
    """Everything one MAPE-K cycle observed, concluded and did — the dashboard's whole input."""

    cycle_started_at: datetime
    telemetry: OrganismTelemetryCollection
    health_by_component_id: Mapping[str, ComponentHealthAssessment]
    closure: OperationalClosureReport
    remaining_useful_life: tuple[RemainingUsefulLifeEstimate, ...]
    planned_actions: tuple[tuple[str, MaintenanceActionKind], ...]
    executed_outcomes: tuple[RepairExecutionOutcome, ...]
    throttle: HomeostaticThrottleDecision | None
    organism_vitality_index: float
    cycle_error_count: int = 0
    cycle_errors: tuple[str, ...] = ()

    @property
    def degraded_component_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                component_id
                for component_id, assessment in self.health_by_component_id.items()
                if assessment.degradation_state in ACTIONABLE_DEGRADATION_STATES
            )
        )

    @property
    def nearest_to_failure(self) -> RemainingUsefulLifeEstimate | None:
        return self.remaining_useful_life[0] if self.remaining_useful_life else None

    def describe(self) -> str:
        """One block, formatted for the Rule-F by-eye pass."""
        lines = [
            f"MAPE-K cycle @ {self.cycle_started_at.isoformat()}  "
            f"vitality={self.organism_vitality_index:.3f}  "
            f"components={len(self.health_by_component_id)}  "
            f"degraded={len(self.degraded_component_ids)}  "
            f"closure_violations={len(self.closure.violations)}  errors={self.cycle_error_count}"
        ]
        for component_id in self.degraded_component_ids:
            assessment = self.health_by_component_id[component_id]
            lines.append(
                f"  {component_id:38s} h={assessment.health_index:.3f} "
                f"{assessment.degradation_state.value}"
            )
        for component_id, action in self.planned_actions:
            lines.append(f"  PLAN {component_id:36s} -> {action.value}")
        for outcome in self.executed_outcomes:
            lines.append(f"  EXEC {outcome.component_id:36s} -> {outcome.action_kind.value}")
        if self.throttle is not None:
            lines.append(f"  THROTTLE {self.throttle.describe()}")
        for error in self.cycle_errors:
            lines.append(f"  ⚠ {error}")
        return "\n".join(lines)


@dataclass
class AutopoiesisHomeostatOrchestrator:
    """The organism's self-maintenance loop. One instance, owned by one thread (see module docstring)."""

    registry: OrganismComponentRegistry = field(default_factory=build_default_component_registry)
    state_store: AutopoiesisStateStore | None = None
    telemetry_collector: ComponentTelemetryCollector | None = None
    health_engine: ComponentHealthIndexEngine = field(default_factory=ComponentHealthIndexEngine)
    hazard_model: ComponentFailureHazardModel = field(default_factory=ComponentFailureHazardModel)
    setpoint_keeper: HomeostaticSetpointKeeper = field(default_factory=build_default_setpoint_keeper)
    vitality_gate: OrganismVitalityGate = field(default_factory=OrganismVitalityGate)
    repair_executor: ComponentRepairExecutor | None = None
    #: Advisory by default: the cycle PLANS actions and publishes the vitality lever, but performs no
    #: repair until the operator grants autonomy. The full acting path is built and armed; this is the
    #: blast-radius switch, not a feature gate (research/170 §6 plan-then-apply).
    autonomous_repair_enabled: bool = False

    _policy_table: MaintenancePolicyTable | None = field(default=None, init=False)
    _policy_solved_at: datetime | None = field(default=None, init=False)
    _hazard_fitted_at: datetime | None = field(default=None, init=False)
    _latest_report: MaintenanceCycleReport | None = field(default=None, init=False)
    _cycle_count: int = field(default=0, init=False)
    _cumulative_error_count: int = field(default=0, init=False)

    # -- the cycle ---------------------------------------------------------------------------------

    def run_maintenance_cycle(
        self,
        now: datetime | None = None,
        injected_observations: Iterable[InjectedComponentObservation] = (),
    ) -> MaintenanceCycleReport:
        """One complete MAPE-K pass. Never raises into the caller's loop; errors are counted + carried.

        The service calls this on a cadence from its writer thread. Any internal failure produces a
        report with `cycle_errors` populated rather than an exception, because a homeostat that can
        crash the loop it is supposed to protect is worse than no homeostat (Rule O.3).
        """
        moment = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        errors: list[str] = []
        self._cycle_count += 1

        telemetry = self._monitor(moment, injected_observations, errors)
        health = self._analyze_health(telemetry, errors)
        closure = self._analyze_closure(errors)
        lifetimes = self._record_and_read_lifetime_observations(health, moment, errors)
        remaining_life = self._analyze_remaining_life(lifetimes, moment, errors)
        planned = self._plan_maintenance_actions(health, moment, errors)
        throttle = self._plan_throttle(telemetry, moment, errors)
        executed = self._execute_planned_actions(planned, moment, errors)
        vitality = self._publish_vitality(health, closure, errors)

        report = MaintenanceCycleReport(
            cycle_started_at=moment,
            telemetry=telemetry,
            health_by_component_id=health,
            closure=closure,
            remaining_useful_life=remaining_life,
            planned_actions=planned,
            executed_outcomes=executed,
            throttle=throttle,
            organism_vitality_index=vitality,
            cycle_error_count=len(errors),
            cycle_errors=tuple(errors),
        )
        self._cumulative_error_count += len(errors)
        self._latest_report = report
        return report

    # -- MONITOR -----------------------------------------------------------------------------------

    def _monitor(
        self,
        moment: datetime,
        injected_observations: Iterable[InjectedComponentObservation],
        errors: list[str],
    ) -> OrganismTelemetryCollection:
        collector = self.telemetry_collector
        if collector is None:
            collector = ComponentTelemetryCollector(
                registry=self.registry, state_store=self.state_store
            )
            self.telemetry_collector = collector
            self._bind_severity_specs(collector)
        try:
            return collector.collect_organism_vital_signs(moment, injected_observations)
        except Exception as failure:  # noqa: BLE001 — a blind cycle is reported, never fatal
            errors.append(f"MONITOR failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis MONITOR failed", exc_info=True)
            return OrganismTelemetryCollection(
                collected_at=moment, samples=(), readings=(), diagnostics=_empty_diagnostics()
            )

    def _bind_severity_specs(self, collector: ComponentTelemetryCollector) -> None:
        """Teach the health engine how each collected signal maps to a severity.

        WITHOUT this the engine has no spec for `staleness_ratio_vs_declared_maximum`,
        `broker_token_expired` and the rest, so every signal is unmapped and EVERY component reads
        perfectly healthy no matter how broken it is. That failure is silent — the cycle completes
        with zero errors and reports vitality 1.000 on a dead organism — which is precisely why the
        Rule-F by-eye pass exists (caught 2026-07-27: `store.market_data` and `session.breeze` are
        both FAILED in reality, yet the unbound engine reported 0 degraded).
        """
        if self.health_engine.tracked_component_ids():
            return  # already carrying per-component state; rebinding would discard the baselines
        specs = collector.signal_severity_specs
        self.health_engine = ComponentHealthIndexEngine(
            calibration=self.health_engine.calibration,
            signal_severity_specs_by_component_id={
                component.component_id: specs for component in self.registry.self_components()
            },
        )

    # -- ANALYZE -----------------------------------------------------------------------------------

    def _analyze_health(
        self, telemetry: OrganismTelemetryCollection, errors: list[str]
    ) -> Mapping[str, ComponentHealthAssessment]:
        try:
            return self.health_engine.assess_all(telemetry.samples)
        except Exception as failure:  # noqa: BLE001
            errors.append(f"ANALYZE(health) failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis health analysis failed", exc_info=True)
            return {}

    def _analyze_closure(self, errors: list[str]) -> OperationalClosureReport:
        try:
            return audit_operational_closure(self.registry)
        except Exception as failure:  # noqa: BLE001
            errors.append(f"ANALYZE(closure) failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis closure audit failed", exc_info=True)
            return OperationalClosureReport(
                is_closed=False,
                violations=(),
                organizations=(),
                critical_articulation_points=(),
                criticality_ranking=(),
                component_count=0,
                maintenance_edge_count=0,
            )

    def _record_and_read_lifetime_observations(
        self,
        health: Mapping[str, ComponentHealthAssessment],
        moment: datetime,
        errors: list[str],
    ) -> tuple[ComponentLifetimeObservation, ...]:
        """Append this cycle's censored lifetime rows, then read the class history back for the fit.

        Every healthy component contributes a RIGHT-CENSORED observation ("still alive at T hours").
        That is not filler: censored rows carry most of the survival information when few things have
        failed, which is permanently this organism's regime.
        """
        store = self.state_store
        if store is None:
            return ()
        try:
            prior_events = store.read_lifetime_events()
        except Exception as failure:  # noqa: BLE001
            errors.append(f"lifetime read failed: {type(failure).__name__}: {failure}")
            return ()

        # Uptime is measured from when THIS homeostat first observed the component alive, not from the
        # health index's sample count (those are baseline samples, not hours — conflating them produced
        # a zero-duration survival row on the first cycle, which the hazard model correctly rejected).
        first_observed_at: dict[str, datetime] = {}
        for event in prior_events:
            existing = first_observed_at.get(event.component_id)
            if existing is None or event.recorded_at < existing:
                first_observed_at[event.component_id] = event.recorded_at

        for component_id, assessment in health.items():
            component = self.registry.find(component_id)
            if component is None:
                continue
            observed_failure = assessment.degradation_state is DegradationState.FAILED
            try:
                store.record_lifetime_event(
                    PersistedLifetimeEvent(
                        component_id=component_id,
                        component_class=component.component_class,
                        recorded_at=moment,
                        uptime_hours=_observed_uptime_hours(
                            first_observed_at.get(component_id), moment
                        ),
                        observed_failure=observed_failure,
                        restart_count=0,
                        degradation_trend=float(1.0 - assessment.health_index),
                        failure_reason=(
                            assessment.degradation_state.value if observed_failure else ""
                        ),
                    )
                )
            except Exception as failure:  # noqa: BLE001
                errors.append(f"lifetime write failed for {component_id}: {type(failure).__name__}")
                LOGGER.error("autopoiesis lifetime write failed", exc_info=True)
                break
        try:
            persisted = store.read_lifetime_events()
        except Exception as failure:  # noqa: BLE001
            errors.append(f"lifetime re-read failed: {type(failure).__name__}: {failure}")
            return ()
        return tuple(
            ComponentLifetimeObservation(
                component_id=event.component_id,
                component_class=event.component_class,
                uptime_hours=event.uptime_hours,
                observed_failure=event.observed_failure,
                restart_count=event.restart_count,
                degradation_trend=event.degradation_trend,
            )
            for event in persisted
        )

    def _analyze_remaining_life(
        self,
        lifetimes: Sequence[ComponentLifetimeObservation],
        moment: datetime,
        errors: list[str],
    ) -> tuple[RemainingUsefulLifeEstimate, ...]:
        if not lifetimes:
            return ()
        try:
            if self._should_refit_hazard(moment):
                self.hazard_model.fit(lifetimes)
                self._hazard_fitted_at = moment
            return self.hazard_model.estimate_remaining_useful_life_for_all(lifetimes)
        except Exception as failure:  # noqa: BLE001
            errors.append(f"ANALYZE(RUL) failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis RUL estimation failed", exc_info=True)
            return ()

    # -- PLAN --------------------------------------------------------------------------------------

    def _plan_maintenance_actions(
        self,
        health: Mapping[str, ComponentHealthAssessment],
        moment: datetime,
        errors: list[str],
    ) -> tuple[tuple[str, MaintenanceActionKind], ...]:
        """Look each actionable component up in the solved control-limit table. Never guesses."""
        try:
            table = self._maintenance_policy_table(moment)
        except Exception as failure:  # noqa: BLE001
            errors.append(f"PLAN(policy) failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis policy solve failed", exc_info=True)
            return ()
        planned: list[tuple[str, MaintenanceActionKind]] = []
        for component_id, assessment in sorted(health.items()):
            if assessment.degradation_state not in ACTIONABLE_DEGRADATION_STATES:
                continue
            component = self.registry.find(component_id)
            if component is None:
                continue
            action = select_action_for_component(table, component, assessment.health_index)
            if action is None or action is MaintenanceActionKind.MONITOR:
                continue
            planned.append((component_id, action))
        return tuple(planned)

    def _plan_throttle(
        self, telemetry: OrganismTelemetryCollection, moment: datetime, errors: list[str]
    ) -> HomeostaticThrottleDecision | None:
        """Hold the essential variables inside the viability set by slowing the organism down."""
        measurements = telemetry.essential_variable_measurements()
        try:
            return self.setpoint_keeper.regulate_toward_viability(measurements, moment)
        except Exception as failure:  # noqa: BLE001
            errors.append(f"PLAN(throttle) failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis setpoint regulation failed", exc_info=True)
            return None

    # -- EXECUTE -----------------------------------------------------------------------------------

    def _execute_planned_actions(
        self,
        planned: Sequence[tuple[str, MaintenanceActionKind]],
        moment: datetime,
        errors: list[str],
    ) -> tuple[RepairExecutionOutcome, ...]:
        """Perform the plan — or, while autonomy is withheld, only dry-run it.

        `plan_only=True` still exercises the whole refusal chain (off-switch, referee, budget, breaker),
        so the acting path is continuously verified rather than lying dormant until the day it matters.
        """
        executor = self.repair_executor
        if executor is None or not planned:
            return ()
        outcomes: list[RepairExecutionOutcome] = []
        for component_id, action in planned:
            try:
                outcomes.append(
                    executor.execute_maintenance_action(
                        component_id,
                        action,
                        now=moment,
                        plan_only=not self.autonomous_repair_enabled,
                    )
                )
            except Exception as failure:  # noqa: BLE001
                errors.append(
                    f"EXECUTE failed for {component_id}/{action.value}: {type(failure).__name__}"
                )
                LOGGER.error("autopoiesis repair execution failed", exc_info=True)
        return tuple(outcomes)

    def _publish_vitality(
        self,
        health: Mapping[str, ComponentHealthAssessment],
        closure: OperationalClosureReport,
        errors: list[str],
    ) -> float:
        """Hand the freshly-measured body state to the entry-site lever. This is the acting output."""
        try:
            self.vitality_gate.ingest_assessment(tuple(health.values()), closure)
            return self.vitality_gate.evaluate().vitality_index
        except Exception as failure:  # noqa: BLE001
            errors.append(f"publish(vitality) failed: {type(failure).__name__}: {failure}")
            LOGGER.error("autopoiesis vitality publication failed", exc_info=True)
            return 1.0

    # -- cadence + accessors -----------------------------------------------------------------------

    def _maintenance_policy_table(self, moment: datetime) -> MaintenancePolicyTable:
        if self._policy_table is None or self._should_resolve_policy(moment):
            self._policy_table = solve_maintenance_policy_table(self.registry)
            self._policy_solved_at = moment
        return self._policy_table

    def _should_resolve_policy(self, moment: datetime) -> bool:
        return _hours_since(self._policy_solved_at, moment) >= POLICY_RESOLVE_INTERVAL_HOURS

    def _should_refit_hazard(self, moment: datetime) -> bool:
        return _hours_since(self._hazard_fitted_at, moment) >= HAZARD_REFIT_INTERVAL_HOURS

    @property
    def latest_report(self) -> MaintenanceCycleReport | None:
        return self._latest_report

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def cumulative_error_count(self) -> int:
        return self._cumulative_error_count

    def dashboard_metrics(self) -> tuple[tuple[str, str], ...]:
        """Rule N. Includes the maturity ladder so the operator sees what is armed vs still gathering."""
        report = self._latest_report
        if report is None:
            return (("status", "no cycle has run yet"),)
        nearest = report.nearest_to_failure
        armed = sum(1 for a in report.health_by_component_id.values() if a.is_pca_armed)
        return (
            ("organism vitality", f"{report.organism_vitality_index:.3f}"),
            ("components watched", str(len(report.health_by_component_id))),
            ("degraded now", str(len(report.degraded_component_ids))),
            ("closure violations", str(len(report.closure.violations))),
            (
                "nearest to failure",
                f"{nearest.component_id} ({nearest.median_hours:.1f}h)" if nearest else "—",
            ),
            ("actions planned", str(len(report.planned_actions))),
            (
                "autonomous repair",
                "enabled" if self.autonomous_repair_enabled else "advisory (dry-run)",
            ),
            ("health model armed", f"{armed}/{len(report.health_by_component_id)}"),
            ("cycles run", str(self._cycle_count)),
            ("cycle errors (cumulative)", str(self._cumulative_error_count)),
        )


#: A component observed alive for the first time has survived at least this long. Survival analysis
#: rejects a zero duration (it carries no information), and inventing a large number would fabricate
#: evidence — so the first observation is recorded as the smallest honest positive duration.
MINIMUM_OBSERVED_UPTIME_HOURS: float = 0.01


def _observed_uptime_hours(first_observed_at: datetime | None, moment: datetime) -> float:
    """Hours this component has been continuously observed alive by the homeostat."""
    if first_observed_at is None:
        return MINIMUM_OBSERVED_UPTIME_HOURS
    elapsed = (moment - first_observed_at).total_seconds() / 3600.0
    return max(MINIMUM_OBSERVED_UPTIME_HOURS, elapsed)


def _hours_since(previous: datetime | None, moment: datetime) -> float:
    if previous is None:
        return float("inf")
    return max(0.0, (moment - previous).total_seconds() / 3600.0)


def _empty_diagnostics() -> TelemetryCollectionDiagnostics:
    """An honest empty record for a cycle whose MONITOR phase failed outright."""
    return TelemetryCollectionDiagnostics()


def build_autopoiesis_homeostat(
    state_store: AutopoiesisStateStore | None = None,
    autonomous_repair_enabled: bool = False,
) -> AutopoiesisHomeostatOrchestrator:
    """The production constructor. One instance per process, owned by the service's writer thread."""
    registry = build_default_component_registry()
    collector = ComponentTelemetryCollector(registry=registry, state_store=state_store)
    homeostat = AutopoiesisHomeostatOrchestrator(
        registry=registry,
        state_store=state_store,
        telemetry_collector=collector,
        autonomous_repair_enabled=autonomous_repair_enabled,
    )
    homeostat._bind_severity_specs(collector)
    return homeostat
