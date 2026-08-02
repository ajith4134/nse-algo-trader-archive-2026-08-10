"""Multi-agent memory governance (Trunk VI; research/136).

Governance of the shared cognitive commons: a reputation POLICY over which desks may contribute to
the shared belief space. TRUSTED desks (reputation ≥ threshold) participate; persistently-poor desks
are QUARANTINED (excluded) so a bad voice cannot corrupt the shared consensus. Distinct from consensus
(aggregation) and from XIII misinfo-resistance (which scores mechanism-sources, not agent-desks).
Sourcing (research/136): no fitting library — bespoke reputation policy over the council's log-loss.
PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentStanding:
    agent: str
    reputation: float      # 0..1 (higher = more proven)
    is_trusted: bool
    is_quarantined: bool


@dataclass(frozen=True)
class GovernanceReport:
    standings: tuple[AgentStanding, ...] = field(default_factory=tuple)  # reputation-desc
    trusted: tuple[str, ...] = field(default_factory=tuple)
    quarantined: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


def govern_agents(
    reputations: dict, trust_threshold: float = 0.5, quarantine_threshold: float = 0.25
) -> GovernanceReport:
    """Classify each desk by reputation into the shared-belief governance policy. `reputations` =
    {agent: reputation in [0,1]}. Trusted may contribute; quarantined are excluded."""
    if not reputations:
        return GovernanceReport(summary="no desks with a reputation to govern")
    standings = []
    for agent, rep in reputations.items():
        standings.append(AgentStanding(
            agent=agent, reputation=rep,
            is_trusted=rep >= trust_threshold,
            is_quarantined=rep < quarantine_threshold,
        ))
    standings.sort(key=lambda s: s.reputation, reverse=True)
    trusted = tuple(s.agent for s in standings if s.is_trusted)
    quarantined = tuple(s.agent for s in standings if s.is_quarantined)
    summary = (
        f"{len(standings)} desks governed · {len(trusted)} trusted · {len(quarantined)} quarantined"
        + (f" (excluded: {', '.join(quarantined[:2])})" if quarantined else "")
    )
    return GovernanceReport(
        standings=tuple(standings), trusted=trusted, quarantined=quarantined, summary=summary,
    )
