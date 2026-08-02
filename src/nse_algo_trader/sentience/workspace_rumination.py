"""Workspace replay / rumination (Trunk VIII; research/129).

Like hippocampal replay / rumination, the workspace revisits its recent broadcast history: if the
SAME concern has dominated across many recent cycles, the mind is "ruminating" on a persistent,
unresolved concern — distinct from a one-off spike. Read-only diagnostic over the service's bounded
history of ignited broadcasts. Sourcing (research/125): `cpprb` PrioritizedReplayBuffer evaluated +
rejected (a C++/numpy RL batch buffer — wrong shape for replaying a few broadcast objects); BUILD a
Counter over a bounded history, referencing the experience-replay pattern. PURE (no I/O).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class RuminationReport:
    dominant_recurring: str | None
    dominant_kind: str | None
    recurrence_count: int
    recurrence_fraction: float
    distinct_concerns: int
    is_ruminating: bool
    summary: str = ""


def ruminate(
    broadcasts: list,
    min_history: int = 4,
    dominance_fraction: float = 0.6,
) -> RuminationReport:
    """Replay recent IGNITED broadcasts and detect rumination — one concern dominating the recent
    history. `broadcasts` is the bounded history (each has `.winner_source` / `.kind`)."""
    considered = [b for b in broadcasts if b is not None]
    total = len(considered)
    if total == 0:
        return RuminationReport(None, None, 0, 0.0, 0, False,
                                "no ignited broadcasts yet — nothing to ruminate on")
    by_source = Counter(b.winner_source for b in considered)
    dominant_source, count = by_source.most_common(1)[0]
    fraction = count / total
    dominant_kind = next(
        (b.kind for b in considered if b.winner_source == dominant_source), None
    )
    is_ruminating = total >= min_history and fraction >= dominance_fraction
    summary = (
        f"{'RUMINATING on ' if is_ruminating else 'recent focus '}{dominant_source} "
        f"({dominant_kind}) — {count}/{total} of recent broadcasts ({fraction:.0%}); "
        f"{len(by_source)} distinct concern(s)"
        + (" — a persistent, unresolved concern" if is_ruminating else "")
    )
    return RuminationReport(
        dominant_recurring=dominant_source, dominant_kind=dominant_kind,
        recurrence_count=count, recurrence_fraction=fraction,
        distinct_concerns=len(by_source), is_ruminating=is_ruminating, summary=summary,
    )
