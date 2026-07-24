"""Murphy Brier-score decomposition: reliability − resolution + uncertainty.

Explains WHY a mechanism's probabilistic calibration is off — the Layer-10
"explainable memory" goal. A high **reliability** error means the forecasts are
biased but the mechanism may still discriminate (recalibratable); ~0
**resolution** means it has no edge at all (its confident and uncertain calls win
at the same rate).

Provenance: the formula is Murphy (1973), "A New Vector Partition of the
Probability Score" (J. Appl. Meteorol. 12:595-600; mirrored on the Wikipedia
"Brier score" page) — a published equation, not copied code. The identity
BS = REL - RES + UNC is exact when grouping by unique forecast values; with
continuous probabilities a small within-bin residual remains (Stephenson 2008;
Ferro & Fricker 2012), so we bin by equal frequency and keep the bin count
modest. Lives in Layer 10 (a reflection concern) so it needs no Layer-7 import.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BrierDecomposition:
    """Murphy decomposition of a cohort's Brier score. `brier_reconstructed` =
    reliability − resolution + uncertainty; it approximates the direct Brier to
    within the continuous-binning residual."""

    reliability: float  # calibration error — lower is better
    resolution: float  # discrimination — HIGHER is better
    uncertainty: float  # base-rate variance ō(1−ō) — irreducible
    brier_reconstructed: float
    sample_count: int
    bin_count: int


def _equal_frequency_bins(
    paired_sorted_by_probability: list[tuple[float, float]], bin_count: int
) -> list[list[tuple[float, float]]]:
    """Split (probability, outcome) pairs — pre-sorted by probability — into up
    to `bin_count` contiguous near-equal-size bins."""
    n = len(paired_sorted_by_probability)
    bins: list[list[tuple[float, float]]] = []
    for index in range(bin_count):
        start = (index * n) // bin_count
        stop = ((index + 1) * n) // bin_count
        if stop > start:
            bins.append(paired_sorted_by_probability[start:stop])
    return bins


def murphy_brier_decomposition(
    predicted_probabilities: list[float],
    win_outcomes: list[float],
    bin_count: int = 10,
) -> BrierDecomposition | None:
    """Decompose the Brier score of paired (predicted win-probability, actual
    win-indicator 0/1) into reliability − resolution + uncertainty using equal-
    frequency bins. Returns None below 2 samples."""
    if len(predicted_probabilities) != len(win_outcomes):
        raise ValueError("predicted_probabilities and win_outcomes length mismatch")
    total = len(predicted_probabilities)
    if total < 2:
        return None
    base_rate = sum(win_outcomes) / total
    pairs = sorted(zip(predicted_probabilities, win_outcomes), key=lambda p: p[0])
    bins = _equal_frequency_bins(pairs, bin_count)

    reliability = 0.0
    resolution = 0.0
    for one_bin in bins:
        bin_size = len(one_bin)
        mean_forecast = sum(prob for prob, _ in one_bin) / bin_size
        observed_rate = sum(outcome for _, outcome in one_bin) / bin_size
        reliability += bin_size * (mean_forecast - observed_rate) ** 2
        resolution += bin_size * (observed_rate - base_rate) ** 2
    reliability /= total
    resolution /= total
    uncertainty = base_rate * (1.0 - base_rate)
    return BrierDecomposition(
        reliability=reliability,
        resolution=resolution,
        uncertainty=uncertainty,
        brier_reconstructed=reliability - resolution + uncertainty,
        sample_count=total,
        bin_count=len(bins),
    )


# A resolution at or below this share of the uncertainty is treated as "no edge":
# the mechanism barely discriminates winners from losers.
_NO_EDGE_RESOLUTION_FRACTION = 0.05


def reliability_diagnosis(decomposition: BrierDecomposition) -> str:
    """One-line plain-English read of a decomposition for the explainable-memory
    surface: is the miscalibration a fixable bias (reliability) or a fundamental
    lack of edge (resolution ≈ 0)?"""
    if decomposition.uncertainty <= 0:
        return "degenerate (all outcomes identical)"
    if decomposition.resolution <= _NO_EDGE_RESOLUTION_FRACTION * decomposition.uncertainty:
        return "resolution ≈ 0 — no discriminating edge"
    if decomposition.reliability > decomposition.resolution:
        return "reliability-driven — biased but discriminates (recalibratable)"
    return "well-resolved — discriminates and is roughly calibrated"
