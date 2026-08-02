"""Hierarchical partial pooling of component failure rates/probabilities (research/168 §5b/§5c/§5d).

Almost nothing in this organism has ever failed, and that is the PERMANENT operating condition, not a
warm-up phase: 7 SQLite stores, 6 persisted artifacts, 3 broker sessions, 5 background threads, 9 cadence
engines and 4 host resources, with a near-empty failure ledger. A no-pooling maximum-likelihood estimate
would hand every one of them `λ̂ = 0/T = 0` — "this component has literally zero hazard forever" — which is
both false and dangerous, because every downstream consumer (RUL, the maintenance-policy solver, the
vitality gate) would then price the risk of a dead component at exactly zero. Full pooling (one shared
rate for all stores) is the opposite error: it denies that a specific store can be systematically worse.

Partial pooling is the honest middle, and it is what makes day-one estimates principled (Rule Q): each
component's rate is drawn from a POPULATION distribution shared by its `ComponentClass`, so a store with
zero observed failures borrows strength from the other six stores' pooled experience, and detaches from
the population as its own exposure accrues — automatically, with no "is N big enough yet" switch and no
code change (research/168 §5b).

Two conjugate families are implemented in closed form, hand-rolled — research/168 §5c verified that
conjugacy suffices here, so no probabilistic-programming dependency is taken:

  * **Gamma-Poisson** for failure RATES (failures per hour of exposure):
        prior      λ ~ Gamma(α₀, β₀)                     (β₀ in RATE parameterisation, units = hours)
        data       k failures observed over T hours of exposure
        posterior  λ | k, T ~ Gamma(α₀ + k, β₀ + T)      exact, and well-defined at k = 0
        mean       λ̂ = (α₀ + k) / (β₀ + T)

  * **Beta-Binomial** for failure PROBABILITIES (failures per opportunity — health checks, invocations):
        prior      θ ~ Beta(α, β)
        data       k failures in n opportunities
        posterior  θ | k, n ~ Beta(α + k, β + n − k)
        mean       θ̂ = (α + k) / (α + β + n)

Both posterior means, and the empirical-Bayes degradation-rate shrinkage of research/168 §5d, are the
SAME convex combination of a prior mean and a raw ratio, weighted by relative sample size. research/168
§5 asks explicitly for that unification, so exactly one primitive — `shrink_toward_prior()` — computes
all three (Rule C: one well-named function, not three near-duplicate formulas):

        (α₀ + k)/(β₀ + T)  =  (β₀/(β₀+T))·(α₀/β₀)  +  (T/(β₀+T))·(k/T)
        shrink_toward_prior(observed_sum=k, observed_count=T, prior_mean=α₀/β₀, prior_strength=β₀)

The population hyperparameters (α₀, β₀) / (α, β) are estimated by **empirical Bayes, method of moments**
(Clayton-Kaldor style: subtract the expected Poisson sampling variance from the observed between-member
variance, and match the remainder to a Gamma). Three documented fallbacks cover the degenerate cases this
organism is actually in today, in priority order:

  1. `METHOD_OF_MOMENTS` — the class has ≥2 members, real exposure, ≥1 failure, and positive residual
     between-member variance.
  2. `POOLED_MEAN_DEFAULT_CONCENTRATION` — the class has failures but the moment estimate of the
     between-member variance is non-positive (all members look alike, or only one member exists). The
     prior mean is still the pooled class rate; the prior STRENGTH defaults to one member's mean exposure.
  3. `JEFFREYS_ZERO_FAILURE` — the class has real exposure but **zero** failures anywhere (today's actual
     state for every class). The pooled mean is 0, which is inadmissible as a prior mean, so we use the
     Jeffreys pseudo-count: α₀ = 0.5 over the class's total observed exposure, i.e. the prior rate is
     0.5/ΣT. This is not a magic number — it is the class's own accumulated survival evidence
     ("this population has run ΣT hours without failing") converted into a proper, non-zero prior.
  4. `FALLBACK_PRIOR` — the class has no members or no exposure at all (a brand-new component class).
     A weakly-informative default of one failure per `FALLBACK_PRIOR_EXPOSURE_HOURS` of pseudo-exposure
     (research/168 §5e: widen, never refuse to estimate).

Hyperparameters are estimated **leave-one-out** by default: a component's own data is excluded from the
population prior it is then shrunk toward. Without that exclusion the target's evidence would enter its
own posterior twice and the shrinkage weight would not be monotone in its exposure.

Every posterior carries uncertainty, never a bare point estimate (research/168 §5e): posterior mean, an
equal-tailed credible interval from the exact conjugate posterior, the effective sample size, and the
explicit weight the prior still carries.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from scipy import stats

from nse_algo_trader.autopoiesis.component_registry import ComponentClass


class QuantileFunction(Protocol):
    """The single method this engine needs from a frozen SciPy distribution (`gamma`/`beta`)."""

    def ppf(self, quantile: float) -> float: ...


# --- Documented fallback constants (see the module docstring's fallback ladder) ---------------------

#: Weakly-informative default population rate when a class has no members and no exposure at all:
#: one failure per 720 hours (~30 days of continuous uptime).
FALLBACK_POPULATION_FAILURE_RATE_PER_HOUR: float = 1.0 / 720.0
#: Weakly-informative default population failure probability per opportunity (1 in 100).
FALLBACK_POPULATION_FAILURE_PROBABILITY: float = 0.01
#: Prior strength, in pseudo-exposure hours, for the `FALLBACK_PRIOR` rung (one week).
FALLBACK_PRIOR_EXPOSURE_HOURS: float = 168.0
#: Prior strength, in pseudo-opportunities, for the `FALLBACK_PRIOR` rung of the Beta-Binomial model.
FALLBACK_PRIOR_OPPORTUNITY_COUNT: float = 50.0
#: Jeffreys pseudo-failure count used when a class has exposure but zero observed failures.
JEFFREYS_PSEUDO_FAILURE_COUNT: float = 0.5
#: Default equal-tailed credible-interval mass reported on every posterior.
DEFAULT_CREDIBLE_INTERVAL_MASS: float = 0.90
#: Numerical floor keeping every reported rate/probability strictly inside its support.
MINIMUM_POSITIVE_RATE_PER_HOUR: float = 1e-12
#: Default prior strength (in pseudo-observations) for `shrink_degradation_rate` (research/168 §5d).
DEFAULT_DEGRADATION_RATE_PRIOR_STRENGTH: float = 5.0


class PopulationPriorEstimationMethod(str, Enum):
    """Which rung of the documented fallback ladder produced a population prior.

    Reported on every prior so a consumer (and the dashboard) can tell a genuinely data-estimated
    population from a defaulted one — an honesty requirement, not decoration.
    """

    METHOD_OF_MOMENTS = "method_of_moments"
    POOLED_MEAN_DEFAULT_CONCENTRATION = "pooled_mean_default_concentration"
    JEFFREYS_ZERO_FAILURE = "jeffreys_zero_failure"
    FALLBACK_PRIOR = "fallback_prior"


# --- Inputs ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentFailureExposure:
    """One component's accumulated failure evidence — the unit the population prior pools over.

    `exposure_hours` is the Poisson exposure (observed uptime). `opportunity_count` is the Binomial
    denominator (how many times the component was invoked / health-checked); leave it at 0 when only the
    rate model applies. `observed_failure_count` is the SAME failure count under both models — a failure
    consumes one opportunity and occurs at some point during the exposure.
    """

    component_id: str
    component_class: ComponentClass
    exposure_hours: float
    observed_failure_count: int
    opportunity_count: int = 0

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("ComponentFailureExposure requires a non-empty component_id")
        if not math.isfinite(self.exposure_hours) or self.exposure_hours < 0.0:
            raise ValueError(
                f"{self.component_id}: exposure_hours must be finite and >= 0, got {self.exposure_hours!r}"
            )
        if self.observed_failure_count < 0:
            raise ValueError(
                f"{self.component_id}: observed_failure_count must be >= 0, "
                f"got {self.observed_failure_count!r}"
            )
        if self.opportunity_count < 0:
            raise ValueError(
                f"{self.component_id}: opportunity_count must be >= 0, got {self.opportunity_count!r}"
            )
        if self.opportunity_count and self.observed_failure_count > self.opportunity_count:
            raise ValueError(
                f"{self.component_id}: observed_failure_count ({self.observed_failure_count}) exceeds "
                f"opportunity_count ({self.opportunity_count})"
            )

    @property
    def raw_failure_rate_per_hour(self) -> float:
        """The unpooled maximum-likelihood rate — 0.0 for every component in this organism today."""
        return self.observed_failure_count / self.exposure_hours if self.exposure_hours > 0.0 else 0.0


# --- Outputs ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentClassPopulationPrior:
    """The population (hyper-)prior a `ComponentClass` shares, plus how it was arrived at."""

    component_class: ComponentClass
    estimation_method: PopulationPriorEstimationMethod
    contributing_member_count: int
    pooled_failure_count: int
    pooled_exposure_hours: float
    pooled_opportunity_count: int
    #: Gamma-Poisson hyperparameters: λ ~ Gamma(shape=α₀, rate=β₀); β₀ carries units of hours.
    gamma_shape: float
    gamma_rate_per_hour: float
    #: Beta-Binomial hyperparameters: θ ~ Beta(α, β).
    beta_alpha: float
    beta_beta: float

    @property
    def prior_mean_failures_per_hour(self) -> float:
        return self.gamma_shape / self.gamma_rate_per_hour

    @property
    def prior_mean_failure_probability(self) -> float:
        return self.beta_alpha / (self.beta_alpha + self.beta_beta)

    @property
    def prior_strength_hours(self) -> float:
        """Prior weight expressed in the data's own units — pseudo-exposure hours (= β₀)."""
        return self.gamma_rate_per_hour

    @property
    def prior_strength_opportunities(self) -> float:
        """Prior weight expressed in pseudo-opportunities (= α + β)."""
        return self.beta_alpha + self.beta_beta

    @property
    def is_estimated_from_class_data(self) -> bool:
        """False only for the `FALLBACK_PRIOR` rung, where no member data existed to estimate from."""
        return self.estimation_method is not PopulationPriorEstimationMethod.FALLBACK_PRIOR


@dataclass(frozen=True)
class GammaPoissonRatePosterior:
    """Exact conjugate posterior over one component's failure RATE, with its uncertainty."""

    component_id: str
    component_class: ComponentClass
    posterior_mean_failures_per_hour: float
    credible_low_failures_per_hour: float
    credible_high_failures_per_hour: float
    credible_interval_mass: float
    posterior_shape: float
    posterior_rate_per_hour: float
    #: Failure-event equivalents (real + prior pseudo-events) backing the estimate = α₀ + k.
    effective_sample_size: float
    #: Exposure-hour equivalents (real + prior pseudo-exposure) backing the estimate = β₀ + T.
    effective_exposure_hours: float
    #: Weight the population prior still carries in the posterior mean, β₀/(β₀+T) ∈ (0, 1].
    shrinkage_weight_on_prior: float
    population_prior_mean_failures_per_hour: float
    population_prior_method: PopulationPriorEstimationMethod
    observed_failure_count: int
    observed_exposure_hours: float
    raw_failure_rate_per_hour: float

    @property
    def mean_hours_between_failures(self) -> float:
        """Posterior-mean MTBF — the form the RUL prior-only path and the dashboard consume."""
        return 1.0 / max(self.posterior_mean_failures_per_hour, MINIMUM_POSITIVE_RATE_PER_HOUR)


@dataclass(frozen=True)
class BetaBinomialProbabilityPosterior:
    """Exact conjugate posterior over one component's per-opportunity failure PROBABILITY."""

    component_id: str
    component_class: ComponentClass
    posterior_mean_failure_probability: float
    credible_low_failure_probability: float
    credible_high_failure_probability: float
    credible_interval_mass: float
    posterior_alpha: float
    posterior_beta: float
    #: Opportunity equivalents (real + prior pseudo-opportunities) backing the estimate = α + β + n.
    effective_sample_size: float
    #: Weight the population prior still carries in the posterior mean, (α+β)/(α+β+n) ∈ (0, 1].
    shrinkage_weight_on_prior: float
    population_prior_mean_failure_probability: float
    population_prior_method: PopulationPriorEstimationMethod
    observed_failure_count: int
    observed_opportunity_count: int
    raw_failure_probability: float


# --- The one shared shrinkage primitive (research/168 §5, Rule C) -----------------------------------


def shrink_toward_prior(
    observed_sum: float,
    observed_count: float,
    prior_mean: float,
    prior_strength: float,
) -> float:
    """Posterior mean as a convex combination of a raw ratio and a prior mean (research/168 §5b/c/d).

        shrink_toward_prior(s, n, m, κ) = (s + κ·m) / (n + κ)
                                        = (κ/(n+κ))·m + (n/(n+κ))·(s/n)

    This ONE function is the shrinkage used by all three estimators in this engine, exactly as
    research/168 §5 requires:

      * failure RATE (Gamma-Poisson):        s = k failures,  n = T exposure hours,  κ = β₀,  m = α₀/β₀
      * failure PROBABILITY (Beta-Binomial): s = k failures,  n = trials,            κ = α+β, m = α/(α+β)
      * degradation RATE (empirical Bayes):  s = Σ rates,     n = observation count, κ tuned, m = class mean

    The interpolation weight is automatic and data-driven: at n = 0 the result is exactly the prior mean,
    and as n → ∞ it converges to the raw ratio s/n. There is no "is N big enough yet" threshold anywhere.

    Raises `ValueError` on non-finite or negative inputs, and on the fully degenerate case
    `observed_count + prior_strength == 0` where no estimate exists at all (Rule O.3/O.4: report, never
    silently return a made-up number).
    """
    for name, value in (
        ("observed_sum", observed_sum),
        ("observed_count", observed_count),
        ("prior_mean", prior_mean),
        ("prior_strength", prior_strength),
    ):
        if not math.isfinite(value):
            raise ValueError(f"shrink_toward_prior: {name} must be finite, got {value!r}")
    if observed_sum < 0.0:
        raise ValueError(f"shrink_toward_prior: observed_sum must be >= 0, got {observed_sum!r}")
    if observed_count < 0.0:
        raise ValueError(f"shrink_toward_prior: observed_count must be >= 0, got {observed_count!r}")
    if prior_strength < 0.0:
        raise ValueError(f"shrink_toward_prior: prior_strength must be >= 0, got {prior_strength!r}")
    denominator = observed_count + prior_strength
    if denominator <= 0.0:
        raise ValueError(
            "shrink_toward_prior: observed_count + prior_strength must be > 0 — with no data and no "
            "prior there is no estimate to report"
        )
    return (observed_sum + prior_strength * prior_mean) / denominator


def prior_weight_in_posterior(observed_count: float, prior_strength: float) -> float:
    """How much of `shrink_toward_prior`'s output still comes from the prior: κ/(n+κ) ∈ [0, 1].

    1.0 means "entirely prior" (no data at all); it decreases monotonically as `observed_count` grows,
    which is precisely the maturity ladder expressing itself as a continuous quantity rather than a gate.
    """
    if not math.isfinite(observed_count) or observed_count < 0.0:
        raise ValueError(f"prior_weight_in_posterior: observed_count must be finite and >= 0, "
                         f"got {observed_count!r}")
    if not math.isfinite(prior_strength) or prior_strength < 0.0:
        raise ValueError(f"prior_weight_in_posterior: prior_strength must be finite and >= 0, "
                         f"got {prior_strength!r}")
    denominator = observed_count + prior_strength
    if denominator <= 0.0:
        raise ValueError("prior_weight_in_posterior: observed_count + prior_strength must be > 0")
    return prior_strength / denominator


# --- The engine ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HierarchicalFailureRatePrior:
    """Empirical-Bayes hierarchical pooling of failure rates/probabilities across a `ComponentClass`.

    Stateless by construction (all evidence is passed in per call), so it is safe to share one instance
    across the whole MAPE-K cycle. `credible_interval_mass` fixes the equal-tailed interval reported on
    every posterior; `leave_target_out_of_population` controls whether a component's own evidence is
    excluded from the population prior it is shrunk toward (default True — see the module docstring).
    """

    credible_interval_mass: float = DEFAULT_CREDIBLE_INTERVAL_MASS
    leave_target_out_of_population: bool = True
    fallback_failure_rate_per_hour: float = FALLBACK_POPULATION_FAILURE_RATE_PER_HOUR
    fallback_failure_probability: float = FALLBACK_POPULATION_FAILURE_PROBABILITY
    fallback_prior_exposure_hours: float = FALLBACK_PRIOR_EXPOSURE_HOURS
    fallback_prior_opportunity_count: float = FALLBACK_PRIOR_OPPORTUNITY_COUNT

    def __post_init__(self) -> None:
        if not 0.0 < self.credible_interval_mass < 1.0:
            raise ValueError(
                f"credible_interval_mass must lie in (0, 1), got {self.credible_interval_mass!r}"
            )
        if not math.isfinite(self.fallback_failure_rate_per_hour) or \
                self.fallback_failure_rate_per_hour <= 0.0:
            raise ValueError("fallback_failure_rate_per_hour must be finite and > 0")
        if not 0.0 < self.fallback_failure_probability < 1.0:
            raise ValueError("fallback_failure_probability must lie in (0, 1)")
        if not math.isfinite(self.fallback_prior_exposure_hours) or \
                self.fallback_prior_exposure_hours <= 0.0:
            raise ValueError("fallback_prior_exposure_hours must be finite and > 0")
        if not math.isfinite(self.fallback_prior_opportunity_count) or \
                self.fallback_prior_opportunity_count <= 0.0:
            raise ValueError("fallback_prior_opportunity_count must be finite and > 0")

    # -- population hyperparameters --

    def estimate_population_prior(
        self,
        component_class: ComponentClass,
        class_exposures: Sequence[ComponentFailureExposure],
        exclude_component_id: str | None = None,
    ) -> ComponentClassPopulationPrior:
        """Empirical-Bayes hyperparameters for one class, by method of moments with documented fallbacks.

        `class_exposures` may contain members of other classes — they are filtered out here so callers can
        pass the whole organism's evidence. `exclude_component_id` implements leave-one-out estimation.
        """
        members = [
            exposure for exposure in class_exposures
            if exposure.component_class is component_class
            and exposure.component_id != exclude_component_id
        ]
        pooled_failures = sum(member.observed_failure_count for member in members)
        pooled_exposure = sum(member.exposure_hours for member in members)
        pooled_opportunities = sum(member.opportunity_count for member in members)

        gamma_shape, gamma_rate, rate_method = self._estimate_gamma_hyperparameters(
            members, pooled_failures, pooled_exposure
        )
        beta_alpha, beta_beta = self._estimate_beta_hyperparameters(
            members, pooled_failures, pooled_opportunities, rate_method
        )
        return ComponentClassPopulationPrior(
            component_class=component_class,
            estimation_method=rate_method,
            contributing_member_count=len(members),
            pooled_failure_count=pooled_failures,
            pooled_exposure_hours=pooled_exposure,
            pooled_opportunity_count=pooled_opportunities,
            gamma_shape=gamma_shape,
            gamma_rate_per_hour=gamma_rate,
            beta_alpha=beta_alpha,
            beta_beta=beta_beta,
        )

    def _estimate_gamma_hyperparameters(
        self,
        members: Sequence[ComponentFailureExposure],
        pooled_failures: int,
        pooled_exposure: float,
    ) -> tuple[float, float, PopulationPriorEstimationMethod]:
        """Gamma(α₀, β₀) for the population failure rate — the fallback ladder in code."""
        if not members or pooled_exposure <= 0.0:
            # Rung 4: nothing to learn from at all (empty or zero-exposure class).
            rate = self.fallback_prior_exposure_hours
            return (self.fallback_failure_rate_per_hour * rate, rate,
                    PopulationPriorEstimationMethod.FALLBACK_PRIOR)

        mean_exposure_hours = pooled_exposure / len(members)

        if pooled_failures == 0:
            # Rung 3: real exposure, zero failures anywhere in the class — today's actual state. The
            # pooled mean (0) is inadmissible as a prior mean; Jeffreys' 0.5 pseudo-failure over the
            # class's own accumulated exposure turns survival evidence into a proper non-zero prior.
            return (JEFFREYS_PSEUDO_FAILURE_COUNT, pooled_exposure,
                    PopulationPriorEstimationMethod.JEFFREYS_ZERO_FAILURE)

        pooled_mean_rate = pooled_failures / pooled_exposure

        if len(members) >= 2:
            # Rung 1: method of moments. Observed exposure-weighted between-member variance of the raw
            # rates, minus the variance the Poisson sampling noise alone would produce, matched to a
            # Gamma (Clayton & Kaldor 1987). A non-positive remainder means the members are statistically
            # indistinguishable — no between-member spread to estimate — so we drop to rung 2.
            observed_variance = sum(
                member.exposure_hours * (member.raw_failure_rate_per_hour - pooled_mean_rate) ** 2
                for member in members
            ) / pooled_exposure
            poisson_sampling_variance = pooled_mean_rate * (len(members) - 1) / pooled_exposure
            between_member_variance = observed_variance - poisson_sampling_variance
            if between_member_variance > 0.0 and math.isfinite(between_member_variance):
                shape = pooled_mean_rate**2 / between_member_variance
                rate = pooled_mean_rate / between_member_variance
                if math.isfinite(shape) and math.isfinite(rate) and shape > 0.0 and rate > 0.0:
                    return (shape, rate, PopulationPriorEstimationMethod.METHOD_OF_MOMENTS)

        # Rung 2: keep the pooled class mean, default the concentration to one member's mean exposure.
        return (pooled_mean_rate * mean_exposure_hours, mean_exposure_hours,
                PopulationPriorEstimationMethod.POOLED_MEAN_DEFAULT_CONCENTRATION)

    def _estimate_beta_hyperparameters(
        self,
        members: Sequence[ComponentFailureExposure],
        pooled_failures: int,
        pooled_opportunities: int,
        rate_method: PopulationPriorEstimationMethod,
    ) -> tuple[float, float]:
        """Beta(α, β) for the population per-opportunity failure probability, by method of moments.

        Mirrors the Gamma ladder: MoM concentration when the members genuinely differ, a Jeffreys
        Beta(0.5, n+0.5)-style prior when the class has trials but no failures, and the weakly-informative
        default when there are no trials at all.
        """
        if pooled_opportunities <= 0:
            strength = self.fallback_prior_opportunity_count
            return (self.fallback_failure_probability * strength,
                    (1.0 - self.fallback_failure_probability) * strength)

        if pooled_failures == 0:
            # Jeffreys pseudo-failure over the class's real trial count: mean = 0.5/pooled_opportunities.
            return (JEFFREYS_PSEUDO_FAILURE_COUNT,
                    max(pooled_opportunities - JEFFREYS_PSEUDO_FAILURE_COUNT,
                        JEFFREYS_PSEUDO_FAILURE_COUNT))

        pooled_mean_probability = min(max(pooled_failures / pooled_opportunities, 1e-9), 1.0 - 1e-9)
        with_trials = [member for member in members if member.opportunity_count > 0]

        if len(with_trials) >= 2 and rate_method is not PopulationPriorEstimationMethod.FALLBACK_PRIOR:
            total_trials = float(sum(member.opportunity_count for member in with_trials))
            observed_variance = sum(
                member.opportunity_count
                * (member.observed_failure_count / member.opportunity_count - pooled_mean_probability) ** 2
                for member in with_trials
            ) / total_trials
            binomial_sampling_variance = (
                pooled_mean_probability * (1.0 - pooled_mean_probability)
                * (len(with_trials) - 1) / total_trials
            )
            between_member_variance = observed_variance - binomial_sampling_variance
            maximum_variance = pooled_mean_probability * (1.0 - pooled_mean_probability)
            if 0.0 < between_member_variance < maximum_variance:
                concentration = maximum_variance / between_member_variance - 1.0
                if math.isfinite(concentration) and concentration > 0.0:
                    return (pooled_mean_probability * concentration,
                            (1.0 - pooled_mean_probability) * concentration)

        # Default concentration: one member's mean trial count.
        concentration = max(pooled_opportunities / max(len(with_trials), 1), 1.0)
        return (pooled_mean_probability * concentration,
                (1.0 - pooled_mean_probability) * concentration)

    # -- posteriors --

    def posterior_failure_rate(
        self,
        target: ComponentFailureExposure,
        class_exposures: Sequence[ComponentFailureExposure],
        population_prior: ComponentClassPopulationPrior | None = None,
    ) -> GammaPoissonRatePosterior:
        """Gamma-Poisson posterior over `target`'s failure rate, pooled across its class.

        Pass `population_prior` to reuse a prior already estimated for the class (and to hold it fixed
        while a caller varies the target's own evidence); otherwise it is estimated here, leave-one-out
        when `leave_target_out_of_population` is set.
        """
        prior = population_prior or self.estimate_population_prior(
            target.component_class,
            class_exposures,
            exclude_component_id=target.component_id if self.leave_target_out_of_population else None,
        )
        posterior_shape = prior.gamma_shape + target.observed_failure_count
        posterior_rate = prior.gamma_rate_per_hour + target.exposure_hours
        posterior_mean = shrink_toward_prior(
            observed_sum=float(target.observed_failure_count),
            observed_count=target.exposure_hours,
            prior_mean=prior.prior_mean_failures_per_hour,
            prior_strength=prior.prior_strength_hours,
        )
        low, high = self._equal_tailed_interval(
            stats.gamma(a=posterior_shape, scale=1.0 / posterior_rate)
        )
        return GammaPoissonRatePosterior(
            component_id=target.component_id,
            component_class=target.component_class,
            posterior_mean_failures_per_hour=max(posterior_mean, MINIMUM_POSITIVE_RATE_PER_HOUR),
            credible_low_failures_per_hour=max(low, 0.0),
            credible_high_failures_per_hour=high,
            credible_interval_mass=self.credible_interval_mass,
            posterior_shape=posterior_shape,
            posterior_rate_per_hour=posterior_rate,
            effective_sample_size=posterior_shape,
            effective_exposure_hours=posterior_rate,
            shrinkage_weight_on_prior=prior_weight_in_posterior(
                target.exposure_hours, prior.prior_strength_hours
            ),
            population_prior_mean_failures_per_hour=prior.prior_mean_failures_per_hour,
            population_prior_method=prior.estimation_method,
            observed_failure_count=target.observed_failure_count,
            observed_exposure_hours=target.exposure_hours,
            raw_failure_rate_per_hour=target.raw_failure_rate_per_hour,
        )

    def posterior_failure_probability(
        self,
        target: ComponentFailureExposure,
        class_exposures: Sequence[ComponentFailureExposure],
        population_prior: ComponentClassPopulationPrior | None = None,
    ) -> BetaBinomialProbabilityPosterior:
        """Beta-Binomial posterior over `target`'s per-opportunity failure probability."""
        prior = population_prior or self.estimate_population_prior(
            target.component_class,
            class_exposures,
            exclude_component_id=target.component_id if self.leave_target_out_of_population else None,
        )
        posterior_alpha = prior.beta_alpha + target.observed_failure_count
        posterior_beta = prior.beta_beta + max(
            target.opportunity_count - target.observed_failure_count, 0
        )
        posterior_mean = shrink_toward_prior(
            observed_sum=float(target.observed_failure_count),
            observed_count=float(target.opportunity_count),
            prior_mean=prior.prior_mean_failure_probability,
            prior_strength=prior.prior_strength_opportunities,
        )
        low, high = self._equal_tailed_interval(stats.beta(a=posterior_alpha, b=posterior_beta))
        raw_probability = (
            target.observed_failure_count / target.opportunity_count
            if target.opportunity_count > 0 else 0.0
        )
        return BetaBinomialProbabilityPosterior(
            component_id=target.component_id,
            component_class=target.component_class,
            posterior_mean_failure_probability=min(max(posterior_mean, 0.0), 1.0),
            credible_low_failure_probability=max(low, 0.0),
            credible_high_failure_probability=min(high, 1.0),
            credible_interval_mass=self.credible_interval_mass,
            posterior_alpha=posterior_alpha,
            posterior_beta=posterior_beta,
            effective_sample_size=posterior_alpha + posterior_beta,
            shrinkage_weight_on_prior=prior_weight_in_posterior(
                float(target.opportunity_count), prior.prior_strength_opportunities
            ),
            population_prior_mean_failure_probability=prior.prior_mean_failure_probability,
            population_prior_method=prior.estimation_method,
            observed_failure_count=target.observed_failure_count,
            observed_opportunity_count=target.opportunity_count,
            raw_failure_probability=raw_probability,
        )

    def posterior_failure_rates_for_class(
        self,
        component_class: ComponentClass,
        class_exposures: Sequence[ComponentFailureExposure],
    ) -> tuple[GammaPoissonRatePosterior, ...]:
        """Every member of one class, each shrunk toward its own leave-one-out population prior."""
        members = [
            exposure for exposure in class_exposures if exposure.component_class is component_class
        ]
        return tuple(self.posterior_failure_rate(member, members) for member in members)

    def posterior_failure_rates_by_component_id(
        self,
        organism_exposures: Sequence[ComponentFailureExposure],
    ) -> dict[str, GammaPoissonRatePosterior]:
        """Whole-organism sweep: one pooled posterior per component, grouped by its `ComponentClass`.

        This is the form `component_failure_hazard_model`'s `PRIOR_ONLY` rung and the maintenance-policy
        solver's per-class cost model consume. A duplicated `component_id` is a caller bug and is raised,
        not silently deduplicated (Rule O.3).
        """
        seen: set[str] = set()
        for exposure in organism_exposures:
            if exposure.component_id in seen:
                raise ValueError(f"duplicate component_id in exposures: {exposure.component_id}")
            seen.add(exposure.component_id)
        posteriors: dict[str, GammaPoissonRatePosterior] = {}
        for component_class in {exposure.component_class for exposure in organism_exposures}:
            for posterior in self.posterior_failure_rates_for_class(component_class, organism_exposures):
                posteriors[posterior.component_id] = posterior
        return posteriors

    # -- the third consumer of the shared primitive (research/168 §5d) --

    def shrink_degradation_rate(
        self,
        observed_degradation_rates: Iterable[float],
        population_mean_degradation_rate: float,
        prior_strength: float = DEFAULT_DEGRADATION_RATE_PRIOR_STRENGTH,
    ) -> float:
        """James-Stein-flavoured shrinkage of a component's health-degradation rate (research/168 §5d).

        The continuous-quantity sibling of the two conjugate posteriors above, sharing the exact same
        `shrink_toward_prior` primitive: a component with two noisy degradation-slope observations is
        pulled toward its class's mean slope, and detaches as its own observations accrue. Non-finite
        observations are rejected rather than silently dropped (Rule O.3).
        """
        rates = list(observed_degradation_rates)
        for rate in rates:
            if not math.isfinite(rate):
                raise ValueError(f"shrink_degradation_rate: non-finite degradation rate {rate!r}")
        if not math.isfinite(population_mean_degradation_rate):
            raise ValueError("shrink_degradation_rate: population_mean_degradation_rate must be finite")
        # Degradation rates may legitimately be negative (a healing component), which the non-negative
        # `observed_sum` contract of `shrink_toward_prior` forbids — so shift into a non-negative frame,
        # shrink, and shift back. The arithmetic is identical; only the guard rails move.
        offset = min([0.0, population_mean_degradation_rate, *rates])
        shrunk = shrink_toward_prior(
            observed_sum=sum(rate - offset for rate in rates),
            observed_count=float(len(rates)),
            prior_mean=population_mean_degradation_rate - offset,
            prior_strength=prior_strength,
        )
        return shrunk + offset

    # -- internals --

    def _equal_tailed_interval(self, distribution: QuantileFunction) -> tuple[float, float]:
        tail = (1.0 - self.credible_interval_mass) / 2.0
        low = float(distribution.ppf(tail))
        high = float(distribution.ppf(1.0 - tail))
        if not math.isfinite(low) or not math.isfinite(high) or high < low:
            raise ValueError(
                f"conjugate posterior produced a non-finite credible interval [{low}, {high}] — "
                "refusing to report an uncertainty band that does not exist"
            )
        return (low, high)


def build_class_exposures_from_registry(
    failure_counts_by_component_id: dict[str, int],
    exposure_hours_by_component_id: dict[str, float],
    components: Sequence[tuple[str, ComponentClass]],
) -> tuple[ComponentFailureExposure, ...]:
    """Adapter from the registry + the failure ledger to this engine's input type.

    `components` is the `(component_id, component_class)` projection of
    `OrganismComponentRegistry.self_components()`. Components missing from either mapping contribute
    zero failures / zero exposure — which is exactly the evidence the hierarchical prior is designed to
    handle, not a reason to drop them from the population.
    """
    return tuple(
        ComponentFailureExposure(
            component_id=component_id,
            component_class=component_class,
            exposure_hours=max(exposure_hours_by_component_id.get(component_id, 0.0), 0.0),
            observed_failure_count=max(failure_counts_by_component_id.get(component_id, 0), 0),
        )
        for component_id, component_class in components
    )
