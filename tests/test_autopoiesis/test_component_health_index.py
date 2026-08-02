"""Tests for the Trunk-X component health index (research/168 §1, research/172 §3/§4/§5).

Four layers, matching research/172 §5.6:
  * unit          — T-squared / SPE-Q on a KNOWN matrix, checked against an independently computed
                    Mahalanobis distance and against the control-limit formulas evaluated by hand;
                    the EWMA checked against the NIST recursion computed by hand.
  * property      — hypothesis-driven invariants: the index never leaves [0, 1], and weighted-max
                    fusion is never better than the worst contributing signal.
  * adversarial   — NaN/inf telemetry, zero-variance baselines, empty series, a single sample,
                    1000 identical samples, non-numeric values, misrouted samples, naive datetimes.
  * maturity      — Rule Q: the PCA layer abstains below 30 baseline samples, a health index is still
                    produced, and the component arms itself at 30 with no code change.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from scipy.stats import chi2 as chi_square_distribution
from scipy.stats import f as fisher_f_distribution

from nse_algo_trader.autopoiesis.component_health_index import (
    MINIMUM_BASELINE_SAMPLE_COUNT_FOR_PCA,
    ComponentHealthAssessment,
    ComponentHealthIndexEngine,
    ComponentHealthIndexEstimator,
    ComponentTelemetrySample,
    DegradationState,
    HealthIndexCalibration,
    HealthyBaselinePrincipalComponentModel,
    SeverityContribution,
    SignalSeveritySpec,
    assess_component_health,
    classify_degradation_state,
    ewma_standard_deviation,
    fuse_severity_contributions_by_weighted_max,
    linear_severity_ramp,
    map_control_limit_ratio_to_severity,
    robust_severity_ramp_from_baseline,
    spe_q_control_limit_chi_square_approximation,
    update_ewma_level,
)

EPOCH = datetime(2026, 7, 27, 4, 0, 0, tzinfo=UTC)


def telemetry(
    signal_values: dict[str, float], minute: int = 0, component_id: str = "component.under_test"
) -> ComponentTelemetrySample:
    return ComponentTelemetrySample(
        component_id=component_id,
        captured_at=EPOCH + timedelta(minutes=minute),
        signal_values=signal_values,
    )


def healthy_noise_series(
    sample_count: int, seed: int = 20260727, component_id: str = "component.under_test"
) -> list[ComponentTelemetrySample]:
    """A well-behaved multivariate healthy stream — the substrate for the maturity tests."""
    generator = np.random.default_rng(seed)
    samples = []
    for index in range(sample_count):
        samples.append(
            telemetry(
                {
                    "heartbeat_age_seconds": float(30.0 + generator.normal(0.0, 2.0)),
                    "consecutive_failure_count": float(abs(generator.normal(0.0, 0.4))),
                    "staleness_hours": float(1.0 + generator.normal(0.0, 0.1)),
                },
                minute=index,
                component_id=component_id,
            )
        )
    return samples


# =====================================================================================================
# UNIT — the multivariate statistics on a known matrix
# =====================================================================================================

#: A deliberately small, fully written-out healthy baseline: two correlated signals, 12 samples.
KNOWN_TWO_SIGNAL_BASELINE = np.array(
    [
        [10.0, 2.0], [11.0, 2.3], [12.0, 2.5], [13.0, 2.9], [14.0, 3.0], [15.0, 3.4],
        [16.0, 3.5], [17.0, 3.9], [18.0, 4.0], [19.0, 4.4], [20.0, 4.5], [21.0, 4.9],
    ],
    dtype=np.float64,
)

#: Rank-2 inside a 3-signal space: the third column is exactly the sum of the first two, so the healthy
#: correlation STRUCTURE is a plane. Breaking that plane is what SPE/Q — and only SPE/Q — detects.
KNOWN_RANK_DEFICIENT_BASELINE = np.array(
    [
        [1.0, 2.0, 3.0], [2.0, 1.0, 3.0], [3.0, 3.0, 6.0], [4.0, 1.0, 5.0],
        [1.0, 5.0, 6.0], [5.0, 2.0, 7.0], [2.0, 4.0, 6.0], [6.0, 1.0, 7.0],
        [3.0, 5.0, 8.0], [4.0, 4.0, 8.0], [5.0, 5.0, 10.0], [2.0, 2.0, 4.0],
    ],
    dtype=np.float64,
)


def fit_known_two_signal_model() -> HealthyBaselinePrincipalComponentModel:
    model = HealthyBaselinePrincipalComponentModel.fit_on_healthy_baseline(
        signal_names=("first_signal", "second_signal"),
        baseline_matrix=KNOWN_TWO_SIGNAL_BASELINE,
        retained_variance_ratio=1.0,          # retain the full spectrum -> T^2 == full Mahalanobis
        control_limit_significance=0.01,
    )
    assert model is not None
    return model


def test_hotelling_t_squared_equals_the_mahalanobis_distance_computed_independently() -> None:
    """T^2 IS the squared Mahalanobis distance in the PC basis (research/168 §1a/§1b).

    The reference value is computed here from first principles with numpy (z-score, sample covariance,
    explicit inverse) — it never touches the module under test, so agreement is real evidence.
    """
    model = fit_known_two_signal_model()
    assert model.retained_component_count == 2

    observation = {"first_signal": 30.0, "second_signal": 3.0}
    statistics = model.evaluate_observation(observation)
    assert statistics is not None

    baseline_mean = KNOWN_TWO_SIGNAL_BASELINE.mean(axis=0)
    baseline_standard_deviation = KNOWN_TWO_SIGNAL_BASELINE.std(axis=0, ddof=1)
    standardized_baseline = (KNOWN_TWO_SIGNAL_BASELINE - baseline_mean) / baseline_standard_deviation
    standardized_observation = (
        np.array([observation["first_signal"], observation["second_signal"]]) - baseline_mean
    ) / baseline_standard_deviation
    covariance = np.cov(standardized_baseline, rowvar=False, ddof=1)
    expected_mahalanobis = float(
        standardized_observation @ np.linalg.inv(covariance) @ standardized_observation
    )

    assert statistics.t_squared == pytest.approx(expected_mahalanobis, rel=1e-9, abs=1e-9)
    # Retaining the full spectrum leaves no residual subspace, so SPE is zero and has no limit.
    assert statistics.spe_q == pytest.approx(0.0, abs=1e-18)
    assert statistics.spe_q_control_limit is None


def test_hotelling_t_squared_control_limit_matches_the_f_distribution_formula() -> None:
    """`T^2_alpha = a(n-1)(n+1) / (n(n-a)) * F_alpha(a, n-a)` (research/168 §1b)."""
    model = fit_known_two_signal_model()
    retained, baseline_count, alpha = model.retained_component_count, model.baseline_sample_count, 0.01
    expected = (
        (retained * (baseline_count - 1) * (baseline_count + 1))
        / (baseline_count * (baseline_count - retained))
    ) * float(fisher_f_distribution.ppf(1.0 - alpha, retained, baseline_count - retained))
    assert model.t_squared_control_limit == pytest.approx(expected, rel=1e-12)
    # Hand-anchored: a=2, n=12 -> scale = 2*11*13 / (12*10) = 2.3833...
    assert (retained * (baseline_count - 1) * (baseline_count + 1)) / (
        baseline_count * (baseline_count - retained)
    ) == pytest.approx(2.3833333333, rel=1e-9)


def test_spe_q_detects_a_broken_correlation_structure_that_t_squared_cannot() -> None:
    """Q catches observations that BREAK the healthy correlation structure (research/168 §1b)."""
    model = HealthyBaselinePrincipalComponentModel.fit_on_healthy_baseline(
        signal_names=("first_signal", "second_signal", "sum_signal"),
        baseline_matrix=KNOWN_RANK_DEFICIENT_BASELINE,
        retained_variance_ratio=0.95,
        control_limit_significance=0.01,
    )
    assert model is not None
    assert model.retained_component_count == 2  # the plane, not the ambient 3-space

    on_plane = model.evaluate_observation(
        {"first_signal": 7.0, "second_signal": 7.0, "sum_signal": 14.0}
    )
    off_plane = model.evaluate_observation(
        {"first_signal": 3.0, "second_signal": 3.0, "sum_signal": 30.0}
    )
    assert on_plane is not None and off_plane is not None

    # An extreme but structure-respecting point: large T^2, essentially no residual.
    assert on_plane.spe_q == pytest.approx(0.0, abs=1e-16)
    assert on_plane.t_squared > 1.0
    # A structure-breaking point: the residual explodes.
    assert off_plane.spe_q > 10.0
    assert off_plane.spe_q > on_plane.spe_q * 1e6


def test_spe_q_chi_square_control_limit_matches_the_formula_computed_by_hand() -> None:
    """`delta^2 = g * chi2_alpha(h)`, `g = w2/w1`, `h = w1^2/w2` over DISCARDED eigenvalues (§1b)."""
    alpha = 0.01
    discarded = np.array([0.5, 0.2, 0.05], dtype=np.float64)
    omega_1 = 0.5 + 0.2 + 0.05
    omega_2 = 0.5**2 + 0.2**2 + 0.05**2
    expected = (omega_2 / omega_1) * float(
        chi_square_distribution.ppf(1.0 - alpha, (omega_1 * omega_1) / omega_2)
    )
    assert spe_q_control_limit_chi_square_approximation(discarded, alpha) == pytest.approx(
        expected, rel=1e-12
    )
    # No discarded variance at all -> the chi-square route has nothing to build a threshold from.
    assert spe_q_control_limit_chi_square_approximation(np.array([]), alpha) is None
    assert spe_q_control_limit_chi_square_approximation(np.zeros(3), alpha) is None


def test_the_fitted_spe_q_limit_dominates_its_chi_square_and_empirical_components() -> None:
    """The deployed limit is the max of the chi-square form, the empirical quantile and the floor.

    Signals share a latent factor (which is what makes PCA meaningful at all), so a genuine residual
    subspace with positive variance survives the z-scoring.
    """
    generator = np.random.default_rng(11)
    latent = generator.normal(0.0, 1.0, 90)
    baseline = np.column_stack(
        [
            latent + generator.normal(0.0, 0.15, 90),
            latent + generator.normal(0.0, 0.15, 90),
            generator.normal(0.0, 1.0, 90),
        ]
    )
    alpha = 0.01
    model = HealthyBaselinePrincipalComponentModel.fit_on_healthy_baseline(
        signal_names=("primary", "correlated_twin", "independent"),
        baseline_matrix=baseline,
        retained_variance_ratio=0.80,
        control_limit_significance=alpha,
    )
    assert model is not None
    assert model.retained_component_count < 3          # a real residual subspace exists
    discarded = model.eigenvalues[model.retained_component_count:]
    chi_square_limit = spe_q_control_limit_chi_square_approximation(discarded, alpha)
    assert chi_square_limit is not None
    assert model.spe_q_control_limit is not None
    assert model.spe_q_control_limit >= chi_square_limit
    residual_dimension_count = 3 - model.retained_component_count
    assert model.spe_q_control_limit >= float(residual_dimension_count)

    # And the limit really is calibrated: a baseline-like point clears it, a structure break does not.
    in_control = model.evaluate_observation(
        {"primary": 0.5, "correlated_twin": 0.5, "independent": 0.0}
    )
    broken = model.evaluate_observation(
        {"primary": 3.0, "correlated_twin": -3.0, "independent": 0.0}
    )
    assert in_control is not None and broken is not None
    assert not in_control.is_spe_q_alarm
    assert broken.is_spe_q_alarm


def test_a_healthy_baseline_point_sits_comfortably_inside_both_control_limits() -> None:
    """Sanity on real geometry: an in-baseline observation must not raise either alarm."""
    model = fit_known_two_signal_model()
    middle_row = KNOWN_TWO_SIGNAL_BASELINE[6]
    statistics = model.evaluate_observation(
        {"first_signal": float(middle_row[0]), "second_signal": float(middle_row[1])}
    )
    assert statistics is not None
    assert not statistics.is_t_squared_alarm
    assert not statistics.is_spe_q_alarm


# =====================================================================================================
# UNIT — the EWMA layer, against the NIST recursion computed by hand
# =====================================================================================================


def test_update_ewma_level_matches_the_nist_recursion_by_hand() -> None:
    """`EWMA_t = lambda*Y_t + (1-lambda)*EWMA_{t-1}` (NIST §6.3.2.4, research/168 §1c).

    Hand-computed with lambda=0.3, EWMA_0=0 and Y=1 throughout:
        0.3*1 + 0.7*0     = 0.3
        0.3*1 + 0.7*0.3   = 0.51
        0.3*1 + 0.7*0.51  = 0.657
    """
    level = 0.0
    for expected in (0.3, 0.51, 0.657):
        level = update_ewma_level(level, 1.0, 0.3)
        assert level == pytest.approx(expected, rel=1e-12)

    # A mixed series, also hand-computed: lambda=0.5, Y = 0.4, 0.0, 1.0
    # (Written as plain statements on purpose: pytest 9's assertion rewriting mis-evaluates a walrus
    # binding inside an assert whose right-hand side also reads the bound name.)
    level = update_ewma_level(0.0, 0.4, 0.5)
    assert level == pytest.approx(0.20, rel=1e-12)
    level = update_ewma_level(level, 0.0, 0.5)
    assert level == pytest.approx(0.10, rel=1e-12)
    level = update_ewma_level(level, 1.0, 0.5)
    assert level == pytest.approx(0.55, rel=1e-12)

    # lambda = 1 degenerates to a plain Shewhart chart (NIST), i.e. no smoothing at all.
    assert update_ewma_level(0.9, 0.2, 1.0) == pytest.approx(0.2)


def test_ewma_standard_deviation_matches_the_nist_transient_formula() -> None:
    """`s_ewma = s*sqrt(lambda/(2-lambda) * (1-(1-lambda)^(2t)))` (research/168 §1c)."""
    smoothing_lambda, process_sigma = 0.2, 2.0
    for update_count in (1, 3, 25):
        expected = process_sigma * math.sqrt(
            (smoothing_lambda / (2.0 - smoothing_lambda))
            * (1.0 - (1.0 - smoothing_lambda) ** (2 * update_count))
        )
        assert ewma_standard_deviation(
            process_sigma, smoothing_lambda, update_count
        ) == pytest.approx(expected, rel=1e-12)

    # It converges upward to the steady-state form NIST quotes, and never exceeds it.
    steady_state = process_sigma * math.sqrt(smoothing_lambda / (2.0 - smoothing_lambda))
    assert ewma_standard_deviation(process_sigma, smoothing_lambda, 10_000) == pytest.approx(
        steady_state, rel=1e-9
    )
    assert ewma_standard_deviation(process_sigma, smoothing_lambda, 2) < steady_state
    assert ewma_standard_deviation(process_sigma, smoothing_lambda, 0) == 0.0


def test_estimator_ewma_level_follows_the_nist_recursion_on_declared_severities() -> None:
    """End-to-end: with a declared 0->1 ramp the severity IS the raw value, so the EWMA is exact."""
    calibration = HealthIndexCalibration(ewma_smoothing_lambda=0.3)
    estimator = ComponentHealthIndexEstimator(
        "component.under_test",
        calibration=calibration,
        signal_severity_specs=[SignalSeveritySpec("error_rate", nominal_value=0.0, alarm_value=1.0)],
    )
    expected_levels = [0.3, 0.51, 0.657]
    for index, expected in enumerate(expected_levels):
        assessment = estimator.ingest(telemetry({"error_rate": 1.0}, minute=index))
        assert assessment.ewma_level == pytest.approx(expected, rel=1e-12)


# =====================================================================================================
# UNIT — normalisation, fusion, banding
# =====================================================================================================


def test_control_limit_severity_map_is_anchored_bounded_and_monotone() -> None:
    severity_at_limit = 0.75
    at_limit = map_control_limit_ratio_to_severity(10.0, 10.0, severity_at_limit)
    assert at_limit == pytest.approx(severity_at_limit, rel=1e-12)

    assert map_control_limit_ratio_to_severity(0.0, 10.0, severity_at_limit) == 0.0
    assert map_control_limit_ratio_to_severity(-5.0, 10.0, severity_at_limit) == 0.0
    assert map_control_limit_ratio_to_severity(1e12, 10.0, severity_at_limit) == pytest.approx(1.0)

    previous = -1.0
    for statistic in (0.5, 1.0, 2.0, 5.0, 9.0, 10.0, 11.0, 40.0, 400.0):
        severity = map_control_limit_ratio_to_severity(statistic, 10.0, severity_at_limit)
        assert 0.0 <= severity <= 1.0
        assert severity > previous
        previous = severity

    # A comfortably in-control statistic must stay near zero — the whole reason for the Hill exponent.
    assert map_control_limit_ratio_to_severity(2.5, 10.0, severity_at_limit) < 0.06

    with pytest.raises(ValueError):
        map_control_limit_ratio_to_severity(1.0, 0.0, severity_at_limit)
    with pytest.raises(ValueError):
        map_control_limit_ratio_to_severity(1.0, 10.0, 1.0)


def test_weighted_max_fusion_never_averages_a_hard_failure_away() -> None:
    """research/172 §3, explicit: one hard failure must dominate, never be diluted."""
    one_dead_signal_among_many_healthy = [
        SeverityContribution("signal:dead_broker_session", 1.0, 1.0),
        *[SeverityContribution(f"signal:healthy_{index}", 0.0, 1.0) for index in range(19)],
    ]
    fused = fuse_severity_contributions_by_weighted_max(one_dead_signal_among_many_healthy)
    assert fused == 1.0
    arithmetic_mean = sum(
        contribution.weighted_severity for contribution in one_dead_signal_among_many_healthy
    ) / len(one_dead_signal_among_many_healthy)
    assert arithmetic_mean == pytest.approx(0.05)
    assert fused > arithmetic_mean  # the exact failure mode a weighted MEAN would produce

    assert fuse_severity_contributions_by_weighted_max([]) == 0.0
    assert fuse_severity_contributions_by_weighted_max(
        [SeverityContribution("signal:discounted", 1.0, 0.4)]
    ) == pytest.approx(0.4)


def test_degradation_state_bands_are_ordered_and_exhaustive() -> None:
    calibration = HealthIndexCalibration()
    assert classify_degradation_state(1.0, calibration) is DegradationState.HEALTHY
    assert classify_degradation_state(calibration.healthy_health_index_floor, calibration) is (
        DegradationState.HEALTHY
    )
    assert classify_degradation_state(0.79, calibration) is DegradationState.DEGRADED
    assert classify_degradation_state(0.49, calibration) is DegradationState.FAILING
    assert classify_degradation_state(0.19, calibration) is DegradationState.FAILED
    assert classify_degradation_state(0.0, calibration) is DegradationState.FAILED


def test_robust_ramp_anchors_on_the_in_control_edge_not_the_median() -> None:
    """Ordinary healthy variation must score exactly zero severity (see the calibration comment)."""
    values = [10.0 + 1.0 * offset for offset in (-1.5, -1.0, -0.5, 0.0, 0.0, 0.5, 1.0, 1.5, 2.0, -2.0)]
    ramp = robust_severity_ramp_from_baseline(values, 3.0, 6.0)
    assert ramp is not None
    nominal_value, alarm_value = ramp
    assert nominal_value > float(np.median(values))
    assert alarm_value > nominal_value
    # The span between the two anchors is exactly (k_alarm - k_nominal) robust sigmas.
    assert (alarm_value - nominal_value) == pytest.approx(nominal_value - np.median(values))

    assert robust_severity_ramp_from_baseline([7.0] * 50, 3.0, 6.0) is None   # zero scale
    assert robust_severity_ramp_from_baseline([1.0], 3.0, 6.0) is None        # too few
    assert robust_severity_ramp_from_baseline([], 3.0, 6.0) is None


def test_linear_severity_ramp_saturates_instead_of_overflowing() -> None:
    """A huge finite reading over a tiny ramp span must saturate, not produce inf (Rule O.4)."""
    assert linear_severity_ramp(0.0, 0.0, 1.0) == 0.0
    assert linear_severity_ramp(0.25, 0.0, 1.0) == pytest.approx(0.25)
    assert linear_severity_ramp(1.0, 0.0, 1.0) == 1.0
    # (1e308 - 0) / 1e-300 overflows to inf in plain float arithmetic.
    assert linear_severity_ramp(1e308, 0.0, 1e-300) == 1.0
    assert linear_severity_ramp(-1e308, 0.0, 1e-300) == 0.0
    assert linear_severity_ramp(-1e308, -1e308, 1e308) == 0.0
    with pytest.raises(ValueError, match="finite"):
        linear_severity_ramp(float("nan"), 0.0, 1.0)
    with pytest.raises(ValueError, match="higher = worse"):
        linear_severity_ramp(0.5, 1.0, 1.0)


def test_extreme_magnitude_telemetry_does_not_break_the_index() -> None:
    """End-to-end version of the same hazard, through the declared and the robust ramp alike."""
    estimator = ComponentHealthIndexEstimator(
        "component.under_test",
        signal_severity_specs=[SignalSeveritySpec("tiny_span_signal", 0.0, 1e-300)],
    )
    for index, value in enumerate([1e308, -1e308, 0.0, 1e308]):
        assessment = estimator.ingest(
            telemetry({"tiny_span_signal": value, "huge_signal": value}, minute=index)
        )
        assert_assessment_invariants(assessment)

    undeclared = ComponentHealthIndexEstimator("component.under_test")
    for index in range(60):
        assessment = undeclared.ingest(
            telemetry({"huge_signal": 1e300 * (1.0 + index * 1e-3)}, minute=index)
        )
        assert_assessment_invariants(assessment)


def test_signal_severity_spec_rejects_an_inverted_polarity() -> None:
    """The convention is higher = worse; a spec that says otherwise is a bug, not a silent flip."""
    with pytest.raises(ValueError, match="higher signal value = worse"):
        SignalSeveritySpec("cache_hit_rate", nominal_value=1.0, alarm_value=0.0)
    ramp = SignalSeveritySpec("heartbeat_age_seconds", nominal_value=30.0, alarm_value=180.0)
    assert ramp.severity_for_value(30.0) == 0.0
    assert ramp.severity_for_value(105.0) == pytest.approx(0.5)
    assert ramp.severity_for_value(1e9) == 1.0
    assert ramp.severity_for_value(-1e9) == 0.0


def test_calibration_rejects_incoherent_settings() -> None:
    with pytest.raises(ValueError, match="ewma_smoothing_lambda"):
        HealthIndexCalibration(ewma_smoothing_lambda=0.0)
    with pytest.raises(ValueError, match="alpha"):
        HealthIndexCalibration(control_limit_significance=0.9)
    with pytest.raises(ValueError, match="floors"):
        HealthIndexCalibration(healthy_health_index_floor=0.1, degraded_health_index_floor=0.9)
    with pytest.raises(ValueError, match="robust_alarm_sigma_multiple"):
        HealthIndexCalibration(robust_nominal_sigma_multiple=6.0, robust_alarm_sigma_multiple=3.0)
    with pytest.raises(ValueError, match="weight"):
        HealthIndexCalibration(spe_q_weight=2.0)


# =====================================================================================================
# PROPERTY / INVARIANT (hypothesis)
# =====================================================================================================

finite_signal_value = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6, width=64),
    # Extreme-but-finite magnitudes: the range where naive ramp arithmetic overflows to inf.
    st.sampled_from([1e300, -1e300, 1e-300, -1e-300, 1.7976931348623157e308]),
)
telemetry_series = st.lists(
    st.dictionaries(
        keys=st.sampled_from(["alpha_signal", "beta_signal", "gamma_signal"]),
        values=finite_signal_value,
        min_size=0,
        max_size=3,
    ),
    min_size=0,
    max_size=45,
)


def assert_assessment_invariants(assessment: ComponentHealthAssessment) -> None:
    """The two invariants research/172 §5 grades this engine on."""
    assert math.isfinite(assessment.health_index)
    assert 0.0 <= assessment.health_index <= 1.0
    assert 0.0 <= assessment.required_sample_count == MINIMUM_BASELINE_SAMPLE_COUNT_FOR_PCA
    assert assessment.is_pca_armed == (assessment.t_squared is not None)
    for _, severity in assessment.contributing_signals:
        assert 0.0 <= severity <= 1.0
        # Weighted-MAX: the fused index is never BETTER than the worst contributing signal.
        assert assessment.health_index <= 1.0 - severity + 1e-12
    if assessment.contributing_signals:
        worst_severity = max(severity for _, severity in assessment.contributing_signals)
        assert assessment.health_index == pytest.approx(1.0 - worst_severity, abs=1e-12)
    else:
        assert assessment.health_index == 1.0


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(series=telemetry_series)
def test_health_index_stays_in_the_unit_interval_for_arbitrary_finite_telemetry(
    series: list[dict[str, float]],
) -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    for index, signal_values in enumerate(series):
        assert_assessment_invariants(estimator.ingest(telemetry(signal_values, minute=index)))
    assert_assessment_invariants(
        assess_component_health(
            "component.under_test",
            [telemetry(values, minute=index) for index, values in enumerate(series)],
        )
    )


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    severities=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False), min_size=1, max_size=25
    ),
    weights=st.lists(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False), min_size=1, max_size=25
    ),
)
def test_weighted_max_fusion_is_never_better_than_the_worst_contributor(
    severities: list[float], weights: list[float]
) -> None:
    contributions = [
        SeverityContribution(f"signal:{index}", severity, weight)
        for index, (severity, weight) in enumerate(zip(severities, weights, strict=False))
    ]
    fused = fuse_severity_contributions_by_weighted_max(contributions)
    assert 0.0 <= fused <= 1.0
    for contribution in contributions:
        assert fused >= contribution.weighted_severity
    assert fused == max(contribution.weighted_severity for contribution in contributions)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    healthy_value=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    catastrophic_value=st.floats(min_value=1e6, max_value=1e12, allow_nan=False),
)
def test_a_single_catastrophic_signal_drives_the_index_to_failed(
    healthy_value: float, catastrophic_value: float
) -> None:
    """No number of healthy signals may dilute one declared-failed signal."""
    specs = [
        SignalSeveritySpec(f"healthy_signal_{index}", 0.0, 1e15) for index in range(9)
    ] + [SignalSeveritySpec("dead_session_seconds_past_expiry", 0.0, 1.0)]
    estimator = ComponentHealthIndexEstimator("component.under_test", signal_severity_specs=specs)
    signal_values = {f"healthy_signal_{index}": healthy_value for index in range(9)}
    signal_values["dead_session_seconds_past_expiry"] = catastrophic_value
    assessment = estimator.ingest(telemetry(signal_values))
    assert assessment.health_index == 0.0
    assert assessment.degradation_state is DegradationState.FAILED


# =====================================================================================================
# ADVERSARIAL
# =====================================================================================================


def test_non_finite_telemetry_is_charged_not_crashed_and_never_enters_the_baseline() -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    for index, bad_value in enumerate([float("nan"), float("inf"), float("-inf")]):
        assessment = estimator.ingest(
            telemetry({"heartbeat_age_seconds": bad_value, "error_rate": 0.01}, minute=index)
        )
        assert_assessment_invariants(assessment)
        assert assessment.health_index < 1.0
        names = [name for name, _ in assessment.contributing_signals]
        assert "unreadable_signal:heartbeat_age_seconds" in names
    diagnostics = estimator.diagnostics()
    assert diagnostics.unreadable_signal_observation_count == 3
    assert diagnostics.baseline_rejection_count == 3
    assert estimator.healthy_baseline_sample_count == 0   # NaN must never poison a healthy baseline


def test_non_numeric_telemetry_value_is_reported_rather_than_raising() -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    assessment = estimator.ingest(
        telemetry({"weird_signal": "not-a-number"})  # type: ignore[dict-item]
    )
    assert_assessment_invariants(assessment)
    assert estimator.diagnostics().unreadable_signal_observation_count == 1
    assert any(
        name == "unreadable_signal:weird_signal" for name, _ in assessment.contributing_signals
    )


def test_one_thousand_identical_samples_abstain_honestly_instead_of_inventing_a_number() -> None:
    """Zero-variance baseline: no scale estimator exists, so every layer must abstain, not fabricate."""
    estimator = ComponentHealthIndexEstimator("component.under_test")
    assessment = None
    for index in range(1000):
        assessment = estimator.ingest(
            telemetry({"heartbeat_age_seconds": 30.0, "error_rate": 0.0}, minute=index)
        )
    assert assessment is not None
    assert_assessment_invariants(assessment)
    assert assessment.health_index == 1.0                  # no evidence of degradation
    assert assessment.degradation_state is DegradationState.HEALTHY
    assert assessment.t_squared is None and assessment.spe_q is None
    assert assessment.is_pca_armed is False                # a constant baseline has no covariance
    # Signals are still reported as watched, but every one abstains at severity zero — nothing invented.
    assert all(severity == 0.0 for _, severity in assessment.contributing_signals)
    assert not any(
        name.startswith("signal:") for name, _ in assessment.contributing_signals
    )
    assert assessment.sample_count == estimator.calibration.maximum_baseline_sample_count
    assert estimator.diagnostics().pca_fit_abstention_count > 0
    assert set(estimator.diagnostics().abstaining_signal_names) == {
        "heartbeat_age_seconds", "error_rate"
    }


def test_empty_sample_list_yields_the_abstaining_identity_assessment() -> None:
    assessment = assess_component_health("component.under_test", [])
    assert_assessment_invariants(assessment)
    assert assessment.component_id == "component.under_test"
    assert assessment.health_index == 1.0
    assert assessment.sample_count == 0
    assert assessment.required_sample_count == MINIMUM_BASELINE_SAMPLE_COUNT_FOR_PCA
    assert assessment.is_pca_armed is False
    assert assessment.t_squared is None and assessment.spe_q is None
    assert assessment.ewma_level == 0.0
    assert assessment.maturity_description == "have 0 / need 30"
    assert assessment.worst_contributing_signal is None


def test_a_single_sample_produces_an_honest_assessment() -> None:
    """One observation cannot support any variance estimate — but a declared spec still works."""
    undeclared = assess_component_health(
        "component.under_test", [telemetry({"heartbeat_age_seconds": 400.0})]
    )
    assert_assessment_invariants(undeclared)
    assert undeclared.health_index == 1.0            # nothing to compare 400.0 against yet
    # Scored against an empty baseline: the sample is admitted only AFTER it has been judged.
    assert undeclared.sample_count == 0
    assert undeclared.is_pca_armed is False

    declared = assess_component_health(
        "component.under_test",
        [telemetry({"heartbeat_age_seconds": 400.0})],
        signal_severity_specs=[SignalSeveritySpec("heartbeat_age_seconds", 30.0, 180.0)],
    )
    assert_assessment_invariants(declared)
    assert declared.health_index == 0.0              # the declared-threshold path acts immediately
    assert declared.degradation_state is DegradationState.FAILED


def test_empty_signal_dictionary_is_counted_and_survives() -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    assessment = estimator.ingest(telemetry({}))
    assert_assessment_invariants(assessment)
    assert assessment.health_index == 1.0
    assert estimator.diagnostics().empty_sample_count == 1
    assert estimator.healthy_baseline_sample_count == 0


def test_a_sample_routed_to_the_wrong_component_raises_rather_than_corrupting_state() -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    with pytest.raises(ValueError, match="routed to the estimator"):
        estimator.ingest(telemetry({"x": 1.0}, component_id="some.other.component"))


def test_naive_timestamps_are_rejected_at_the_contract_boundary() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ComponentTelemetrySample("component.under_test", datetime(2026, 7, 27, 4, 0), {"x": 1.0})
    with pytest.raises(ValueError, match="non-empty identifier"):
        ComponentTelemetrySample("", EPOCH, {"x": 1.0})


def test_out_of_order_telemetry_is_counted_and_still_processed() -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    estimator.ingest(telemetry({"x": 1.0}, minute=10))
    assessment = estimator.ingest(telemetry({"x": 1.0}, minute=3))
    assert_assessment_invariants(assessment)
    assert estimator.diagnostics().out_of_order_sample_count == 1
    assert estimator.healthy_baseline_sample_count == 2   # counted, not silently dropped


def test_an_assessment_that_escapes_the_unit_interval_cannot_be_constructed() -> None:
    """The contract itself is the last line of defence against a fabricated index."""
    with pytest.raises(ValueError, match=r"escaped \[0, 1\]"):
        ComponentHealthAssessment(
            "component.under_test", 1.5, None, None, 0.0, DegradationState.HEALTHY, 0, 30, False, ()
        )
    with pytest.raises(ValueError, match="is_pca_armed must agree"):
        ComponentHealthAssessment(
            "component.under_test", 0.9, 4.0, 0.1, 0.0, DegradationState.HEALTHY, 40, 30, False, ()
        )


def test_a_degenerate_baseline_column_is_excluded_without_taking_the_model_down() -> None:
    """A constant signal alongside varying ones must not block the multivariate model."""
    estimator = ComponentHealthIndexEstimator("component.under_test")
    generator = np.random.default_rng(3)
    assessment = None
    for index in range(45):
        assessment = estimator.ingest(
            telemetry(
                {
                    "always_zero": 0.0,
                    "heartbeat_age_seconds": float(30.0 + generator.normal(0.0, 2.0)),
                    "staleness_hours": float(1.0 + generator.normal(0.0, 0.1)),
                },
                minute=index,
            )
        )
    assert assessment is not None
    assert assessment.is_pca_armed is True
    assert "always_zero" in estimator.diagnostics().constant_baseline_signal_names
    assert "always_zero" in estimator.diagnostics().abstaining_signal_names


# =====================================================================================================
# MATURITY LADDER (Rule Q / research/172 §4)
# =====================================================================================================


def test_pca_abstains_below_the_threshold_and_arms_itself_automatically_at_it() -> None:
    estimator = ComponentHealthIndexEstimator("component.under_test")
    assert estimator.required_baseline_sample_count == MINIMUM_BASELINE_SAMPLE_COUNT_FOR_PCA == 30

    saw_immature_assessment = False
    saw_armed_assessment = False
    for sample in healthy_noise_series(80):
        assessment = estimator.ingest(sample)
        assert_assessment_invariants(assessment)
        # A health index is produced on EVERY cycle, mature or not — that is the Rule-Q requirement.
        assert 0.0 <= assessment.health_index <= 1.0
        if assessment.sample_count < assessment.required_sample_count:
            saw_immature_assessment = True
            assert assessment.is_pca_armed is False
            assert assessment.t_squared is None
            assert assessment.spe_q is None
            assert assessment.maturity_description == (
                f"have {assessment.sample_count} / need 30"
            )
        else:
            saw_armed_assessment = True
            assert assessment.is_pca_armed is True
            assert assessment.t_squared is not None and assessment.t_squared >= 0.0
            assert assessment.spe_q is not None and assessment.spe_q >= 0.0

    assert saw_immature_assessment and saw_armed_assessment
    assert estimator.is_pca_armed is True


def test_the_immature_path_still_acts_on_a_declared_threshold_breach() -> None:
    """Rule Q: full function while immature — the declared path carries the whole assessment."""
    estimator = ComponentHealthIndexEstimator(
        "component.under_test",
        signal_severity_specs=[SignalSeveritySpec("seconds_since_last_heartbeat", 30.0, 180.0)],
    )
    healthy = estimator.ingest(telemetry({"seconds_since_last_heartbeat": 30.0}, minute=0))
    assert healthy.is_pca_armed is False
    assert healthy.health_index == 1.0
    assert healthy.degradation_state is DegradationState.HEALTHY

    breached = estimator.ingest(telemetry({"seconds_since_last_heartbeat": 200.0}, minute=1))
    assert breached.is_pca_armed is False           # still immature ...
    assert breached.t_squared is None
    assert breached.health_index == 0.0             # ... yet it acts, immediately and at full severity
    assert breached.degradation_state is DegradationState.FAILED
    assert breached.sample_count < breached.required_sample_count


@pytest.mark.parametrize("seed", [99, 7, 123, 2026, 55])
def test_arming_lowers_no_guard_a_healthy_component_still_reads_healthy(seed: int) -> None:
    """The armed PCA layer must not manufacture alarms on a genuinely in-control component.

    This is the test that forced the two-window design: with the statistical detectors fused raw at full
    weight, their designed alpha = 0.01 false-alarm rate landed directly on the health index and an
    in-control component read FAILED about once every hundred cycles. Measured over 40 seeds after the
    fix: 94.5% HEALTHY, 5.5% DEGRADED, and zero FAILING/FAILED out of ~5,200 healthy assessments.
    """
    estimator = ComponentHealthIndexEstimator("component.under_test")
    assessments = estimator.ingest_all(healthy_noise_series(160, seed=seed))
    armed = [assessment for assessment in assessments if assessment.is_pca_armed]
    assert len(armed) > 100
    healthy_fraction = sum(
        assessment.degradation_state is DegradationState.HEALTHY for assessment in armed
    ) / len(armed)
    assert healthy_fraction > 0.75
    # A healthy component must NEVER be declared FAILED or FAILING — those bands veto real trading.
    assert not any(
        assessment.degradation_state in {DegradationState.FAILED, DegradationState.FAILING}
        for assessment in armed
    )


def test_an_armed_component_detects_a_multivariate_structure_break_via_spe_q() -> None:
    """The payoff for arming: a fault inside every univariate range but OFF the healthy manifold.

    Queue depth and worker utilisation move together in health. An observation where both sit well
    inside their own ranges but move in OPPOSITE directions breaks that correlation — which is exactly
    the fault SPE/Q exists for and which no per-signal threshold can express. T-squared correctly stays
    small here: the point projects to the centre of the retained subspace. That complementarity is the
    whole reason research/168 §1b insists both statistics are monitored.
    """
    estimator = ComponentHealthIndexEstimator("component.under_test")
    generator = np.random.default_rng(5)
    for index, latent in enumerate(generator.normal(0.0, 1.0, 90)):
        estimator.ingest(
            telemetry(
                {
                    "queue_depth": float(50.0 + 10.0 * latent),
                    "worker_utilisation": float(0.5 + 0.1 * latent),
                },
                minute=index,
            )
        )
    assert estimator.is_pca_armed is True

    first_break = estimator.ingest(
        telemetry({"queue_depth": 70.0, "worker_utilisation": 0.3}, minute=200)
    )
    assert first_break.is_pca_armed is True
    assert first_break.spe_q is not None and first_break.spe_q > 5.0
    assert first_break.t_squared is not None and first_break.t_squared < 1.0
    severities = dict(first_break.contributing_signals)
    assert severities["spe_q_residual"] > 0.3
    assert severities["signal:queue_depth"] == 0.0        # invisible to the per-signal path
    assert severities["signal:worker_utilisation"] == 0.0
    # A SINGLE anomalous reading tightens but does not veto — the short window is capped by design.
    assert first_break.degradation_state is DegradationState.DEGRADED

    # A SUSTAINED break escalates all the way, because the long (EWMA) window now agrees.
    for offset in range(1, 25):
        sustained = estimator.ingest(
            telemetry({"queue_depth": 70.0, "worker_utilisation": 0.3}, minute=200 + offset)
        )
    assert sustained.health_index < 0.2
    assert sustained.degradation_state is DegradationState.FAILED
    assert dict(sustained.contributing_signals)["multivariate_anomaly_ewma"] > 0.8


def test_an_armed_component_detects_an_extreme_in_structure_excursion_via_t_squared() -> None:
    """The complementary half: a point far along the healthy direction raises T-squared, not SPE."""
    estimator = ComponentHealthIndexEstimator("component.under_test")
    generator = np.random.default_rng(17)
    for index, latent in enumerate(generator.normal(0.0, 1.0, 90)):
        estimator.ingest(
            telemetry(
                {
                    "queue_depth": float(50.0 + 10.0 * latent),
                    "worker_utilisation": float(0.5 + 0.1 * latent),
                },
                minute=index,
            )
        )
    assert estimator.is_pca_armed is True
    excursion = estimator.ingest(
        telemetry({"queue_depth": 130.0, "worker_utilisation": 1.3}, minute=200)
    )
    assert excursion.t_squared is not None and excursion.t_squared > 25.0
    assert excursion.spe_q is not None and excursion.spe_q < 1.0
    assert dict(excursion.contributing_signals)["hotelling_t_squared"] > 0.3


def test_a_sustained_degradation_is_caught_by_the_smoothed_alarm_path() -> None:
    """EWMA is the primary alarm path (research/168 §1c) — it must persist a sustained shift."""
    estimator = ComponentHealthIndexEstimator(
        "component.under_test",
        signal_severity_specs=[SignalSeveritySpec("error_rate", 0.0, 0.5)],
    )
    for index in range(40):
        estimator.ingest(telemetry({"error_rate": 0.0}, minute=index))
    assert estimator.ewma_level == pytest.approx(0.0)

    for index in range(40, 180):
        assessment = estimator.ingest(telemetry({"error_rate": 0.20}, minute=index))
    assert assessment.ewma_level == pytest.approx(0.4, abs=1e-6)   # 0.20 / 0.50 declared ramp
    assert assessment.degradation_state is not DegradationState.HEALTHY
    # The alarm PERSISTS through one clean reading rather than resetting on it.
    recovered = estimator.ingest(telemetry({"error_rate": 0.0}, minute=180))
    assert recovered.ewma_level > 0.3
    assert recovered.health_index < 0.7
    # ADWIN independently flags the change — the cross-check for signals whose timescale is unknown.
    assert estimator.diagnostics().adwin_drift_detection_count >= 1


# =====================================================================================================
# FLEET FACADE
# =====================================================================================================


def test_the_engine_keeps_per_component_state_apart_on_an_interleaved_stream() -> None:
    engine = ComponentHealthIndexEngine(
        signal_severity_specs_by_component_id={
            "session.kite": (SignalSeveritySpec("hours_past_token_expiry", 0.0, 1.0),),
            "store.market_data": (SignalSeveritySpec("staleness_hours", 24.0, 72.0),),
        }
    )
    interleaved: list[ComponentTelemetrySample] = []
    for index in range(12):
        interleaved.append(
            telemetry({"hours_past_token_expiry": 6.0}, minute=index, component_id="session.kite")
        )
        interleaved.append(
            telemetry({"staleness_hours": 2.0}, minute=index, component_id="store.market_data")
        )
    assessments = engine.assess_all(interleaved)

    assert set(assessments) == {"session.kite", "store.market_data"}
    assert engine.tracked_component_ids() == ("session.kite", "store.market_data")
    expired_session = assessments["session.kite"]
    fresh_store = assessments["store.market_data"]
    assert expired_session.health_index == 0.0
    assert expired_session.degradation_state is DegradationState.FAILED
    assert fresh_store.health_index == 1.0
    assert fresh_store.degradation_state is DegradationState.HEALTHY
    # research/172 §5.5: the index must SEPARATE the genuinely degraded from the healthy.
    assert expired_session.health_index < fresh_store.health_index
    for assessment in assessments.values():
        assert_assessment_invariants(assessment)


def test_the_engine_reuses_one_estimator_per_component() -> None:
    engine = ComponentHealthIndexEngine()
    first = engine.estimator_for("thread.live_paper_loop")
    second = engine.estimator_for("thread.live_paper_loop")
    assert first is second
    assert engine.estimator_for("store.news") is not first
