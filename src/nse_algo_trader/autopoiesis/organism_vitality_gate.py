"""Trunk X AUTOPOIESIS — the ENTRY-SITE LEVER: organism health changes what the system trades.

This is the module that makes Trunk X an engine rather than a health dashboard (Rule P). Everything
upstream — telemetry, health index, RUL, closure audit, maintenance policy — exists so that THIS can
answer one question at each of the 4 entry sites:

    given the current condition of the organism's own body, should this entry be taken,
    and at what size?

Design decisions that are load-bearing:

  · **Tighten-only, structurally.** `size_multiplier` is clamped into [0, 1] at the boundary, so the
    homeostat can shrink or veto an entry but can NEVER up-size one. That is what allows it to act
    IMMEDIATELY without an earned-calibration gate (research/172 §4): a degraded organism trading
    smaller is safe by construction, whereas a degraded organism trading BIGGER on a bad signal is the
    exact failure this trunk exists to prevent.

  · **Only the SIGNAL PATH matters for a veto.** A degraded news poller must not veto a cash ORB entry
    that never consumed news. Vetoes key off VITAL components, closure violations on VITAL components,
    and any component the caller declares its entry depends on.

  · **It keys off `violations`, NEVER off `is_closed`.** The organism deliberately has no
    mutually-maintaining cycle: every maintenance chain terminates on `operator.human` /
    `platform.systemd`, because Trunk VII CONSCIENCE requires the human to stay in the maintenance
    path (corrigibility). `is_closed == False` is therefore the CORRECT steady state here, not a
    fault, and gating on it would veto every trade forever. Only genuinely-unmaintained components
    (in-degree 0 in the maintenance-flow graph) are real faults.

  · **It never raises.** Every entry site calls this inside its multiplier chain; an exception here
    would break the trading loop. Any internal failure degrades to identity (1.0, permit) and is
    COUNTED so a silently-inert gate is distinguishable from a healthy one (Rule O.3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from nse_algo_trader.autopoiesis.component_health_index import (
    ComponentHealthAssessment,
    DegradationState,
)
from nse_algo_trader.autopoiesis.component_registry import (
    ComponentCriticality,
    OrganismComponentRegistry,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.component_telemetry_collector import (
    OBSERVABILITY_GAP_SIGNAL_PREFIX,
)
from nse_algo_trader.autopoiesis.operational_closure_auditor import OperationalClosureReport

# Size multipliers applied per degradation band of the WORST binding component. Tighten-only: every
# value is <= 1.0 and the boundary re-clamps, so no configuration change can make this up-size.
DEGRADATION_SIZE_MULTIPLIER: Mapping[DegradationState, float] = {
    DegradationState.HEALTHY: 1.00,
    DegradationState.DEGRADED: 0.60,
    DegradationState.FAILING: 0.25,
    DegradationState.FAILED: 0.00,
}

# A VITAL component in these states vetoes outright — no size is safe when the body part the decision
# depends on is effectively dead. This is the ACUTE case: something that was working has broken.
VETOING_DEGRADATION_STATES: frozenset[DegradationState] = frozenset(
    {DegradationState.FAILING, DegradationState.FAILED}
)

# A CRITICAL closure violation prices risk DOWN; it must never veto. This distinction was found by a
# real-data pass on 2026-07-27 and is the single most important safety property in this module:
#
#   A closure violation is CHRONIC, not ACUTE. "Nothing inside the organism maintains
#   `artifact.win_probability_model`" is true continuously, from now until someone builds a retraining
#   path. Treating it as a veto meant that with EVERY component reporting perfect health, the gate
#   still returned permits_order=False — i.e. wiring it in would have halted all trading indefinitely,
#   for a condition that is a known, logged, structural fact rather than a live fault.
#
# So: chronic structural risk => trade smaller (an unmaintained component's correctness is not
# warranted, so lean on it less). Acute failure of a VITAL organ => veto. Unit tests pass either way;
# only running it against the real closure report exposes the difference (Rule O.2).
CRITICAL_CLOSURE_VIOLATION_SIZE_MULTIPLIER = 0.50

IDENTITY_SIZE_MULTIPLIER = 1.0


@dataclass(frozen=True)
class ComponentMaturityReading:
    """`have N / need M` for one component — surfaced so the operator sees what is armed (Rule Q)."""

    component_id: str
    observed_sample_count: int
    required_sample_count: int

    @property
    def is_armed(self) -> bool:
        return self.observed_sample_count >= self.required_sample_count

    def describe(self) -> str:
        state = "armed" if self.is_armed else "gathering"
        return f"{self.component_id}: {self.observed_sample_count}/{self.required_sample_count} ({state})"


@dataclass(frozen=True)
class OrganismVitalityVerdict:
    """What the organism's own condition says about taking this entry."""

    vitality_index: float          # [0,1] — the worst-case health across the binding components
    size_multiplier: float         # [0,1] — tighten-only, structurally clamped
    permits_order: bool
    binding_component_id: str      # which component drove the verdict ("" when nothing bound)
    reason: str
    maturity: tuple[ComponentMaturityReading, ...] = ()

    @property
    def is_identity(self) -> bool:
        return self.permits_order and self.size_multiplier >= IDENTITY_SIZE_MULTIPLIER


def _permissive_verdict(reason: str) -> OrganismVitalityVerdict:
    """The safe default: full size, permitted. Used when the homeostat has nothing to say."""
    return OrganismVitalityVerdict(
        vitality_index=1.0,
        size_multiplier=IDENTITY_SIZE_MULTIPLIER,
        permits_order=True,
        binding_component_id="",
        reason=reason,
    )


@dataclass
class OrganismVitalityGate:
    """Turns the homeostat's assessment of the body into an entry-site size lever + hard veto.

    Mutable by design: it carries the counters that make its own activity visible on the dashboard
    (Rule N) and distinguishable from silent inertness (Rule O.3).
    """

    registry: OrganismComponentRegistry = field(default_factory=build_default_component_registry)
    health_by_component_id: dict[str, ComponentHealthAssessment] = field(default_factory=dict)
    closure_report: OperationalClosureReport | None = None
    sized_down_count: int = 0
    vetoed_count: int = 0
    internal_failure_count: int = 0

    def ingest_assessment(
        self,
        assessments: Sequence[ComponentHealthAssessment],
        closure_report: OperationalClosureReport | None = None,
    ) -> None:
        """Called once per homeostat cycle by the orchestrator with the freshly-measured body state."""
        self.health_by_component_id = {a.component_id: a for a in assessments}
        if closure_report is not None:
            self.closure_report = closure_report

    def evaluate(self, depends_on_component_ids: Sequence[str] = ()) -> OrganismVitalityVerdict:
        """The verdict for one prospective entry.

        `depends_on_component_ids` names the components THIS entry's signal path actually consumed
        (e.g. the news store for a news-gated option entry). Those are judged alongside the VITAL
        components; unrelated degraded components never veto an entry that does not depend on them.
        """
        try:
            return self._evaluate_uncaught(depends_on_component_ids)
        except Exception as error:  # noqa: BLE001 — must never break the trading loop (Rule O.3)
            self.internal_failure_count += 1
            return _permissive_verdict(f"vitality gate failed internally ({type(error).__name__}); identity")

    def _evaluate_uncaught(self, depends_on_component_ids: Sequence[str]) -> OrganismVitalityVerdict:
        if not self.health_by_component_id:
            return _permissive_verdict("no health assessment yet — homeostat still gathering")

        binding_ids = self._binding_component_ids(depends_on_component_ids)
        assessments = [
            self.health_by_component_id[component_id]
            for component_id in binding_ids
            if component_id in self.health_by_component_id
        ]
        if not assessments:
            return _permissive_verdict("no assessed component binds this entry")

        worst = min(assessments, key=lambda a: a.health_index)
        maturity = tuple(
            ComponentMaturityReading(a.component_id, a.sample_count, a.required_sample_count)
            for a in assessments
        )

        veto_reason = self._acute_veto_reason(worst)
        if veto_reason:
            self.vetoed_count += 1
            return OrganismVitalityVerdict(
                vitality_index=_clamp_unit(worst.health_index),
                size_multiplier=0.0,
                permits_order=False,
                binding_component_id=worst.component_id,
                reason=veto_reason,
                maturity=maturity,
            )

        # Chronic + acute risk compose by taking the TIGHTEST lever, never the average — the same
        # weighted-max principle the health index uses, for the same reason: one real problem must
        # not be diluted by everything else being fine.
        degradation_multiplier = _clamp_unit(
            DEGRADATION_SIZE_MULTIPLIER.get(worst.degradation_state, 1.0)
        )
        violated_component_id = self._critical_closure_violation_in(binding_ids)
        closure_multiplier = (
            CRITICAL_CLOSURE_VIOLATION_SIZE_MULTIPLIER if violated_component_id
            else IDENTITY_SIZE_MULTIPLIER
        )
        multiplier = _clamp_unit(min(degradation_multiplier, closure_multiplier))

        if multiplier < IDENTITY_SIZE_MULTIPLIER:
            self.sized_down_count += 1
            if closure_multiplier < degradation_multiplier:
                binding_id = violated_component_id
                reason = (
                    f"unmaintained VITAL component {violated_component_id} (closure violation): "
                    f"its correctness is not warranted — sizing down ×{multiplier:.2f}"
                )
            elif _degradation_is_only_unobservability(worst):
                # BLIND, not broken — the operator must be able to tell these apart at a glance,
                # because the remedy is completely different (instrument it, vs repair it).
                binding_id = worst.component_id
                reason = (
                    f"{worst.component_id} is UNOBSERVABLE (no telemetry reaching the homeostat; "
                    f"health {worst.health_index:.2f} charged entirely to observability gaps, no "
                    f"failure signal firing) — trading smaller ×{multiplier:.2f}, not halted"
                )
            else:
                binding_id = worst.component_id
                reason = (
                    f"{worst.component_id} is {worst.degradation_state.value} "
                    f"(health {worst.health_index:.2f}) — sizing down ×{multiplier:.2f}"
                )
            return OrganismVitalityVerdict(
                vitality_index=_clamp_unit(worst.health_index),
                size_multiplier=multiplier,
                permits_order=True,
                binding_component_id=binding_id,
                reason=reason,
                maturity=maturity,
            )
        reason = "organism healthy across binding components"
        return OrganismVitalityVerdict(
            vitality_index=_clamp_unit(worst.health_index),
            size_multiplier=multiplier,
            permits_order=True,
            binding_component_id=worst.component_id if multiplier < 1.0 else "",
            reason=reason,
            maturity=maturity,
        )

    def _binding_component_ids(self, depends_on_component_ids: Sequence[str]) -> tuple[str, ...]:
        """VITAL components always bind; declared dependencies bind for this specific entry."""
        binding = set(self.registry.vital_component_ids())
        for component_id in depends_on_component_ids:
            if self.registry.is_recognized(component_id):
                binding.add(component_id)
        return tuple(sorted(binding))

    def _acute_veto_reason(self, worst: ComponentHealthAssessment) -> str:
        """A hard veto requires an ACUTE failure of a VITAL organ — never a chronic closure violation,
        and never mere BLINDNESS to that organ.

        See CRITICAL_CLOSURE_VIOLATION_SIZE_MULTIPLIER: gating vetoes on a chronic structural fact
        halts trading forever, because the fact stays true until a human changes the architecture.
        An `observability_gap:*` reading is exactly such a chronic structural fact — no heartbeat /
        operational-observation instrumentation exists for that component, so the gap stays true until
        someone builds it. That doctrine was applied to closure violations but NOT to observability
        gaps, and on 2026-07-27 the omission halted ALL trading in both segments with every declared
        failure signal reading 0.0 (`thread_not_alive=0.0` on a thread that was demonstrably alive).
        `component_health_index` already charges an unreadable signal at the DEGRADED tier precisely
        because it is "not proof of failure either" — this makes the VETO honour the same distinction.

        An organism that cannot SEE itself trades smaller; only one that is demonstrably BROKEN stops.
        """
        component = self.registry.find(worst.component_id)
        is_vital = component is not None and component.criticality is ComponentCriticality.VITAL
        if not (is_vital and worst.degradation_state in VETOING_DEGRADATION_STATES):
            return ""
        if _degradation_is_only_unobservability(worst):
            return ""  # blind, not broken — falls through to the size-down path
        return (
            f"VITAL component {worst.component_id} is {worst.degradation_state.value} "
            f"(health {worst.health_index:.2f}) — no entry size is safe"
        )

    def _critical_closure_violation_in(self, binding_ids: tuple[str, ...]) -> str:
        """Closure violations bind ONLY through `violations` — never through `is_closed` (see docstring)."""
        report = self.closure_report
        if report is None:
            return ""
        binding = set(binding_ids)
        for violation in report.violations:
            if violation.severity == "critical" and violation.component_id in binding:
                return violation.component_id
        return ""

    def size_multiplier_for_entry(self, depends_on_component_ids: Sequence[str] = ()) -> float:
        """The entry sites' multiplier-chain hook. Always in [0,1]; never raises."""
        return _clamp_unit(self.evaluate(depends_on_component_ids).size_multiplier)

    def permits_order(self, depends_on_component_ids: Sequence[str] = ()) -> bool:
        """The entry sites' hard-gate hook, beside `power_budget_permits_order`. Never raises."""
        return self.evaluate(depends_on_component_ids).permits_order

    def dashboard_metrics(self) -> tuple[tuple[str, str], ...]:
        """Rule N: the gate's own activity, so an inert gate is visibly distinct from a healthy one."""
        verdict = self.evaluate()
        armed = sum(1 for reading in verdict.maturity if reading.is_armed)
        return (
            ("organism vitality", f"{verdict.vitality_index:.2f}"),
            ("size lever", f"×{verdict.size_multiplier:.2f}"),
            ("entries sized down", str(self.sized_down_count)),
            ("entries vetoed", str(self.vetoed_count)),
            ("components armed", f"{armed}/{len(verdict.maturity)}"),
            ("gate internal failures", str(self.internal_failure_count)),
        )


def _degradation_is_only_unobservability(assessment: ComponentHealthAssessment) -> bool:
    """True when EVERY signal charging this component is an observability gap — i.e. we cannot see it,
    but nothing has reported failing.

    Returns False when no signal carries severity (nothing to attribute the state to — that is not
    positive evidence of blindness, so it must not excuse a veto), and False the moment ANY genuine
    failure signal contributes: blindness never EXCUSES an accompanying real failure.
    """
    charging_signals = [
        signal_name
        for signal_name, severity in assessment.contributing_signals
        if severity > 0.0
    ]
    if not charging_signals:
        return False
    return all(
        signal_name.startswith(OBSERVABILITY_GAP_SIGNAL_PREFIX)
        for signal_name in charging_signals
    )


def _clamp_unit(value: float) -> float:
    """Structural tighten-only guarantee — also normalises NaN to the safe identity."""
    if value != value:  # NaN
        return IDENTITY_SIZE_MULTIPLIER
    return max(0.0, min(float(value), 1.0))
