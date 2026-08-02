"""Hermetic test for cross-modal binding (Trunk VIII; research/130): corroborating modalities bind to
a higher combined confidence than any single one (Stouffer); a lone modality doesn't bind;
disagreeing modalities don't corroborate; extremes stay finite. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.sentience.cross_modal_binding import ModalitySignal, bind_percept


def test_two_corroborating_modalities_raise_confidence():
    sig = [ModalitySignal("memory", 0.7, True), ModalitySignal("safety", 0.7, True)]
    bp = bind_percept(sig, "elevated risk")
    assert bp.is_bound and bp.modality_count == 2
    assert bp.bound_confidence > 0.7  # corroboration raises confidence above the single-modality 0.7


def test_single_modality_does_not_bind():
    bp = bind_percept([ModalitySignal("memory", 0.8, True)], "elevated risk")
    assert not bp.is_bound and bp.modality_count == 1
    assert abs(bp.bound_confidence - 0.8) < 0.02  # ~its own confidence


def test_non_supporting_signals_excluded():
    sig = [ModalitySignal("memory", 0.9, True), ModalitySignal("safety", 0.9, False)]
    bp = bind_percept(sig, "elevated risk")
    assert bp.corroborating_modalities == ("memory",) and not bp.is_bound


def test_no_support_returns_zero():
    bp = bind_percept([ModalitySignal("m", 0.9, False)], "elevated risk")
    assert bp.bound_confidence == 0.0 and not bp.is_bound


def test_more_corroboration_raises_confidence_monotonically():
    two = bind_percept([ModalitySignal("a", 0.7, True), ModalitySignal("b", 0.7, True)], "x")
    three = bind_percept(
        [ModalitySignal("a", 0.7, True), ModalitySignal("b", 0.7, True),
         ModalitySignal("c", 0.7, True)], "x")
    assert three.bound_confidence > two.bound_confidence


def test_extreme_confidences_stay_finite():
    bp = bind_percept([ModalitySignal("a", 1.0, True), ModalitySignal("b", 0.0, True)], "x")
    assert 0.0 <= bp.bound_confidence <= 1.0  # clipping keeps norm.ppf finite
