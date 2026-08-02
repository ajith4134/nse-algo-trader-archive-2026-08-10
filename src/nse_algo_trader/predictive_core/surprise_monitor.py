"""Surprise / free-energy monitor (Trunk IX; research/134) — active inference.

The agent minimises SURPRISE (−log p of outcomes = variational free energy). This organ measures the
per-mechanism Bayesian surprise — the cross-entropy (in bits) between what a mechanism CONFIDENTLY
predicted and what actually happened — and flags the anomalously-surprising mechanism via a compact
Page-Hinkley change detector: a world-model that is being surprised is failing, and that is the
early-warning. Sourcing (research/133): `pymdp`/FEP libs rejected (jax-heavy for one scalar); the
surprise value is our own log-loss; Page-Hinkley VENDORED compact (Page 1954; river's BSD impl is
~100 LOC pure-Python but `river` isn't installed — this is the lightweight-piece pattern). PURE.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2


class PageHinkley:
    """Compact Page-Hinkley test for detecting an INCREASE in a stream's mean (a rising-surprise
    changepoint). Vendored-from-formula (E.S. Page 1954; equivalent to river.drift.PageHinkley's
    increase branch). `update(x)` returns True once the cumulative positive deviation crosses the
    threshold."""

    def __init__(self, delta: float = 0.005, threshold: float = 0.5, alpha: float = 0.9999) -> None:
        self._delta = delta
        self._threshold = threshold
        self._alpha = alpha
        self._n = 0
        self._mean = 0.0
        self._cumulative = 0.0
        self.change_detected = False

    def update(self, value: float) -> bool:
        self._n += 1
        self._mean += (value - self._mean) / self._n
        # cumulative sum of (deviation above the running mean, net of tolerance delta), decayed.
        self._cumulative = self._alpha * self._cumulative + (value - self._mean - self._delta)
        self._cumulative = max(0.0, self._cumulative)
        self.change_detected = self._cumulative > self._threshold
        return self.change_detected


_CLIP = 1e-6


@dataclass(frozen=True)
class SurpriseReport:
    mean_surprise_bits: float          # n-weighted mean per-mechanism surprise
    most_surprising: str | None
    most_surprising_bits: float
    spike_detected: bool               # Page-Hinkley flagged a rising-surprise mechanism
    mechanisms_scored: int
    summary: str = ""


def _cross_entropy_bits(predicted: float, actual: float) -> float:
    """Bayesian surprise of the realised win-rate `actual` under the confident prediction `predicted`
    — the binary cross-entropy in bits: −[a·log₂p + (1−a)·log₂(1−p)]."""
    p = min(1 - _CLIP, max(_CLIP, predicted))
    a = min(1.0, max(0.0, actual))
    return -(a * log2(p) + (1 - a) * log2(1 - p))


def monitor_surprise(board: list, spike_threshold: float = 0.5) -> SurpriseReport:
    """Measure per-mechanism surprise over the calibration board and flag the anomalously-surprising
    mechanism. `board` = CalibrationBoardRow-like (`.mechanism_name`, `.experiment_count`,
    `.predicted_win_rate`, `.actual_win_rate`)."""
    rows = [r for r in board if r.experiment_count > 0]
    if not rows:
        return SurpriseReport(0.0, None, 0.0, False, 0, "no predictions to measure surprise over")

    surprises = [(r.mechanism_name, _cross_entropy_bits(r.predicted_win_rate, r.actual_win_rate),
                  r.experiment_count) for r in rows]
    total_n = sum(n for _, _, n in surprises)
    mean_bits = sum(s * n for _, s, n in surprises) / total_n

    # feed the per-mechanism surprises (least→most surprising) to Page-Hinkley to flag a spike.
    detector = PageHinkley(threshold=spike_threshold)
    spike = False
    for _, s, _ in sorted(surprises, key=lambda x: x[1]):
        if detector.update(s):
            spike = True
    most_name, most_bits, _ = max(surprises, key=lambda x: x[1])

    summary = (
        f"mean surprise {mean_bits:.2f} bits over {len(rows)} mechanisms; most-surprising "
        f"{most_name} ({most_bits:.2f} bits)"
        + (" — SPIKE: the world-model is being surprised (degrading)" if spike else
           " — no surprise spike")
    )
    return SurpriseReport(
        mean_surprise_bits=mean_bits, most_surprising=most_name, most_surprising_bits=most_bits,
        spike_detected=spike, mechanisms_scored=len(rows), summary=summary,
    )
