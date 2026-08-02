"""Remaining-useful-life prognostics for organism components (research/168 §2 + §5; research/172 §3/§4).

Right censoring is not an edge case here, it is the data: at any instant almost every SQLite store,
broker session, background thread and cadence engine **has not yet failed**, so its true lifetime is known
only to exceed its current age (research/168 §2a). Dropping those rows ("no data") or treating them as
deaths ("failed now") are the two classic, both-wrong readings. Survival analysis exists to use them
correctly, and this module is built entirely around that fact.

Three fully-implemented estimators sit on a Rule-Q maturity ladder (research/172 §4). Every one of them
is a real estimator — none is a stub — and each arms itself automatically as evidence accrues, with no
code change and no new slice:

  1. **`WEIBULL_AFT` — lifelines `WeibullAFTFitter`, right-censored accelerated-failure-time regression.**
     `log(T) = βᵀx + σ·ε`, fitted by maximum likelihood on the censored likelihood
     `L = Π_i f(t_i|x_i)^{δ_i} · S(t_i|x_i)^{1−δ_i}` (research/168 §2c), where `δ_i = 1` marks an observed
     failure and `δ_i = 0` a component that is still alive. Weibull is the one distribution that is
     simultaneously proportional-hazards and accelerated-failure-time, so choosing it costs nothing
     against Cox while yielding a full parametric survival curve that RUL quantiles read directly off.
     Covariates: restart count, EWMA degradation trend, and component-class indicators. Component AGE is
     the model's time axis (`duration_col`), which is how age enters an AFT model — putting it on the
     right-hand side as well would make it perfectly collinear with the response and non-identifiable.
     `penalizer` is the small-N regulariser (ridge/elastic-net on the coefficients), the same shrinkage
     family as research/168 §5. **Arms at ≥2 observed failures in the component's own class**, the
     regime pre-verified during sourcing (research/172 §10: 2/10 failures, 80% right-censored →
     converged, ρ = 1.857, concordance 1.0, RUL rank-ordered 71.6 h → 970.8 h).

  2. **`WIENER_FIRST_PASSAGE` — Wiener-process first-passage-time RUL, closed-form Inverse Gaussian.**
     Models the health-index trajectory itself as `X(t) = X(0) + μt + σB(t)` and calls "failure" the first
     crossing of a threshold, so it needs **zero observed failures** to produce a calibrated RUL
     distribution (research/168 §2d) — it is what carries the cold-start, which is the organism's
     permanent condition, and it is a genuinely different valid estimator, not a fallback stub. A Wiener
     (not Gamma) process is the right choice because these health indices legitimately move in BOTH
     directions: a broker session recovers after a network blip, a model's drift score shrinks after a
     retrain. First passage of a Wiener process to a level `d` away is Inverse-Gaussian with
     `mean = d/μ` and `shape λ = d²/σ²`, whose quantiles are closed-form.

  3. **`PRIOR_ONLY` — the hierarchical Gamma-Poisson posterior from `hierarchical_failure_rate_prior`.**
     When a component has neither class failures nor a health trajectory (a just-registered component),
     its class-pooled posterior failure rate `λ̂` still exists by construction, and an exponential lifetime
     with that rate gives honest, wide RUL quantiles: `t_q = −ln(1−q)/λ̂`. Never "undefined", never 0.

`is_earned` is True only on rung 1 — the estimator actually used is reported on every estimate, so a
consumer can never mistake a prior-driven number for a fitted one. Convergence failures are recorded in
`WeibullAftFitReport` and logged, never silently swallowed (Rule O.3): the ladder still steps down, but
the reason is carried, not lost. lifelines' convergence warnings are captured with a LOCAL
`warnings.catch_warnings()` block and turned into that report — the global warning filter is untouched.
"""

from __future__ import annotations

import logging
import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from scipy import stats

from nse_algo_trader.autopoiesis.component_registry import ComponentClass
from nse_algo_trader.autopoiesis.hierarchical_failure_rate_prior import (
    ComponentFailureExposure,
    HierarchicalFailureRatePrior,
)

if TYPE_CHECKING:  # pragma: no cover - typing only; pandas is imported lazily inside the fit path
    import pandas as pd

LOGGER = logging.getLogger(__name__)

#: Observed failures required IN A COMPONENT'S OWN CLASS before the Weibull AFT model is armed for it.
REQUIRED_CLASS_FAILURE_COUNT: int = 2
#: Rows required before an AFT regression is numerically meaningful at all (censored rows count).
MINIMUM_AFT_OBSERVATION_COUNT: int = 3
#: Default elastic-net penalty on the AFT coefficients — the small-N regulariser (research/168 §6).
DEFAULT_AFT_PENALIZER: float = 0.1
#: Health-index samples required before a Wiener drift/diffusion pair can be estimated.
MINIMUM_TRAJECTORY_SAMPLE_COUNT: int = 3
#: Drift floor (health units per hour). A component whose measured trajectory is flat or improving has no
#: proper first-passage distribution (the Wiener FPT is defective for μ ≤ 0), so we hold a small positive
#: wear-out floor: everything degrades eventually. Reported via `WienerFirstPassageParameters`.
MINIMUM_DEGRADATION_DRIFT_PER_HOUR: float = 1e-5
#: Diffusion floor keeping the Inverse-Gaussian proper when a trajectory has zero measured variance.
MINIMUM_DEGRADATION_DIFFUSION_PER_HOUR: float = 1e-9
#: Floor on the health distance still to be travelled before failure (a component already at/past its
#: threshold still gets a proper, if vanishing, first-passage distribution rather than a division by zero).
MINIMUM_REMAINING_HEALTH_DISTANCE: float = 1e-6
#: Every reported RUL is strictly positive; a component already past its threshold reports this floor.
MINIMUM_REMAINING_USEFUL_LIFE_HOURS: float = 1e-3
#: Upper clamp on any reported RUL quantile (~11 years) so a near-zero hazard cannot produce `inf`.
MAXIMUM_REMAINING_USEFUL_LIFE_HOURS: float = 1e5
#: Health index at which a component counts as failed (1.0 = perfectly healthy, per research/172 §2).
DEFAULT_FAILURE_HEALTH_INDEX: float = 0.0


class RemainingUsefulLifeEstimator(str, Enum):
    """Which rung of the maturity ladder produced an estimate — reported honestly, never inferred."""

    WEIBULL_AFT = "weibull_aft"
    WIENER_FIRST_PASSAGE = "wiener_first_passage"
    PRIOR_ONLY = "prior_only"


# --- Inputs ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentLifetimeObservation:
    """One row of the right-censored survival dataset — one component's life so far.

    `observed_failure` is the censoring flag in its natural polarity: True = the failure was actually
    observed (`event = 1`), False = the component is still alive and its lifetime is right-censored at
    `uptime_hours` (`event = 0`). `degradation_trend` is the EWMA slope of the health index (positive =
    degrading) and may be NaN when telemetry is too thin to compute it — that is sanitised at fit time
    with a recorded count, never silently.
    """

    component_id: str
    component_class: ComponentClass
    uptime_hours: float
    observed_failure: bool
    restart_count: int = 0
    degradation_trend: float = 0.0

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("ComponentLifetimeObservation requires a non-empty component_id")
        if not math.isfinite(self.uptime_hours) or self.uptime_hours <= 0.0:
            raise ValueError(
                f"{self.component_id}: uptime_hours must be finite and > 0 (a survival duration of "
                f"zero carries no information), got {self.uptime_hours!r}"
            )
        if self.restart_count < 0:
            raise ValueError(
                f"{self.component_id}: restart_count must be >= 0, got {self.restart_count!r}"
            )


@dataclass(frozen=True)
class ComponentHealthTrajectory:
    """The health-index time series the Wiener first-passage estimator runs on (research/168 §2d).

    Samples are ordered oldest → newest, each in `[0, 1]` with 1.0 = perfectly healthy (research/172 §2's
    sign convention, so multipliers compose directly). `failure_health_index` is the crossing threshold.
    """

    component_id: str
    health_index_samples: tuple[float, ...]
    sample_interval_hours: float
    failure_health_index: float = DEFAULT_FAILURE_HEALTH_INDEX

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("ComponentHealthTrajectory requires a non-empty component_id")
        if not math.isfinite(self.sample_interval_hours) or self.sample_interval_hours <= 0.0:
            raise ValueError(
                f"{self.component_id}: sample_interval_hours must be finite and > 0, "
                f"got {self.sample_interval_hours!r}"
            )
        if not 0.0 <= self.failure_health_index < 1.0:
            raise ValueError(
                f"{self.component_id}: failure_health_index must lie in [0, 1), "
                f"got {self.failure_health_index!r}"
            )
        for sample in self.health_index_samples:
            if not math.isfinite(sample) or not 0.0 <= sample <= 1.0:
                raise ValueError(
                    f"{self.component_id}: health index samples must be finite and within [0, 1], "
                    f"got {sample!r}"
                )

    @property
    def is_estimable(self) -> bool:
        """Enough samples to estimate a drift AND a diffusion coefficient."""
        return len(self.health_index_samples) >= MINIMUM_TRAJECTORY_SAMPLE_COUNT

    @property
    def current_health_index(self) -> float:
        if not self.health_index_samples:
            raise ValueError(f"{self.component_id}: trajectory has no samples")
        return self.health_index_samples[-1]


# --- Outputs ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RemainingUsefulLifeEstimate:
    """RUL for one component, with the estimator that produced it named honestly.

    Hours are REMAINING hours from now, conditional on the component having survived to its current age
    — not absolute lifetimes. `p10_hours <= median_hours <= p90_hours` always holds, and every quantile
    is strictly positive and finite.
    """

    component_id: str
    median_hours: float
    p10_hours: float
    p90_hours: float
    estimator: RemainingUsefulLifeEstimator
    is_earned: bool
    observed_failure_count: int
    required_failure_count: int


@dataclass(frozen=True)
class WeibullAftFitReport:
    """Carried diagnostics of the last AFT fit — the Rule-O.3 record that a solver failure is not lost."""

    attempted: bool
    converged: bool
    observation_count: int
    observed_failure_count: int
    censored_fraction: float
    covariate_columns: tuple[str, ...]
    dropped_zero_variance_columns: tuple[str, ...]
    sanitized_covariate_count: int
    penalizer: float
    weibull_shape_rho: float | None = None
    concordance_index: float | None = None
    convergence_warnings: tuple[str, ...] = ()
    failure_reason: str | None = None


@dataclass(frozen=True)
class WienerFirstPassageParameters:
    """Estimated Wiener degradation parameters + the Inverse-Gaussian first-passage distribution."""

    component_id: str
    degradation_drift_per_hour: float
    degradation_diffusion_per_hour: float
    remaining_health_distance: float
    inverse_gaussian_mean_hours: float
    inverse_gaussian_shape: float
    drift_was_floored: bool
    diffusion_was_floored: bool
    sample_count: int


# --- The engine ------------------------------------------------------------------------------------


class ComponentFailureHazardModel:
    """RUL prognostics over the organism's right-censored component-lifetime ledger.

    Carries state: the fitted `WeibullAFTFitter`, the design matrix it was fitted on, and the fit report.
    The fit is refreshed only when the observation set changes, so `estimate_remaining_useful_life` is
    cheap to call once per component per MAPE-K cycle.
    """

    def __init__(
        self,
        hierarchical_prior: HierarchicalFailureRatePrior | None = None,
        penalizer: float = DEFAULT_AFT_PENALIZER,
        required_class_failure_count: int = REQUIRED_CLASS_FAILURE_COUNT,
    ) -> None:
        if not math.isfinite(penalizer) or penalizer < 0.0:
            raise ValueError(f"penalizer must be finite and >= 0, got {penalizer!r}")
        if required_class_failure_count < 1:
            raise ValueError(
                f"required_class_failure_count must be >= 1, got {required_class_failure_count!r}"
            )
        self._hierarchical_prior = hierarchical_prior or HierarchicalFailureRatePrior()
        self._penalizer = penalizer
        self._required_class_failure_count = required_class_failure_count
        self._fitted_model: Any | None = None
        self._fitted_covariates: Any | None = None
        self._fitted_signature: tuple[tuple[str, float, bool, int, float], ...] | None = None
        self._fit_report: WeibullAftFitReport | None = None

    # -- public API --

    @property
    def fit_report(self) -> WeibullAftFitReport | None:
        """Diagnostics of the most recent AFT fit attempt (None until one is attempted)."""
        return self._fit_report

    @property
    def required_class_failure_count(self) -> int:
        return self._required_class_failure_count

    def observed_failure_count_for_class(
        self,
        component_class: ComponentClass,
        observations: Sequence[ComponentLifetimeObservation],
    ) -> int:
        """`have N` of the Rule-Q `have N / need M` maturity display, per component class."""
        return sum(
            1 for observation in observations
            if observation.component_class is component_class and observation.observed_failure
        )

    def fit(self, observations: Sequence[ComponentLifetimeObservation]) -> WeibullAftFitReport:
        """Fit the right-censored Weibull AFT regression over the whole organism's lifetime ledger.

        Fitting pools ALL classes (class membership enters as an indicator covariate) because censored
        rows from other classes still carry real information about the shared baseline hazard — which is
        the entire point of using survival analysis instead of counting failures. Returns the report; a
        non-converging solve is reported with `converged=False` and a `failure_reason`, and logged at
        WARNING — never swallowed.
        """
        signature = self._observation_signature(observations)
        if self._fit_report is not None and signature == self._fitted_signature:
            return self._fit_report
        report = self._fit_uncached(observations)
        self._fitted_signature = signature
        self._fit_report = report
        return report

    def estimate_remaining_useful_life(
        self,
        component_id: str,
        observations: Sequence[ComponentLifetimeObservation],
        health_trajectory: ComponentHealthTrajectory | None = None,
    ) -> RemainingUsefulLifeEstimate:
        """Walk the maturity ladder for one component and return its RUL with the estimator used.

        Ladder: Weibull AFT (armed at ≥`required_class_failure_count` observed failures in the
        component's own class, and only if the solver actually converged) → Wiener first-passage off the
        health trajectory (needs zero failures) → the class-pooled hierarchical prior.
        """
        target = self._find_observation(component_id, observations)
        class_failure_count = self.observed_failure_count_for_class(
            target.component_class, observations
        )

        if class_failure_count >= self._required_class_failure_count:
            report = self.fit(observations)
            if report.converged:
                estimate = self._aft_estimate(target, class_failure_count)
                if estimate is not None:
                    return estimate
            else:
                # Rule O.3: the ladder steps down, but the reason travels with it into the log.
                LOGGER.warning(
                    "Weibull AFT is armed for class %s (%d observed failures) but the fit did not "
                    "converge (%s); stepping down the RUL maturity ladder for %s",
                    target.component_class.value, class_failure_count, report.failure_reason,
                    component_id,
                )

        if health_trajectory is not None and health_trajectory.is_estimable:
            if health_trajectory.component_id != component_id:
                raise ValueError(
                    f"health_trajectory belongs to {health_trajectory.component_id!r}, "
                    f"not {component_id!r}"
                )
            return self._wiener_estimate(target, health_trajectory, class_failure_count)

        return self._prior_only_estimate(target, observations, class_failure_count)

    def estimate_remaining_useful_life_for_all(
        self,
        observations: Sequence[ComponentLifetimeObservation],
        health_trajectories: Sequence[ComponentHealthTrajectory] = (),
    ) -> tuple[RemainingUsefulLifeEstimate, ...]:
        """Whole-organism sweep, ordered nearest-to-failure first (the dashboard's headline metric)."""
        trajectories = {trajectory.component_id: trajectory for trajectory in health_trajectories}
        estimates = [
            self.estimate_remaining_useful_life(
                observation.component_id, observations, trajectories.get(observation.component_id)
            )
            for observation in observations
        ]
        return tuple(sorted(estimates, key=lambda estimate: estimate.median_hours))

    # -- rung 1: Weibull AFT --

    def _fit_uncached(
        self, observations: Sequence[ComponentLifetimeObservation]
    ) -> WeibullAftFitReport:
        observation_count = len(observations)
        failure_count = sum(1 for observation in observations if observation.observed_failure)
        censored_fraction = (
            1.0 - failure_count / observation_count if observation_count else 0.0
        )

        if observation_count < MINIMUM_AFT_OBSERVATION_COUNT:
            return self._unfitted_report(
                observation_count, failure_count, censored_fraction,
                f"only {observation_count} lifetime observations; "
                f"{MINIMUM_AFT_OBSERVATION_COUNT} are required for an AFT regression",
            )
        if failure_count == 0:
            return self._unfitted_report(
                observation_count, failure_count, censored_fraction,
                "every observation is right-censored — a maximum-likelihood AFT fit has no event "
                "information to identify the shape from",
            )

        frame, sanitized_count, dropped_columns = self._build_design_matrix(observations)
        covariate_columns = tuple(
            column for column in frame.columns if column not in ("duration_hours", "failure_observed")
        )

        # lifelines is imported lazily: it drags in autograd/pandas, and a homeostat cycle that never
        # reaches the AFT rung should not pay that cost. An import failure is itself a reported reason.
        try:
            from lifelines import WeibullAFTFitter
            from lifelines.exceptions import ConvergenceWarning
        except ImportError as error:
            return self._unfitted_report(
                observation_count, failure_count, censored_fraction,
                f"lifelines is unavailable ({error}) — the Weibull AFT rung cannot arm",
                covariate_columns, dropped_columns, sanitized_count,
            )

        try:
            fitter = WeibullAFTFitter(penalizer=self._penalizer)
            # LOCAL warning capture only: lifelines' ConvergenceWarning is turned into a recorded
            # diagnostic instead of stderr noise. The global warning filter is never touched.
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                fitter.fit(frame, duration_col="duration_hours", event_col="failure_observed")
            convergence_warnings = tuple(
                str(entry.message) for entry in caught
                if issubclass(entry.category, ConvergenceWarning)
            )
        except Exception as error:
            # Rule O.3: a solver that does not converge is REPORTED (report + log + carried reason),
            # never silently replaced by a different estimator behind the caller's back.
            return self._unfitted_report(
                observation_count, failure_count, censored_fraction,
                f"{type(error).__name__}: {error}", covariate_columns, dropped_columns,
                sanitized_count,
            )

        for message in convergence_warnings:
            LOGGER.warning("lifelines WeibullAFTFitter convergence warning: %s", message)

        rho = self._extract_weibull_shape(fitter)
        concordance = getattr(fitter, "concordance_index_", None)
        self._fitted_model = fitter
        self._fitted_covariates = frame.drop(columns=["duration_hours", "failure_observed"])
        return WeibullAftFitReport(
            attempted=True,
            converged=True,
            observation_count=observation_count,
            observed_failure_count=failure_count,
            censored_fraction=censored_fraction,
            covariate_columns=covariate_columns,
            dropped_zero_variance_columns=dropped_columns,
            sanitized_covariate_count=sanitized_count,
            penalizer=self._penalizer,
            weibull_shape_rho=rho,
            concordance_index=float(concordance) if concordance is not None else None,
            convergence_warnings=convergence_warnings,
        )

    def _build_design_matrix(
        self, observations: Sequence[ComponentLifetimeObservation]
    ) -> tuple[pd.DataFrame, int, tuple[str, ...]]:
        """Survival frame: duration = age, event = censoring flag, covariates = restarts/trend/class.

        Age is the DURATION, not a covariate — see the module docstring. Non-finite degradation trends
        are replaced by the finite-sample mean (a recorded count, not a silent drop, so the row keeps its
        censoring information). Zero-variance columns are dropped because they are unidentifiable in a
        regression and would otherwise force the penalizer to carry them.
        """
        import pandas as pandas_module

        finite_trends = [
            observation.degradation_trend for observation in observations
            if math.isfinite(observation.degradation_trend)
        ]
        replacement_trend = sum(finite_trends) / len(finite_trends) if finite_trends else 0.0
        sanitized_count = len(observations) - len(finite_trends)

        present_classes = sorted({observation.component_class.value for observation in observations})
        rows = []
        for observation in observations:
            trend = (
                observation.degradation_trend
                if math.isfinite(observation.degradation_trend) else replacement_trend
            )
            row: dict[str, float] = {
                "duration_hours": float(observation.uptime_hours),
                "failure_observed": 1.0 if observation.observed_failure else 0.0,
                "restart_count": float(observation.restart_count),
                "degradation_trend": float(trend),
            }
            for class_value in present_classes:
                row[f"class_{class_value}"] = (
                    1.0 if observation.component_class.value == class_value else 0.0
                )
            rows.append(row)

        frame = pandas_module.DataFrame(rows)
        dropped: list[str] = []
        for column in list(frame.columns):
            if column in ("duration_hours", "failure_observed"):
                continue
            if float(frame[column].std(ddof=0)) <= 0.0:
                dropped.append(column)
        if dropped:
            frame = frame.drop(columns=dropped)
        return frame, sanitized_count, tuple(dropped)

    def _aft_estimate(
        self, target: ComponentLifetimeObservation, class_failure_count: int
    ) -> RemainingUsefulLifeEstimate | None:
        """Conditional RUL quantiles from the fitted AFT survival curve, given survival to `uptime_hours`.

        lifelines' `predict_percentile(p)` returns the time at which the survival function drops to `p`,
        so the EARLY (10th-percentile-of-lifetime) RUL comes from `p = 0.9` and the LATE one from
        `p = 0.1` — verified numerically against this lifelines build before wiring.
        """
        fitter = self._fitted_model
        covariates = self._fitted_covariates
        if fitter is None or covariates is None:
            return None
        row_index = self._covariate_row_index(target)
        if row_index is None:
            return None
        design_row = covariates.iloc[[row_index]]
        conditional_after = [float(target.uptime_hours)]
        try:
            quantiles = {
                percentile: float(
                    fitter.predict_percentile(
                        design_row, p=percentile, conditional_after=conditional_after
                    ).to_numpy()[0]
                )
                for percentile in (0.9, 0.5, 0.1)
            }
        except Exception as error:  # surfaced below, then the ladder steps down (Rule O.3)
            LOGGER.warning(
                "Weibull AFT prediction failed for %s (%s: %s); stepping down the RUL ladder",
                target.component_id, type(error).__name__, error,
            )
            return None

        p10, median, p90 = (quantiles[0.9], quantiles[0.5], quantiles[0.1])
        if not all(math.isfinite(value) for value in (p10, median, p90)):
            LOGGER.warning(
                "Weibull AFT produced non-finite RUL quantiles for %s (p10=%s median=%s p90=%s); "
                "stepping down the RUL ladder", target.component_id, p10, median, p90,
            )
            return None
        return self._build_estimate(
            target.component_id, median, p10, p90,
            RemainingUsefulLifeEstimator.WEIBULL_AFT, True, class_failure_count,
        )

    def _covariate_row_index(self, target: ComponentLifetimeObservation) -> int | None:
        signature = self._fitted_signature
        if signature is None:
            return None
        for index, (component_id, _, _, _, _) in enumerate(signature):
            if component_id == target.component_id:
                return index
        return None

    # -- rung 2: Wiener first-passage --

    def estimate_wiener_first_passage_parameters(
        self, trajectory: ComponentHealthTrajectory
    ) -> WienerFirstPassageParameters:
        """MLE of the Wiener drift/diffusion off a health trajectory + its Inverse-Gaussian FPT.

        Degradation is measured in health units LOST per hour, so drift is positive when the component is
        deteriorating. `μ̂` is the total decline over the observed window divided by its span; `σ̂²` is the
        mean squared deviation of the per-step declines from `μ̂·Δt`, per unit time. Both are floored (and
        the flooring reported) because the first-passage distribution is defective at `μ ≤ 0` and
        degenerate at `σ² = 0`.
        """
        if not trajectory.is_estimable:
            raise ValueError(
                f"{trajectory.component_id}: {len(trajectory.health_index_samples)} health samples is "
                f"below the {MINIMUM_TRAJECTORY_SAMPLE_COUNT} needed to estimate drift and diffusion"
            )
        samples = trajectory.health_index_samples
        step_hours = trajectory.sample_interval_hours
        span_hours = step_hours * (len(samples) - 1)

        raw_drift = (samples[0] - samples[-1]) / span_hours
        drift_was_floored = raw_drift <= MINIMUM_DEGRADATION_DRIFT_PER_HOUR
        drift = max(raw_drift, MINIMUM_DEGRADATION_DRIFT_PER_HOUR)

        squared_residuals = [
            ((samples[index - 1] - samples[index]) - raw_drift * step_hours) ** 2
            for index in range(1, len(samples))
        ]
        raw_diffusion = sum(squared_residuals) / (len(squared_residuals) * step_hours)
        diffusion_was_floored = raw_diffusion <= MINIMUM_DEGRADATION_DIFFUSION_PER_HOUR
        diffusion = max(raw_diffusion, MINIMUM_DEGRADATION_DIFFUSION_PER_HOUR)

        distance = max(
            trajectory.current_health_index - trajectory.failure_health_index,
            MINIMUM_REMAINING_HEALTH_DISTANCE,
        )
        return WienerFirstPassageParameters(
            component_id=trajectory.component_id,
            degradation_drift_per_hour=drift,
            degradation_diffusion_per_hour=diffusion,
            remaining_health_distance=distance,
            inverse_gaussian_mean_hours=distance / drift,
            inverse_gaussian_shape=distance**2 / diffusion,
            drift_was_floored=drift_was_floored,
            diffusion_was_floored=diffusion_was_floored,
            sample_count=len(samples),
        )

    def _wiener_estimate(
        self,
        target: ComponentLifetimeObservation,
        trajectory: ComponentHealthTrajectory,
        class_failure_count: int,
    ) -> RemainingUsefulLifeEstimate:
        parameters = self.estimate_wiener_first_passage_parameters(trajectory)
        # SciPy's `invgauss(mu, scale)` has mean = mu·scale and shape = scale, so an IG with
        # mean m and shape λ is `invgauss(mu=m/λ, scale=λ)` — verified numerically against
        # mean = m and variance = m³/λ before wiring.
        mean_hours = parameters.inverse_gaussian_mean_hours
        shape = parameters.inverse_gaussian_shape
        distribution = stats.invgauss(mu=mean_hours / shape, scale=shape)
        p10, median, p90 = (
            float(distribution.ppf(0.10)),
            float(distribution.ppf(0.50)),
            float(distribution.ppf(0.90)),
        )
        if not all(math.isfinite(value) for value in (p10, median, p90)):
            raise ValueError(
                f"{target.component_id}: Wiener first-passage produced non-finite RUL quantiles "
                f"(drift={parameters.degradation_drift_per_hour}, "
                f"diffusion={parameters.degradation_diffusion_per_hour})"
            )
        return self._build_estimate(
            target.component_id, median, p10, p90,
            RemainingUsefulLifeEstimator.WIENER_FIRST_PASSAGE, False, class_failure_count,
        )

    # -- rung 3: hierarchical prior only --

    def _prior_only_estimate(
        self,
        target: ComponentLifetimeObservation,
        observations: Sequence[ComponentLifetimeObservation],
        class_failure_count: int,
    ) -> RemainingUsefulLifeEstimate:
        exposures = tuple(
            ComponentFailureExposure(
                component_id=observation.component_id,
                component_class=observation.component_class,
                exposure_hours=observation.uptime_hours,
                observed_failure_count=1 if observation.observed_failure else 0,
            )
            for observation in observations
        )
        target_exposure = next(
            exposure for exposure in exposures if exposure.component_id == target.component_id
        )
        posterior = self._hierarchical_prior.posterior_failure_rate(target_exposure, exposures)
        rate = max(posterior.posterior_mean_failures_per_hour, 1.0 / MAXIMUM_REMAINING_USEFUL_LIFE_HOURS)
        # Exponential lifetime at the class-pooled posterior rate: t_q = −ln(1−q)/λ̂ (memoryless, so the
        # quantiles are already REMAINING life conditional on survival to the current age).
        return self._build_estimate(
            target.component_id,
            math.log(2.0) / rate,
            -math.log(0.9) / rate,
            -math.log(0.1) / rate,
            RemainingUsefulLifeEstimator.PRIOR_ONLY,
            False,
            class_failure_count,
        )

    # -- internals --

    def _build_estimate(
        self,
        component_id: str,
        median_hours: float,
        p10_hours: float,
        p90_hours: float,
        estimator: RemainingUsefulLifeEstimator,
        is_earned: bool,
        observed_failure_count: int,
    ) -> RemainingUsefulLifeEstimate:
        """Clamp to the reportable range and enforce the p10 ≤ median ≤ p90 invariant structurally."""
        clamped = [
            min(max(value, MINIMUM_REMAINING_USEFUL_LIFE_HOURS), MAXIMUM_REMAINING_USEFUL_LIFE_HOURS)
            for value in (p10_hours, median_hours, p90_hours)
        ]
        p10, median, p90 = sorted(clamped)
        return RemainingUsefulLifeEstimate(
            component_id=component_id,
            median_hours=median,
            p10_hours=p10,
            p90_hours=p90,
            estimator=estimator,
            is_earned=is_earned,
            observed_failure_count=observed_failure_count,
            required_failure_count=self._required_class_failure_count,
        )

    def _unfitted_report(
        self,
        observation_count: int,
        failure_count: int,
        censored_fraction: float,
        failure_reason: str,
        covariate_columns: tuple[str, ...] = (),
        dropped_columns: tuple[str, ...] = (),
        sanitized_count: int = 0,
    ) -> WeibullAftFitReport:
        LOGGER.info("Weibull AFT not fitted: %s", failure_reason)
        self._fitted_model = None
        self._fitted_covariates = None
        return WeibullAftFitReport(
            attempted=True,
            converged=False,
            observation_count=observation_count,
            observed_failure_count=failure_count,
            censored_fraction=censored_fraction,
            covariate_columns=covariate_columns,
            dropped_zero_variance_columns=dropped_columns,
            sanitized_covariate_count=sanitized_count,
            penalizer=self._penalizer,
            failure_reason=failure_reason,
        )

    @staticmethod
    def _extract_weibull_shape(fitter: object) -> float | None:
        """The fitted Weibull shape ρ (>1 = wear-out, ≈1 = constant hazard) — research/168 §3d."""
        params = getattr(fitter, "params_", None)
        if params is None:
            return None
        try:
            return float(params[("rho_", "Intercept")])
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _observation_signature(
        observations: Sequence[ComponentLifetimeObservation],
    ) -> tuple[tuple[str, float, bool, int, float], ...]:
        return tuple(
            (
                observation.component_id,
                observation.uptime_hours,
                observation.observed_failure,
                observation.restart_count,
                observation.degradation_trend,
            )
            for observation in observations
        )

    @staticmethod
    def _find_observation(
        component_id: str, observations: Sequence[ComponentLifetimeObservation]
    ) -> ComponentLifetimeObservation:
        if not observations:
            raise ValueError(
                "estimate_remaining_useful_life needs at least one ComponentLifetimeObservation — "
                "an empty organism has no components to prognose"
            )
        for observation in observations:
            if observation.component_id == component_id:
                return observation
        raise ValueError(
            f"{component_id!r} has no ComponentLifetimeObservation; known ids: "
            f"{sorted(observation.component_id for observation in observations)}"
        )
