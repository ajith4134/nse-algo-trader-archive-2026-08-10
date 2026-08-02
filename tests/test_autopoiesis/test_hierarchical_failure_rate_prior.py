"""Tests for the conjugate hierarchical failure-rate prior (research/168 §5b/§5c/§5d).

The load-bearing property under test is the one Rule Q exists for: with essentially ZERO observed
failures anywhere in the organism — the permanent condition, not a warm-up — every component must still
get a principled, non-zero, uncertainty-carrying failure-rate estimate, and that estimate must detach
from the population prior automatically as its own exposure accrues.
"""

from __future__ import annotations

import math

import pytest

from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.hierarchical_failure_rate_prior import (
    ComponentFailureExposure,
    HierarchicalFailureRatePrior,
    PopulationPriorEstimationMethod,
    build_class_exposures_from_registry,
    prior_weight_in_posterior,
    shrink_toward_prior,
)

STORE = ComponentClass.PERSISTENT_STORE
SESSION = ComponentClass.BROKER_SESSION


def _store_exposures_with_failures() -> list[ComponentFailureExposure]:
    """7 persistent stores — the real population size — where two of them have actually failed."""
    exposures = [
        ComponentFailureExposure(f"store.{index}", STORE, 400.0 + 50.0 * index, 0)
        for index in range(7)
    ]
    exposures[3] = ComponentFailureExposure("store.3", STORE, 550.0, 3)
    exposures[5] = ComponentFailureExposure("store.5", STORE, 650.0, 1)
    return exposures


# --- the shared primitive ---------------------------------------------------------------------------


def test_shrink_toward_prior_returns_the_prior_mean_when_there_is_no_data() -> None:
    assert shrink_toward_prior(0.0, 0.0, prior_mean=0.004, prior_strength=250.0) == pytest.approx(0.004)


def test_shrink_toward_prior_converges_to_the_raw_maximum_likelihood_ratio_with_huge_n() -> None:
    raw_rate = 0.02
    exposure = 1e9
    shrunk = shrink_toward_prior(raw_rate * exposure, exposure, prior_mean=0.5, prior_strength=250.0)
    assert shrunk == pytest.approx(raw_rate, rel=1e-4)


def test_shrink_toward_prior_is_monotone_in_the_observation_count() -> None:
    prior_mean, prior_strength, raw_rate = 0.5, 100.0, 0.01
    distances = [
        abs(shrink_toward_prior(raw_rate * n, n, prior_mean, prior_strength) - raw_rate)
        for n in (1.0, 10.0, 100.0, 1_000.0, 10_000.0)
    ]
    assert distances == sorted(distances, reverse=True)
    weights = [prior_weight_in_posterior(n, prior_strength) for n in (1.0, 10.0, 100.0, 1_000.0)]
    assert weights == sorted(weights, reverse=True)
    assert all(0.0 < weight <= 1.0 for weight in weights)


@pytest.mark.parametrize(
    ("observed_sum", "observed_count", "prior_mean", "prior_strength"),
    [
        (float("nan"), 10.0, 0.1, 1.0),
        (1.0, float("inf"), 0.1, 1.0),
        (-1.0, 10.0, 0.1, 1.0),
        (1.0, -10.0, 0.1, 1.0),
        (1.0, 10.0, 0.1, -1.0),
        (0.0, 0.0, 0.1, 0.0),
    ],
)
def test_shrink_toward_prior_rejects_degenerate_input_rather_than_inventing_a_number(
    observed_sum: float, observed_count: float, prior_mean: float, prior_strength: float
) -> None:
    with pytest.raises(ValueError):
        shrink_toward_prior(observed_sum, observed_count, prior_mean, prior_strength)


# --- the Rule-Q core: borrowing strength ------------------------------------------------------------


def test_zero_failure_component_in_a_failing_class_gets_a_non_zero_shrunk_rate() -> None:
    engine = HierarchicalFailureRatePrior()
    exposures = _store_exposures_with_failures()
    healthy = exposures[0]

    posterior = engine.posterior_failure_rate(healthy, exposures)

    assert healthy.raw_failure_rate_per_hour == 0.0, "the unpooled MLE is the nonsense we are fixing"
    assert posterior.posterior_mean_failures_per_hour > 0.0
    # It borrows from the class but is pulled below the population mean by its own clean record.
    assert 0.0 < posterior.posterior_mean_failures_per_hour \
        < posterior.population_prior_mean_failures_per_hour
    assert posterior.population_prior_method is PopulationPriorEstimationMethod.METHOD_OF_MOMENTS
    assert 0.0 < posterior.shrinkage_weight_on_prior < 1.0
    assert posterior.effective_sample_size > 0.0
    assert posterior.credible_low_failures_per_hour \
        <= posterior.posterior_mean_failures_per_hour \
        <= posterior.credible_high_failures_per_hour
    assert posterior.credible_interval_mass == pytest.approx(0.90)


def test_a_class_with_no_failures_anywhere_still_yields_a_positive_rate_for_every_member() -> None:
    """Today's actual organism state: real exposure, zero failures, in every single class."""
    engine = HierarchicalFailureRatePrior()
    exposures = [
        ComponentFailureExposure(f"store.{index}", STORE, 400.0 + 50.0 * index, 0)
        for index in range(7)
    ]

    prior = engine.estimate_population_prior(STORE, exposures)
    posteriors = engine.posterior_failure_rates_for_class(STORE, exposures)

    assert prior.estimation_method is PopulationPriorEstimationMethod.JEFFREYS_ZERO_FAILURE
    assert prior.prior_mean_failures_per_hour > 0.0
    assert len(posteriors) == 7
    for posterior in posteriors:
        assert posterior.posterior_mean_failures_per_hour > 0.0
        assert math.isfinite(posterior.mean_hours_between_failures)
        assert posterior.credible_low_failures_per_hour < posterior.credible_high_failures_per_hour


def test_shrinkage_decreases_monotonically_as_the_component_accrues_exposure() -> None:
    """The maturity ladder as a continuous quantity: no threshold, no code change, just more data."""
    engine = HierarchicalFailureRatePrior()
    peers = _store_exposures_with_failures()
    prior = engine.estimate_population_prior(STORE, peers, exclude_component_id="store.target")

    weights: list[float] = []
    distances_to_raw: list[float] = []
    # 0.1 failures/hour divides every exposure below exactly, so the raw MLE is identical at each step
    # and only the SHRINKAGE moves — which is the thing under test.
    raw_rate = 0.1
    for exposure_hours in (10.0, 100.0, 1_000.0, 10_000.0, 1_000_000.0):
        target = ComponentFailureExposure(
            "store.target", STORE, exposure_hours, int(raw_rate * exposure_hours)
        )
        posterior = engine.posterior_failure_rate(target, peers, population_prior=prior)
        weights.append(posterior.shrinkage_weight_on_prior)
        distances_to_raw.append(
            abs(posterior.posterior_mean_failures_per_hour - target.raw_failure_rate_per_hour)
        )

    assert weights == sorted(weights, reverse=True)
    assert distances_to_raw == sorted(distances_to_raw, reverse=True)
    assert weights[-1] < 1e-3, "with a million hours of exposure the prior is essentially gone"


def test_with_huge_exposure_the_posterior_converges_to_the_raw_maximum_likelihood_estimate() -> None:
    engine = HierarchicalFailureRatePrior()
    peers = _store_exposures_with_failures()
    target = ComponentFailureExposure("store.target", STORE, 1e8, 400_000)

    posterior = engine.posterior_failure_rate(target, [*peers, target])

    assert posterior.posterior_mean_failures_per_hour == pytest.approx(
        target.raw_failure_rate_per_hour, rel=1e-3
    )
    assert posterior.credible_high_failures_per_hour - posterior.credible_low_failures_per_hour \
        < 0.01 * posterior.posterior_mean_failures_per_hour, "uncertainty collapses as evidence accrues"


def test_the_population_prior_excludes_the_target_component_leave_one_out() -> None:
    engine = HierarchicalFailureRatePrior()
    exposures = _store_exposures_with_failures()
    heavy_failer = exposures[3]

    leave_one_out = engine.estimate_population_prior(
        STORE, exposures, exclude_component_id=heavy_failer.component_id
    )
    all_members = engine.estimate_population_prior(STORE, exposures)

    assert leave_one_out.contributing_member_count == all_members.contributing_member_count - 1
    assert leave_one_out.pooled_failure_count == all_members.pooled_failure_count - 3
    assert leave_one_out.prior_mean_failures_per_hour < all_members.prior_mean_failures_per_hour


# --- Beta-Binomial ----------------------------------------------------------------------------------


def test_beta_binomial_posterior_sits_between_the_raw_ratio_and_the_population_mean() -> None:
    engine = HierarchicalFailureRatePrior()
    exposures = [
        ComponentFailureExposure("session.kite", SESSION, 100.0, 2, opportunity_count=50),
        ComponentFailureExposure("session.breeze", SESSION, 100.0, 0, opportunity_count=40),
        ComponentFailureExposure("session.angel_one", SESSION, 100.0, 6, opportunity_count=60),
    ]
    clean_session = exposures[1]

    posterior = engine.posterior_failure_probability(clean_session, exposures)

    assert posterior.raw_failure_probability == 0.0
    assert 0.0 < posterior.posterior_mean_failure_probability < 1.0
    assert posterior.posterior_mean_failure_probability \
        < posterior.population_prior_mean_failure_probability
    assert posterior.effective_sample_size > clean_session.opportunity_count
    assert 0.0 <= posterior.credible_low_failure_probability \
        <= posterior.posterior_mean_failure_probability \
        <= posterior.credible_high_failure_probability <= 1.0


def test_beta_binomial_with_no_failures_anywhere_uses_the_jeffreys_rung() -> None:
    engine = HierarchicalFailureRatePrior()
    exposures = [
        ComponentFailureExposure(f"session.{index}", SESSION, 200.0, 0, opportunity_count=30)
        for index in range(3)
    ]

    posterior = engine.posterior_failure_probability(exposures[0], exposures)

    assert posterior.population_prior_method is PopulationPriorEstimationMethod.JEFFREYS_ZERO_FAILURE
    assert posterior.posterior_mean_failure_probability > 0.0


def test_beta_binomial_probability_converges_to_the_raw_ratio_with_many_opportunities() -> None:
    engine = HierarchicalFailureRatePrior()
    peers = [
        ComponentFailureExposure("session.kite", SESSION, 100.0, 2, opportunity_count=50),
        ComponentFailureExposure("session.breeze", SESSION, 100.0, 0, opportunity_count=40),
    ]
    target = ComponentFailureExposure("session.busy", SESSION, 100.0, 30_000, opportunity_count=1_000_000)

    posterior = engine.posterior_failure_probability(target, [*peers, target])

    assert posterior.posterior_mean_failure_probability == pytest.approx(0.03, rel=1e-2)


# --- degenerate and adversarial input ---------------------------------------------------------------


def test_an_empty_class_falls_back_to_the_documented_weakly_informative_prior() -> None:
    engine = HierarchicalFailureRatePrior()

    prior = engine.estimate_population_prior(ComponentClass.DATA_ADAPTER, [])

    assert prior.estimation_method is PopulationPriorEstimationMethod.FALLBACK_PRIOR
    assert prior.is_estimated_from_class_data is False
    assert prior.contributing_member_count == 0
    assert prior.prior_mean_failures_per_hour > 0.0
    assert prior.prior_mean_failure_probability > 0.0


def test_a_single_member_class_keeps_the_pooled_mean_with_a_defaulted_concentration() -> None:
    engine = HierarchicalFailureRatePrior()
    only_member = ComponentFailureExposure("adapter.bars", ComponentClass.DATA_ADAPTER, 500.0, 4)

    prior = engine.estimate_population_prior(ComponentClass.DATA_ADAPTER, [only_member])

    assert prior.estimation_method is PopulationPriorEstimationMethod.POOLED_MEAN_DEFAULT_CONCENTRATION
    assert prior.prior_mean_failures_per_hour == pytest.approx(4.0 / 500.0)


def test_a_zero_exposure_class_falls_back_rather_than_dividing_by_zero() -> None:
    engine = HierarchicalFailureRatePrior()
    idle = [ComponentFailureExposure(f"host.{index}", ComponentClass.HOST_RESOURCE, 0.0, 0)
            for index in range(4)]

    prior = engine.estimate_population_prior(ComponentClass.HOST_RESOURCE, idle)
    posterior = engine.posterior_failure_rate(idle[0], idle)

    assert prior.estimation_method is PopulationPriorEstimationMethod.FALLBACK_PRIOR
    assert posterior.posterior_mean_failures_per_hour > 0.0
    assert posterior.shrinkage_weight_on_prior == pytest.approx(1.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exposure_hours": -1.0},
        {"exposure_hours": float("nan")},
        {"exposure_hours": float("inf")},
        {"observed_failure_count": -2},
        {"opportunity_count": -3},
    ],
)
def test_component_failure_exposure_rejects_degenerate_fields(kwargs: dict[str, float]) -> None:
    base = {"component_id": "store.x", "component_class": STORE,
            "exposure_hours": 10.0, "observed_failure_count": 0}
    with pytest.raises(ValueError):
        ComponentFailureExposure(**{**base, **kwargs})  # type: ignore[arg-type]


def test_more_failures_than_opportunities_is_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        ComponentFailureExposure("store.x", STORE, 10.0, 5, opportunity_count=2)


def test_an_empty_component_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="component_id"):
        ComponentFailureExposure("", STORE, 10.0, 0)


def test_duplicate_component_ids_are_reported_not_silently_deduplicated() -> None:
    engine = HierarchicalFailureRatePrior()
    duplicated = [
        ComponentFailureExposure("store.a", STORE, 100.0, 0),
        ComponentFailureExposure("store.a", STORE, 200.0, 1),
    ]
    with pytest.raises(ValueError, match="duplicate component_id"):
        engine.posterior_failure_rates_by_component_id(duplicated)


@pytest.mark.parametrize("credible_mass", [0.0, 1.0, -0.5, 1.5])
def test_an_out_of_range_credible_interval_mass_is_rejected(credible_mass: float) -> None:
    with pytest.raises(ValueError, match="credible_interval_mass"):
        HierarchicalFailureRatePrior(credible_interval_mass=credible_mass)


# --- the third consumer of the shared primitive -----------------------------------------------------


def test_degradation_rate_shrinkage_pulls_toward_the_class_mean_and_handles_healing() -> None:
    engine = HierarchicalFailureRatePrior()

    lightly_observed = engine.shrink_degradation_rate([0.05], 0.01, prior_strength=5.0)
    heavily_observed = engine.shrink_degradation_rate([0.05] * 500, 0.01, prior_strength=5.0)
    healing = engine.shrink_degradation_rate([-0.04, -0.06], 0.01, prior_strength=5.0)

    assert 0.01 < lightly_observed < 0.05
    assert heavily_observed == pytest.approx(0.05, rel=1e-2)
    assert abs(heavily_observed - 0.05) < abs(lightly_observed - 0.05)
    assert healing < 0.01, "a healing component must be allowed to shrink toward a NEGATIVE rate"
    assert engine.shrink_degradation_rate([], 0.02) == pytest.approx(0.02)


def test_degradation_rate_shrinkage_rejects_non_finite_observations() -> None:
    engine = HierarchicalFailureRatePrior()
    with pytest.raises(ValueError, match="non-finite"):
        engine.shrink_degradation_rate([0.01, float("nan")], 0.01)
    with pytest.raises(ValueError, match="population_mean_degradation_rate"):
        engine.shrink_degradation_rate([0.01], float("inf"))


# --- against the REAL organism registry --------------------------------------------------------------


def test_every_real_registry_class_gets_a_positive_pooled_rate_from_todays_zero_failure_ledger() -> None:
    """Rule-F-shaped: the real class populations (7/6/3/5/9/4) with the real (empty) failure ledger."""
    registry = build_default_component_registry()
    engine = HierarchicalFailureRatePrior()
    components = [
        (component.component_id, component.component_class)
        for component in registry.self_components()
    ]
    exposures = build_class_exposures_from_registry(
        failure_counts_by_component_id={},
        exposure_hours_by_component_id={component_id: 720.0 for component_id, _ in components},
        components=components,
    )

    posteriors = engine.posterior_failure_rates_by_component_id(exposures)

    assert len(posteriors) == len(components)
    expected_population_sizes = {
        ComponentClass.PERSISTENT_STORE: 7,
        ComponentClass.PERSISTED_ARTIFACT: 6,
        ComponentClass.BROKER_SESSION: 3,
        ComponentClass.BACKGROUND_THREAD: 5,
        ComponentClass.CADENCE_ENGINE: 9,
        ComponentClass.HOST_RESOURCE: 4,
    }
    for component_class, expected_size in expected_population_sizes.items():
        assert len(registry.members_of_class(component_class)) == expected_size

    for posterior in posteriors.values():
        assert posterior.posterior_mean_failures_per_hour > 0.0
        assert math.isfinite(posterior.posterior_mean_failures_per_hour)
        assert posterior.raw_failure_rate_per_hour == 0.0
        assert posterior.population_prior_method in (
            PopulationPriorEstimationMethod.JEFFREYS_ZERO_FAILURE,
            PopulationPriorEstimationMethod.FALLBACK_PRIOR,
        )
        assert 0.0 < posterior.shrinkage_weight_on_prior <= 1.0


def test_build_class_exposures_from_registry_treats_missing_ledger_entries_as_zero_evidence() -> None:
    exposures = build_class_exposures_from_registry(
        failure_counts_by_component_id={"store.market_data": 2},
        exposure_hours_by_component_id={"store.market_data": 300.0},
        components=[("store.market_data", STORE), ("store.news", STORE)],
    )

    by_id = {exposure.component_id: exposure for exposure in exposures}
    assert by_id["store.market_data"].observed_failure_count == 2
    assert by_id["store.news"].observed_failure_count == 0
    assert by_id["store.news"].exposure_hours == 0.0
