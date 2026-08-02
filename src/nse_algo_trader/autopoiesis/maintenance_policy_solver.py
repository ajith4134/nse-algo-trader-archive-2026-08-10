"""Trunk X AUTOPOIESIS — condition-based-maintenance MDP solver → control-limit threshold table.

The organism must decide, per component, whether to MONITOR / REPAIR / REPLACE / QUARANTINE a degrading
part of itself. It does NOT decide that with hand-tuned if-statements. It solves a **condition-based
maintenance Markov Decision Process** by hand-rolled Bellman value iteration and deploys the resulting
policy as a cheap **control-limit threshold table** (research/168 §3a/§3c; research/172 §3 "Policy" row).

**research/168 §3a — CBM as an MDP.** State `s` = the discretized health index of §1 plus an absorbing
FAILED state; actions `a ∈ {monitor, repair, replace, quarantine}`; the standard CBM cost structure =
a large *downtime/failure* cost, a moderate *repair* cost that partially restores health, a *replacement*
cost that is the largest planned cost but resets degradation to as-good-as-new, and a near-zero
*monitoring* cost. Solved by the Bellman recursion

    V(s) = min_a [ c(s, a) + γ · Σ_{s'} P(s' | s, a) · V(s') ]

iterated to a fixed point on the sup-norm. `quarantine` is this organism's fourth action (not in the
textbook three): it removes the component from service permanently at a recurring service-loss cost —
the "cap the loss and fail over to the sibling" lever of research/172 §9.

**research/168 §3c — control-limit optimality.** Under monotone costs and monotone transition
probabilities the optimal CBM policy provably collapses to a small number of threshold cutoffs per
action. That is why the solve happens on a cadence and the trading loop only ever does an O(1) table
lookup (`select_maintenance_action`) — and why a *non-monotone* solved policy is a genuine finding about
the cost structure, surfaced in `MaintenanceControlLimitPolicy.is_monotone` and never silently smoothed.

**research/168 §3b — the certainty-equivalent stance.** The health index is a noisy observation of true
wear, so the exact object is a POMDP. This module implements the documented v1: a certainty-equivalent
MDP over the posterior-flavoured health index. The belief-state POMDP is the recorded upgrade path.

**Rule Q.** Costs start from per-class priors (`build_cost_model_for_component_class`) and are refined by
empirical-Bayes shrinkage as real repair outcomes accrue (`refine_cost_model_with_observed_repairs`).
The solver is fully built and armed from day one; only cost *accuracy* improves with data.

**Rule O.3.** Non-convergence is never hidden: it is reported through `converged` /
`iterations_to_converge`. Malformed input (NaN/inf/negative costs, γ ∉ [0,1), empty state space) raises
a named `ValueError` rather than silently producing a meaningless policy.

Runtime dependency: numpy only. `pymdptoolbox` is a **dev-only** numerical cross-check (research/172
§10) and is deliberately not imported here.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum

import numpy as np
import numpy.typing as npt

from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    ComponentCriticality,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)

LOGGER = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float64]

DEFAULT_DEGRADATION_LEVEL_COUNT = 12
DEFAULT_DISCOUNT_FACTOR = 0.97
DEFAULT_VALUE_ITERATION_TOLERANCE = 1e-10
DEFAULT_MAXIMUM_VALUE_ITERATIONS = 20_000


class MaintenanceActionKind(str, Enum):
    """The four levers the homeostat can pull on one of its own components.

    Declaration order IS the escalation-severity order, and `select_maintenance_action` /
    `find_policy_monotonicity_violations` rely on it: a control-limit policy is one whose severity is
    non-decreasing in degradation (research/168 §3c).
    """

    MONITOR = "monitor"
    REPAIR = "repair"
    REPLACE = "replace"
    QUARANTINE = "quarantine"


MAINTENANCE_ACTION_ORDER: tuple[MaintenanceActionKind, ...] = (
    MaintenanceActionKind.MONITOR,
    MaintenanceActionKind.REPAIR,
    MaintenanceActionKind.REPLACE,
    MaintenanceActionKind.QUARANTINE,
)

_ACTION_SEVERITY_RANK: dict[MaintenanceActionKind, int] = {
    action: rank for rank, action in enumerate(MAINTENANCE_ACTION_ORDER)
}

# Downtime and degraded-service losses scale with how much organism function the component carries
# (research/172 §3: a VITAL component that is FAILING vetoes trading; an ANCILLARY one is observability
# only). Repair/replace costs deliberately do NOT scale — that asymmetry is exactly what makes a VITAL
# component repair at a *lower* degradation level than an identical ANCILLARY one.
CRITICALITY_SERVICE_LOSS_MULTIPLIER: dict[ComponentCriticality, float] = {
    ComponentCriticality.VITAL: 12.0,
    ComponentCriticality.SUPPORTING: 3.0,
    ComponentCriticality.ANCILLARY: 1.0,
}


@dataclass(frozen=True)
class MaintenanceCostModel:
    """Per-component-class CBM cost + degradation priors (research/168 §3a cost structure).

    All costs are in abstract "organism loss units" per solve cycle; only their RATIOS matter to the
    optimal policy, which is why day-one priors are already decision-grade (Rule Q).
    """

    component_class: str
    criticality: ComponentCriticality
    # --- cost structure -----------------------------------------------------------------------
    monitoring_cost_per_cycle: float
    repair_cost: float
    replace_cost: float
    downtime_cost_per_cycle: float
    quarantine_service_loss_cost_per_cycle: float
    # Loss from operating at the WORST working degradation level; scales linearly to 0 at level 0.
    degraded_service_cost_at_worst_level: float
    # --- degradation dynamics ------------------------------------------------------------------
    degradation_rate_levels_per_cycle: float
    failure_hazard_at_best_level: float
    failure_hazard_at_worst_level: float
    repair_success_probability: float
    # Kijima-style IMPERFECT repair: a successful repair removes this fraction of the degradation
    # accumulated so far (1.0 would be as-good-as-new, i.e. a replacement). Proportional restoration —
    # rather than a fixed number of levels — is what keeps the marginal value of repair monotone in the
    # degradation level, and therefore keeps the optimal policy a control limit (research/168 §3c).
    repair_restoration_fraction: float
    # --- solver knobs ---------------------------------------------------------------------------
    degradation_level_count: int = DEFAULT_DEGRADATION_LEVEL_COUNT
    discount_factor: float = DEFAULT_DISCOUNT_FACTOR
    # Rule Q maturity: how many real repair outcomes have been folded into this model so far.
    observed_repair_outcome_count: int = 0

    @property
    def total_state_count(self) -> int:
        """Working degradation levels plus the single absorbing FAILED state."""
        return self.degradation_level_count + 1

    @property
    def failed_state_index(self) -> int:
        return self.degradation_level_count


class MaintenanceCostModelError(ValueError):
    """Raised when a cost model / MDP instance is malformed (Rule O.3: surfaced, never swallowed)."""


@dataclass(frozen=True)
class BellmanValueIterationResult:
    """Raw output of the hand-rolled solver, before it is expressed as thresholds."""

    value_function: tuple[float, ...]
    greedy_action_indices: tuple[int, ...]
    iterations_to_converge: int
    converged: bool
    final_sup_norm_delta: float


@dataclass(frozen=True)
class MaintenanceControlLimitPolicy:
    """The solved policy expressed as a control-limit threshold table (research/168 §3c).

    `action_by_degradation_level` is indexed by discretized degradation level 0 (healthiest) ..
    `degradation_level_count - 1` (worst still-working), with the FINAL index being the absorbing
    FAILED state. `component_class` is the cohort key `"<component_class>/<criticality>"` for policies
    solved from the registry, or a free-form label for standalone solves.

    Threshold semantics (chosen so the research/172 §5.5 acceptance bar reads literally):
      * `monitor_threshold_level` — the HIGHEST level at which passive monitoring is still optimal
        ("monitor while degradation ≤ this"); `-1` when monitoring is never optimal.
      * `repair_threshold_level` — the LOWEST level at which the policy escalates to REPAIR-or-worse;
        `total_state_count` when it never escalates that far.
      * `replace_threshold_level` — the LOWEST level at which it escalates to REPLACE-or-worse.
    """

    component_class: str
    action_by_degradation_level: tuple[MaintenanceActionKind, ...]
    monitor_threshold_level: int
    repair_threshold_level: int
    replace_threshold_level: int
    is_monotone: bool
    value_function: tuple[float, ...]
    iterations_to_converge: int
    converged: bool

    @property
    def degradation_level_count(self) -> int:
        """Working levels only — the last policy entry is the absorbing FAILED state."""
        return max(len(self.action_by_degradation_level) - 1, 0)

    @property
    def failed_state_action(self) -> MaintenanceActionKind:
        return self.action_by_degradation_level[-1]


@dataclass(frozen=True)
class MaintenancePolicyTable:
    """One control-limit policy per component cohort, solved on a cadence and looked up at runtime.

    This is the object the trading loop holds: `select_action_for_component` is an O(1) dict lookup plus
    an integer comparison, so value iteration never runs inline in a decision path (research/168 §3c).
    """

    policy_by_cohort_key: Mapping[str, MaintenanceControlLimitPolicy]
    solved_at_utc: datetime
    non_monotone_cohort_keys: tuple[str, ...]
    non_converged_cohort_keys: tuple[str, ...]

    def policy_for_component(self, component: RegisteredComponent) -> MaintenanceControlLimitPolicy | None:
        return self.policy_by_cohort_key.get(
            build_component_cohort_key(component.component_class, component.criticality)
        )


# =====================================================================================================
# Rule Q — per-class cost priors, and their refinement from real repair outcomes.
# =====================================================================================================

# Prior (repair_cost, replace_cost, downtime_per_cycle, degradation_rate, worst-level hazard,
#        repair_success_probability, repair_level_improvement) per component class.
# Read as: how expensive is a partial fix, how expensive is a from-scratch reset, how fast does this
# kind of thing rot, and does patching it actually work? These are the research/172 §1 verified
# substrate facts turned into numbers (a broker session cannot be "repaired" — only re-authenticated;
# a joblib model can only be retrained; a SQLite store genuinely can be checkpointed/re-indexed).
_COMPONENT_CLASS_COST_PRIORS: dict[ComponentClass, dict[str, float]] = {
    ComponentClass.PERSISTENT_STORE: {
        "repair_cost": 3.0, "replace_cost": 30.0, "downtime_cost_per_cycle": 12.0,
        "degradation_rate_levels_per_cycle": 0.30, "failure_hazard_at_worst_level": 0.10,
        "repair_success_probability": 0.80, "repair_restoration_fraction": 0.70,
    },
    ComponentClass.PERSISTED_ARTIFACT: {
        # "Replace" = retrain/redeploy the model — expensive, and the only thing that truly resets it.
        "repair_cost": 6.0, "replace_cost": 55.0, "downtime_cost_per_cycle": 14.0,
        "degradation_rate_levels_per_cycle": 0.22, "failure_hazard_at_worst_level": 0.08,
        "repair_success_probability": 0.45, "repair_restoration_fraction": 0.40,
    },
    ComponentClass.BROKER_SESSION: {
        # Sessions rot fast (daily hard expiry) and cannot be patched — re-auth is cheap and total.
        "repair_cost": 4.0, "replace_cost": 6.0, "downtime_cost_per_cycle": 25.0,
        "degradation_rate_levels_per_cycle": 0.95, "failure_hazard_at_worst_level": 0.22,
        "repair_success_probability": 0.20, "repair_restoration_fraction": 0.30,
    },
    ComponentClass.BACKGROUND_THREAD: {
        # "Replace" = kill + restart the thread: cheap and as-good-as-new.
        "repair_cost": 2.5, "replace_cost": 5.0, "downtime_cost_per_cycle": 18.0,
        "degradation_rate_levels_per_cycle": 0.40, "failure_hazard_at_worst_level": 0.16,
        "repair_success_probability": 0.35, "repair_restoration_fraction": 0.35,
    },
    ComponentClass.CADENCE_ENGINE: {
        "repair_cost": 3.5, "replace_cost": 9.0, "downtime_cost_per_cycle": 15.0,
        "degradation_rate_levels_per_cycle": 0.35, "failure_hazard_at_worst_level": 0.12,
        "repair_success_probability": 0.55, "repair_restoration_fraction": 0.50,
    },
    ComponentClass.DATA_ADAPTER: {
        # Adapters have real siblings to fail over to, so quarantine is genuinely cheap here.
        "repair_cost": 3.0, "replace_cost": 10.0, "downtime_cost_per_cycle": 20.0,
        "degradation_rate_levels_per_cycle": 0.50, "failure_hazard_at_worst_level": 0.18,
        "repair_success_probability": 0.50, "repair_restoration_fraction": 0.45,
    },
    ComponentClass.EXTERNAL_SERVICE: {
        # We do not own it; "repair" is a cooldown wait, "replace" is switching provider.
        "repair_cost": 2.0, "replace_cost": 8.0, "downtime_cost_per_cycle": 10.0,
        "degradation_rate_levels_per_cycle": 0.55, "failure_hazard_at_worst_level": 0.20,
        "repair_success_probability": 0.40, "repair_restoration_fraction": 0.40,
    },
    ComponentClass.HOST_RESOURCE: {
        # RSS/fd/disk are reclaimed by throttling (repair) or a process restart (replace).
        "repair_cost": 2.0, "replace_cost": 20.0, "downtime_cost_per_cycle": 22.0,
        "degradation_rate_levels_per_cycle": 0.25, "failure_hazard_at_worst_level": 0.14,
        "repair_success_probability": 0.70, "repair_restoration_fraction": 0.65,
    },
}

# Fraction of full-downtime loss still incurred while a component sits quarantined. Below 1.0 because
# quarantine is graceful (`fallback_component_id` takes over) whereas an uncaught failure is not.
QUARANTINE_SERVICE_LOSS_FRACTION = 0.42
# Ongoing loss from RUNNING degraded, at the worst working level, as a fraction of full downtime.
DEGRADED_SERVICE_LOSS_FRACTION_AT_WORST_LEVEL = 0.55
# Curvature of that loss across levels: `loss(i) = worst · fraction(i)^exponent`. Convex (>1) because a
# component 10% into its degradation range is still nearly fine, while one 90% in is nearly broken —
# and because a LINEAR loss makes preventive repair optimal at level 1 for every VITAL component, which
# is a modelling artefact rather than a real finding. Any exponent > 0 keeps the loss monotone in the
# degradation level, which is the structural condition control-limit optimality needs (research/168 §3c).
DEGRADED_SERVICE_LOSS_CURVATURE_EXPONENT = 2.5
# Empirical-Bayes prior weight: how many synthetic observations the class prior is worth (research/168
# §5d — shrink real outcomes toward the prior until enough of them have accrued).
COST_PRIOR_EQUIVALENT_OBSERVATION_COUNT = 8.0


def build_component_cohort_key(
    component_class: ComponentClass, criticality: ComponentCriticality
) -> str:
    """Policy cohort identity: the cost structure depends on BOTH class and criticality."""
    return f"{component_class.value}/{criticality.value}"


def build_cost_model_for_component_class(
    component_class: ComponentClass,
    criticality: ComponentCriticality,
    degradation_level_count: int = DEFAULT_DEGRADATION_LEVEL_COUNT,
    discount_factor: float = DEFAULT_DISCOUNT_FACTOR,
) -> MaintenanceCostModel:
    """Day-one CBM cost model from class priors, scaled by criticality (Rule Q step 1)."""
    prior = _COMPONENT_CLASS_COST_PRIORS.get(component_class)
    if prior is None:  # pragma: no cover - every enum member is covered above; guard against additions
        raise MaintenanceCostModelError(f"no cost prior declared for component class {component_class!r}")
    service_loss_multiplier = CRITICALITY_SERVICE_LOSS_MULTIPLIER[criticality]
    downtime_cost = prior["downtime_cost_per_cycle"] * service_loss_multiplier
    return MaintenanceCostModel(
        component_class=build_component_cohort_key(component_class, criticality),
        criticality=criticality,
        monitoring_cost_per_cycle=0.05,
        repair_cost=prior["repair_cost"],
        replace_cost=prior["replace_cost"],
        downtime_cost_per_cycle=downtime_cost,
        quarantine_service_loss_cost_per_cycle=downtime_cost * QUARANTINE_SERVICE_LOSS_FRACTION,
        degraded_service_cost_at_worst_level=(
            downtime_cost * DEGRADED_SERVICE_LOSS_FRACTION_AT_WORST_LEVEL
        ),
        degradation_rate_levels_per_cycle=prior["degradation_rate_levels_per_cycle"],
        failure_hazard_at_best_level=prior["failure_hazard_at_worst_level"] * 0.05,
        failure_hazard_at_worst_level=prior["failure_hazard_at_worst_level"],
        repair_success_probability=prior["repair_success_probability"],
        repair_restoration_fraction=prior["repair_restoration_fraction"],
        degradation_level_count=degradation_level_count,
        discount_factor=discount_factor,
    )


def refine_cost_model_with_observed_repairs(
    cost_model: MaintenanceCostModel,
    observed_repair_cost_samples: Iterable[float],
    observed_repair_success_flags: Iterable[bool],
) -> MaintenanceCostModel:
    """Rule Q step 3: shrink the class prior toward real repair-ledger outcomes as they accrue.

    Empirical-Bayes / James-Stein flavour (research/168 §5d): the posterior mean is a precision-weighted
    blend `w·prior + (1-w)·observed` with `w = n0 / (n0 + n)`. With `n = 0` this is exactly the prior, so
    the caller can invoke it unconditionally from day one — the solver never changes shape, only the
    numbers sharpen.
    """
    cost_samples = [float(value) for value in observed_repair_cost_samples]
    success_flags = [bool(flag) for flag in observed_repair_success_flags]
    if any(not math.isfinite(value) or value < 0.0 for value in cost_samples):
        raise MaintenanceCostModelError("observed repair-cost samples must be finite and non-negative")

    prior_weight = COST_PRIOR_EQUIVALENT_OBSERVATION_COUNT
    refined_repair_cost = cost_model.repair_cost
    if cost_samples:
        observed_mean = sum(cost_samples) / len(cost_samples)
        blend = prior_weight / (prior_weight + len(cost_samples))
        refined_repair_cost = blend * cost_model.repair_cost + (1.0 - blend) * observed_mean

    refined_success_probability = cost_model.repair_success_probability
    if success_flags:
        # Beta-Binomial conjugate update with the prior expressed as pseudo-counts.
        prior_successes = cost_model.repair_success_probability * prior_weight
        prior_failures = prior_weight - prior_successes
        successes = float(sum(success_flags))
        failures = float(len(success_flags)) - successes
        refined_success_probability = (prior_successes + successes) / (
            prior_successes + prior_failures + successes + failures
        )

    return replace(
        cost_model,
        repair_cost=refined_repair_cost,
        repair_success_probability=min(max(refined_success_probability, 0.0), 1.0),
        observed_repair_outcome_count=(
            cost_model.observed_repair_outcome_count + max(len(cost_samples), len(success_flags))
        ),
    )


# =====================================================================================================
# The MDP instance: transition tensor + stage-cost matrix.
# =====================================================================================================


def _validate_cost_model(cost_model: MaintenanceCostModel) -> None:
    """Rule O.4 — every degenerate input is named and rejected, never silently coerced."""
    if cost_model.degradation_level_count < 1:
        raise MaintenanceCostModelError(
            f"degradation_level_count must be >= 1, got {cost_model.degradation_level_count}"
        )
    monetary_fields = {
        "monitoring_cost_per_cycle": cost_model.monitoring_cost_per_cycle,
        "repair_cost": cost_model.repair_cost,
        "replace_cost": cost_model.replace_cost,
        "downtime_cost_per_cycle": cost_model.downtime_cost_per_cycle,
        "quarantine_service_loss_cost_per_cycle": cost_model.quarantine_service_loss_cost_per_cycle,
        "degraded_service_cost_at_worst_level": cost_model.degraded_service_cost_at_worst_level,
    }
    for field_name, value in monetary_fields.items():
        if not math.isfinite(value):
            raise MaintenanceCostModelError(f"{field_name} must be finite, got {value!r}")
        if value < 0.0:
            raise MaintenanceCostModelError(f"{field_name} must be non-negative, got {value!r}")
    if not math.isfinite(cost_model.degradation_rate_levels_per_cycle):
        raise MaintenanceCostModelError("degradation_rate_levels_per_cycle must be finite")
    if cost_model.degradation_rate_levels_per_cycle < 0.0:
        raise MaintenanceCostModelError("degradation_rate_levels_per_cycle must be non-negative")
    for field_name, probability in (
        ("failure_hazard_at_best_level", cost_model.failure_hazard_at_best_level),
        ("failure_hazard_at_worst_level", cost_model.failure_hazard_at_worst_level),
        ("repair_success_probability", cost_model.repair_success_probability),
    ):
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise MaintenanceCostModelError(f"{field_name} must lie in [0, 1], got {probability!r}")
    if cost_model.failure_hazard_at_worst_level < cost_model.failure_hazard_at_best_level:
        raise MaintenanceCostModelError(
            "failure hazard must be monotone non-decreasing in degradation "
            f"(best={cost_model.failure_hazard_at_best_level}, "
            f"worst={cost_model.failure_hazard_at_worst_level}) — a decreasing hazard destroys the "
            "control-limit structure of research/168 §3c"
        )
    if (
        not math.isfinite(cost_model.repair_restoration_fraction)
        or not 0.0 < cost_model.repair_restoration_fraction <= 1.0
    ):
        raise MaintenanceCostModelError(
            "repair_restoration_fraction must lie in (0, 1] — a repair that restores nothing is not a "
            f"maintenance action, got {cost_model.repair_restoration_fraction!r}"
        )
    if not math.isfinite(cost_model.discount_factor) or not 0.0 <= cost_model.discount_factor < 1.0:
        raise MaintenanceCostModelError(
            f"discount_factor must lie in [0, 1) for a convergent infinite-horizon solve, "
            f"got {cost_model.discount_factor!r}"
        )


def _degradation_level_fraction(level_index: int, degradation_level_count: int) -> float:
    """0.0 at the healthiest working level, 1.0 at the worst working level."""
    if degradation_level_count <= 1:
        return 1.0
    return level_index / (degradation_level_count - 1)


def _monitor_row_for_working_level(cost_model: MaintenanceCostModel, level_index: int) -> FloatArray:
    """One row of the natural (do-nothing) degradation kernel: monotone-worsening + failure hazard.

    Jump size follows a geometric law with mean `degradation_rate_levels_per_cycle`, so the component
    can never improve on its own (monotone worsening, research/168 §3a); all probability mass that would
    carry it past the worst working level folds into the absorbing FAILED state, on top of an explicit
    random-shock hazard that increases with degradation.
    """
    level_count = cost_model.degradation_level_count
    row = np.zeros(level_count + 1, dtype=np.float64)
    fraction = _degradation_level_fraction(level_index, level_count)
    shock_hazard = cost_model.failure_hazard_at_best_level + fraction * (
        cost_model.failure_hazard_at_worst_level - cost_model.failure_hazard_at_best_level
    )
    survive_probability = 1.0 - shock_hazard

    mean_jump = cost_model.degradation_rate_levels_per_cycle
    jump_continuation = mean_jump / (1.0 + mean_jump)  # geometric parameter q with mean q/(1-q)
    reachable_levels = level_count - 1 - level_index
    for jump in range(reachable_levels + 1):
        row[level_index + jump] = survive_probability * (1.0 - jump_continuation) * jump_continuation**jump
    # Geometric tail beyond the worst working level = wear-out failure.
    row[level_count] = shock_hazard + survive_probability * jump_continuation ** (reachable_levels + 1)
    return row


def build_degradation_transition_tensor(cost_model: MaintenanceCostModel) -> FloatArray:
    """`P[action, state, next_state]` for the four CBM actions (research/168 §3a).

    Uniform semantics: the action's restorative effect lands first, then ONE cycle of natural
    degradation elapses from wherever it landed. That uniformity is what makes the actions economically
    comparable — REPLACE is exactly REPAIR with restoration 1.0 and success 1.0, at a higher price.

    * MONITOR   — no restoration: natural monotone-worsening degradation, with the geometric wear-out
                  tail and the level-increasing shock hazard folding into the absorbing FAILED state.
    * REPAIR    — Kijima imperfect repair: with `repair_success_probability` the accumulated degradation
                  is cut by `repair_restoration_fraction` (from FAILED too, landing heavily degraded but
                  back in service); otherwise the component degrades as if unattended.
    * REPLACE   — as-good-as-new: degradation is reset to level 0 from any state, including FAILED.
    * QUARANTINE— removed from service: an absorbing self-loop paid for by a recurring service loss.
    """
    _validate_cost_model(cost_model)
    level_count = cost_model.degradation_level_count
    state_count = cost_model.total_state_count
    failed_index = cost_model.failed_state_index
    transition = np.zeros((len(MAINTENANCE_ACTION_ORDER), state_count, state_count), dtype=np.float64)

    monitor_index = _ACTION_SEVERITY_RANK[MaintenanceActionKind.MONITOR]
    repair_index = _ACTION_SEVERITY_RANK[MaintenanceActionKind.REPAIR]
    replace_index = _ACTION_SEVERITY_RANK[MaintenanceActionKind.REPLACE]
    quarantine_index = _ACTION_SEVERITY_RANK[MaintenanceActionKind.QUARANTINE]

    for level_index in range(level_count):
        transition[monitor_index, level_index, :] = _monitor_row_for_working_level(cost_model, level_index)
    transition[monitor_index, failed_index, failed_index] = 1.0

    # Kijima virtual-age restoration: level i carries i units of accumulated degradation; a successful
    # repair removes `repair_restoration_fraction` of them. FAILED is treated as carrying the full
    # `degradation_level_count` units, so repairing a failed component lands it heavily degraded.
    # The restored virtual age is generally FRACTIONAL, and it is embedded into the discretized state
    # space by linear interpolation across the two adjacent levels rather than by flooring. Flooring
    # quantizes the marginal value of a repair into a saw-tooth (gain 3, 3, 4, 4, ... levels) which
    # manufactures spurious single-level reversals in the solved policy — an artefact of the grid, not
    # of the economics.
    success = cost_model.repair_success_probability
    for state_index in range(state_count):
        accumulated_degradation = float(min(state_index, level_count))
        restored_virtual_age = accumulated_degradation * (1.0 - cost_model.repair_restoration_fraction)
        restored_virtual_age = min(max(restored_virtual_age, 0.0), float(level_count - 1))
        lower_level = int(math.floor(restored_virtual_age))
        upper_level = min(lower_level + 1, level_count - 1)
        upper_weight = restored_virtual_age - lower_level
        restored_row = (1.0 - upper_weight) * transition[monitor_index, lower_level, :] + (
            upper_weight * transition[monitor_index, upper_level, :]
        )
        transition[repair_index, state_index, :] = (
            success * restored_row + (1.0 - success) * transition[monitor_index, state_index, :]
        )

    transition[replace_index, :, :] = transition[monitor_index, 0, :]

    for state_index in range(state_count):
        transition[quarantine_index, state_index, state_index] = 1.0

    row_sums = transition.sum(axis=2)
    if not np.allclose(row_sums, 1.0, atol=1e-9):
        worst = float(np.max(np.abs(row_sums - 1.0)))
        raise MaintenanceCostModelError(
            f"transition rows must be probability distributions; worst row-sum error {worst:.3e}"
        )
    return transition


def build_stage_cost_matrix(cost_model: MaintenanceCostModel) -> FloatArray:
    """`C[state, action]`: the expected one-cycle cost of taking `action` in `state`.

    Running degraded is not free — `degraded_service_cost_at_worst_level` accrues in proportion to the
    degradation level, and the full `downtime_cost_per_cycle` accrues in FAILED. That monotone-in-state
    cost is one of the two structural conditions behind control-limit optimality (research/168 §3c).
    """
    _validate_cost_model(cost_model)
    level_count = cost_model.degradation_level_count
    state_count = cost_model.total_state_count

    in_service_loss = np.empty(state_count, dtype=np.float64)
    for level_index in range(level_count):
        degradation_fraction = (
            _degradation_level_fraction(level_index, level_count) if level_count > 1 else 0.0
        )
        in_service_loss[level_index] = cost_model.degraded_service_cost_at_worst_level * (
            degradation_fraction**DEGRADED_SERVICE_LOSS_CURVATURE_EXPONENT
        )
    in_service_loss[cost_model.failed_state_index] = cost_model.downtime_cost_per_cycle

    stage_costs = np.empty((state_count, len(MAINTENANCE_ACTION_ORDER)), dtype=np.float64)
    stage_costs[:, _ACTION_SEVERITY_RANK[MaintenanceActionKind.MONITOR]] = (
        cost_model.monitoring_cost_per_cycle + in_service_loss
    )
    stage_costs[:, _ACTION_SEVERITY_RANK[MaintenanceActionKind.REPAIR]] = (
        cost_model.monitoring_cost_per_cycle + cost_model.repair_cost + in_service_loss
    )
    stage_costs[:, _ACTION_SEVERITY_RANK[MaintenanceActionKind.REPLACE]] = (
        cost_model.monitoring_cost_per_cycle + cost_model.replace_cost + in_service_loss
    )
    stage_costs[:, _ACTION_SEVERITY_RANK[MaintenanceActionKind.QUARANTINE]] = (
        cost_model.quarantine_service_loss_cost_per_cycle
    )
    return stage_costs


# =====================================================================================================
# The hand-rolled Bellman value-iteration solver (research/168 §3a).
# =====================================================================================================


def run_bellman_value_iteration(
    transition_probabilities: FloatArray,
    stage_costs: FloatArray,
    discount_factor: float,
    tolerance: float = DEFAULT_VALUE_ITERATION_TOLERANCE,
    maximum_iterations: int = DEFAULT_MAXIMUM_VALUE_ITERATIONS,
) -> BellmanValueIterationResult:
    """Minimise `V(s) = min_a [ c(s,a) + γ Σ_{s'} P(s'|s,a) V(s') ]` to a sup-norm fixed point.

    Convergence test is the sup-norm of successive value iterates against the γ-scaled bound
    `tolerance·(1-γ)/(2γ)`, the standard criterion guaranteeing a `tolerance`-optimal value function;
    with `γ = 0` the Bellman operator is a single myopic backup and one sweep is exact.

    Rule O.3: exhausting `maximum_iterations` is REPORTED (`converged=False`, plus a WARNING log and the
    achieved `final_sup_norm_delta`), never raised away and never silently reported as success.
    """
    transitions = np.asarray(transition_probabilities, dtype=np.float64)
    costs = np.asarray(stage_costs, dtype=np.float64)

    if transitions.ndim != 3:
        raise MaintenanceCostModelError(
            f"transition tensor must be (actions, states, states), got shape {transitions.shape}"
        )
    action_count, state_count, next_state_count = transitions.shape
    if state_count != next_state_count or state_count < 1 or action_count < 1:
        raise MaintenanceCostModelError(
            f"transition tensor must be square in the state axis and non-empty, got {transitions.shape}"
        )
    if costs.shape != (state_count, action_count):
        raise MaintenanceCostModelError(
            f"stage-cost matrix must be (states, actions) = {(state_count, action_count)}, "
            f"got {costs.shape}"
        )
    if not np.all(np.isfinite(transitions)) or not np.all(np.isfinite(costs)):
        raise MaintenanceCostModelError(
            "transition probabilities and stage costs must all be finite (NaN/inf rejected outright: "
            "a NaN silently poisons every Bellman backup)"
        )
    if np.any(transitions < -1e-12) or not np.allclose(transitions.sum(axis=2), 1.0, atol=1e-8):
        raise MaintenanceCostModelError("each transition row must be a valid probability distribution")
    if not math.isfinite(discount_factor) or not 0.0 <= discount_factor < 1.0:
        raise MaintenanceCostModelError(
            f"discount_factor must lie in [0, 1), got {discount_factor!r}"
        )
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise MaintenanceCostModelError(f"tolerance must be finite and positive, got {tolerance!r}")
    if maximum_iterations < 1:
        raise MaintenanceCostModelError(
            f"maximum_iterations must be >= 1, got {maximum_iterations}"
        )

    # Sup-norm stopping bound: ||V_k - V*||_inf <= tolerance/2 once successive iterates differ by less.
    stopping_bound = (
        tolerance if discount_factor <= 0.0
        else tolerance * (1.0 - discount_factor) / (2.0 * discount_factor)
    )

    value_function = np.zeros(state_count, dtype=np.float64)
    action_values = np.empty((state_count, action_count), dtype=np.float64)
    converged = False
    iterations = 0
    sup_norm_delta = math.inf

    while iterations < maximum_iterations:
        iterations += 1
        # Q(s,a) = c(s,a) + gamma * sum_s' P(s'|s,a) V(s')  — einsum over the (a, s, s') tensor.
        np.einsum("asn,n->sa", transitions, value_function, out=action_values)
        action_values *= discount_factor
        action_values += costs
        updated_value_function = action_values.min(axis=1)
        sup_norm_delta = float(np.max(np.abs(updated_value_function - value_function)))
        value_function = updated_value_function
        if sup_norm_delta <= stopping_bound:
            converged = True
            break

    if not converged:
        LOGGER.warning(
            "maintenance-policy value iteration did NOT converge: %d iterations, sup-norm delta %.6g > "
            "bound %.6g (discount=%.4f). Policy is reported with converged=False (Rule O.3).",
            iterations, sup_norm_delta, stopping_bound, discount_factor,
        )

    # One final greedy backup so the reported policy is exactly greedy w.r.t. the reported values.
    np.einsum("asn,n->sa", transitions, value_function, out=action_values)
    action_values *= discount_factor
    action_values += costs
    greedy_action_indices = np.argmin(action_values, axis=1)

    return BellmanValueIterationResult(
        value_function=tuple(float(value) for value in value_function),
        greedy_action_indices=tuple(int(index) for index in greedy_action_indices),
        iterations_to_converge=iterations,
        converged=converged,
        final_sup_norm_delta=sup_norm_delta,
    )


# =====================================================================================================
# Policy → control-limit thresholds (research/168 §3c) + the monotonicity audit.
# =====================================================================================================


def find_policy_monotonicity_violations(
    action_by_degradation_level: tuple[MaintenanceActionKind, ...],
) -> tuple[tuple[int, int], ...]:
    """Levels where escalation severity DECREASES as degradation worsens.

    Returned as `(level, next_level)` pairs. A control-limit policy has none (research/168 §3c); any
    that exist are reported to the caller and to the log — never smoothed away, because a non-monotone
    optimum is real information about the cost structure that produced it.
    """
    violations: list[tuple[int, int]] = []
    for level_index in range(len(action_by_degradation_level) - 1):
        current_rank = _ACTION_SEVERITY_RANK[action_by_degradation_level[level_index]]
        next_rank = _ACTION_SEVERITY_RANK[action_by_degradation_level[level_index + 1]]
        if next_rank < current_rank:
            violations.append((level_index, level_index + 1))
    return tuple(violations)


def _first_level_at_or_above_severity(
    action_by_degradation_level: tuple[MaintenanceActionKind, ...], action: MaintenanceActionKind
) -> int:
    """Lowest degradation level whose prescribed action is at least as severe as `action`."""
    target_rank = _ACTION_SEVERITY_RANK[action]
    for level_index, prescribed in enumerate(action_by_degradation_level):
        if _ACTION_SEVERITY_RANK[prescribed] >= target_rank:
            return level_index
    return len(action_by_degradation_level)


def _highest_level_still_monitoring(
    action_by_degradation_level: tuple[MaintenanceActionKind, ...],
) -> int:
    """Top of the passive-monitoring region; `-1` when monitoring is never optimal."""
    highest = -1
    for level_index, prescribed in enumerate(action_by_degradation_level):
        if prescribed is MaintenanceActionKind.MONITOR:
            highest = level_index
    return highest


def build_control_limit_policy_from_solution(
    component_class: str, solution: BellmanValueIterationResult
) -> MaintenanceControlLimitPolicy:
    """Express a solved value function as the deployable threshold table."""
    action_by_degradation_level = tuple(
        MAINTENANCE_ACTION_ORDER[action_index] for action_index in solution.greedy_action_indices
    )
    monitor_threshold_level = _highest_level_still_monitoring(action_by_degradation_level)
    repair_threshold_level = _first_level_at_or_above_severity(
        action_by_degradation_level, MaintenanceActionKind.REPAIR
    )
    replace_threshold_level = _first_level_at_or_above_severity(
        action_by_degradation_level, MaintenanceActionKind.REPLACE
    )
    violations = find_policy_monotonicity_violations(action_by_degradation_level)
    # research/172 §5.5 acceptance bar, stated literally: repair threshold >= monitor threshold.
    is_monotone = not violations and repair_threshold_level >= monitor_threshold_level
    if not is_monotone:
        LOGGER.warning(
            "maintenance policy for %s is NOT a monotone control limit: severity reversals at %s, "
            "monitor_threshold=%d, repair_threshold=%d. Reported as-is (research/172 §5.5).",
            component_class, violations, monitor_threshold_level, repair_threshold_level,
        )
    return MaintenanceControlLimitPolicy(
        component_class=component_class,
        action_by_degradation_level=action_by_degradation_level,
        monitor_threshold_level=monitor_threshold_level,
        repair_threshold_level=repair_threshold_level,
        replace_threshold_level=replace_threshold_level,
        is_monotone=is_monotone,
        value_function=solution.value_function,
        iterations_to_converge=solution.iterations_to_converge,
        converged=solution.converged,
    )


def solve_maintenance_control_limit_policy(
    cost_model: MaintenanceCostModel,
    tolerance: float = DEFAULT_VALUE_ITERATION_TOLERANCE,
    maximum_iterations: int = DEFAULT_MAXIMUM_VALUE_ITERATIONS,
) -> MaintenanceControlLimitPolicy:
    """Build the CBM MDP from `cost_model`, solve it, and return the control-limit threshold table."""
    transition = build_degradation_transition_tensor(cost_model)
    stage_costs = build_stage_cost_matrix(cost_model)
    solution = run_bellman_value_iteration(
        transition_probabilities=transition,
        stage_costs=stage_costs,
        discount_factor=cost_model.discount_factor,
        tolerance=tolerance,
        maximum_iterations=maximum_iterations,
    )
    return build_control_limit_policy_from_solution(cost_model.component_class, solution)


# =====================================================================================================
# Cadence solve (whole organism) + the O(1) runtime lookup.
# =====================================================================================================


def solve_maintenance_policy_table(
    registry: OrganismComponentRegistry | None = None,
    degradation_level_count: int = DEFAULT_DEGRADATION_LEVEL_COUNT,
    discount_factor: float = DEFAULT_DISCOUNT_FACTOR,
    cost_model_overrides: Mapping[str, MaintenanceCostModel] | None = None,
    solved_at_utc: datetime | None = None,
) -> MaintenancePolicyTable:
    """Solve one control-limit policy per (component class, criticality) cohort present in the organism.

    This is the CADENCE-side entry point of research/168 §3c: run it hourly, hand the resulting table to
    the trading loop, and let the loop do nothing but `select_action_for_component` lookups.
    `cost_model_overrides` is keyed by cohort key and is how refined (Rule Q) models are injected.
    """
    active_registry = registry if registry is not None else build_default_component_registry()
    overrides = dict(cost_model_overrides or {})

    policies: dict[str, MaintenanceControlLimitPolicy] = {}
    non_monotone: list[str] = []
    non_converged: list[str] = []
    for component in active_registry.self_components():
        cohort_key = build_component_cohort_key(component.component_class, component.criticality)
        if cohort_key in policies:
            continue
        cost_model = overrides.get(cohort_key) or build_cost_model_for_component_class(
            component_class=component.component_class,
            criticality=component.criticality,
            degradation_level_count=degradation_level_count,
            discount_factor=discount_factor,
        )
        policy = solve_maintenance_control_limit_policy(cost_model)
        policies[cohort_key] = policy
        if not policy.is_monotone:
            non_monotone.append(cohort_key)
        if not policy.converged:
            non_converged.append(cohort_key)

    if non_monotone or non_converged:
        LOGGER.warning(
            "maintenance policy table solved with findings: non-monotone cohorts=%s, "
            "non-converged cohorts=%s",
            tuple(non_monotone), tuple(non_converged),
        )
    return MaintenancePolicyTable(
        policy_by_cohort_key=policies,
        solved_at_utc=solved_at_utc or datetime.now(UTC),
        non_monotone_cohort_keys=tuple(non_monotone),
        non_converged_cohort_keys=tuple(non_converged),
    )


def discretize_health_index_to_degradation_level(
    health_index: float, degradation_level_count: int
) -> int:
    """Map `h ∈ [0,1]` (1 = perfectly healthy, research/172 §2) to a policy-table index.

    `h = 0.0` — or a non-finite health index, which means the health engine could not form an estimate —
    maps to the absorbing FAILED index. Treating "unknown" as failed is the fail-safe direction: the
    homeostat may only tighten, never relax (research/172 §2 sign conventions).
    """
    if degradation_level_count < 1:
        raise MaintenanceCostModelError(
            f"degradation_level_count must be >= 1, got {degradation_level_count}"
        )
    if not math.isfinite(health_index):
        LOGGER.warning(
            "non-finite health_index %r fed to the maintenance lookup — treated as FAILED (fail-safe)",
            health_index,
        )
        return degradation_level_count
    clamped_health = min(max(health_index, 0.0), 1.0)
    if clamped_health <= 0.0:
        return degradation_level_count
    level_index = int(math.floor((1.0 - clamped_health) * degradation_level_count))
    return min(max(level_index, 0), degradation_level_count - 1)


def select_maintenance_action(
    policy: MaintenanceControlLimitPolicy, health_index: float
) -> MaintenanceActionKind:
    """The runtime lookup: O(1) discretization plus one tuple index. No solving in the decision path."""
    if not policy.action_by_degradation_level:
        raise MaintenanceCostModelError("policy has an empty action table — nothing to look up")
    level_index = discretize_health_index_to_degradation_level(
        health_index, policy.degradation_level_count
    )
    return policy.action_by_degradation_level[level_index]


def select_action_for_component(
    table: MaintenancePolicyTable, component: RegisteredComponent, health_index: float
) -> MaintenanceActionKind | None:
    """Cohort lookup + action lookup. `None` when the cohort has no solved policy (never a guess)."""
    policy = table.policy_for_component(component)
    if policy is None:
        LOGGER.warning(
            "no solved maintenance policy for cohort %s (component %s) — no action selected",
            build_component_cohort_key(component.component_class, component.criticality),
            component.component_id,
        )
        return None
    return select_maintenance_action(policy, health_index)
