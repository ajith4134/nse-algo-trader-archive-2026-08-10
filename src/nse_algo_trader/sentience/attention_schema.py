"""Attention schema (Trunk VIII; research/128) — a model of the system's OWN attention.

Graziano's Attention Schema Theory: modelling one's own attention — what is being attended to and how
attention is distributed — is the substrate of awareness. Here it is a concrete introspective read
over the Global Workspace: what the workspace is currently attending to (the dominant broadcast) and
the distribution of attention across signal kinds, given the current context. Sourcing (research/125):
BUILD — zero linked code exists anywhere for AST, even the 2025 paper. PURE (no I/O).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttentionSchema:
    attending_to: str | None       # the dominant source the workspace is attending to (None = diffuse)
    attending_kind: str | None     # its kind (safety/risk/opportunity/info)
    attention_by_kind: dict = field(default_factory=dict)  # kind -> count of contributions in play
    context_regime: str = "unknown"
    is_defensive: bool = False
    summary: str = ""


def build_attention_schema(broadcast, attention_context, contributions) -> AttentionSchema:
    """Build the model of the workspace's own attention from the current broadcast, the attention
    context, and the contributions in play."""
    by_kind = dict(Counter(c.kind for c in contributions))
    attending_to = getattr(broadcast, "winner_source", None) if broadcast is not None else None
    attending_kind = getattr(broadcast, "kind", None) if broadcast is not None else None
    regime = getattr(attention_context, "market_regime", "unknown") if attention_context else "unknown"
    defensive = bool(getattr(attention_context, "is_defensive", False)) if attention_context else False

    if attending_to is None:
        focus = "attention is diffuse — no dominant focus this cycle"
    else:
        focus = f"attending to {attending_to} ({attending_kind})"
    dist = ", ".join(f"{k}:{v}" for k, v in by_kind.items()) or "—"
    summary = (
        f"{focus}; attention distribution [{dist}]; context regime={regime}"
        + (", DEFENSIVE arousal" if defensive else "")
    )
    return AttentionSchema(
        attending_to=attending_to, attending_kind=attending_kind,
        attention_by_kind=by_kind, context_regime=regime, is_defensive=defensive,
        summary=summary,
    )
