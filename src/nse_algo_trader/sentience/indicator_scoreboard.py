"""Indicator scoreboard (Trunk VIII; research/131) — the workspace's own dashboard of its specialists.

Scores each faculty ("indicator") by its CURRENT contribution salience and how often it has been the
dominant broadcast, ranked — so the workspace can see which specialists actually drive it. Sourcing
(research/125): `river` rolling-metric evaluated + rejected as a heavy streaming-ML framework for what
is a rolling count/salience; BUILD the small primitive (referencing river's rolling idea + Elo). PURE.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from nse_algo_trader.sentience.global_workspace import salience_score


@dataclass(frozen=True)
class IndicatorScore:
    source: str
    kind: str
    current_salience: float
    times_dominant: int  # how often this faculty won the broadcast in the recent history


@dataclass(frozen=True)
class ScoreboardReport:
    scores: tuple[IndicatorScore, ...]  # ranked by current salience desc
    leader: str | None
    summary: str = ""


def build_indicator_scoreboard(contributions, broadcast_history) -> ScoreboardReport:
    """Rank the current faculty contributions by salience, annotated with how often each has been the
    dominant broadcast in the recent history."""
    dominance = Counter(
        b.winner_source for b in broadcast_history if b is not None
    )
    scores = [
        IndicatorScore(
            source=c.source, kind=c.kind, current_salience=salience_score(c),
            times_dominant=dominance.get(c.source, 0),
        )
        for c in contributions
    ]
    scores.sort(key=lambda s: s.current_salience, reverse=True)
    leader = scores[0].source if scores else None
    summary = (
        f"{len(scores)} faculties scored; leader {leader} "
        f"({scores[0].current_salience:.2f}, dominant {scores[0].times_dominant}× recently)"
        if scores else "no faculties contributing this cycle"
    )
    return ScoreboardReport(scores=tuple(scores), leader=leader, summary=summary)
