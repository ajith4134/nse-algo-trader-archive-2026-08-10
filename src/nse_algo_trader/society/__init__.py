"""Trunk VI · SOCIETY — multi-agent / communication (docs/research/32-36).

The bot runs a SOCIETY of specialist desks (the prediction council roles, the bull/bear/risk debate).
It already has the council, prediction-market weighting, and the debate protocol. Here:
- CONSENSUS / conflict-resolution — a track-record-weighted consensus over the desks + a conflict
  measure + deadlock resolution toward the most-proven desk.
- MULTI-AGENT MEMORY GOVERNANCE — a reputation policy over which desks may contribute to the shared
  belief space (trusted vs quarantined).
"""

from __future__ import annotations

from nse_algo_trader.society.consensus_resolution import (
    AgentOpinion,
    ConsensusVerdict,
    resolve_consensus,
)
from nse_algo_trader.society.multi_agent_governance import (
    AgentStanding,
    GovernanceReport,
    govern_agents,
)

__all__ = [
    "AgentOpinion",
    "AgentStanding",
    "ConsensusVerdict",
    "GovernanceReport",
    "govern_agents",
    "resolve_consensus",
]
