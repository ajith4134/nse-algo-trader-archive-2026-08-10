"""Minimum Backtest Length (MinBTL) gate + Probability of Backtest Overfitting
(PBO) — the two multiple-testing defences that sit beside the Deflated Sharpe
promotion gate (L2 validation engine; design doc ``docs/research/166``).

Why this module exists
----------------------
A short backtest tried many times is *guaranteed* to produce a spurious
"winner": with enough trials the expected MAXIMUM Sharpe arising from pure
noise climbs above any target, so the best-looking configuration is an
artifact of multiple testing rather than genuine edge. Two complementary
López de Prado defences guard against that here:

* **MinBTL** answers, *ex ante*: given ``N`` independent strategy trials and a
  target annualised Sharpe, what is the minimum backtest length (in years, by
  default) such that the expected max Sharpe from ``N`` noise strategies stays
  below the target? A backtest shorter than MinBTL cannot distinguish skill
  from luck at that trial count and must be rejected.

* **PBO** answers, *ex post*: given the in-/out-of-sample performance of every
  configuration across a family of symmetric cross-validation splits, what is
  the probability that the configuration that looked best IN-SAMPLE ranks below
  the median OUT-OF-SAMPLE? A high PBO means the selection procedure is
  overfitting.

Equations (public — implemented directly from the papers)
---------------------------------------------------------
MinBTL — Bailey, Borwein, López de Prado & Zhu, *"Pseudo-Mathematics and
Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample
Performance"* (Notices of the AMS, 2014), eq. for the minimum backtest length.
Under IID-normal returns with true Sharpe 0, the estimated ANNUALISED Sharpe
has standard deviation ``1/sqrt(y)`` where ``y`` is the number of years of data
(this is frequency-independent). The expected maximum annualised Sharpe over
``N`` independent trials is

    E[max SR_N] ≈ (1/sqrt(y)) · Z_N ,   with the expected-max-of-N-Gaussians
    coefficient   Z_N = (1 - γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)) ,

γ = Euler–Mascheroni, Φ⁻¹ the standard-normal inverse CDF. ``Z_N`` is exactly
the benchmark computed by
:func:`strategy_promotion_gate.estimate_deflated_sharpe_benchmark` with a
cross-trial Sharpe dispersion of 1.0 — so this module REUSES that function for
consistency with the Deflated-Sharpe gate. Setting the target equal to the
expected max and solving for ``y`` gives

    MinBTL (years) = ( Z_N / target_annual_sharpe )² .

PBO / CSCV — Bailey, Borwein, López de Prado & Zhu, *"The Probability of
Backtest Overfitting"* (Journal of Computational Finance, 2016; SSRN 2326253).
Combinatorially-Symmetric Cross-Validation splits the T×N performance matrix
into ``S`` sub-matrices, forms every C(S, S/2) in-sample/out-of-sample split,
and for each split takes the IS-optimal configuration ``n*`` and its relative
rank ``ω`` among all configurations OUT-OF-SAMPLE. The logit ``λ = ln(ω/(1-ω))``
is negative exactly when ``n*`` lands below the OOS median, and

    PBO = fraction of splits with λ < 0
        = P( IS-best configuration ranks below the OOS median ) .

Sourcing (Rule O.1)
-------------------
mlfinlab (Hudson & Thames) is the canonical reference implementation of both
gates but is LICENSE-GATED / commercial (a paid business/enterprise agreement
is required and the backtest-overfitting modules are not freely pip-installable)
— a tier-1 installability reject, so NOT vendored. ``esvhd/pypbo`` is a real
MIT-style PBO impl but is pandas/matplotlib-heavy with a plotting-oriented,
DataFrame-shaped API that does not match this repo's plain-matrix seam — its
CSCV *algorithm* is adapted here, its package is not vendored. The CRAN ``pbo``
package is R (wrong language). The equations above are PUBLIC, so both gates are
implemented directly from the papers and cross-checked against the in-repo
Deflated-Sharpe machinery.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from nse_algo_trader.paper_trading.strategy_promotion_gate import (
    estimate_deflated_sharpe_benchmark,
)

# ---------------------------------------------------------------------------
# Minimum Backtest Length (MinBTL)
# ---------------------------------------------------------------------------


def expected_maximum_sharpe_coefficient(number_of_trials: int) -> float:
    """The expected maximum of ``number_of_trials`` independent standard
    Gaussians — the coefficient ``Z_N`` in the MinBTL equation.

    This is exactly ``estimate_deflated_sharpe_benchmark`` evaluated with a
    unit cross-trial Sharpe dispersion, so MinBTL stays numerically consistent
    with the Deflated-Sharpe promotion gate. Returns ``0.0`` for
    ``number_of_trials < 2`` (no maximum-over-trials inflation exists for a
    single trial), matching that function's degenerate convention.
    """
    return estimate_deflated_sharpe_benchmark(
        sharpe_std_across_trials=1.0, number_of_trials=number_of_trials
    )


def minimum_backtest_length(
    number_of_trials: int,
    target_annual_sharpe: float,
    *,
    observations_per_year: float = 1.0,
) -> float:
    """Minimum backtest length so the expected max Sharpe from ``N`` noise
    strategies stays below ``target_annual_sharpe``.

    Units
    -----
    Returns a length in ``years × observations_per_year``. With the default
    ``observations_per_year=1.0`` the result is in **years** (the natural unit
    of the equation, since the annualised-Sharpe standard error is ``1/sqrt(y)``
    with ``y`` in years). Pass e.g. ``observations_per_year=252`` to get the
    minimum number of daily observations, or ``52`` for weekly, etc.

    Formula
    -------
    ``MinBTL = (Z_N / target)² · observations_per_year`` where ``Z_N`` is
    :func:`expected_maximum_sharpe_coefficient`.

    Degenerate conventions
    ----------------------
    * ``number_of_trials < 2`` → ``0.0``: with no multiple testing there is no
      maximum-over-trials inflation, so this defence imposes no minimum length.
    * ``target_annual_sharpe <= 0`` → ``math.inf``: since ``E[max SR] > 0`` for
      ``N >= 2``, no finite backtest can drive it below a non-positive target.
    * ``observations_per_year <= 0`` → ``ValueError`` (a length scale must be
      strictly positive).
    """
    if observations_per_year <= 0.0:
        raise ValueError("observations_per_year must be > 0")
    if number_of_trials < 2:
        return 0.0
    coefficient = expected_maximum_sharpe_coefficient(number_of_trials)
    if coefficient <= 0.0:
        # Only possible via floating-point edge cases; no inflation to defend.
        return 0.0
    if target_annual_sharpe <= 0.0:
        return math.inf
    return (coefficient / target_annual_sharpe) ** 2 * observations_per_year


def backtest_length_is_sufficient(
    observation_count: int,
    number_of_trials: int,
    target_annual_sharpe: float,
    *,
    observations_per_year: float = 252.0,
) -> tuple[bool, float]:
    """Gate verdict: is ``observation_count`` observations enough for
    ``number_of_trials`` trials at ``target_annual_sharpe``?

    Returns ``(is_sufficient, margin)`` where ``margin = observation_count -
    MinBTL`` in observations (positive ⇒ sufficient, the size of the surplus;
    negative ⇒ short by that many observations). The required MinBTL is computed
    in the SAME observation units via ``observations_per_year`` (default 252
    trading days/year). The verdict flips exactly at ``observation_count ==
    MinBTL`` (``>=`` is sufficient).

    When ``target_annual_sharpe <= 0`` the required length is infinite, so the
    verdict is ``False`` with ``margin = -math.inf``.
    """
    required_observations = minimum_backtest_length(
        number_of_trials,
        target_annual_sharpe,
        observations_per_year=observations_per_year,
    )
    if math.isinf(required_observations):
        return (False, -math.inf)
    margin = observation_count - required_observations
    return (observation_count >= required_observations, margin)


# ---------------------------------------------------------------------------
# Probability of Backtest Overfitting (PBO) via CSCV
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestOverfittingResult:
    """Outcome of a PBO estimate.

    * ``probability_of_backtest_overfitting`` — the PBO statistic in ``[0, 1]``:
      the fraction of splits where the IS-best configuration ranks below the OOS
      median. ``0.5`` ≈ selection is pure luck; ``→ 0`` ≈ IS-best generalises;
      ``→ 1`` ≈ severe overfitting.
    * ``is_estimable`` — ``False`` when the input is degenerate (no splits, or
      fewer than two configurations to rank); in that case the probability is
      set to the conservative ``1.0`` (assume overfit when it cannot be ruled
      out), mirroring the promotion gate's reject-on-thin-evidence stance.
    * ``per_split_logits`` — ``λ = ln(ω/(1-ω))`` per split; its distribution is
      the diagnostic the PBO summarises.
    * ``split_count`` / ``configuration_count`` — the shape actually evaluated.
    """

    probability_of_backtest_overfitting: float
    is_estimable: bool
    per_split_logits: tuple[float, ...]
    split_count: int
    configuration_count: int


def _relative_rank_of_value(value: float, population: list[float]) -> float:
    """Relative rank ``ω ∈ (0, 1)`` of ``value`` within ``population`` using a
    tie-averaged (fractional) rank, normalised by ``N + 1`` so it never hits
    the ``{0, 1}`` endpoints that would blow up the logit.

    ``ω < 0.5`` ⇔ below the population median; ``ω > 0.5`` ⇔ above.
    """
    n = len(population)
    strictly_less = sum(1 for v in population if v < value)
    equal = sum(1 for v in population if v == value)  # includes `value` itself
    # Mid-rank of the tied block, in 1..N, then normalise by N+1.
    average_rank = strictly_less + (equal + 1) / 2.0
    return average_rank / (n + 1)


def probability_of_backtest_overfitting(
    in_sample_performance_matrix: list[list[float]],
    out_of_sample_performance_matrix: list[list[float]],
) -> BacktestOverfittingResult:
    """PBO from paired IS/OOS performance matrices (CSCV, Bailey et al. 2016).

    Both arguments are ``splits × configurations`` matrices: row ``c`` gives
    every configuration's performance (e.g. Sharpe) on the in-sample /
    out-of-sample half of CSCV split ``c``. For each split it takes the
    IS-argmax configuration ``n*`` and its OOS relative rank ``ω``, forms the
    logit ``λ = ln(ω/(1-ω))``, and returns

        PBO = mean over splits of 1[λ < 0]

    — the probability the IS-best configuration underperforms the OOS median.

    Use :func:`combinatorially_symmetric_cross_validation` to build the two
    matrices from a raw ``T × configurations`` performance matrix.

    Robustness
    ----------
    Empty input, mismatched shapes, or fewer than two configurations are
    degenerate: the result is ``is_estimable=False`` with the conservative
    ``probability=1.0``. Ties in OOS ranks are handled by mid-rank averaging.
    """
    if len(in_sample_performance_matrix) != len(out_of_sample_performance_matrix):
        raise ValueError("IS and OOS matrices must have the same number of splits")

    logits: list[float] = []
    below_median_count = 0
    configuration_count = 0

    for is_row, oos_row in zip(
        in_sample_performance_matrix, out_of_sample_performance_matrix, strict=True
    ):
        if len(is_row) != len(oos_row):
            raise ValueError("each split's IS and OOS rows must have equal width")
        if len(is_row) < 2:
            # Cannot rank a single (or zero) configuration — skip this split.
            continue
        configuration_count = len(is_row)
        # IS-optimal configuration (first argmax; ties broken deterministically).
        best_in_sample_index = max(range(len(is_row)), key=lambda i: is_row[i])
        best_out_of_sample_value = oos_row[best_in_sample_index]
        relative_rank = _relative_rank_of_value(best_out_of_sample_value, oos_row)
        # Guard the logit against the theoretical endpoints.
        relative_rank = min(max(relative_rank, 1e-12), 1.0 - 1e-12)
        logit = math.log(relative_rank / (1.0 - relative_rank))
        logits.append(logit)
        if logit < 0.0:
            below_median_count += 1

    if not logits:
        return BacktestOverfittingResult(
            probability_of_backtest_overfitting=1.0,
            is_estimable=False,
            per_split_logits=(),
            split_count=0,
            configuration_count=configuration_count,
        )

    return BacktestOverfittingResult(
        probability_of_backtest_overfitting=below_median_count / len(logits),
        is_estimable=True,
        per_split_logits=tuple(logits),
        split_count=len(logits),
        configuration_count=configuration_count,
    )


def _sharpe_of_column(rows: list[list[float]], column_index: int) -> float:
    """Sharpe of one configuration's per-period performance over the given
    rows (period-observation performance matrix ``T × configurations``)."""
    series = [row[column_index] for row in rows]
    if len(series) < 2:
        return 0.0
    mean_value = sum(series) / len(series)
    variance = sum((v - mean_value) ** 2 for v in series) / (len(series) - 1)
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0.0:
        return 0.0
    return mean_value / standard_deviation


def combinatorially_symmetric_cross_validation(
    performance_matrix: list[list[float]],
    split_count: int = 16,
) -> tuple[list[list[float]], list[list[float]]]:
    """Build the paired IS/OOS performance matrices for
    :func:`probability_of_backtest_overfitting` from a raw ``T × configurations``
    per-period performance matrix (row = time period, column = configuration).

    Partitions the ``T`` rows into ``split_count`` (must be even) contiguous
    sub-matrices, then for every C(split_count, split_count/2) way of choosing
    half as IN-SAMPLE (complement = OUT-OF-SAMPLE) computes each configuration's
    Sharpe on both halves. Returns ``(is_matrix, oos_matrix)``, each of shape
    ``n_combinations × configurations``.

    Raises ``ValueError`` on an odd ``split_count`` (< 2), too few rows, or a
    ragged matrix.
    """
    if split_count < 2 or split_count % 2 != 0:
        raise ValueError("split_count must be an even integer >= 2")
    if not performance_matrix:
        raise ValueError("performance_matrix is empty")
    configuration_count = len(performance_matrix[0])
    if any(len(row) != configuration_count for row in performance_matrix):
        raise ValueError("performance_matrix is ragged")
    if len(performance_matrix) < split_count:
        raise ValueError("need at least split_count rows")

    # Contiguous partition of the T rows into split_count sub-matrices.
    base_size, remainder = divmod(len(performance_matrix), split_count)
    sub_matrices: list[list[list[float]]] = []
    cursor = 0
    for block_index in range(split_count):
        this_size = base_size + (1 if block_index < remainder else 0)
        sub_matrices.append(performance_matrix[cursor : cursor + this_size])
        cursor += this_size

    half = split_count // 2
    is_matrix: list[list[float]] = []
    oos_matrix: list[list[float]] = []
    all_blocks = set(range(split_count))
    for in_sample_blocks in itertools.combinations(range(split_count), half):
        out_of_sample_blocks = sorted(all_blocks - set(in_sample_blocks))
        in_sample_rows = [
            row for block in in_sample_blocks for row in sub_matrices[block]
        ]
        out_of_sample_rows = [
            row for block in out_of_sample_blocks for row in sub_matrices[block]
        ]
        is_matrix.append(
            [_sharpe_of_column(in_sample_rows, c) for c in range(configuration_count)]
        )
        oos_matrix.append(
            [_sharpe_of_column(out_of_sample_rows, c) for c in range(configuration_count)]
        )
    return is_matrix, oos_matrix


def estimate_probability_of_backtest_overfitting_via_cscv(
    performance_matrix: list[list[float]],
    split_count: int = 16,
) -> BacktestOverfittingResult:
    """End-to-end PBO from a raw ``T × configurations`` per-period performance
    matrix: run CSCV to build the IS/OOS Sharpe matrices, then estimate PBO.

    Thin convenience wrapper composing
    :func:`combinatorially_symmetric_cross_validation` and
    :func:`probability_of_backtest_overfitting`.
    """
    is_matrix, oos_matrix = combinatorially_symmetric_cross_validation(
        performance_matrix, split_count
    )
    return probability_of_backtest_overfitting(is_matrix, oos_matrix)
