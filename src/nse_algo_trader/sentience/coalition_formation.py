"""Coalition formation for the Global Workspace (Trunk VIII; research/127).

Real Global-Workspace ignition is a COALITION of co-active signals crossing threshold together, not a
lone winner. When several near-salience contributions of the SAME kind are co-active they corroborate
— their combined salience is amplified, so a corroborated coalition (e.g. goal-integrity + red-team +
wireheading all firing) ignites more readily than any single member. Sourcing (research/125): BUILD,
referencing the AIOps alert-correlation pattern (group co-occurring alerts). PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Coalition:
    """A group of co-active contributions within ε of the top. `combined_salience` amplifies the base
    when ≥2 members share the winner's kind (corroboration)."""

    members: tuple[str, ...]
    kind: str
    base_salience: float
    combined_salience: float
    corroborating_count: int = 1  # members sharing the winner's kind (incl. the winner)
    runner_up: str | None = None

    @property
    def is_corroborated(self) -> bool:
        return self.corroborating_count >= 2


def form_coalition(
    scored: list[tuple],
    epsilon: float = 0.10,
    per_member_bonus: float = 0.05,
    cap: float = 0.20,
) -> Coalition | None:
    """Form a coalition from `scored` = [(contribution, salience)] (any order). Members are the
    contributions within `epsilon` of the top salience; the coalition is amplified by
    `per_member_bonus` per extra SAME-KIND member (capped, clamped ≤1.0). None if empty."""
    if not scored:
        return None
    ordered = sorted(scored, key=lambda cs: cs[1], reverse=True)
    top_contribution, base_salience = ordered[0]
    winner_kind = top_contribution.kind
    members = [c for c, s in ordered if base_salience - s <= epsilon]
    corroborating = sum(1 for c in members if c.kind == winner_kind)
    amplification = min(cap, per_member_bonus * max(0, corroborating - 1))
    combined = min(1.0, base_salience + amplification)
    return Coalition(
        members=tuple(c.source for c in members),
        kind=winner_kind,
        base_salience=base_salience,
        combined_salience=combined,
        corroborating_count=corroborating,
        runner_up=ordered[1][0].source if len(ordered) > 1 else None,
    )
