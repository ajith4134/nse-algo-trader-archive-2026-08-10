"""Trunk X AUTOPOIESIS — the component HEALTH INDEX: raw telemetry -> one scalar `h(t) in [0,1]`.

This is the PHM/CBM "health index" layer of the component-lifecycle homeostat (spec: research/172 §3
health-index row, §4 maturity ladder, §5 acceptance criteria). It turns a stream of per-signal telemetry
observations about ONE component into a single scalar the rest of the homeostat can reason over:
`1.0` = perfectly healthy, `0.0` = failed. The sign convention is chosen so the index composes directly
as a multiplier in the tighten-only vitality gate (research/172 §2 "sign/unit conventions").

--------------------------------------------------------------------------------------------------
THE MATH (all formulas from research/168 §1 — every one of them verified there against a primary source
except where that document explicitly flags otherwise; the flags are repeated inline below)
--------------------------------------------------------------------------------------------------

1. PER-SIGNAL NORMALISATION (research/168 §1d).
   Convention: **higher raw signal value = worse** (heartbeat-age seconds, consecutive-failure count,
   staleness hours, error rate, lock-wait milliseconds ... all grow as the component degrades). Each raw
   signal is mapped onto a *severity* in `[0,1]` by a linear ramp between a declared `nominal_value`
   (fully healthy) and a declared `alarm_value` (fully failed):

       severity = clip((value - nominal) / (alarm - nominal), 0, 1)

   When no `SignalSeveritySpec` is declared for a signal, the ramp is derived from the component's own
   healthy baseline **robustly**: `nominal = median + 3 * scale` (the Shewhart in-control edge, so
   ordinary healthy variation scores exactly zero) and `alarm = median + 6 * scale`, where `scale` is
   `1.4826 *` the median of the deviations ABOVE the median — 1.4826 being the Gaussian consistency
   constant for the MAD, and the upper semi-deviation being the right estimator because the convention
   makes the upper tail the one that matters — falling back to the symmetric MAD and then to the sample
   standard deviation as each collapses. If no scale estimator is usable
   (all-identical baseline, or too few baseline samples) the signal **abstains**: it contributes nothing
   rather than a fabricated number (Rule O.3/O.4).

2. PCA + HOTELLING'S T-SQUARED + SPE/Q (research/168 §1b — multivariate statistical process control).
   Telemetry signals are collinear by construction (heartbeat latency, queue depth, error rate and
   retry count all move together under load), so the multivariate model is fitted on the component's
   own **healthy baseline** after z-scoring, and two ORTHOGONAL statistics are monitored:

   * `T^2 = sum_k t_k^2 / lambda_k` over the `a` retained principal components, where `t` is the score
     vector of the new observation and `lambda_k` the k-th eigenvalue (`PCA.explained_variance_`).
     T-squared IS the squared Mahalanobis distance expressed in the reduced PC basis (research/168 §1a
     and §1b are the same statistic in two coordinate systems). It catches an observation that moves to
     an unusual joint value *within* the healthy correlation structure.
     Control limit (research/168 §1b; that document flags this one as recalled from Jackson 1991 /
     Chiang-Russell-Braatz 2001 rather than re-fetched this pass — it is standard textbook material):

         T^2_alpha = [a (n - 1)(n + 1)] / [n (n - a)] * F_alpha(a, n - a)

     with `n` = number of healthy-baseline samples the PCA was fitted on.

   * `Q = || x - x_hat ||^2` (SPE, squared prediction error), the residual OUTSIDE the retained
     subspace, where `x_hat` is `x` reconstructed from the `a` retained components only. It catches an
     observation that *breaks* the healthy correlation structure. Control limit via the chi-square
     approximation, which research/168 §1b verified directly (the refined Jackson & Mudholkar 1979
     normal-approximation form could NOT be transcribed verbatim from any source that pass — see
     research/168 §7 — so the verified chi-square form is what is implemented here):

         delta^2 = g * chi2_alpha(h),  g = w2 / w1,  h = w1^2 / w2,  w_i = sum_{j>a} lambda_j^i

     i.e. the *discarded* eigenvalue spectrum alone sets the SPE alarm threshold. That spectrum
     collapses to numerical zero whenever the healthy baseline is (near-)perfectly collinear, so the
     limit actually used is the MAXIMUM of the chi-square form, the `(1-alpha)` empirical quantile of
     the baseline's own `Q` values, and a one-sigma-squared-per-residual-dimension practical floor —
     see `_spe_q_control_limit`. Without that, a rigid healthy relation could be broken outright and
     SPE would have no threshold to report it against (found by test, not by inspection).

   Decision rule (research/168 §1b): a fault is indicated iff `T^2 > T^2_alpha` OR `Q > delta^2`. The
   two are complementary, never redundant — which is why both are computed and both are fused, rather
   than collapsing them into one score the way a generic PCA outlier detector does (research/168 §6
   rejects `pyod`'s PCA detector as the primary primitive for exactly this reason).

3. EWMA — THE TEMPORAL LAYER AND THE PRIMARY ALARM PATH (research/168 §1c, verified verbatim against
   the NIST/SEMATECH e-Handbook §6.3.2.4):

       EWMA_t = lambda * Y_t + (1 - lambda) * EWMA_{t-1}

   with `EWMA_0` = the healthy-baseline mean (here `0.0`: on the severity scale, healthy IS zero).
   Control limit `UCL = centre + k * s_ewma` with the transient variance form

       s^2_ewma = s^2 * [lambda / (2 - lambda)] * (1 - (1 - lambda)^(2t))

   which converges to the steady-state `s^2 * lambda/(2-lambda)` that NIST states. The EWMA is what
   carries the assessment while the PCA layer is immature: it needs no baseline covariance, only the
   per-signal severities, so it is armed from the very first observation.

4. ADWIN CROSS-CHECK (research/168 §1c/§6; `river.drift.ADWIN`). EWMA has a fixed smoothing constant.
   For a component whose degradation timescale is not known a priori that constant is a guess, so the
   severity stream is ALSO fed to ADWIN's adaptive-window change detector as an independent second
   opinion. A detected drift contributes only when it is an UPWARD (worsening) drift — an improving
   component must not be penalised for changing.

4b. TWO WINDOWS FOR STATISTICAL EVIDENCE, ONE FOR DIRECT EVIDENCE. `T^2`, `Q` and any per-signal ramp
   *derived from the baseline* are statistical **inferences**, carrying a designed false-alarm rate;
   a **declared**-threshold breach ("this token expired four hours ago") and an unreadable value are
   direct **observations**. Fusing both kinds identically hands the false-alarm rate straight to the
   vitality gate — an in-control component reads FAILED on noise and vetoes real trading. So every
   inference enters as a short window capped inside the DEGRADED band, plus a long EWMA-smoothed window
   with full authority: both must agree before the index collapses, which is the multiwindow structure
   of research/168 §4 (Google SRE burn-rate alerting). Observations act instantly and unsmoothed.

5. FUSION BY WEIGHTED-MAX, NEVER WEIGHTED-MEAN (research/168 §1d; research/172 §3, explicit):

       fused_severity = max_i (weight_i * severity_i)
       health_index   = 1 - fused_severity

   A component with a dead broker session is not "50% healthy" because its threading subsystem is fine.
   Averaging would let one hard failure be diluted by any number of healthy signals; the max cannot be
   diluted. This is the same "never average away a hard failure" principle Rule O.4 states generally.
   The direct consequence, asserted as an invariant in the tests: **the fused index is never better than
   the worst contributing signal.**

--------------------------------------------------------------------------------------------------
RULE-Q MATURITY LADDER (research/172 §4, row 1)
--------------------------------------------------------------------------------------------------
The FULL code path above exists from the first observation. Only the *arming* of the PCA layer is
data-gated: it needs `>= 30` healthy-baseline samples for the T-squared control limit to mean anything.
Below that threshold the PCA layer **abstains** (`t_squared is None`, `spe_q is None`,
`is_pca_armed is False`) and the EWMA + declared-threshold path carries the whole assessment; a health
index is still produced every single cycle. The component arms itself automatically the moment its 30th
healthy baseline sample lands — no code change, no new slice. `sample_count` / `required_sample_count`
are the `have N / need M` pair research/172 §4 requires on the dashboard.

Baseline admission convention: a sample is scored FIRST, against the baseline as it stood without it,
and is admitted afterwards only if it was in control on every unsmoothed statistic (per-signal ramps,
EWMA level, raw `T^2`/`Q`) and every one of its values was readable. This is the textbook
adaptive/recursive-MSPC rule — update the model with in-control data only — and including the
multivariate statistics in the gate is load-bearing: without them the gate is blind to exactly the
faults the PCA layer exists to catch, and a sustained structure break gets absorbed into the "healthy"
baseline and relearned as normal. `sample_count` therefore reports the baseline size the assessment was
actually computed against.

Safe identity behaviour while immature (Rule Q, "safe identity behavior"): with no evidence of
degradation the index is `1.0`. Because every consumer of this index is tighten-only (the vitality gate
can shrink or veto, never up-size — research/172 §2), `1.0` is the identity element, and "no data" must
therefore read as `1.0` rather than as a fabricated pessimistic number.

--------------------------------------------------------------------------------------------------
CONSUMERS (Rule G). This module is the health-index row of research/172 §8. Its declared consumers are
`autopoiesis_orchestrator` (the MAPE-K Analyze phase), `component_failure_hazard_model` (the health
trajectory is the Wiener first-passage degradation signal), `maintenance_policy_solver` (the health
index is the MDP's discretized state) and `organism_vitality_gate` (the entry-site multiplier). Those
modules are queued in `docs/BACKLOG.md` under the component-lifecycle homeostat feature.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Final

import numpy as np
from numpy.typing import NDArray
from river.drift import ADWIN
from scipy.stats import chi2 as chi_square_distribution
from scipy.stats import f as fisher_f_distribution
from sklearn.decomposition import PCA

LOGGER: Final = logging.getLogger(__name__)

#: Rule-Q arming threshold for the PCA/T-squared layer (research/172 §4, row 1). Below this many
#: healthy-baseline samples the PCA layer abstains and the EWMA + declared-threshold path carries the
#: assessment. This is the "need M" half of the dashboard's `have N / need M`.
MINIMUM_BASELINE_SAMPLE_COUNT_FOR_PCA: Final[int] = 30

#: Gaussian consistency constant: 1.4826 * MAD estimates sigma for normally distributed data.
_MEDIAN_ABSOLUTE_DEVIATION_TO_SIGMA: Final[float] = 1.4826

#: Below this a baseline column is treated as constant — z-scoring it would divide by ~zero.
_ZERO_VARIANCE_TOLERANCE: Final[float] = 1e-12

#: Slack allowed when comparing cumulative explained variance against the retained-variance target, so
#: that `retained_variance_ratio=1.0` selects the full spectrum despite float round-off in the cumsum.
_CUMULATIVE_VARIANCE_TOLERANCE: Final[float] = 1e-9

#: Largest magnitude the multivariate layer will accept. Every statistic here sums SQUARES, and
#: `float64` overflows above ~1.34e154, so a baseline holding values beyond this bound would silently
#: produce `inf` variances and `nan` explained-variance ratios. The layer abstains instead — the raw
#: value is still covered by its own per-signal ramp, so no evidence is lost (Rule O.3/O.4).
_MAXIMUM_SAFE_MAGNITUDE_FOR_SUM_OF_SQUARES: Final[float] = 1e150


class DegradationState(str, Enum):
    """Discrete condition band of a component, derived from the scalar health index.

    These are the states the maintenance-policy MDP discretizes over (research/168 §3a) and the bands
    the vitality gate keys its tighten/veto decision off (research/172 §2).
    """

    HEALTHY = "healthy"      # no evidence of degradation; full behaviour permitted
    DEGRADED = "degraded"    # measurable degradation; tighten, do not veto
    FAILING = "failing"      # at or past a control limit; repair/quarantine territory
    FAILED = "failed"        # effectively dead; veto anything that depends on it


@dataclass(frozen=True)
class ComponentTelemetrySample:
    """One point-in-time reading of every vital sign of ONE component.

    `signal_values` follows the module-wide convention: **higher value = worse**. A collector that
    naturally produces a "goodness" signal (e.g. cache hit-rate) must invert it before emitting, so
    that this module never has to guess a signal's polarity.
    """

    component_id: str
    captured_at: datetime
    signal_values: dict[str, float]

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("ComponentTelemetrySample.component_id must be a non-empty identifier")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError(
                f"ComponentTelemetrySample.captured_at must be timezone-aware (UTC-explicit); "
                f"got naive datetime {self.captured_at!r} for {self.component_id}"
            )


@dataclass(frozen=True)
class SignalSeveritySpec:
    """Declared healthy/failed anchors for one telemetry signal — the immature-path normaliser.

    This is the "declared-threshold path" of research/172 §4: it works from the FIRST observation, needs
    no history at all, and is therefore what carries a brand-new component's assessment while the PCA
    layer is still gathering its baseline.
    """

    signal_name: str
    nominal_value: float       # value at which the signal is considered perfectly healthy
    alarm_value: float         # value at which the signal is considered fully failed
    weight: float = 1.0        # (0, 1] — how much of the fused severity this signal may claim

    def __post_init__(self) -> None:
        if not math.isfinite(self.nominal_value) or not math.isfinite(self.alarm_value):
            raise ValueError(f"SignalSeveritySpec({self.signal_name}) anchors must be finite")
        if self.alarm_value <= self.nominal_value:
            raise ValueError(
                f"SignalSeveritySpec({self.signal_name}) requires alarm_value > nominal_value "
                f"(convention: higher signal value = worse); got {self.nominal_value} -> {self.alarm_value}"
            )
        if not 0.0 < self.weight <= 1.0:
            raise ValueError(f"SignalSeveritySpec({self.signal_name}).weight must lie in (0, 1]")

    def severity_for_value(self, value: float) -> float:
        """Linear ramp nominal -> alarm, clipped into `[0, 1]`."""
        return linear_severity_ramp(value, self.nominal_value, self.alarm_value)


@dataclass(frozen=True)
class HealthIndexCalibration:
    """Every tunable of the health-index computation, in one auditable frozen object.

    Defaults are the research-backed ones: `control_limit_significance` is the `alpha` of both control
    limits, `ewma_smoothing_lambda` the NIST `lambda`, `adwin_drift_confidence_delta` river's `delta`.
    """

    minimum_baseline_sample_count_for_pca: int = MINIMUM_BASELINE_SAMPLE_COUNT_FOR_PCA
    maximum_baseline_sample_count: int = 512
    retained_variance_ratio: float = 0.95
    control_limit_significance: float = 0.01
    #: Severity assigned to a statistic sitting exactly ON its control limit. The Hill map
    #: `severity(r) = r^m / (r^m + c)` with `c = (1 - s_limit) / s_limit` is monotone in
    #: `r = stat / limit`, hits `s_limit` at `r = 1` and approaches 1 as `r -> inf` — so crossing a limit
    #: is severe without instantly pinning the index to zero, and no overshoot can leave `[0, 1]`.
    severity_at_control_limit: float = 0.75
    #: Hill exponent `m`. `m = 1` is a hyperbola that already charges ~0.44 severity at a quarter of the
    #: control limit, which makes a perfectly in-control component read as DEGRADED. `m = 5` keeps the map
    #: flat well below the limit and sharpens it around it, which is the shape a control chart's alarm
    #: actually has: research/168 §1b's own decision rule is the BINARY `T^2 > T^2_alpha`, so a steep
    #: sigmoid is the faithful smooth reading of it.
    control_limit_severity_hill_exponent: float = 5.0
    #: Practical-significance floor on the SPE/Q limit, in squared standardized units per residual
    #: dimension. When the healthy baseline is (near-)perfectly collinear the discarded eigenvalues are
    #: numerically zero, so both the chi-square approximation and the empirical quantile collapse toward
    #: float noise and ANY residual would alarm. One sigma-squared per residual dimension is the honest
    #: floor: a component may sit one standard deviation off its healthy manifold without that being a
    #: fault.
    spe_q_control_limit_floor_per_residual_dimension: float = 1.0
    ewma_smoothing_lambda: float = 0.2
    ewma_control_limit_sigma_multiple: float = 3.0
    minimum_samples_for_ewma_control_limit: int = 5
    #: Practical-significance floor on the EWMA upper control limit. A severity stream is bounded below
    #: at 0 and has near-zero variance while a component is genuinely healthy, so a purely statistical
    #: `mean + 3*s_ewma` limit lands at ~0.01 severity and alarms on operationally meaningless
    #: excursions. This floor encodes "a severity below this is not actionable however statistically
    #: unusual it is" — the standard SPC practical-vs-statistical significance guard, and the same
    #: reasoning behind SRE burn-rate alerting (research/168 §4).
    minimum_ewma_control_limit_severity: float = 0.25
    minimum_samples_for_robust_signal_threshold: int = 8
    #: Upper edge of the normal operating band for an undeclared signal, in robust sigmas above its
    #: baseline median. Severity stays at 0 inside this band — the classic Shewhart 3-sigma in-control
    #: edge. Anchoring the ramp at the MEDIAN instead would charge every above-median reading a positive
    #: severity, and under weighted-max fusion those floors compound across signals until a perfectly
    #: healthy component reads DEGRADED. (Observed exactly that in the first real run of this engine.)
    robust_nominal_sigma_multiple: float = 3.0
    robust_alarm_sigma_multiple: float = 6.0
    adwin_drift_confidence_delta: float = 0.002
    adwin_drift_latch_sample_count: int = 10
    #: Severity charged for a signal whose value could not be read (NaN/inf/non-numeric). Unreadable
    #: telemetry is a genuine loss of observability, not a healthy reading — but it is not proof of
    #: failure either, so it is charged at the DEGRADED tier rather than the FAILED tier.
    unreadable_signal_severity: float = 0.5
    pca_refit_interval_sample_count: int = 10
    baseline_admission_severity_ceiling: float = 0.5
    healthy_health_index_floor: float = 0.80
    degraded_health_index_floor: float = 0.50
    failing_health_index_floor: float = 0.20
    #: A signal whose ramp was DERIVED from the baseline is a statistical inference like `T^2`/`Q`, so it
    #: gets the same capped short-window authority. A signal with a DECLARED `SignalSeveritySpec` is a
    #: direct observation ("this token expired four hours ago") and keeps full authority via its own
    #: `SignalSeveritySpec.weight`. In both cases `ewma_smoothed_severity` is the long window that can
    #: reach FAILED once the reading is sustained.
    undeclared_signal_weight: float = 0.35
    #: An unreadable value is a direct observation of lost observability, not an inference — full weight.
    unreadable_signal_weight: float = 1.0
    #: T-squared and SPE/Q are STATISTICAL inferences with a designed false-alarm rate of `alpha`, not
    #: direct observations of a known-bad condition. Fusing them raw at full weight would hand that
    #: false-alarm rate straight to the vitality gate — an in-control component would read FAILED roughly
    #: `alpha` of the time. So they enter as a SHORT window capped inside the DEGRADED band, while their
    #: EWMA-smoothed level (below) is the LONG window that carries full authority. Both must agree before
    #: the index collapses, which is exactly the multiwindow structure research/168 §4 (Google SRE
    #: burn-rate alerting) prescribes and what §RECOMMENDATION means by "feed the raw statistics through
    #: an EWMA for the primary smoothing/alarm layer". Declared-threshold breaches are NOT smoothed:
    #: an expired token is an observation, not an inference, and must act instantly.
    hotelling_t_squared_weight: float = 0.35
    spe_q_weight: float = 0.35
    multivariate_anomaly_ewma_weight: float = 1.0
    ewma_level_weight: float = 1.0
    ewma_control_limit_weight: float = 1.0
    #: ADWIN is the cross-check, not the primary path — discounted so it can raise an alarm on its own
    #: but cannot by itself drive the index all the way to FAILED.
    adwin_drift_weight: float = 0.8

    def __post_init__(self) -> None:
        if self.minimum_baseline_sample_count_for_pca < 3:
            raise ValueError("minimum_baseline_sample_count_for_pca must be at least 3 for a covariance")
        if self.maximum_baseline_sample_count < self.minimum_baseline_sample_count_for_pca:
            raise ValueError("maximum_baseline_sample_count must be >= minimum_baseline_sample_count_for_pca")
        if not 0.0 < self.retained_variance_ratio <= 1.0:
            raise ValueError("retained_variance_ratio must lie in (0, 1]")
        if not 0.0 < self.control_limit_significance < 0.5:
            raise ValueError("control_limit_significance (alpha) must lie in (0, 0.5)")
        if not 0.0 < self.severity_at_control_limit < 1.0:
            raise ValueError("severity_at_control_limit must lie in (0, 1)")
        if self.control_limit_severity_hill_exponent <= 0.0:
            raise ValueError("control_limit_severity_hill_exponent must be positive")
        if not 0.0 <= self.minimum_ewma_control_limit_severity <= 1.0:
            raise ValueError("minimum_ewma_control_limit_severity must lie in [0, 1]")
        if self.spe_q_control_limit_floor_per_residual_dimension < 0.0:
            raise ValueError("spe_q_control_limit_floor_per_residual_dimension must be non-negative")
        if not 0.0 < self.ewma_smoothing_lambda <= 1.0:
            raise ValueError("ewma_smoothing_lambda must lie in (0, 1] (NIST EWMA parameter)")
        if self.ewma_control_limit_sigma_multiple <= 0.0:
            raise ValueError("ewma_control_limit_sigma_multiple must be positive")
        if self.robust_nominal_sigma_multiple < 0.0:
            raise ValueError("robust_nominal_sigma_multiple must be non-negative")
        if self.robust_alarm_sigma_multiple <= self.robust_nominal_sigma_multiple:
            raise ValueError(
                "robust_alarm_sigma_multiple must exceed robust_nominal_sigma_multiple "
                "(the severity ramp needs a positive span)"
            )
        if not 0.0 < self.adwin_drift_confidence_delta < 1.0:
            raise ValueError("adwin_drift_confidence_delta must lie in (0, 1)")
        if self.adwin_drift_latch_sample_count < 1:
            raise ValueError("adwin_drift_latch_sample_count must be at least 1")
        if not 0.0 <= self.unreadable_signal_severity <= 1.0:
            raise ValueError("unreadable_signal_severity must lie in [0, 1]")
        if self.pca_refit_interval_sample_count < 1:
            raise ValueError("pca_refit_interval_sample_count must be at least 1")
        if not 0.0 <= self.baseline_admission_severity_ceiling <= 1.0:
            raise ValueError("baseline_admission_severity_ceiling must lie in [0, 1]")
        if not 0.0 <= self.failing_health_index_floor <= self.degraded_health_index_floor <= \
                self.healthy_health_index_floor <= 1.0:
            raise ValueError(
                "health-index floors must satisfy 0 <= failing <= degraded <= healthy <= 1"
            )
        for weight_name, weight in (
            ("undeclared_signal_weight", self.undeclared_signal_weight),
            ("unreadable_signal_weight", self.unreadable_signal_weight),
            ("hotelling_t_squared_weight", self.hotelling_t_squared_weight),
            ("spe_q_weight", self.spe_q_weight),
            ("multivariate_anomaly_ewma_weight", self.multivariate_anomaly_ewma_weight),
            ("ewma_level_weight", self.ewma_level_weight),
            ("ewma_control_limit_weight", self.ewma_control_limit_weight),
            ("adwin_drift_weight", self.adwin_drift_weight),
        ):
            if not 0.0 < weight <= 1.0:
                raise ValueError(f"{weight_name} must lie in (0, 1]; got {weight}")


@dataclass(frozen=True)
class SeverityContribution:
    """One named piece of evidence that the component is unhealthy, on the common `[0, 1]` scale.

    Keeping the raw severity and its weight separate (rather than pre-multiplying) is what makes the
    weighted-max fusion auditable: the dashboard can show both "how bad is this signal" and "how much
    is this signal allowed to matter".
    """

    signal_name: str
    raw_severity: float
    weight: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.raw_severity) or not 0.0 <= self.raw_severity <= 1.0:
            raise ValueError(f"SeverityContribution({self.signal_name}).raw_severity must lie in [0, 1]")
        if not math.isfinite(self.weight) or not 0.0 < self.weight <= 1.0:
            raise ValueError(f"SeverityContribution({self.signal_name}).weight must lie in (0, 1]")

    @property
    def weighted_severity(self) -> float:
        return _clamp_to_unit_interval(self.raw_severity * self.weight)


@dataclass(frozen=True)
class MultivariateControlStatistics:
    """The T-squared / SPE-Q pair for one observation, with the control limits they are judged against."""

    t_squared: float
    t_squared_control_limit: float
    spe_q: float
    #: `None` when the retained subspace spans the whole baseline rank, so there is no residual space
    #: whose eigenvalue spectrum could set a limit (research/168 §1b: `w_i` sums over DISCARDED
    #: eigenvalues, and an empty sum cannot define a threshold).
    spe_q_control_limit: float | None
    retained_component_count: int
    baseline_sample_count: int
    signal_names: tuple[str, ...]

    @property
    def is_t_squared_alarm(self) -> bool:
        return self.t_squared > self.t_squared_control_limit

    @property
    def is_spe_q_alarm(self) -> bool:
        return self.spe_q_control_limit is not None and self.spe_q > self.spe_q_control_limit


@dataclass(frozen=True)
class ComponentHealthAssessment:
    """The health verdict for one component at one instant — the contract other modules bind to."""

    component_id: str
    health_index: float                    # [0, 1], 1.0 = perfectly healthy
    t_squared: float | None                # None while the PCA layer is immature or abstaining
    spe_q: float | None
    ewma_level: float
    degradation_state: DegradationState
    #: have N: the number of healthy-baseline samples THIS assessment was computed against (the current
    #: sample is admitted, if it qualifies, only afterwards — so an observation is never scored against a
    #: baseline containing itself). `sample_count >= required_sample_count` is exactly the condition
    #: under which the PCA layer arms, degenerate baselines aside.
    sample_count: int
    required_sample_count: int             # need M: the Rule-Q PCA arming threshold
    is_pca_armed: bool
    contributing_signals: tuple[tuple[str, float], ...]   # (signal_name, weighted severity), worst first

    def __post_init__(self) -> None:
        if not math.isfinite(self.health_index) or not 0.0 <= self.health_index <= 1.0:
            raise ValueError(
                f"health_index for {self.component_id} escaped [0, 1]: {self.health_index!r}"
            )
        if not math.isfinite(self.ewma_level):
            raise ValueError(f"ewma_level for {self.component_id} is not finite: {self.ewma_level!r}")
        if self.is_pca_armed != (self.t_squared is not None):
            raise ValueError(
                f"{self.component_id}: is_pca_armed must agree with the presence of t_squared "
                f"(armed={self.is_pca_armed}, t_squared={self.t_squared!r})"
            )

    @property
    def maturity_description(self) -> str:
        """`have N / need M`, the exact string research/172 §4 requires on the dashboard."""
        return f"have {self.sample_count} / need {self.required_sample_count}"

    @property
    def worst_contributing_signal(self) -> tuple[str, float] | None:
        return self.contributing_signals[0] if self.contributing_signals else None


# ---------------------------------------------------------------------------------------------------
# Free functions — each one independently testable, which is the point of pulling them out.
# ---------------------------------------------------------------------------------------------------


def _clamp_to_unit_interval(value: float) -> float:
    """Clamp into `[0, 1]`. Non-finite input is a caller bug, so it raises rather than being papered
    over with a plausible-looking number (Rule O.3)."""
    if not math.isfinite(value):
        raise ValueError(f"cannot clamp non-finite value {value!r} into [0, 1]")
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def linear_severity_ramp(value: float, nominal_value: float, alarm_value: float) -> float:
    """`clip((value - nominal) / (alarm - nominal), 0, 1)` — overflow-safe (research/168 §1d).

    The subtraction and division are each guarded: a legitimately huge finite reading over a tiny ramp
    span overflows to `inf` in plain float arithmetic, and `inf` would then blow up the clamp rather than
    saturating the way the ramp's own semantics say it should. Ordered comparisons decide the saturated
    ends first, so no arithmetic that could overflow is ever reached in those cases (Rule O.4).
    """
    if not math.isfinite(value) or not math.isfinite(nominal_value) or not math.isfinite(alarm_value):
        raise ValueError("linear_severity_ramp requires finite value and anchors")
    if alarm_value <= nominal_value:
        raise ValueError("linear_severity_ramp requires alarm_value > nominal_value (higher = worse)")
    if value <= nominal_value:
        return 0.0
    if value >= alarm_value:
        return 1.0
    severity = (value - nominal_value) / (alarm_value - nominal_value)
    return _clamp_to_unit_interval(severity) if math.isfinite(severity) else 1.0


def update_ewma_level(previous_level: float, observation: float, smoothing_lambda: float) -> float:
    """NIST EWMA recursion `EWMA_t = lambda*Y_t + (1-lambda)*EWMA_{t-1}` (research/168 §1c)."""
    if not 0.0 < smoothing_lambda <= 1.0:
        raise ValueError("smoothing_lambda must lie in (0, 1]")
    if not math.isfinite(previous_level) or not math.isfinite(observation):
        raise ValueError("EWMA inputs must be finite")
    return smoothing_lambda * observation + (1.0 - smoothing_lambda) * previous_level


def ewma_standard_deviation(
    process_standard_deviation: float, smoothing_lambda: float, update_count: int
) -> float:
    """`s_ewma = s * sqrt(lambda/(2-lambda) * (1 - (1-lambda)^(2t)))` (research/168 §1c, transient form).

    The `(1 - (1-lambda)^(2t))` factor is the exact transient correction; it converges to the
    steady-state `s*sqrt(lambda/(2-lambda))` NIST quotes, so early observations are not judged against
    an over-wide limit.
    """
    if process_standard_deviation < 0.0 or not math.isfinite(process_standard_deviation):
        raise ValueError("process_standard_deviation must be finite and non-negative")
    if not 0.0 < smoothing_lambda <= 1.0:
        raise ValueError("smoothing_lambda must lie in (0, 1]")
    if update_count < 1:
        return 0.0
    steady_state_factor = smoothing_lambda / (2.0 - smoothing_lambda)
    transient_factor = 1.0 - (1.0 - smoothing_lambda) ** (2 * update_count)
    return process_standard_deviation * math.sqrt(max(steady_state_factor * transient_factor, 0.0))


def map_control_limit_ratio_to_severity(
    statistic: float,
    control_limit: float,
    severity_at_control_limit: float,
    hill_exponent: float = 3.0,
) -> float:
    """Map a control-chart statistic onto `[0, 1)` severity, saturating rather than clipping.

    `severity(r) = r^m / (r^m + c)` with `r = statistic / control_limit` and `c = (1-s_L)/s_L`, so that
    `severity(0) = 0`, `severity(1) = s_L` (the declared severity of sitting exactly ON the limit) and
    `severity(r) -> 1` as the statistic runs away. Monotone in `r`, bounded in `[0, 1)`, and free of the
    discontinuity a hard clip at the limit would introduce (research/168 §1d asks for each statistic to
    be normalised against its own control limit; this is that normalisation, made smooth).

    The Hill exponent `m` controls how sharply the map turns on around the limit. `m = 1` is a plain
    hyperbola, which charges ~0.44 severity at a quarter of the control limit — far too eager for a
    component that is comfortably in control; `m = 3` keeps the map near zero well below the limit.
    """
    if not math.isfinite(control_limit) or control_limit <= 0.0:
        raise ValueError(f"control_limit must be finite and positive; got {control_limit!r}")
    if not 0.0 < severity_at_control_limit < 1.0:
        raise ValueError("severity_at_control_limit must lie in (0, 1)")
    if not math.isfinite(hill_exponent) or hill_exponent <= 0.0:
        raise ValueError("hill_exponent must be finite and positive")
    if not math.isfinite(statistic) or statistic <= 0.0:
        return 0.0
    ratio = statistic / control_limit
    if not math.isfinite(ratio):
        return 1.0
    try:
        steepened_ratio = ratio**hill_exponent
    except OverflowError:
        return 1.0
    if not math.isfinite(steepened_ratio):
        return 1.0
    half_saturation = (1.0 - severity_at_control_limit) / severity_at_control_limit
    return _clamp_to_unit_interval(steepened_ratio / (steepened_ratio + half_saturation))


def fuse_severity_contributions_by_weighted_max(
    contributions: Sequence[SeverityContribution],
) -> float:
    """Weighted-MAX fusion (research/172 §3; research/168 §1d) — deliberately never a weighted mean.

    One hard failure must dominate the fused severity and must not be diluted by any number of healthy
    signals. With no contributions at all the fused severity is `0.0` (no evidence of degradation), which
    yields the identity health index `1.0` — see the module docstring on safe identity behaviour.
    """
    if not contributions:
        return 0.0
    return max(contribution.weighted_severity for contribution in contributions)


def classify_degradation_state(
    health_index: float, calibration: HealthIndexCalibration
) -> DegradationState:
    """Band the scalar index into the discrete state the MDP and the vitality gate reason over."""
    if health_index >= calibration.healthy_health_index_floor:
        return DegradationState.HEALTHY
    if health_index >= calibration.degraded_health_index_floor:
        return DegradationState.DEGRADED
    if health_index >= calibration.failing_health_index_floor:
        return DegradationState.FAILING
    return DegradationState.FAILED


def robust_severity_ramp_from_baseline(
    baseline_values: Sequence[float],
    robust_nominal_sigma_multiple: float,
    robust_alarm_sigma_multiple: float,
) -> tuple[float, float] | None:
    """Derive `(nominal, alarm)` for an undeclared signal from its own healthy baseline.

    `nominal = median + k_nominal * scale` (the upper edge of the normal operating band, so ordinary
    healthy variation scores exactly zero severity) and `alarm = median + k_alarm * scale`.

    `scale` is `1.4826 *` the median of the deviations ABOVE the median (the upper semi-MAD), falling
    back to the ordinary symmetric MAD and then to the sample standard deviation as each collapses —
    which happens once more than half the baseline values are identical. Returns `None` when no scale
    estimator is usable: an honest abstention, never an invented threshold (Rule O.3/O.4).
    """
    finite_values = [value for value in baseline_values if math.isfinite(value)]
    if len(finite_values) < 2:
        return None
    values = np.asarray(finite_values, dtype=np.float64)
    median = float(np.median(values))
    # UPPER-semi-MAD: the median of the deviations ABOVE the median. For a symmetric distribution this
    # is identically the ordinary MAD (the upper deviations are exactly half of the |deviation|
    # distribution, with the same median); for a right-skewed one — which most telemetry is, being
    # non-negative counts and latencies — it is larger, and it is the upper tail that the
    # "higher = worse" convention makes us care about. A symmetric MAD systematically under-scales such
    # a signal and manufactures FAILING readings out of ordinary healthy skew (found by test).
    upper_deviations = values[values > median] - median
    scale = 0.0
    if upper_deviations.size >= 2:
        scale = _MEDIAN_ABSOLUTE_DEVIATION_TO_SIGMA * float(np.median(upper_deviations))
    if scale <= _ZERO_VARIANCE_TOLERANCE:
        scale = _MEDIAN_ABSOLUTE_DEVIATION_TO_SIGMA * float(np.median(np.abs(values - median)))
    if scale <= _ZERO_VARIANCE_TOLERANCE:
        scale = float(np.std(values, ddof=1))
    if not math.isfinite(scale) or scale <= _ZERO_VARIANCE_TOLERANCE:
        return None
    nominal_value = median + robust_nominal_sigma_multiple * scale
    alarm_value = median + robust_alarm_sigma_multiple * scale
    if (
        not math.isfinite(nominal_value)
        or not math.isfinite(alarm_value)
        or alarm_value <= nominal_value
    ):
        return None
    return nominal_value, alarm_value


@dataclass(frozen=True, eq=False)
class HealthyBaselinePrincipalComponentModel:
    """A PCA model fitted on a component's healthy baseline, plus both MSPC control limits.

    Frozen because it is swapped wholesale on refit rather than mutated; `eq=False` because it carries
    numpy arrays, for which the generated `__eq__` would be ambiguous.
    """

    signal_names: tuple[str, ...]
    baseline_mean: NDArray[np.float64]
    baseline_standard_deviation: NDArray[np.float64]
    principal_axes: NDArray[np.float64]        # (r, p) rows, in standardized-signal space
    eigenvalues: NDArray[np.float64]           # (r,) = sklearn's explained_variance_
    projection_mean: NDArray[np.float64]       # (p,) the PCA's own centring of the standardized matrix
    retained_component_count: int
    baseline_sample_count: int
    t_squared_control_limit: float
    spe_q_control_limit: float | None
    discarded_signal_names: tuple[str, ...] = ()

    @classmethod
    def fit_on_healthy_baseline(
        cls,
        signal_names: Sequence[str],
        baseline_matrix: NDArray[np.float64],
        retained_variance_ratio: float,
        control_limit_significance: float,
        spe_q_control_limit_floor_per_residual_dimension: float = 1.0,
    ) -> HealthyBaselinePrincipalComponentModel | None:
        """Fit on an `(n, p)` healthy-baseline matrix, or return `None` if the baseline is degenerate.

        Every abstention path returns `None` with a DEBUG log naming the reason; none of them raises and
        none of them fabricates a model, so a caller sees "PCA is not armed" rather than a silent lie.
        """
        if baseline_matrix.ndim != 2:
            LOGGER.debug("PCA abstains: baseline matrix must be 2-D, got shape %r", baseline_matrix.shape)
            return None
        sample_count, signal_count = baseline_matrix.shape
        if signal_count != len(signal_names):
            raise ValueError("signal_names length must match the baseline matrix column count")
        if sample_count < 3 or signal_count < 1:
            LOGGER.debug("PCA abstains: baseline too small (%d x %d)", sample_count, signal_count)
            return None
        if not bool(np.all(np.isfinite(baseline_matrix))):
            LOGGER.debug("PCA abstains: healthy baseline contains non-finite values")
            return None
        if not _is_within_safe_magnitude(baseline_matrix):
            LOGGER.debug(
                "PCA abstains: healthy baseline holds magnitudes beyond %.0e, where sums of squares "
                "overflow float64", _MAXIMUM_SAFE_MAGNITUDE_FOR_SUM_OF_SQUARES,
            )
            return None

        column_mean = baseline_matrix.mean(axis=0)
        column_standard_deviation = baseline_matrix.std(axis=0, ddof=1)
        usable_columns = column_standard_deviation > _ZERO_VARIANCE_TOLERANCE
        discarded = tuple(
            name for name, is_usable in zip(signal_names, usable_columns, strict=True) if not is_usable
        )
        if not bool(np.any(usable_columns)):
            LOGGER.debug(
                "PCA abstains: every baseline column is constant (%d signals, %d samples)",
                signal_count, sample_count,
            )
            return None

        kept_names = tuple(
            name for name, is_usable in zip(signal_names, usable_columns, strict=True) if is_usable
        )
        kept_mean = column_mean[usable_columns]
        kept_standard_deviation = column_standard_deviation[usable_columns]
        standardized = (baseline_matrix[:, usable_columns] - kept_mean) / kept_standard_deviation
        if not bool(np.all(np.isfinite(standardized))) or not _is_within_safe_magnitude(standardized):
            LOGGER.debug("PCA abstains: z-scoring the healthy baseline left unusable magnitudes")
            return None

        maximum_component_count = int(min(sample_count - 1, standardized.shape[1]))
        if maximum_component_count < 1:
            LOGGER.debug("PCA abstains: no admissible component count")
            return None
        principal_component_analysis = PCA(
            n_components=maximum_component_count, svd_solver="full"
        ).fit(standardized)
        eigenvalues = np.asarray(principal_component_analysis.explained_variance_, dtype=np.float64)
        variance_ratios = np.asarray(
            principal_component_analysis.explained_variance_ratio_, dtype=np.float64
        )
        if not bool(np.all(np.isfinite(eigenvalues))) or not bool(np.all(np.isfinite(variance_ratios))):
            LOGGER.debug("PCA abstains: eigen-decomposition produced non-finite values")
            return None

        retained_count = _select_retained_component_count(
            eigenvalues, variance_ratios, retained_variance_ratio
        )
        if retained_count is None or sample_count - retained_count <= 0:
            LOGGER.debug(
                "PCA abstains: cannot retain a usable subspace (n=%d, candidates=%d)",
                sample_count, maximum_component_count,
            )
            return None

        t_squared_limit = _hotelling_t_squared_control_limit(
            retained_count, sample_count, control_limit_significance
        )
        if t_squared_limit is None:
            LOGGER.debug("PCA abstains: T-squared control limit is not computable")
            return None
        principal_axes = np.asarray(principal_component_analysis.components_, dtype=np.float64)
        projection_mean = np.asarray(principal_component_analysis.mean_, dtype=np.float64)
        spe_q_limit = _spe_q_control_limit(
            discarded_eigenvalues=eigenvalues[retained_count:],
            residual_dimension_count=standardized.shape[1] - retained_count,
            baseline_spe_q_values=_baseline_spe_q_values(
                standardized, principal_axes, projection_mean, retained_count
            ),
            control_limit_significance=control_limit_significance,
            floor_per_residual_dimension=spe_q_control_limit_floor_per_residual_dimension,
        )
        return cls(
            signal_names=kept_names,
            baseline_mean=kept_mean,
            baseline_standard_deviation=kept_standard_deviation,
            principal_axes=principal_axes,
            eigenvalues=eigenvalues,
            projection_mean=projection_mean,
            retained_component_count=retained_count,
            baseline_sample_count=sample_count,
            t_squared_control_limit=t_squared_limit,
            spe_q_control_limit=spe_q_limit,
            discarded_signal_names=discarded,
        )

    def evaluate_observation(
        self, signal_values: Mapping[str, float]
    ) -> MultivariateControlStatistics | None:
        """Score one observation, or return `None` when it cannot be scored against this model."""
        try:
            raw_vector = np.asarray(
                [float(signal_values[name]) for name in self.signal_names], dtype=np.float64
            )
        except KeyError as missing_signal:
            LOGGER.debug("PCA abstains for this observation: missing signal %s", missing_signal)
            return None
        except (TypeError, ValueError):
            LOGGER.debug("PCA abstains for this observation: non-numeric signal value")
            return None
        if not bool(np.all(np.isfinite(raw_vector))):
            LOGGER.debug("PCA abstains for this observation: non-finite signal value")
            return None

        standardized = (raw_vector - self.baseline_mean) / self.baseline_standard_deviation
        if not bool(np.all(np.isfinite(standardized))) or not _is_within_safe_magnitude(standardized):
            LOGGER.debug("PCA abstains for this observation: z-score magnitude would overflow")
            return None
        centered = standardized - self.projection_mean
        scores = centered @ self.principal_axes.T
        retained_scores = scores[: self.retained_component_count]
        retained_eigenvalues = self.eigenvalues[: self.retained_component_count]
        safe_eigenvalues = np.where(
            retained_eigenvalues > _ZERO_VARIANCE_TOLERANCE, retained_eigenvalues, np.nan
        )
        t_squared = float(np.nansum(np.square(retained_scores) / safe_eigenvalues))

        reconstruction = (
            retained_scores @ self.principal_axes[: self.retained_component_count] + self.projection_mean
        )
        residual = standardized - reconstruction
        spe_q = float(np.dot(residual, residual))
        if not math.isfinite(t_squared) or not math.isfinite(spe_q):
            LOGGER.debug("PCA abstains for this observation: statistics were not finite")
            return None
        return MultivariateControlStatistics(
            t_squared=max(t_squared, 0.0),
            t_squared_control_limit=self.t_squared_control_limit,
            spe_q=max(spe_q, 0.0),
            spe_q_control_limit=self.spe_q_control_limit,
            retained_component_count=self.retained_component_count,
            baseline_sample_count=self.baseline_sample_count,
            signal_names=self.signal_names,
        )


def _is_within_safe_magnitude(values: NDArray[np.float64]) -> bool:
    """True when every entry can be squared and summed without overflowing float64."""
    if values.size == 0:
        return True
    return bool(np.max(np.abs(values)) <= _MAXIMUM_SAFE_MAGNITUDE_FOR_SUM_OF_SQUARES)


def _select_retained_component_count(
    eigenvalues: NDArray[np.float64],
    variance_ratios: NDArray[np.float64],
    retained_variance_ratio: float,
) -> int | None:
    """Smallest `a` whose cumulative explained variance reaches the target, trimmed to non-null axes."""
    cumulative = np.cumsum(variance_ratios)
    reached = np.nonzero(cumulative >= retained_variance_ratio - _CUMULATIVE_VARIANCE_TOLERANCE)[0]
    retained_count = int(reached[0]) + 1 if reached.size else int(eigenvalues.size)
    # Never retain an axis whose eigenvalue is numerically zero: T-squared divides by it.
    while retained_count > 0 and eigenvalues[retained_count - 1] <= _ZERO_VARIANCE_TOLERANCE:
        retained_count -= 1
    return retained_count if retained_count >= 1 else None


def _hotelling_t_squared_control_limit(
    retained_component_count: int, baseline_sample_count: int, control_limit_significance: float
) -> float | None:
    """`T^2_alpha = a(n-1)(n+1) / (n(n-a)) * F_alpha(a, n-a)` (research/168 §1b)."""
    a = retained_component_count
    n = baseline_sample_count
    if a < 1 or n - a < 1:
        return None
    scale = (a * (n - 1) * (n + 1)) / (n * (n - a))
    quantile = float(fisher_f_distribution.ppf(1.0 - control_limit_significance, a, n - a))
    limit = scale * quantile
    return limit if math.isfinite(limit) and limit > 0.0 else None


def spe_q_control_limit_chi_square_approximation(
    discarded_eigenvalues: NDArray[np.float64], control_limit_significance: float
) -> float | None:
    """`delta^2 = g * chi2_alpha(h)`, `g = w2/w1`, `h = w1^2/w2`, `w_i = sum_{j>a} lambda_j^i`.

    research/168 §1b — the chi-square approximation, which that pass verified directly; the refined
    Jackson & Mudholkar (1979) normal-approximation form could not be transcribed from any source
    (research/168 §7) and is deliberately NOT guessed at here.

    Returns `None` when the discarded eigenvalue spectrum is empty or numerically zero, i.e. when the
    healthy baseline is (near-)perfectly collinear so there is no residual VARIANCE to build a
    distributional threshold from. `_spe_q_control_limit` handles that case separately.
    """
    if discarded_eigenvalues.size == 0:
        return None
    positive = discarded_eigenvalues[discarded_eigenvalues > _ZERO_VARIANCE_TOLERANCE]
    if positive.size == 0:
        return None
    omega_1 = float(np.sum(positive))
    omega_2 = float(np.sum(np.square(positive)))
    if omega_1 <= _ZERO_VARIANCE_TOLERANCE or omega_2 <= _ZERO_VARIANCE_TOLERANCE:
        return None
    g_scale = omega_2 / omega_1
    h_degrees_of_freedom = (omega_1 * omega_1) / omega_2
    if not math.isfinite(g_scale) or not math.isfinite(h_degrees_of_freedom) or h_degrees_of_freedom <= 0:
        return None
    limit = g_scale * float(
        chi_square_distribution.ppf(1.0 - control_limit_significance, h_degrees_of_freedom)
    )
    return limit if math.isfinite(limit) and limit > 0.0 else None


def _baseline_spe_q_values(
    standardized_baseline: NDArray[np.float64],
    principal_axes: NDArray[np.float64],
    projection_mean: NDArray[np.float64],
    retained_component_count: int,
) -> NDArray[np.float64]:
    """`Q` for every healthy-baseline row — the empirical residual distribution the model was fitted on."""
    centered = standardized_baseline - projection_mean
    scores = centered @ principal_axes.T
    reconstruction = (
        scores[:, :retained_component_count] @ principal_axes[:retained_component_count]
        + projection_mean
    )
    residuals = standardized_baseline - reconstruction
    return np.asarray(np.sum(np.square(residuals), axis=1), dtype=np.float64)


def _spe_q_control_limit(
    discarded_eigenvalues: NDArray[np.float64],
    residual_dimension_count: int,
    baseline_spe_q_values: NDArray[np.float64],
    control_limit_significance: float,
    floor_per_residual_dimension: float,
) -> float | None:
    """The SPE/Q alarm threshold: the strictest-but-defensible of three independent constructions.

    1. the verified chi-square approximation of research/168 §1b (the primary, distributional route);
    2. the `(1-alpha)` EMPIRICAL quantile of the baseline's own `Q` values — no distributional
       assumption at all, and the only route that survives a perfectly collinear baseline where the
       discarded eigenvalues are numerically zero;
    3. a practical-significance FLOOR of one squared standardized unit per residual dimension, so that
       float-noise-sized residuals can never raise an alarm.

    The maximum of the three is used: each is a valid lower bound on "how far off the healthy manifold is
    still normal", and taking the max is the conservative choice (it can only suppress false alarms,
    never a real one relative to the strictest route). `None` means there is no residual subspace at all
    (`a` spans the full standardized space), in which case `Q` is identically zero and cannot alarm.
    """
    if residual_dimension_count <= 0:
        return None
    candidate_limits = [float(residual_dimension_count) * floor_per_residual_dimension]
    chi_square_limit = spe_q_control_limit_chi_square_approximation(
        discarded_eigenvalues, control_limit_significance
    )
    if chi_square_limit is not None:
        candidate_limits.append(chi_square_limit)
    if baseline_spe_q_values.size > 0 and bool(np.all(np.isfinite(baseline_spe_q_values))):
        empirical_limit = float(
            np.quantile(baseline_spe_q_values, 1.0 - control_limit_significance)
        )
        if math.isfinite(empirical_limit):
            candidate_limits.append(empirical_limit)
    limit = max(candidate_limits)
    return limit if math.isfinite(limit) and limit > 0.0 else None


@dataclass
class _RunningMeanAndVariance:
    """Welford's online mean/variance — numerically stable, and the only mutable state class here."""

    count: int = 0
    mean: float = 0.0
    sum_of_squared_deviations: float = 0.0

    def update(self, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("running variance accumulator requires finite values")
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.sum_of_squared_deviations += delta * (value - self.mean)

    @property
    def sample_standard_deviation(self) -> float:
        if self.count < 2:
            return 0.0
        variance = self.sum_of_squared_deviations / (self.count - 1)
        return math.sqrt(variance) if variance > 0.0 else 0.0


@dataclass(frozen=True)
class HealthIndexDiagnostics:
    """Everything the engine chose not to use, and why — Rule O.3's "count and surface" made concrete.

    None of these are silent: each is incremented at the point of the decision, logged (WARNING the first
    time, DEBUG thereafter) and exposed here for the dashboard and the orchestrator's own health view.
    """

    unreadable_signal_observation_count: int = 0
    empty_sample_count: int = 0
    out_of_order_sample_count: int = 0
    baseline_rejection_count: int = 0
    pca_fit_abstention_count: int = 0
    pca_evaluation_abstention_count: int = 0
    adwin_drift_detection_count: int = 0
    abstaining_signal_names: tuple[str, ...] = ()
    constant_baseline_signal_names: tuple[str, ...] = ()


class ComponentHealthIndexEstimator:
    """Carried per-component state that turns a telemetry stream into `ComponentHealthAssessment`s.

    One instance per component (the state — healthy baseline, EWMA level, ADWIN window, fitted PCA
    model — is what makes this an estimator rather than a pure function). Feed it samples with
    :meth:`ingest`; each call returns the assessment for that instant.
    """

    def __init__(
        self,
        component_id: str,
        calibration: HealthIndexCalibration | None = None,
        signal_severity_specs: Iterable[SignalSeveritySpec] = (),
    ) -> None:
        if not component_id:
            raise ValueError("ComponentHealthIndexEstimator requires a non-empty component_id")
        self.component_id = component_id
        self.calibration = calibration if calibration is not None else HealthIndexCalibration()
        self._signal_severity_specs: dict[str, SignalSeveritySpec] = {
            spec.signal_name: spec for spec in signal_severity_specs
        }
        self._healthy_baseline_samples: deque[dict[str, float]] = deque(
            maxlen=self.calibration.maximum_baseline_sample_count
        )
        self._baseline_severity_statistics = _RunningMeanAndVariance()
        self._ewma_level: float = 0.0
        self._ewma_update_count: int = 0
        self._multivariate_anomaly_ewma_level: float = 0.0
        self._adwin_detector: ADWIN = ADWIN(delta=self.calibration.adwin_drift_confidence_delta)
        self._samples_since_adwin_drift: int | None = None
        self._ewma_level_before_adwin_drift: float = 0.0
        self._principal_component_model: HealthyBaselinePrincipalComponentModel | None = None
        self._total_baseline_admission_count: int = 0
        #: -1 = never attempted. Monotone admission counts (not the bounded deque length) gate refits, so
        #: a component whose baseline deque is already full still re-fits as fresh samples roll through.
        self._admission_count_at_last_fit_attempt: int = -1
        self._latest_captured_at: datetime | None = None
        self._unreadable_signal_observation_count = 0
        self._empty_sample_count = 0
        self._out_of_order_sample_count = 0
        self._baseline_rejection_count = 0
        self._pca_fit_abstention_count = 0
        self._pca_evaluation_abstention_count = 0
        self._adwin_drift_detection_count = 0
        self._abstaining_signal_names: set[str] = set()
        self._constant_baseline_signal_names: tuple[str, ...] = ()

    # -- introspection -----------------------------------------------------------------------------

    @property
    def healthy_baseline_sample_count(self) -> int:
        """`have N` — how many healthy-baseline samples this component has accumulated."""
        return len(self._healthy_baseline_samples)

    @property
    def required_baseline_sample_count(self) -> int:
        """`need M` — the Rule-Q PCA arming threshold."""
        return self.calibration.minimum_baseline_sample_count_for_pca

    @property
    def is_pca_armed(self) -> bool:
        """True only when the maturity threshold is met AND a usable model actually fitted."""
        return (
            self.healthy_baseline_sample_count >= self.required_baseline_sample_count
            and self._principal_component_model is not None
        )

    @property
    def ewma_level(self) -> float:
        return self._ewma_level

    def diagnostics(self) -> HealthIndexDiagnostics:
        return HealthIndexDiagnostics(
            unreadable_signal_observation_count=self._unreadable_signal_observation_count,
            empty_sample_count=self._empty_sample_count,
            out_of_order_sample_count=self._out_of_order_sample_count,
            baseline_rejection_count=self._baseline_rejection_count,
            pca_fit_abstention_count=self._pca_fit_abstention_count,
            pca_evaluation_abstention_count=self._pca_evaluation_abstention_count,
            adwin_drift_detection_count=self._adwin_drift_detection_count,
            abstaining_signal_names=tuple(sorted(self._abstaining_signal_names)),
            constant_baseline_signal_names=self._constant_baseline_signal_names,
        )

    # -- the assessment cycle ----------------------------------------------------------------------

    def current_assessment(self) -> ComponentHealthAssessment:
        """The abstaining assessment for a component that has produced no usable observation yet.

        Health `1.0` is the identity element of every tighten-only consumer (module docstring), so "no
        evidence" reads as "no tightening" — never as a fabricated pessimistic number.
        """
        return ComponentHealthAssessment(
            component_id=self.component_id,
            health_index=1.0,
            t_squared=None,
            spe_q=None,
            ewma_level=self._ewma_level,
            degradation_state=classify_degradation_state(1.0, self.calibration),
            sample_count=self.healthy_baseline_sample_count,
            required_sample_count=self.required_baseline_sample_count,
            is_pca_armed=False,
            contributing_signals=(),
        )

    def ingest(self, sample: ComponentTelemetrySample) -> ComponentHealthAssessment:
        """Absorb one telemetry sample and return the resulting health assessment."""
        if sample.component_id != self.component_id:
            raise ValueError(
                f"sample for {sample.component_id!r} routed to the estimator of {self.component_id!r}"
            )
        self._record_sample_ordering(sample.captured_at)

        readable_values, unreadable_names = self._partition_readable_signal_values(sample.signal_values)
        if not sample.signal_values:
            self._empty_sample_count += 1
            self._log_once(
                self._empty_sample_count,
                "component %s emitted a telemetry sample with no signals at all",
                self.component_id,
            )

        raw_signal_contributions = self._raw_signal_contributions(readable_values, unreadable_names)
        instantaneous_severity = fuse_severity_contributions_by_weighted_max(raw_signal_contributions)

        ewma_level_before_update = self._ewma_level
        self._ewma_level = update_ewma_level(
            self._ewma_level, instantaneous_severity, self.calibration.ewma_smoothing_lambda
        )
        self._ewma_update_count += 1
        ewma_level_contribution = SeverityContribution(
            "ewma_smoothed_severity",
            _clamp_to_unit_interval(self._ewma_level),
            self.calibration.ewma_level_weight,
        )
        change_detector_contributions = self._change_detector_contributions(
            instantaneous_severity, ewma_level_before_update
        )

        # Fit/refit BEFORE scoring, on the baseline as it stands without this sample: the observation is
        # judged against a model it has not contributed to, and `sample_count` reports exactly the
        # baseline size the assessment was computed against.
        self._maybe_refit_principal_component_model()
        baseline_sample_count_used = self.healthy_baseline_sample_count
        statistics = self._evaluate_principal_component_model(readable_values)
        multivariate_contributions, instantaneous_anomaly_severity = (
            self._multivariate_contributions(statistics)
        )

        all_contributions = [
            *raw_signal_contributions,
            ewma_level_contribution,
            *change_detector_contributions,
            *multivariate_contributions,
        ]
        health_index = _clamp_to_unit_interval(
            1.0 - fuse_severity_contributions_by_weighted_max(all_contributions)
        )
        self._maybe_admit_to_healthy_baseline(
            readable_values,
            unreadable_names,
            max(instantaneous_severity, self._ewma_level, instantaneous_anomaly_severity),
            instantaneous_severity,
        )
        return ComponentHealthAssessment(
            component_id=self.component_id,
            health_index=health_index,
            t_squared=statistics.t_squared if statistics is not None else None,
            spe_q=statistics.spe_q if statistics is not None else None,
            ewma_level=self._ewma_level,
            degradation_state=classify_degradation_state(health_index, self.calibration),
            sample_count=baseline_sample_count_used,
            required_sample_count=self.required_baseline_sample_count,
            is_pca_armed=statistics is not None,
            contributing_signals=_ordered_contributing_signals(all_contributions),
        )

    def ingest_all(
        self, samples: Iterable[ComponentTelemetrySample]
    ) -> tuple[ComponentHealthAssessment, ...]:
        """Absorb a whole telemetry series, returning one assessment per sample."""
        return tuple(self.ingest(sample) for sample in samples)

    # -- internals ---------------------------------------------------------------------------------

    def _record_sample_ordering(self, captured_at: datetime) -> None:
        if self._latest_captured_at is not None and captured_at < self._latest_captured_at:
            self._out_of_order_sample_count += 1
            self._log_once(
                self._out_of_order_sample_count,
                "component %s telemetry arrived out of order (%s before %s); processing anyway",
                self.component_id, captured_at.isoformat(), self._latest_captured_at.isoformat(),
            )
        else:
            self._latest_captured_at = captured_at

    def _partition_readable_signal_values(
        self, signal_values: Mapping[str, float]
    ) -> tuple[dict[str, float], tuple[str, ...]]:
        """Split a raw reading into usable finite floats and the names that could not be read."""
        readable: dict[str, float] = {}
        unreadable: list[str] = []
        for signal_name, raw_value in signal_values.items():
            numeric_value = _coerce_to_finite_float(raw_value)
            if numeric_value is None:
                unreadable.append(signal_name)
            else:
                readable[signal_name] = numeric_value
        if unreadable:
            self._unreadable_signal_observation_count += len(unreadable)
            self._log_once(
                self._unreadable_signal_observation_count,
                "component %s emitted unreadable telemetry values for %s (NaN/inf/non-numeric); "
                "charging the declared unreadable-signal severity instead of ignoring them",
                self.component_id, ", ".join(sorted(unreadable)),
            )
        return readable, tuple(sorted(unreadable))

    def _raw_signal_contributions(
        self, readable_values: Mapping[str, float], unreadable_names: Sequence[str]
    ) -> list[SeverityContribution]:
        contributions: list[SeverityContribution] = []
        for signal_name in sorted(readable_values):
            severity = self._severity_for_signal(signal_name, readable_values[signal_name])
            if severity is None:
                self._abstaining_signal_names.add(signal_name)
                continue
            self._abstaining_signal_names.discard(signal_name)
            spec = self._signal_severity_specs.get(signal_name)
            weight = spec.weight if spec is not None else self.calibration.undeclared_signal_weight
            contributions.append(
                SeverityContribution(f"signal:{signal_name}", severity, weight)
            )
        for signal_name in unreadable_names:
            if self.calibration.unreadable_signal_severity <= 0.0:
                continue
            contributions.append(
                SeverityContribution(
                    f"unreadable_signal:{signal_name}",
                    self.calibration.unreadable_signal_severity,
                    self.calibration.unreadable_signal_weight,
                )
            )
        return contributions

    def _severity_for_signal(self, signal_name: str, value: float) -> float | None:
        """Declared ramp if one exists, else a robust baseline-derived ramp, else abstain."""
        spec = self._signal_severity_specs.get(signal_name)
        if spec is not None:
            return spec.severity_for_value(value)
        if len(self._healthy_baseline_samples) < self.calibration.minimum_samples_for_robust_signal_threshold:
            return None
        baseline_values = [
            baseline[signal_name]
            for baseline in self._healthy_baseline_samples
            if signal_name in baseline
        ]
        ramp = robust_severity_ramp_from_baseline(
            baseline_values,
            self.calibration.robust_nominal_sigma_multiple,
            self.calibration.robust_alarm_sigma_multiple,
        )
        if ramp is None:
            return None
        nominal_value, alarm_value = ramp
        return linear_severity_ramp(value, nominal_value, alarm_value)

    def _change_detector_contributions(
        self, instantaneous_severity: float, ewma_level_before_update: float
    ) -> list[SeverityContribution]:
        """EWMA control-limit exceedance + the ADWIN drift cross-check.

        Both are calibrated relative to the healthy baseline, which is why they are kept apart from the
        absolute-severity contributions the baseline-admission decision uses.
        """
        contributions: list[SeverityContribution] = []
        control_limit = self._ewma_upper_control_limit()
        if control_limit is not None:
            contributions.append(
                SeverityContribution(
                    "ewma_control_limit_exceedance",
                    map_control_limit_ratio_to_severity(
                        self._ewma_level,
                        control_limit,
                        self.calibration.severity_at_control_limit,
                        self.calibration.control_limit_severity_hill_exponent,
                    ),
                    self.calibration.ewma_control_limit_weight,
                )
            )
        drift_contribution = self._adwin_drift_contribution(
            instantaneous_severity, ewma_level_before_update
        )
        if drift_contribution is not None:
            contributions.append(drift_contribution)
        return contributions

    def _ewma_upper_control_limit(self) -> float | None:
        """`UCL = max(centre + k * s_ewma, practical-significance floor)` (research/168 §1c).

        `None` while the process variance is not yet estimable at all — the chart abstains rather than
        alarming off an unestimated spread.
        """
        statistics = self._baseline_severity_statistics
        if statistics.count < self.calibration.minimum_samples_for_ewma_control_limit:
            return None
        process_standard_deviation = statistics.sample_standard_deviation
        if process_standard_deviation <= _ZERO_VARIANCE_TOLERANCE:
            return None
        spread = ewma_standard_deviation(
            process_standard_deviation,
            self.calibration.ewma_smoothing_lambda,
            self._ewma_update_count,
        )
        statistical_limit = (
            statistics.mean + self.calibration.ewma_control_limit_sigma_multiple * spread
        )
        limit = max(statistical_limit, self.calibration.minimum_ewma_control_limit_severity)
        return limit if math.isfinite(limit) and limit > _ZERO_VARIANCE_TOLERANCE else None

    def _adwin_drift_contribution(
        self, instantaneous_severity: float, ewma_level_before_update: float
    ) -> SeverityContribution | None:
        self._adwin_detector.update(instantaneous_severity)
        if bool(self._adwin_detector.drift_detected):
            self._adwin_drift_detection_count += 1
            self._samples_since_adwin_drift = 0
            self._ewma_level_before_adwin_drift = ewma_level_before_update
            LOGGER.info(
                "component %s: ADWIN flagged a change in the severity stream (window mean %.4f)",
                self.component_id, float(self._adwin_detector.estimation),
            )
        elif self._samples_since_adwin_drift is not None:
            self._samples_since_adwin_drift += 1

        if (
            self._samples_since_adwin_drift is None
            or self._samples_since_adwin_drift >= self.calibration.adwin_drift_latch_sample_count
        ):
            return None
        drifted_level = _coerce_to_finite_float(self._adwin_detector.estimation)
        if drifted_level is None:
            return None
        # Only a WORSENING drift is evidence of ill health; a component that improves must not be
        # penalised for having changed.
        if drifted_level <= self._ewma_level_before_adwin_drift:
            return None
        return SeverityContribution(
            "adwin_drift_level",
            _clamp_to_unit_interval(drifted_level),
            self.calibration.adwin_drift_weight,
        )

    def _maybe_admit_to_healthy_baseline(
        self,
        readable_values: Mapping[str, float],
        unreadable_names: Sequence[str],
        admission_severity: float,
        instantaneous_severity: float,
    ) -> None:
        """Admit this sample to the healthy baseline iff it is IN CONTROL on every unsmoothed statistic.

        The gate is the textbook adaptive/recursive-MSPC rule — update the model with in-control data
        only — evaluated on the UNSMOOTHED evidence: the per-signal ramps, the EWMA level, and the raw
        `T^2`/`Q` severities. It deliberately excludes the latching change detectors (EWMA control-limit
        exceedance, ADWIN), which would keep rejecting for many samples after a transient and could
        starve the baseline.

        Including the multivariate statistics here is load-bearing, not belt-and-braces: without them
        the gate is blind to exactly the faults the PCA layer exists to catch, so a SUSTAINED structure
        break is admitted, absorbed into the healthy baseline at the next refit, and silently relearned
        as normal. (Found by test — the index recovered to 0.78 while the fault was still present.)

        The consequence is intentional: a component in a genuinely new regime stops accruing baseline
        and stays alarmed rather than normalising its own fault. Resolving that is the repair/quarantine
        layer's job, not this one's.
        """
        if not readable_values or unreadable_names:
            self._baseline_rejection_count += 1
            return
        if admission_severity > self.calibration.baseline_admission_severity_ceiling:
            self._baseline_rejection_count += 1
            return
        self._healthy_baseline_samples.append(dict(readable_values))
        self._total_baseline_admission_count += 1
        self._baseline_severity_statistics.update(instantaneous_severity)

    def _maybe_refit_principal_component_model(self) -> None:
        if len(self._healthy_baseline_samples) < self.required_baseline_sample_count:
            self._principal_component_model = None
            return
        admissions_since_attempt = (
            self._total_baseline_admission_count - self._admission_count_at_last_fit_attempt
        )
        has_attempted_before = self._admission_count_at_last_fit_attempt >= 0
        if (
            has_attempted_before
            and admissions_since_attempt < self.calibration.pca_refit_interval_sample_count
        ):
            return
        self._admission_count_at_last_fit_attempt = self._total_baseline_admission_count

        signal_names, baseline_matrix = _build_baseline_matrix(self._healthy_baseline_samples)
        if not signal_names:
            self._principal_component_model = None
            self._register_pca_fit_abstention("healthy baseline shares no common signal")
            return
        model = HealthyBaselinePrincipalComponentModel.fit_on_healthy_baseline(
            signal_names=signal_names,
            baseline_matrix=baseline_matrix,
            retained_variance_ratio=self.calibration.retained_variance_ratio,
            control_limit_significance=self.calibration.control_limit_significance,
            spe_q_control_limit_floor_per_residual_dimension=(
                self.calibration.spe_q_control_limit_floor_per_residual_dimension
            ),
        )
        if model is None:
            self._principal_component_model = None
            self._register_pca_fit_abstention("healthy baseline is degenerate (no usable variance)")
            return
        self._principal_component_model = model
        self._constant_baseline_signal_names = model.discarded_signal_names
        if model.discarded_signal_names:
            LOGGER.debug(
                "component %s: signals %s are constant across the healthy baseline and are excluded "
                "from the multivariate model (their declared/robust per-signal path still applies)",
                self.component_id, ", ".join(model.discarded_signal_names),
            )

    def _register_pca_fit_abstention(self, reason: str) -> None:
        self._pca_fit_abstention_count += 1
        self._log_once(
            self._pca_fit_abstention_count,
            "component %s: PCA layer abstaining — %s (have %d / need %d baseline samples)",
            self.component_id, reason,
            self.healthy_baseline_sample_count, self.required_baseline_sample_count,
        )

    def _evaluate_principal_component_model(
        self, readable_values: Mapping[str, float]
    ) -> MultivariateControlStatistics | None:
        model = self._principal_component_model
        if model is None:
            return None
        statistics = model.evaluate_observation(readable_values)
        if statistics is None:
            self._pca_evaluation_abstention_count += 1
            self._log_once(
                self._pca_evaluation_abstention_count,
                "component %s: PCA model could not score this observation (missing/non-finite signal); "
                "the EWMA + declared-threshold path carries the assessment",
                self.component_id,
            )
        return statistics

    def _multivariate_contributions(
        self, statistics: MultivariateControlStatistics | None
    ) -> tuple[list[SeverityContribution], float]:
        """The MSPC pair as a short window (raw, capped) plus a long window (EWMA, full authority).

        Also returns the UNCAPPED instantaneous anomaly severity, which is what the baseline-admission
        gate needs (the caps limit authority over the index, not over model updating).
        """
        if statistics is None:
            return [], 0.0
        contributions = [
            SeverityContribution(
                "hotelling_t_squared",
                map_control_limit_ratio_to_severity(
                    statistics.t_squared,
                    statistics.t_squared_control_limit,
                    self.calibration.severity_at_control_limit,
                    self.calibration.control_limit_severity_hill_exponent,
                ),
                self.calibration.hotelling_t_squared_weight,
            )
        ]
        if statistics.spe_q_control_limit is not None:
            contributions.append(
                SeverityContribution(
                    "spe_q_residual",
                    map_control_limit_ratio_to_severity(
                        statistics.spe_q,
                        statistics.spe_q_control_limit,
                        self.calibration.severity_at_control_limit,
                        self.calibration.control_limit_severity_hill_exponent,
                    ),
                    self.calibration.spe_q_weight,
                )
            )
        # research/168 §RECOMMENDATION: "feed the raw statistics through an EWMA for the primary
        # smoothing/alarm layer". The unweighted severities are what gets smoothed — the weights above
        # exist only to cap the SHORT window's authority, and must not also shrink the long one.
        instantaneous_anomaly_severity = max(
            contribution.raw_severity for contribution in contributions
        )
        self._multivariate_anomaly_ewma_level = update_ewma_level(
            self._multivariate_anomaly_ewma_level,
            instantaneous_anomaly_severity,
            self.calibration.ewma_smoothing_lambda,
        )
        contributions.append(
            SeverityContribution(
                "multivariate_anomaly_ewma",
                _clamp_to_unit_interval(self._multivariate_anomaly_ewma_level),
                self.calibration.multivariate_anomaly_ewma_weight,
            )
        )
        return contributions, instantaneous_anomaly_severity

    def _log_once(self, occurrence_count: int, message: str, *arguments: object) -> None:
        """WARNING the first time a degenerate condition is met, DEBUG on every repeat.

        Rule O.3: the condition is always counted and always logged — the level is throttled so that a
        permanently degenerate component cannot drown the log, never so that it becomes invisible.
        """
        if occurrence_count <= 1:
            LOGGER.warning(message, *arguments)
        else:
            LOGGER.debug(message, *arguments)


def _coerce_to_finite_float(value: object) -> float | None:
    """Best-effort numeric read. `None` means "unreadable" — counted and surfaced by every caller."""
    if isinstance(value, bool):
        return float(value)
    try:
        numeric_value = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return numeric_value if math.isfinite(numeric_value) else None


def _build_baseline_matrix(
    baseline_samples: Sequence[Mapping[str, float]] | deque[dict[str, float]],
) -> tuple[tuple[str, ...], NDArray[np.float64]]:
    """The `(n, p)` healthy-baseline matrix over the signals present in EVERY baseline sample.

    Intersecting rather than unioning is deliberate: a signal that only some samples carry would have to
    be imputed, and imputed values in a healthy baseline would silently distort both control limits.
    """
    samples = list(baseline_samples)
    if not samples:
        return (), np.empty((0, 0), dtype=np.float64)
    common_names = set(samples[0])
    for sample in samples[1:]:
        common_names &= set(sample)
    signal_names = tuple(sorted(common_names))
    if not signal_names:
        return (), np.empty((0, 0), dtype=np.float64)
    matrix = np.asarray(
        [[sample[name] for name in signal_names] for sample in samples], dtype=np.float64
    )
    return signal_names, matrix


def _ordered_contributing_signals(
    contributions: Sequence[SeverityContribution],
) -> tuple[tuple[str, float], ...]:
    """Worst first, then alphabetical — deterministic, so dashboards and tests never flap."""
    ordered = sorted(
        contributions, key=lambda contribution: (-contribution.weighted_severity, contribution.signal_name)
    )
    return tuple((contribution.signal_name, contribution.weighted_severity) for contribution in ordered)


@dataclass(frozen=True)
class ComponentHealthIndexEngine:
    """Fleet-level facade: one :class:`ComponentHealthIndexEstimator` per component, created on demand.

    This is what the MAPE-K orchestrator holds — it receives an interleaved telemetry stream for the
    whole organism and needs the per-component state kept apart, which is exactly what this does.
    """

    calibration: HealthIndexCalibration = field(default_factory=HealthIndexCalibration)
    signal_severity_specs_by_component_id: Mapping[str, tuple[SignalSeveritySpec, ...]] = field(
        default_factory=dict
    )
    _estimators_by_component_id: dict[str, ComponentHealthIndexEstimator] = field(
        default_factory=dict, init=False, repr=False
    )

    def estimator_for(self, component_id: str) -> ComponentHealthIndexEstimator:
        estimator = self._estimators_by_component_id.get(component_id)
        if estimator is None:
            estimator = ComponentHealthIndexEstimator(
                component_id=component_id,
                calibration=self.calibration,
                signal_severity_specs=self.signal_severity_specs_by_component_id.get(component_id, ()),
            )
            self._estimators_by_component_id[component_id] = estimator
        return estimator

    def ingest(self, sample: ComponentTelemetrySample) -> ComponentHealthAssessment:
        return self.estimator_for(sample.component_id).ingest(sample)

    def assess_all(
        self, samples: Iterable[ComponentTelemetrySample]
    ) -> dict[str, ComponentHealthAssessment]:
        """Absorb an interleaved multi-component stream, returning each component's LATEST assessment."""
        latest: dict[str, ComponentHealthAssessment] = {}
        for sample in samples:
            latest[sample.component_id] = self.ingest(sample)
        for component_id, estimator in self._estimators_by_component_id.items():
            latest.setdefault(component_id, estimator.current_assessment())
        return latest

    def tracked_component_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._estimators_by_component_id))


def assess_component_health(
    component_id: str,
    telemetry_samples: Sequence[ComponentTelemetrySample],
    calibration: HealthIndexCalibration | None = None,
    signal_severity_specs: Iterable[SignalSeveritySpec] = (),
) -> ComponentHealthAssessment:
    """Assess one component from a whole telemetry series, returning the FINAL assessment.

    The stateless entry point, for callers that hold the series rather than the estimator (backfills,
    the Rule-F real-data pass, tests). An empty series yields the abstaining `health_index=1.0`
    assessment rather than raising — a component we have not yet heard from is not evidence of illness.
    """
    estimator = ComponentHealthIndexEstimator(
        component_id=component_id,
        calibration=calibration,
        signal_severity_specs=signal_severity_specs,
    )
    latest = estimator.current_assessment()
    for sample in telemetry_samples:
        latest = estimator.ingest(sample)
    return latest
