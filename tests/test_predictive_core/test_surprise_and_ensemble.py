"""Hermetic test for Trunk IX predictive-core (research/134): the surprise monitor scores
per-mechanism cross-entropy + Page-Hinkley spike; the ensemble world-model combines forecasts +
measures disagreement. Pure, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.predictive_core.ensemble_world_model import build_ensemble_forecast
from nse_algo_trader.predictive_core.surprise_monitor import PageHinkley, monitor_surprise


@dataclass
class _Row:
    mechanism_name: str
    experiment_count: int
    predicted_win_rate: float
    actual_win_rate: float


def test_page_hinkley_detects_a_rising_step():
    ph = PageHinkley(delta=0.001, threshold=0.5)
    detected = False
    for v in [0.1] * 20 + [5.0] * 10:  # a clear upward step
        detected = ph.update(v) or detected
    assert detected


def test_page_hinkley_stable_stream_no_detection():
    ph = PageHinkley()
    assert not any(ph.update(0.2) for _ in range(50))


def test_confidently_wrong_mechanism_is_most_surprising():
    board = [_Row("wrong", 40, 0.90, 0.20), _Row("ok", 40, 0.55, 0.55)]
    rep = monitor_surprise(board)
    assert rep.most_surprising == "wrong"
    assert rep.most_surprising_bits > 1.0  # high surprise in bits


def test_calibrated_board_low_surprise():
    board = [_Row("a", 40, 0.55, 0.55), _Row("b", 40, 0.50, 0.50)]
    rep = monitor_surprise(board)
    assert rep.mean_surprise_bits < 1.5 and not rep.spike_detected


def test_empty_board_surprise_handled():
    rep = monitor_surprise([])
    assert rep.mechanisms_scored == 0 and not rep.spike_detected


def test_ensemble_weighted_mean_and_disagreement():
    board = [_Row("a", 80, 0.70, 0.0), _Row("b", 20, 0.30, 0.0)]  # n-weighted toward 0.70
    ef = build_ensemble_forecast(board)
    assert abs(ef.ensemble_prediction - (0.70 * 80 + 0.30 * 20) / 100) < 1e-9
    assert ef.member_count == 2 and ef.disagreement > 0


def test_ensemble_high_disagreement_flagged():
    board = [_Row("a", 50, 0.85, 0.0), _Row("b", 50, 0.15, 0.0)]  # wide split
    ef = build_ensemble_forecast(board)
    assert ef.high_disagreement


def test_ensemble_agreement_not_flagged():
    board = [_Row("a", 50, 0.55, 0.0), _Row("b", 50, 0.57, 0.0)]
    ef = build_ensemble_forecast(board)
    assert not ef.high_disagreement


def test_ensemble_empty_handled():
    ef = build_ensemble_forecast([])
    assert ef.member_count == 0 and not ef.high_disagreement
