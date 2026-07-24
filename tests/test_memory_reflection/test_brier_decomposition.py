"""Murphy Brier decomposition — hermetic + reconstruction identity."""
from nse_algo_trader.memory_reflection.brier_decomposition import (
    murphy_brier_decomposition, reliability_diagnosis,
)


def _brier(preds, outs):
    return sum((p - o) ** 2 for p, o in zip(preds, outs)) / len(preds)


def test_reconstruction_approximates_brier():
    # varied predictions/outcomes -> REL - RES + UNC ~= direct Brier
    preds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95] * 4
    outs = [0, 0, 0, 1, 0, 1, 1, 1, 1, 1] * 4
    d = murphy_brier_decomposition(preds, outs, bin_count=10)
    assert abs(d.brier_reconstructed - _brier(preds, outs)) < 0.03  # binning residual


def test_no_edge_when_outcomes_independent_of_forecast():
    # forecasts vary but win rate is ~constant -> resolution ~ 0 -> "no edge"
    preds = [0.2, 0.5, 0.8] * 20
    outs = ([1, 0] * 30)  # 50% regardless of forecast
    d = murphy_brier_decomposition(preds, outs, bin_count=3)
    assert d.resolution < 0.01
    assert "no discriminating edge" in reliability_diagnosis(d)


def test_biased_but_discriminating_reads_reliability_driven():
    # forecasts discriminate (low preds lose, high win) but are over-confident
    preds = [0.9] * 20 + [0.9] * 20  # all predict 90%
    outs = [1] * 20 + [0] * 20       # half win -> biased, but no spread in preds
    # give spread so resolution>0:
    preds = [0.95] * 20 + [0.55] * 20
    outs = [1] * 14 + [0] * 6 + [1] * 4 + [0] * 16  # high-pred wins more (resolves)
    d = murphy_brier_decomposition(preds, outs, bin_count=2)
    assert d.resolution > 0
    diag = reliability_diagnosis(d)
    assert "recalibratable" in diag or "well-resolved" in diag


def test_below_two_samples_returns_none():
    assert murphy_brier_decomposition([0.5], [1]) is None
