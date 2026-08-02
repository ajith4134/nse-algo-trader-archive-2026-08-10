"""Tests for the RUL prognostics ladder (research/168 §2 + §5; research/172 §4/§5.5).

Three acceptance bars from research/172 §5.5 are asserted directly here:
  * the Weibull AFT converges under ≥80% right-censoring and rank-orders components by their degradation
    covariate;
  * the Wiener first-passage estimator produces a finite, calibrated RUL from ZERO observed failures;
  * the maturity ladder reports the estimator it actually used, and `is_earned` is True only when the
    AFT model is genuinely armed for that component's class.
"""

from __future__ import annotations

import logging
import math

import pytest

from nse_algo_trader.autopoiesis.component_failure_hazard_model import (
    MINIMUM_TRAJECTORY_SAMPLE_COUNT,
    REQUIRED_CLASS_FAILURE_COUNT,
    ComponentFailureHazardModel,
    ComponentHealthTrajectory,
    ComponentLifetimeObservation,
    RemainingUsefulLifeEstimate,
    RemainingUsefulLifeEstimator,
)
from nse_algo_trader.autopoiesis.component_registry import ComponentClass

ENGINE = ComponentClass.CADENCE_ENGINE
STORE = ComponentClass.PERSISTENT_STORE

#: 10 cadence engines, 2 observed failures (80% right-censored — the pre-verified regime of
#: research/172 §10), where the components that failed are the ones with the worst degradation trend.
_CENSORED_LEDGER_SPEC: tuple[tuple[str, float, bool, int, float], ...] = (
    ("engine.debate_risk_gate", 120.0, True, 3, 0.90),
    ("engine.prediction_council", 160.0, True, 3, 0.80),
    ("engine.curiosity", 300.0, False, 2, 0.60),
    ("engine.capital_allocation", 340.0, False, 2, 0.55),
    ("engine.world_model_planning", 520.0, False, 1, 0.30),
    ("engine.incident_post_mortem", 560.0, False, 1, 0.25),
    ("engine.setpoint_keeper", 800.0, False, 0, 0.10),
    ("engine.replay_selector", 840.0, False, 0, 0.08),
    ("engine.autopoiesis_homeostat", 1000.0, False, 0, 0.03),
    ("engine.vitality_gate", 1040.0, False, 0, 0.02),
)


def _censored_ledger() -> list[ComponentLifetimeObservation]:
    return [
        ComponentLifetimeObservation(component_id, ENGINE, uptime, failed, restarts, trend)
        for component_id, uptime, failed, restarts, trend in _CENSORED_LEDGER_SPEC
    ]


def _zero_failure_ledger() -> list[ComponentLifetimeObservation]:
    """The organism's actual state: real uptime everywhere, no failure ever observed."""
    return [
        ComponentLifetimeObservation(f"store.{index}", STORE, 400.0 + 50.0 * index, False)
        for index in range(7)
    ]


def _degrading_trajectory(
    component_id: str, decline_per_sample: float, sample_count: int = 24
) -> ComponentHealthTrajectory:
    """A noisy, non-monotone health trajectory — the regime the Wiener (not Gamma) process is for."""
    jitter = (0.0, 0.004, -0.003, 0.002, -0.004, 0.003)
    samples = tuple(
        min(max(1.0 - decline_per_sample * index + jitter[index % len(jitter)], 0.0), 1.0)
        for index in range(sample_count)
    )
    return ComponentHealthTrajectory(component_id, samples, sample_interval_hours=1.0)


def _assert_reportable(estimate: RemainingUsefulLifeEstimate) -> None:
    """The invariants every RUL must satisfy no matter which rung produced it."""
    assert estimate.p10_hours <= estimate.median_hours <= estimate.p90_hours
    for hours in (estimate.p10_hours, estimate.median_hours, estimate.p90_hours):
        assert math.isfinite(hours)
        assert hours > 0.0
    assert estimate.required_failure_count == REQUIRED_CLASS_FAILURE_COUNT
    assert estimate.observed_failure_count >= 0


# --- the contract other modules bind to --------------------------------------------------------------


def test_the_estimator_enum_and_estimate_fields_match_the_published_contract() -> None:
    assert RemainingUsefulLifeEstimator.WEIBULL_AFT.value == "weibull_aft"
    assert RemainingUsefulLifeEstimator.WIENER_FIRST_PASSAGE.value == "wiener_first_passage"
    assert RemainingUsefulLifeEstimator.PRIOR_ONLY.value == "prior_only"
    assert REQUIRED_CLASS_FAILURE_COUNT == 2

    estimate = RemainingUsefulLifeEstimate(
        component_id="store.market_data", median_hours=10.0, p10_hours=1.0, p90_hours=100.0,
        estimator=RemainingUsefulLifeEstimator.PRIOR_ONLY, is_earned=False,
        observed_failure_count=0, required_failure_count=2,
    )
    with pytest.raises(Exception):  # frozen dataclass
        estimate.median_hours = 5.0  # type: ignore[misc]


# --- rung 1: Weibull AFT under heavy right-censoring -------------------------------------------------


def test_weibull_aft_converges_under_eighty_percent_right_censoring() -> None:
    observations = _censored_ledger()
    model = ComponentFailureHazardModel()

    report = model.fit(observations)

    assert report.converged, report.failure_reason
    assert report.censored_fraction == pytest.approx(0.8)
    assert report.observed_failure_count == 2
    assert report.observation_count == 10
    assert report.weibull_shape_rho is not None and report.weibull_shape_rho > 1.0, \
        "rho > 1 is genuine wear-out, matching the pre-verified rho=1.857 regime"
    assert report.concordance_index is not None and report.concordance_index > 0.5
    assert report.failure_reason is None
    # The single-class ledger makes the class indicator constant, so it must be dropped, not penalised.
    assert "class_cadence_engine" in report.dropped_zero_variance_columns
    assert "degradation_trend" in report.covariate_columns


def test_weibull_aft_rank_orders_components_by_their_degradation_covariate() -> None:
    """research/172 §5.5 acceptance bar: a worse degradation trend must mean a shorter RUL."""
    observations = _censored_ledger()
    model = ComponentFailureHazardModel()

    estimates = [
        (observation.degradation_trend,
         model.estimate_remaining_useful_life(observation.component_id, observations))
        for observation in observations
    ]
    for _, estimate in estimates:
        assert estimate.estimator is RemainingUsefulLifeEstimator.WEIBULL_AFT
        assert estimate.is_earned is True
        _assert_reportable(estimate)

    by_worsening_degradation = sorted(estimates, key=lambda pair: pair[0], reverse=True)
    medians = [estimate.median_hours for _, estimate in by_worsening_degradation]
    assert medians == sorted(medians), "RUL must increase strictly as the degradation trend improves"
    assert medians[0] < medians[-1] / 10.0, "the spread must be decision-grade, not cosmetic"


def test_the_aft_fit_is_cached_until_the_observation_set_changes() -> None:
    observations = _censored_ledger()
    model = ComponentFailureHazardModel()

    first = model.fit(observations)
    assert model.fit(observations) is first

    changed = [*observations[:-1],
               ComponentLifetimeObservation("engine.vitality_gate", ENGINE, 1200.0, False, 0, 0.02)]
    assert model.fit(changed) is not first


# --- rung 2: Wiener first passage, with ZERO observed failures ----------------------------------------


def test_wiener_first_passage_produces_a_finite_rul_from_zero_observed_failures() -> None:
    observations = _zero_failure_ledger()
    model = ComponentFailureHazardModel()
    trajectory = _degrading_trajectory("store.0", decline_per_sample=0.01)

    estimate = model.estimate_remaining_useful_life("store.0", observations, trajectory)

    assert estimate.estimator is RemainingUsefulLifeEstimator.WIENER_FIRST_PASSAGE
    assert estimate.is_earned is False
    assert estimate.observed_failure_count == 0
    _assert_reportable(estimate)
    assert estimate.p10_hours < estimate.p90_hours, "a calibrated distribution, not a point guess"


def test_wiener_rul_shortens_as_the_health_trajectory_degrades_faster() -> None:
    observations = _zero_failure_ledger()
    model = ComponentFailureHazardModel()

    medians = [
        model.estimate_remaining_useful_life(
            "store.0", observations, _degrading_trajectory("store.0", decline)
        ).median_hours
        for decline in (0.002, 0.005, 0.01, 0.02)
    ]

    assert medians == sorted(medians, reverse=True)
    assert medians[0] > 5.0 * medians[-1]


def test_wiener_parameters_are_floored_and_the_flooring_is_reported() -> None:
    model = ComponentFailureHazardModel()
    healing = ComponentHealthTrajectory("store.0", tuple(0.5 + 0.01 * i for i in range(10)), 1.0)

    parameters = model.estimate_wiener_first_passage_parameters(healing)

    assert parameters.drift_was_floored is True, "an improving component has no proper FPT at mu<=0"
    assert parameters.degradation_drift_per_hour > 0.0
    assert math.isfinite(parameters.inverse_gaussian_mean_hours)
    assert parameters.sample_count == 10

    deterministic = ComponentHealthTrajectory("store.0", tuple(1.0 - 0.01 * i for i in range(10)), 1.0)
    assert model.estimate_wiener_first_passage_parameters(deterministic).diffusion_was_floored is True


def test_a_trajectory_belonging_to_a_different_component_is_rejected() -> None:
    model = ComponentFailureHazardModel()
    with pytest.raises(ValueError, match="belongs to"):
        model.estimate_remaining_useful_life(
            "store.0", _zero_failure_ledger(), _degrading_trajectory("store.6", 0.01)
        )


# --- rung 3: the hierarchical prior ------------------------------------------------------------------


def test_prior_only_carries_components_with_neither_failures_nor_a_trajectory() -> None:
    observations = _zero_failure_ledger()
    model = ComponentFailureHazardModel()

    estimate = model.estimate_remaining_useful_life("store.3", observations)

    assert estimate.estimator is RemainingUsefulLifeEstimator.PRIOR_ONLY
    assert estimate.is_earned is False
    _assert_reportable(estimate)


def test_a_trajectory_too_short_to_estimate_drift_steps_down_to_the_prior() -> None:
    observations = _zero_failure_ledger()
    model = ComponentFailureHazardModel()
    stub = ComponentHealthTrajectory("store.0", (1.0, 0.99), sample_interval_hours=1.0)

    assert len(stub.health_index_samples) < MINIMUM_TRAJECTORY_SAMPLE_COUNT
    assert stub.is_estimable is False
    estimate = model.estimate_remaining_useful_life("store.0", observations, stub)
    assert estimate.estimator is RemainingUsefulLifeEstimator.PRIOR_ONLY
    _assert_reportable(estimate)


# --- the maturity ladder -----------------------------------------------------------------------------


@pytest.mark.parametrize("class_failure_count", [0, 1])
def test_below_the_arming_threshold_the_aft_never_claims_to_be_earned(class_failure_count: int) -> None:
    observations = [
        ComponentLifetimeObservation(
            f"engine.{index}", ENGINE, 200.0 + 60.0 * index,
            observed_failure=index < class_failure_count, restart_count=index % 3,
            degradation_trend=0.05 * (index + 1),
        )
        for index in range(8)
    ]
    model = ComponentFailureHazardModel()

    without_trajectory = model.estimate_remaining_useful_life("engine.5", observations)
    with_trajectory = model.estimate_remaining_useful_life(
        "engine.5", observations, _degrading_trajectory("engine.5", 0.01)
    )

    for estimate in (without_trajectory, with_trajectory):
        assert estimate.estimator in (
            RemainingUsefulLifeEstimator.WIENER_FIRST_PASSAGE,
            RemainingUsefulLifeEstimator.PRIOR_ONLY,
        )
        assert estimate.is_earned is False
        assert estimate.observed_failure_count == class_failure_count
        assert estimate.observed_failure_count < estimate.required_failure_count
        _assert_reportable(estimate)


def test_the_aft_arms_itself_at_two_class_failures_with_no_code_change() -> None:
    """The same component, the same call — only one more observed failure in its class."""
    model = ComponentFailureHazardModel()
    immature = [*_CENSORED_LEDGER_SPEC]
    immature[1] = ("engine.prediction_council", 160.0, False, 3, 0.80)
    immature_observations = [
        ComponentLifetimeObservation(cid, ENGINE, uptime, failed, restarts, trend)
        for cid, uptime, failed, restarts, trend in immature
    ]

    before = model.estimate_remaining_useful_life("engine.curiosity", immature_observations)
    after = model.estimate_remaining_useful_life("engine.curiosity", _censored_ledger())

    assert before.is_earned is False
    assert before.estimator is RemainingUsefulLifeEstimator.PRIOR_ONLY
    assert after.is_earned is True
    assert after.estimator is RemainingUsefulLifeEstimator.WEIBULL_AFT


def test_the_class_failure_counter_backs_the_have_n_need_m_display() -> None:
    model = ComponentFailureHazardModel()
    observations = [*_censored_ledger(), *_zero_failure_ledger()]

    assert model.observed_failure_count_for_class(ENGINE, observations) == 2
    assert model.observed_failure_count_for_class(STORE, observations) == 0
    assert model.required_class_failure_count == REQUIRED_CLASS_FAILURE_COUNT


def test_the_whole_organism_sweep_orders_components_nearest_to_failure_first() -> None:
    observations = _censored_ledger()
    model = ComponentFailureHazardModel()

    estimates = model.estimate_remaining_useful_life_for_all(observations)

    assert len(estimates) == len(observations)
    assert [estimate.median_hours for estimate in estimates] == sorted(
        estimate.median_hours for estimate in estimates
    )
    for estimate in estimates:
        _assert_reportable(estimate)


# --- adversarial / degenerate -------------------------------------------------------------------------


def test_an_all_censored_ledger_reports_why_the_aft_cannot_fit_instead_of_pretending() -> None:
    model = ComponentFailureHazardModel()

    report = model.fit(_zero_failure_ledger())

    assert report.attempted is True
    assert report.converged is False
    assert report.observed_failure_count == 0
    assert report.censored_fraction == pytest.approx(1.0)
    assert report.failure_reason is not None and "censored" in report.failure_reason


def test_a_single_observation_is_reported_as_insufficient_for_a_regression() -> None:
    model = ComponentFailureHazardModel()
    single = [ComponentLifetimeObservation("store.market_data", STORE, 500.0, True)]

    report = model.fit(single)
    estimate = model.estimate_remaining_useful_life("store.market_data", single)

    assert report.converged is False
    assert report.failure_reason is not None and "observation" in report.failure_reason
    assert estimate.estimator is RemainingUsefulLifeEstimator.PRIOR_ONLY
    _assert_reportable(estimate)


def test_a_non_convergent_solve_is_logged_and_reported_never_silently_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rule O.3. Identical durations give the AFT no spread to identify a scale from."""
    degenerate = [
        ComponentLifetimeObservation(f"engine.{index}", ENGINE, 300.0, index < 2, 1, 0.1 * index)
        for index in range(10)
    ]
    model = ComponentFailureHazardModel()

    with caplog.at_level(logging.WARNING):
        estimate = model.estimate_remaining_useful_life("engine.5", degenerate)

    report = model.fit_report
    assert report is not None and report.converged is False
    assert report.failure_reason is not None
    assert any("did not converge" in record.getMessage() for record in caplog.records)
    assert "ConvergenceError" in report.failure_reason
    assert estimate.is_earned is False
    assert estimate.estimator is RemainingUsefulLifeEstimator.PRIOR_ONLY
    _assert_reportable(estimate)


def test_a_nan_covariate_is_sanitized_with_a_recorded_count_not_dropped() -> None:
    observations = _censored_ledger()
    observations[4] = ComponentLifetimeObservation(
        "engine.world_model_planning", ENGINE, 520.0, False, 1, float("nan")
    )
    model = ComponentFailureHazardModel()

    report = model.fit(observations)

    assert report.sanitized_covariate_count == 1
    assert report.observation_count == 10, "the censored row keeps its survival information"
    assert report.converged, report.failure_reason
    _assert_reportable(
        model.estimate_remaining_useful_life("engine.world_model_planning", observations)
    )


def test_zero_variance_covariates_are_dropped_rather_than_left_unidentifiable() -> None:
    observations = [
        ComponentLifetimeObservation(f"engine.{index}", ENGINE, 150.0 + 95.0 * index,
                                     observed_failure=index < 2, restart_count=4,
                                     degradation_trend=0.7 - 0.07 * index)
        for index in range(10)
    ]
    model = ComponentFailureHazardModel()

    report = model.fit(observations)

    assert "restart_count" in report.dropped_zero_variance_columns
    assert "class_cadence_engine" in report.dropped_zero_variance_columns
    assert "restart_count" not in report.covariate_columns
    assert report.converged, report.failure_reason


@pytest.mark.parametrize("uptime_hours", [0.0, -5.0, float("nan"), float("inf")])
def test_a_degenerate_survival_duration_is_rejected_at_construction(uptime_hours: float) -> None:
    with pytest.raises(ValueError, match="uptime_hours"):
        ComponentLifetimeObservation("store.x", STORE, uptime_hours, False)


def test_a_negative_restart_count_and_an_empty_component_id_are_rejected() -> None:
    with pytest.raises(ValueError, match="restart_count"):
        ComponentLifetimeObservation("store.x", STORE, 10.0, False, restart_count=-1)
    with pytest.raises(ValueError, match="component_id"):
        ComponentLifetimeObservation("", STORE, 10.0, False)


@pytest.mark.parametrize(
    ("samples", "interval", "threshold"),
    [
        ((1.0, float("nan"), 0.9), 1.0, 0.0),
        ((1.0, 1.4, 0.9), 1.0, 0.0),
        ((1.0, -0.2, 0.9), 1.0, 0.0),
        ((1.0, 0.9, 0.8), 0.0, 0.0),
        ((1.0, 0.9, 0.8), -1.0, 0.0),
        ((1.0, 0.9, 0.8), 1.0, 1.0),
        ((1.0, 0.9, 0.8), 1.0, -0.1),
    ],
)
def test_a_corrupt_health_trajectory_is_rejected_rather_than_silently_cleaned(
    samples: tuple[float, ...], interval: float, threshold: float
) -> None:
    with pytest.raises(ValueError):
        ComponentHealthTrajectory("store.0", samples, interval, threshold)


def test_an_unknown_component_id_and_an_empty_ledger_are_reported() -> None:
    model = ComponentFailureHazardModel()
    with pytest.raises(ValueError, match="no ComponentLifetimeObservation"):
        model.estimate_remaining_useful_life("store.does_not_exist", _zero_failure_ledger())
    with pytest.raises(ValueError, match="at least one"):
        model.estimate_remaining_useful_life("store.0", [])


@pytest.mark.parametrize(("penalizer", "required"), [(-0.1, 2), (float("nan"), 2), (0.1, 0)])
def test_the_model_rejects_a_degenerate_configuration(penalizer: float, required: int) -> None:
    with pytest.raises(ValueError):
        ComponentFailureHazardModel(penalizer=penalizer, required_class_failure_count=required)


def test_a_component_already_at_its_failure_threshold_still_reports_a_positive_rul() -> None:
    observations = _zero_failure_ledger()
    model = ComponentFailureHazardModel()
    collapsed = ComponentHealthTrajectory(
        "store.0", (0.30, 0.20, 0.12, 0.06, 0.02, 0.0), sample_interval_hours=1.0
    )

    estimate = model.estimate_remaining_useful_life("store.0", observations, collapsed)

    assert estimate.estimator is RemainingUsefulLifeEstimator.WIENER_FIRST_PASSAGE
    _assert_reportable(estimate)
