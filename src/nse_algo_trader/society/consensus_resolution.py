"""Consensus / conflict-resolution (Trunk VI; research/136).

The society of desks (council roles, debate roles) each hold an opinion; this organ produces a
TRACK-RECORD-WEIGHTED consensus, measures the CONFLICT (disagreement), and RESOLVES: low conflict →
consensus reached; high conflict → deadlock broken toward the highest-track-record desk (the
most-proven voice decides a tie). Sourcing (research/136): references Dawid-Skene / WISE but built
bespoke — we already have per-desk weights, so no EM/confusion-matrix estimation is needed. PURE.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentOpinion:
    agent: str
    probability: float   # 0..1 — this desk's forecast for the proposition
    weight: float        # track-record weight (≥0)


@dataclass(frozen=True)
class ConsensusVerdict:
    consensus_probability: float   # weight-weighted mean opinion
    conflict: float                # weighted spread of opinions (disagreement)
    is_consensus: bool             # conflict below the threshold
    decisive_agent: str | None     # the highest-weight desk (breaks a deadlock)
    participant_count: int
    resolution: str = ""
    summary: str = ""


def resolve_consensus(
    opinions: list, conflict_threshold: float = 0.20
) -> ConsensusVerdict:
    """Aggregate the desks' opinions into a track-record-weighted consensus + resolve conflict.
    `opinions` = AgentOpinion list."""
    usable = [o for o in opinions if o.weight > 0]
    if not usable:
        return ConsensusVerdict(0.0, 0.0, False, None, 0, "no weighted desks",
                                "no desks with a track record to form consensus")
    total_w = sum(o.weight for o in usable)
    consensus = sum(o.probability * o.weight for o in usable) / total_w
    variance = sum(o.weight * (o.probability - consensus) ** 2 for o in usable) / total_w
    conflict = variance ** 0.5
    decisive = max(usable, key=lambda o: o.weight).agent
    is_consensus = conflict <= conflict_threshold

    if is_consensus:
        resolution = f"consensus reached at {consensus:.0%} (conflict {conflict:.2f})"
    else:
        resolution = (f"deadlock (conflict {conflict:.2f}) — defer to {decisive} "
                      f"(highest track record)")
    summary = (
        f"{len(usable)} desks · consensus {consensus:.0%} · conflict {conflict:.2f} · "
        + ("CONSENSUS" if is_consensus else f"DEADLOCK → {decisive}")
    )
    return ConsensusVerdict(
        consensus_probability=consensus, conflict=conflict, is_consensus=is_consensus,
        decisive_agent=decisive, participant_count=len(usable), resolution=resolution,
        summary=summary,
    )
