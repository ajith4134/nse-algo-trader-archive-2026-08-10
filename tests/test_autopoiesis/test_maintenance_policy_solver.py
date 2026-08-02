"""Tests for the CBM maintenance-policy MDP solver (research/168 §3, research/172 §5.5).

Four layers, in increasing order of what they can catch:

1. **Numerical cross-check against `pymdptoolbox`** — an independent implementation of the same maths,
   kept in the dev extras for exactly this (research/172 §10). If our hand-rolled Bellman recursion is
   wrong, this fails.
2. **Known-optimal toy MDPs solved by hand on paper** — catches errors the cross-check cannot, because
   both implementations could in principle share a convention mistake.
3. **Structural + economic acceptance bars from research/172 §5.5** — monotone control limits, and the
   comparative statics that make the policy decision-grade rather than merely well-typed.
4. **Adversarial / degenerate input** (Rule O.4) and **honest non-convergence reporting** (Rule O.3).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    ComponentCriticality,
    ComponentMembership,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.maintenance_policy_solver import (
    DEFAULT_DEGRADATION_LEVEL_COUNT,
    MAINTENANCE_ACTION_ORDER,
    BellmanValueIterationResult,
    MaintenanceActionKind,
    MaintenanceControlLimitPolicy,
    MaintenanceCostModelError,
    build_component_cohort_key,
    build_control_limit_policy_from_solution,
    build_cost_model_for_component_class,
    build_degradation_transition_tensor,
    build_stage_cost_matrix,
    discretize_health_index_to_degradation_level,
    find_policy_monotonicity_violations,
    refine_cost_model_with_observed_repairs,
    run_bellman_value_iteration,
    select_action_for_component,
    select_maintenance_action,
    solve_maintenance_control_limit_policy,
    solve_maintenance_policy_table,
)

EXACT_TOLERANCE = 1e-9
CROSS_CHECK_TOLERANCE = 1e-8


def _persistent_store_cost_model(**overrides: object):
    model = build_cost_model_for_component_class(
        ComponentClass.PERSISTENT_STORE, ComponentCriticality.SUPPORTING
    )
    return dataclasses.replace(model, **overrides)  # type: ignore[arg-type]


def _random_toy_mdp(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, float]:
    """A small dense MDP with strictly positive transition mass and bounded costs."""
    state_count = int(rng.integers(2, 7))
    action_count = int(rng.integers(2, 5))
    transitions = rng.random((action_count, state_count, state_count)) + 1e-3
    transitions /= transitions.sum(axis=2, keepdims=True)
    stage_costs = rng.random((state_count, action_count)) * 10.0
    discount_factor = float(rng.uniform(0.5, 0.95))
    return transitions, stage_costs, discount_factor


# -- 1. cross-check against pymdptoolbox -------------------------------------------------------------


def _import_pymdptoolbox_or_skip():
    try:
        import mdptoolbox.mdp as pymdptoolbox_mdp
    except ImportError as import_error:  # pragma: no cover - environment-dependent
        pytest.skip(
            "pymdptoolbox is not importable, so the independent numerical cross-check of the Bellman "
            f"solver CANNOT run ({import_error}). It is declared in the [dev] extra for exactly this "
            "purpose — install it with `pip install 'pymdptoolbox>=4.0b3'`. This test is SKIPPED, not "
            "passed: the value function is unverified against a second implementation in this run."
        )
    return pymdptoolbox_mdp


def test_value_function_matches_pymdptoolbox_on_random_toy_mdps() -> None:
    """Our minimising value iteration must equal pymdptoolbox's exact maximising policy iteration.

    pymdptoolbox maximises reward, so it is handed `-stage_costs` and its `V` must equal `-V_ours`.
    `PolicyIteration` is used as the reference because it solves the evaluation step as a linear system
    and therefore returns the EXACT `V*`, with no iteration-count caveat of its own.
    """
    pymdptoolbox_mdp = _import_pymdptoolbox_or_skip()
    rng = np.random.default_rng(20260727)

    worst_absolute_difference = 0.0
    for _ in range(30):
        transitions, stage_costs, discount_factor = _random_toy_mdp(rng)
        ours = run_bellman_value_iteration(
            transitions, stage_costs, discount_factor, tolerance=1e-12, maximum_iterations=200_000
        )
        reference = pymdptoolbox_mdp.PolicyIteration(transitions, -stage_costs, discount_factor)
        reference.run()

        assert ours.converged
        for our_value, reference_value in zip(ours.value_function, reference.V, strict=True):
            worst_absolute_difference = max(
                worst_absolute_difference, abs(our_value + reference_value)
            )
    assert worst_absolute_difference < CROSS_CHECK_TOLERANCE, worst_absolute_difference


def test_greedy_policy_matches_pymdptoolbox_value_iteration_on_random_toy_mdps() -> None:
    """The ACTION choice must agree with pymdptoolbox's own value iteration on every state.

    Note we compare pymdptoolbox's *policy* rather than its *value function* here: its
    `ValueIteration` caps itself with an internal span-based iteration bound (`_boundIter`), so its
    reported `V` can sit a constant off `V*` even at epsilon=1e-12 while its argmin is already correct.
    Discovering that is precisely what an independent cross-check is for — it is recorded here rather
    than papered over.
    """
    pymdptoolbox_mdp = _import_pymdptoolbox_or_skip()
    rng = np.random.default_rng(4242)

    for _ in range(30):
        transitions, stage_costs, discount_factor = _random_toy_mdp(rng)
        ours = run_bellman_value_iteration(
            transitions, stage_costs, discount_factor, tolerance=1e-12, maximum_iterations=200_000
        )
        reference = pymdptoolbox_mdp.ValueIteration(
            transitions, -stage_costs, discount_factor, epsilon=1e-12, max_iter=100_000
        )
        reference.run()
        assert tuple(reference.policy) == ours.greedy_action_indices


def test_real_cbm_instance_matches_pymdptoolbox() -> None:
    """The cross-check on the REAL organism cost structure, not just abstract random matrices."""
    pymdptoolbox_mdp = _import_pymdptoolbox_or_skip()
    cost_model = build_cost_model_for_component_class(
        ComponentClass.PERSISTENT_STORE, ComponentCriticality.VITAL
    )
    transitions = build_degradation_transition_tensor(cost_model)
    stage_costs = build_stage_cost_matrix(cost_model)

    ours = run_bellman_value_iteration(
        transitions, stage_costs, cost_model.discount_factor,
        tolerance=1e-12, maximum_iterations=500_000,
    )
    reference = pymdptoolbox_mdp.PolicyIteration(
        transitions, -stage_costs, cost_model.discount_factor
    )
    reference.run()

    assert ours.converged
    assert tuple(reference.policy) == ours.greedy_action_indices
    for our_value, reference_value in zip(ours.value_function, reference.V, strict=True):
        assert abs(our_value + reference_value) < CROSS_CHECK_TOLERANCE


# -- 2. known-optimal toy MDPs solved by hand --------------------------------------------------------


def _hand_solvable_two_state_mdp() -> tuple[np.ndarray, np.ndarray]:
    """States {0, 1}; actions {stay, escape}.

    * state 0, action `stay`   — self-loop forever at cost 2/cycle  → V = 2 / (1 - γ)
    * state 0, action `escape` — one-off cost 10, lands in the free absorbing state 1 → V = 10
    * state 1 — absorbing and free under both actions               → V = 0

    Both branches are closed-form, so the optimum is exact arithmetic, not a numerical estimate.
    """
    transitions = np.array(
        [
            [[1.0, 0.0], [0.0, 1.0]],  # stay
            [[0.0, 1.0], [0.0, 1.0]],  # escape
        ]
    )
    stage_costs = np.array([[2.0, 10.0], [0.0, 0.0]])
    return transitions, stage_costs


def test_hand_solved_toy_mdp_prefers_escaping_when_patient() -> None:
    transitions, stage_costs = _hand_solvable_two_state_mdp()
    result = run_bellman_value_iteration(transitions, stage_costs, 0.9, tolerance=1e-14)

    # stay = 2/(1-0.9) = 20 ; escape = 10 → escape wins, V(0) = 10 exactly.
    assert result.converged
    assert result.greedy_action_indices == (1, 0)
    assert result.value_function[0] == pytest.approx(10.0, abs=EXACT_TOLERANCE)
    assert result.value_function[1] == pytest.approx(0.0, abs=EXACT_TOLERANCE)


def test_hand_solved_toy_mdp_prefers_staying_when_impatient() -> None:
    transitions, stage_costs = _hand_solvable_two_state_mdp()
    result = run_bellman_value_iteration(transitions, stage_costs, 0.5, tolerance=1e-14)

    # stay = 2/(1-0.5) = 4 ; escape = 10 → stay wins, V(0) = 4 exactly. The SAME MDP flips its optimal
    # action purely on the discount factor, so this also pins down that gamma is applied at all.
    assert result.greedy_action_indices == (0, 0)
    assert result.value_function[0] == pytest.approx(4.0, abs=EXACT_TOLERANCE)


def test_single_state_single_action_mdp_is_the_closed_form_geometric_sum() -> None:
    """1-state space (Rule O.4 degenerate guard): V = c / (1 - γ), the geometric series."""
    result = run_bellman_value_iteration(
        np.ones((1, 1, 1)), np.array([[3.0]]), 0.9, tolerance=1e-14, maximum_iterations=100_000
    )
    assert result.converged
    assert result.value_function[0] == pytest.approx(30.0, abs=1e-7)
    assert result.greedy_action_indices == (0,)


def test_zero_discount_factor_gives_the_myopic_policy_in_one_sweep() -> None:
    """γ = 0 collapses the Bellman operator to `min_a c(s, a)` — pure myopia, exactly solvable."""
    transitions = np.array([[[0.0, 1.0], [1.0, 0.0]], [[1.0, 0.0], [0.0, 1.0]]])
    stage_costs = np.array([[7.0, 2.0], [1.0, 9.0]])
    result = run_bellman_value_iteration(transitions, stage_costs, 0.0)

    assert result.converged
    assert result.iterations_to_converge <= 2
    assert result.value_function == pytest.approx((2.0, 1.0))
    assert result.greedy_action_indices == (1, 0)


# -- 3a. the MDP instance: transition + cost structure -----------------------------------------------


def test_transition_rows_are_probability_distributions_for_every_action() -> None:
    cost_model = _persistent_store_cost_model()
    transitions = build_degradation_transition_tensor(cost_model)
    assert transitions.shape == (
        len(MAINTENANCE_ACTION_ORDER),
        cost_model.total_state_count,
        cost_model.total_state_count,
    )
    assert np.all(transitions >= 0.0)
    assert np.allclose(transitions.sum(axis=2), 1.0)


def test_monitoring_degradation_is_monotone_worsening_and_failure_is_absorbing() -> None:
    """A component left alone can never spontaneously get healthier (research/168 §3a)."""
    cost_model = _persistent_store_cost_model()
    transitions = build_degradation_transition_tensor(cost_model)
    monitor = transitions[MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.MONITOR)]

    for level_index in range(cost_model.degradation_level_count):
        assert np.allclose(monitor[level_index, :level_index], 0.0), level_index
    failed_index = cost_model.failed_state_index
    assert monitor[failed_index, failed_index] == pytest.approx(1.0)


def test_failure_hazard_and_degraded_service_cost_increase_with_degradation() -> None:
    """The two structural conditions behind control-limit optimality (research/168 §3c)."""
    cost_model = _persistent_store_cost_model()
    transitions = build_degradation_transition_tensor(cost_model)
    stage_costs = build_stage_cost_matrix(cost_model)
    monitor_index = MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.MONITOR)
    failed_index = cost_model.failed_state_index

    failure_probabilities = [
        transitions[monitor_index, level, failed_index]
        for level in range(cost_model.degradation_level_count)
    ]
    assert failure_probabilities == sorted(failure_probabilities)
    monitor_costs = list(stage_costs[: cost_model.degradation_level_count, monitor_index])
    assert monitor_costs == sorted(monitor_costs)


def test_replace_resets_to_a_brand_new_component_and_quarantine_is_absorbing() -> None:
    cost_model = _persistent_store_cost_model()
    transitions = build_degradation_transition_tensor(cost_model)
    monitor_index = MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.MONITOR)
    replace_index = MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.REPLACE)
    quarantine_index = MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.QUARANTINE)

    for state_index in range(cost_model.total_state_count):
        # As-good-as-new: the successor distribution is a brand-new component's, from any state.
        assert np.allclose(transitions[replace_index, state_index], transitions[monitor_index, 0])
        # Out of service: quarantine never changes the state.
        assert transitions[quarantine_index, state_index, state_index] == pytest.approx(1.0)


def test_repair_restores_degradation_proportionally_and_can_recover_a_failed_component() -> None:
    cost_model = _persistent_store_cost_model(repair_success_probability=1.0)
    transitions = build_degradation_transition_tensor(cost_model)
    monitor_index = MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.MONITOR)
    repair_index = MAINTENANCE_ACTION_ORDER.index(MaintenanceActionKind.REPAIR)
    failed_index = cost_model.failed_state_index

    # A certain repair from FAILED puts the component back INTO SERVICE (mass off the absorbing state).
    assert transitions[repair_index, failed_index, failed_index] < 1.0
    # A certain repair strictly reduces expected degradation relative to leaving it alone.
    level_indices = np.arange(cost_model.total_state_count, dtype=float)
    for state_index in range(1, cost_model.total_state_count):
        repaired_mean = float(transitions[repair_index, state_index] @ level_indices)
        unattended_mean = float(transitions[monitor_index, state_index] @ level_indices)
        assert repaired_mean < unattended_mean, state_index


# -- 3b. research/172 §5.5 acceptance bars -----------------------------------------------------------


def test_every_shipped_cohort_solves_to_a_monotone_control_limit() -> None:
    """research/172 §5.5: 'MDP policy is a monotone control-limit: repair threshold >= monitor'."""
    for component_class in ComponentClass:
        for criticality in ComponentCriticality:
            cost_model = build_cost_model_for_component_class(component_class, criticality)
            policy = solve_maintenance_control_limit_policy(cost_model)
            label = policy.component_class

            assert policy.converged, label
            assert find_policy_monotonicity_violations(policy.action_by_degradation_level) == (), label
            assert policy.repair_threshold_level >= policy.monitor_threshold_level, label
            assert policy.replace_threshold_level >= policy.repair_threshold_level, label
            assert policy.is_monotone, label
            assert len(policy.action_by_degradation_level) == cost_model.total_state_count


def test_monotone_control_limit_holds_across_grid_resolutions() -> None:
    """The control-limit structure must be a property of the economics, not of the discretization."""
    for degradation_level_count in (2, 4, 8, 12, 20, 40):
        for criticality in (ComponentCriticality.VITAL, ComponentCriticality.ANCILLARY):
            cost_model = build_cost_model_for_component_class(
                ComponentClass.PERSISTED_ARTIFACT,
                criticality,
                degradation_level_count=degradation_level_count,
            )
            policy = solve_maintenance_control_limit_policy(cost_model)
            assert policy.is_monotone, (degradation_level_count, criticality)


def test_non_monotone_policy_is_reported_and_never_smoothed_away() -> None:
    """A severity reversal must surface in `is_monotone`, with the offending levels retrievable."""
    reversed_actions = (
        MaintenanceActionKind.MONITOR,
        MaintenanceActionKind.REPLACE,
        MaintenanceActionKind.REPAIR,   # <- severity DROPS as degradation worsens
        MaintenanceActionKind.QUARANTINE,
    )
    solution = BellmanValueIterationResult(
        value_function=(1.0, 2.0, 3.0, 4.0),
        greedy_action_indices=tuple(
            MAINTENANCE_ACTION_ORDER.index(action) for action in reversed_actions
        ),
        iterations_to_converge=11,
        converged=True,
        final_sup_norm_delta=0.0,
    )
    policy = build_control_limit_policy_from_solution("synthetic/reversal", solution)

    assert policy.is_monotone is False
    assert find_policy_monotonicity_violations(policy.action_by_degradation_level) == ((1, 2),)
    # Reported, not smoothed: the actions come back exactly as the solver produced them.
    assert policy.action_by_degradation_level == reversed_actions


def test_monitor_threshold_above_repair_threshold_is_flagged_even_without_a_reversal() -> None:
    """The literal §5.5 bar is checked in its own right, not only via the severity sequence."""
    actions = (MaintenanceActionKind.REPAIR, MaintenanceActionKind.REPAIR, MaintenanceActionKind.MONITOR)
    solution = BellmanValueIterationResult(
        value_function=(0.0, 0.0, 0.0),
        greedy_action_indices=tuple(MAINTENANCE_ACTION_ORDER.index(action) for action in actions),
        iterations_to_converge=1,
        converged=True,
        final_sup_norm_delta=0.0,
    )
    policy = build_control_limit_policy_from_solution("synthetic/late-monitor", solution)
    assert policy.monitor_threshold_level == 2
    assert policy.repair_threshold_level == 0
    assert policy.is_monotone is False


# -- 3c. economic sanity (comparative statics) -------------------------------------------------------


def test_raising_repair_cost_pushes_the_repair_threshold_to_worse_degradation() -> None:
    """Dearer repairs must be deferred, never brought forward — and eventually abandoned entirely."""
    thresholds: list[int] = []
    for repair_cost in (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 64.0, 256.0):
        policy = solve_maintenance_control_limit_policy(
            _persistent_store_cost_model(repair_cost=repair_cost)
        )
        assert policy.converged
        thresholds.append(policy.repair_threshold_level)

    assert thresholds == sorted(thresholds), thresholds
    assert thresholds[-1] > thresholds[0], thresholds


def test_lowering_replace_cost_pulls_the_replace_threshold_toward_healthier_states() -> None:
    thresholds: list[int] = []
    for replace_cost in (200.0, 100.0, 50.0, 25.0, 12.0, 6.0, 3.0):
        policy = solve_maintenance_control_limit_policy(
            _persistent_store_cost_model(replace_cost=replace_cost)
        )
        thresholds.append(policy.replace_threshold_level)
    assert thresholds == sorted(thresholds, reverse=True), thresholds


def test_vital_components_repair_earlier_than_ancillary_ones_with_identical_dynamics() -> None:
    """Criticality scales SERVICE-LOSS only, so the same machine gets maintained harder when it matters.

    Every component class is checked, because this is the mechanism that makes the vitality gate of
    research/172 §9 differ between `store.market_data` (VITAL) and an observability-only component.
    """
    for component_class in ComponentClass:
        thresholds = {}
        for criticality in (
            ComponentCriticality.VITAL,
            ComponentCriticality.SUPPORTING,
            ComponentCriticality.ANCILLARY,
        ):
            cost_model = build_cost_model_for_component_class(component_class, criticality)
            # Dynamics really are identical across the three — only the loss scaling differs.
            assert cost_model.repair_cost == pytest.approx(
                build_cost_model_for_component_class(
                    component_class, ComponentCriticality.VITAL
                ).repair_cost
            )
            thresholds[criticality] = solve_maintenance_control_limit_policy(
                cost_model
            ).repair_threshold_level

        assert (
            thresholds[ComponentCriticality.VITAL]
            < thresholds[ComponentCriticality.ANCILLARY]
        ), (component_class, thresholds)
        assert (
            thresholds[ComponentCriticality.VITAL]
            <= thresholds[ComponentCriticality.SUPPORTING]
            <= thresholds[ComponentCriticality.ANCILLARY]
        ), (component_class, thresholds)


def test_quarantine_wins_when_restoring_the_component_is_ruinously_expensive() -> None:
    """The fourth lever must be reachable, not decorative — and still a monotone control limit."""
    policy = solve_maintenance_control_limit_policy(
        _persistent_store_cost_model(
            repair_cost=800.0,
            replace_cost=5_000.0,
            quarantine_service_loss_cost_per_cycle=1.0,
        )
    )
    assert MaintenanceActionKind.QUARANTINE in policy.action_by_degradation_level
    assert policy.failed_state_action is MaintenanceActionKind.QUARANTINE
    assert policy.is_monotone


def test_value_function_increases_with_degradation() -> None:
    """Cost-to-go must be worse for a sicker component — the ordering the dashboard reads."""
    policy = solve_maintenance_control_limit_policy(_persistent_store_cost_model())
    values = list(policy.value_function)
    assert values == sorted(values), values


# -- 4a. convergence reporting (Rule O.3) ------------------------------------------------------------


def test_well_posed_instance_reports_converged_with_a_finite_iteration_count() -> None:
    policy = solve_maintenance_control_limit_policy(_persistent_store_cost_model())
    assert policy.converged is True
    assert 0 < policy.iterations_to_converge < 20_000


def test_pathological_instance_reports_non_convergence_instead_of_lying() -> None:
    """A discount factor at the edge of 1 with a tiny iteration cap CANNOT converge — say so."""
    cost_model = _persistent_store_cost_model(discount_factor=0.999999)
    policy = solve_maintenance_control_limit_policy(cost_model, maximum_iterations=5)

    assert policy.converged is False
    assert policy.iterations_to_converge == 5
    # It still returns a usable (if unconverged) table rather than raising — the caller decides.
    assert len(policy.action_by_degradation_level) == cost_model.total_state_count


def test_non_convergence_propagates_into_the_policy_table_findings() -> None:
    registry = OrganismComponentRegistry(
        components=(
            RegisteredComponent(
                "test.hermetic_store",
                ComponentClass.PERSISTENT_STORE,
                ComponentCriticality.VITAL,
                maintained_by=(),
            ),
        )
    )
    table = solve_maintenance_policy_table(registry=registry, discount_factor=0.5)
    assert table.non_converged_cohort_keys == ()
    assert table.non_monotone_cohort_keys == ()
    assert len(table.policy_by_cohort_key) == 1


# -- 4b. adversarial / degenerate input (Rule O.4) ---------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("repair_cost", float("nan")),
        ("replace_cost", float("inf")),
        ("downtime_cost_per_cycle", float("-inf")),
        ("monitoring_cost_per_cycle", -1.0),
        ("quarantine_service_loss_cost_per_cycle", -0.001),
        ("degraded_service_cost_at_worst_level", float("nan")),
        ("degradation_rate_levels_per_cycle", float("nan")),
        ("degradation_rate_levels_per_cycle", -0.5),
        ("failure_hazard_at_worst_level", 1.5),
        ("failure_hazard_at_worst_level", float("nan")),
        ("repair_success_probability", -0.1),
        ("repair_restoration_fraction", 0.0),
        ("repair_restoration_fraction", 1.5),
        ("degradation_level_count", 0),
        ("degradation_level_count", -3),
        ("discount_factor", 1.0),
        ("discount_factor", 1.5),
        ("discount_factor", -0.1),
        ("discount_factor", float("nan")),
    ],
)
def test_degenerate_cost_models_raise_a_named_error(field_name: str, value: object) -> None:
    with pytest.raises(MaintenanceCostModelError):
        solve_maintenance_control_limit_policy(_persistent_store_cost_model(**{field_name: value}))


def test_decreasing_failure_hazard_is_rejected_because_it_destroys_control_limit_structure() -> None:
    with pytest.raises(MaintenanceCostModelError, match="monotone"):
        solve_maintenance_control_limit_policy(
            _persistent_store_cost_model(
                failure_hazard_at_best_level=0.9, failure_hazard_at_worst_level=0.1
            )
        )


def test_all_equal_costs_still_solve_and_prefer_the_cheapest_available_action() -> None:
    """Degenerate but well-posed: no action dominates on price, so dynamics alone decide."""
    policy = solve_maintenance_control_limit_policy(
        _persistent_store_cost_model(
            monitoring_cost_per_cycle=1.0,
            repair_cost=0.0,
            replace_cost=0.0,
            downtime_cost_per_cycle=1.0,
            quarantine_service_loss_cost_per_cycle=1.0,
            degraded_service_cost_at_worst_level=1.0,
        )
    )
    assert policy.converged
    assert all(math.isfinite(value) for value in policy.value_function)


def test_single_degradation_level_is_solvable() -> None:
    """The smallest legal CBM instance: one working level plus the FAILED absorbing state."""
    policy = solve_maintenance_control_limit_policy(
        _persistent_store_cost_model(degradation_level_count=1)
    )
    assert policy.converged
    assert len(policy.action_by_degradation_level) == 2
    assert policy.is_monotone


@pytest.mark.parametrize(
    ("transitions", "stage_costs", "discount_factor"),
    [
        (np.ones((1, 1, 1)), np.array([[float("nan")]]), 0.9),
        (np.ones((1, 1, 1)), np.array([[float("inf")]]), 0.9),
        (np.array([[[0.5, 0.4]]]), np.array([[1.0]]), 0.9),          # rows do not sum to 1
        (np.array([[[1.0, 0.0], [0.0, 1.0]]]), np.array([[1.0]]), 0.9),  # cost shape mismatch
        (np.ones((2, 2)), np.array([[1.0, 1.0], [1.0, 1.0]]), 0.9),  # not a 3-D tensor
        (np.zeros((1, 0, 0)), np.zeros((0, 1)), 0.9),                # empty state space
        (np.ones((1, 1, 1)), np.array([[1.0]]), 1.0),                # undiscounted
    ],
)
def test_malformed_mdp_instances_raise_rather_than_returning_nonsense(
    transitions: np.ndarray, stage_costs: np.ndarray, discount_factor: float
) -> None:
    with pytest.raises(MaintenanceCostModelError):
        run_bellman_value_iteration(transitions, stage_costs, discount_factor)


@pytest.mark.parametrize(("tolerance", "maximum_iterations"), [(0.0, 100), (-1.0, 100), (1e-9, 0)])
def test_invalid_solver_knobs_raise(tolerance: float, maximum_iterations: int) -> None:
    with pytest.raises(MaintenanceCostModelError):
        run_bellman_value_iteration(
            np.ones((1, 1, 1)), np.array([[1.0]]), 0.9,
            tolerance=tolerance, maximum_iterations=maximum_iterations,
        )


# -- 5. the runtime lookup ---------------------------------------------------------------------------


def test_health_index_discretization_covers_the_whole_unit_interval() -> None:
    level_count = 10
    assert discretize_health_index_to_degradation_level(1.0, level_count) == 0
    assert discretize_health_index_to_degradation_level(0.95, level_count) == 0
    assert discretize_health_index_to_degradation_level(0.85, level_count) == 1
    assert discretize_health_index_to_degradation_level(0.05, level_count) == 9
    # h = 0.0 is the FAILED absorbing state, not merely "very degraded".
    assert discretize_health_index_to_degradation_level(0.0, level_count) == level_count
    # Out-of-range health clamps rather than indexing out of the table.
    assert discretize_health_index_to_degradation_level(7.0, level_count) == 0
    assert discretize_health_index_to_degradation_level(-7.0, level_count) == level_count
    # An unknown (non-finite) health index fails SAFE: treated as failed, never as healthy.
    assert discretize_health_index_to_degradation_level(float("nan"), level_count) == level_count


def test_discretization_is_monotone_non_increasing_in_health() -> None:
    level_count = DEFAULT_DEGRADATION_LEVEL_COUNT
    levels = [
        discretize_health_index_to_degradation_level(health / 100.0, level_count)
        for health in range(100, -1, -1)
    ]
    assert levels == sorted(levels)


def test_select_maintenance_action_escalates_as_health_falls() -> None:
    policy = solve_maintenance_control_limit_policy(
        build_cost_model_for_component_class(
            ComponentClass.PERSISTENT_STORE, ComponentCriticality.VITAL
        )
    )
    severity_by_health = [
        MAINTENANCE_ACTION_ORDER.index(select_maintenance_action(policy, health / 100.0))
        for health in range(100, -1, -1)
    ]
    assert severity_by_health == sorted(severity_by_health)
    assert select_maintenance_action(policy, 1.0) is MaintenanceActionKind.MONITOR
    assert select_maintenance_action(policy, 0.0) is policy.failed_state_action
    assert select_maintenance_action(policy, float("nan")) is policy.failed_state_action


def test_select_maintenance_action_rejects_an_empty_policy_table() -> None:
    empty_policy = MaintenanceControlLimitPolicy(
        component_class="empty",
        action_by_degradation_level=(),
        monitor_threshold_level=-1,
        repair_threshold_level=0,
        replace_threshold_level=0,
        is_monotone=True,
        value_function=(),
        iterations_to_converge=0,
        converged=True,
    )
    with pytest.raises(MaintenanceCostModelError):
        select_maintenance_action(empty_policy, 0.5)


# -- 6. the cadence-solved table over the REAL organism registry -------------------------------------


def test_policy_table_covers_every_self_component_of_the_real_registry() -> None:
    """Rule F-adjacent: solved against the REAL declared organism, not a fixture."""
    registry = build_default_component_registry()
    table = solve_maintenance_policy_table(registry=registry)

    assert table.non_monotone_cohort_keys == ()
    assert table.non_converged_cohort_keys == ()
    assert table.solved_at_utc.tzinfo is not None

    for component in registry.self_components():
        policy = table.policy_for_component(component)
        assert policy is not None, component.component_id
        assert policy.component_class == build_component_cohort_key(
            component.component_class, component.criticality
        )
        action = select_action_for_component(table, component, health_index=0.5)
        assert isinstance(action, MaintenanceActionKind)


def test_real_registry_vital_store_is_maintained_harder_than_a_supporting_sibling() -> None:
    """`store.market_data` (VITAL) vs `store.news` (SUPPORTING) — same class, different stakes."""
    registry = build_default_component_registry()
    table = solve_maintenance_policy_table(registry=registry)
    vital_store = registry.find("store.market_data")
    supporting_store = registry.find("store.news")
    assert vital_store is not None and supporting_store is not None

    vital_policy = table.policy_for_component(vital_store)
    supporting_policy = table.policy_for_component(supporting_store)
    assert vital_policy is not None and supporting_policy is not None
    assert vital_policy.repair_threshold_level <= supporting_policy.repair_threshold_level
    assert vital_policy.replace_threshold_level <= supporting_policy.replace_threshold_level


def test_unknown_cohort_returns_no_action_rather_than_guessing() -> None:
    table = solve_maintenance_policy_table(
        registry=OrganismComponentRegistry(
            components=(
                RegisteredComponent(
                    "test.only_member",
                    ComponentClass.PERSISTENT_STORE,
                    ComponentCriticality.VITAL,
                    maintained_by=(),
                ),
            )
        )
    )
    stranger = RegisteredComponent(
        "test.stranger", ComponentClass.HOST_RESOURCE, ComponentCriticality.ANCILLARY
    )
    assert select_action_for_component(table, stranger, health_index=0.1) is None


def test_exogenous_components_get_no_policy_because_the_organism_does_not_maintain_them() -> None:
    registry = OrganismComponentRegistry(
        components=(
            RegisteredComponent(
                "test.outsider",
                ComponentClass.EXTERNAL_SERVICE,
                ComponentCriticality.VITAL,
                membership=ComponentMembership.EXOGENOUS,
            ),
        )
    )
    table = solve_maintenance_policy_table(registry=registry)
    assert table.policy_by_cohort_key == {}


def test_cost_model_overrides_are_honoured_by_the_cadence_solve() -> None:
    registry = OrganismComponentRegistry(
        components=(
            RegisteredComponent(
                "test.hermetic_store",
                ComponentClass.PERSISTENT_STORE,
                ComponentCriticality.VITAL,
                maintained_by=(),
            ),
        )
    )
    cohort_key = build_component_cohort_key(
        ComponentClass.PERSISTENT_STORE, ComponentCriticality.VITAL
    )
    baseline = solve_maintenance_policy_table(registry=registry)
    expensive = solve_maintenance_policy_table(
        registry=registry,
        cost_model_overrides={
            cohort_key: dataclasses.replace(
                build_cost_model_for_component_class(
                    ComponentClass.PERSISTENT_STORE, ComponentCriticality.VITAL
                ),
                repair_cost=500.0,
            )
        },
    )
    assert (
        expensive.policy_by_cohort_key[cohort_key].repair_threshold_level
        >= baseline.policy_by_cohort_key[cohort_key].repair_threshold_level
    )


# -- 7. Rule Q — priors now, refinement as real repair outcomes accrue -------------------------------


def test_refinement_with_no_observations_is_exactly_the_class_prior() -> None:
    """Rule Q: the solver is fully armed from day one; N = 0 must be the identity, not a special case."""
    prior_model = build_cost_model_for_component_class(
        ComponentClass.BACKGROUND_THREAD, ComponentCriticality.VITAL
    )
    refined = refine_cost_model_with_observed_repairs(prior_model, (), ())
    assert refined.repair_cost == pytest.approx(prior_model.repair_cost)
    assert refined.repair_success_probability == pytest.approx(prior_model.repair_success_probability)
    assert refined.observed_repair_outcome_count == 0
    assert solve_maintenance_control_limit_policy(refined).action_by_degradation_level == (
        solve_maintenance_control_limit_policy(prior_model).action_by_degradation_level
    )


def test_refinement_shrinks_toward_observed_outcomes_without_ever_overshooting_them() -> None:
    prior_model = build_cost_model_for_component_class(
        ComponentClass.BACKGROUND_THREAD, ComponentCriticality.VITAL
    )
    observed_cost = prior_model.repair_cost * 10.0
    lightly_refined = refine_cost_model_with_observed_repairs(prior_model, [observed_cost] * 2, [])
    heavily_refined = refine_cost_model_with_observed_repairs(prior_model, [observed_cost] * 200, [])

    assert prior_model.repair_cost < lightly_refined.repair_cost < heavily_refined.repair_cost
    assert heavily_refined.repair_cost < observed_cost
    assert lightly_refined.observed_repair_outcome_count == 2
    assert heavily_refined.observed_repair_outcome_count == 200


def test_refined_repair_success_probability_stays_a_probability() -> None:
    prior_model = build_cost_model_for_component_class(
        ComponentClass.BROKER_SESSION, ComponentCriticality.SUPPORTING
    )
    all_failed = refine_cost_model_with_observed_repairs(prior_model, [], [False] * 500)
    all_succeeded = refine_cost_model_with_observed_repairs(prior_model, [], [True] * 500)

    assert 0.0 <= all_failed.repair_success_probability < prior_model.repair_success_probability
    assert prior_model.repair_success_probability < all_succeeded.repair_success_probability <= 1.0
    # Both remain solvable — refinement can never produce an instance the solver rejects.
    assert solve_maintenance_control_limit_policy(all_failed).converged
    assert solve_maintenance_control_limit_policy(all_succeeded).converged


def test_repairs_that_never_work_push_the_policy_toward_replacement() -> None:
    """The behaviour change Rule Q is FOR: real outcomes must move the decision, not just a number."""
    prior_model = dataclasses.replace(
        build_cost_model_for_component_class(
            ComponentClass.PERSISTENT_STORE, ComponentCriticality.VITAL
        ),
        repair_success_probability=0.9,
    )
    futile_repairs = refine_cost_model_with_observed_repairs(prior_model, [], [False] * 400)
    assert (
        solve_maintenance_control_limit_policy(futile_repairs).replace_threshold_level
        < solve_maintenance_control_limit_policy(prior_model).replace_threshold_level
    )


def test_refinement_rejects_impossible_observed_costs() -> None:
    prior_model = build_cost_model_for_component_class(
        ComponentClass.CADENCE_ENGINE, ComponentCriticality.VITAL
    )
    with pytest.raises(MaintenanceCostModelError):
        refine_cost_model_with_observed_repairs(prior_model, [float("nan")], [])
    with pytest.raises(MaintenanceCostModelError):
        refine_cost_model_with_observed_repairs(prior_model, [-5.0], [])
