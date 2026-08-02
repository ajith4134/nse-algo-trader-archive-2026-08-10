"""Selective + state-dependent attention for the Global Workspace (Trunk VIII; research/126).

The workspace has limited capacity — not every faculty signal deserves equal entry to the
competition. Two attention mechanisms modulate a contribution's salience BEFORE it competes:
  - SELECTIVE attention: weight by current CONTEXT relevance (market regime) — opportunity signals
    get more attention in a TRENDING regime, less in INDECISIVE; safety is always attended.
  - STATE-DEPENDENT attention: modulate by the system's INTERNAL state (defensive arousal) — after a
    loss streak / in drawdown / with the off-switch near, boost SAFETY & RISK attention and damp
    OPPORTUNITY (attend to danger when hurting).
Sourcing (research/125): BUILD — every OSS candidate was dead/immature; no cognitive-arch package
ships attention codelets. PURE (no I/O); reshapes the contributions the workspace then competes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from nse_algo_trader.sentience.global_workspace import WorkspaceContribution


@dataclass(frozen=True)
class AttentionContext:
    """The current attention-shaping context: the external regime + the system's internal state."""

    market_regime: str = "unknown"   # trending / range / indecisive / unknown
    consecutive_losses: int = 0
    drawdown_fraction: float = 0.0   # ≥0; how far below the high-water the account is
    off_switch_engaged: bool = False

    @property
    def is_defensive(self) -> bool:
        """True when the system is 'hurting' — attention should tilt to safety/risk over opportunity."""
        return (
            self.off_switch_engaged
            or self.consecutive_losses >= 2
            or self.drawdown_fraction >= 0.02
        )


def attention_weight(
    contribution: WorkspaceContribution, context: AttentionContext
) -> float:
    """A salience multiplier (~0.3..1.5) for one contribution given the attention context. Safety is
    always fully attended (more when defensive); risk is boosted when hurting; opportunity follows the
    regime and is damped under defensive arousal; info is background."""
    kind = contribution.kind
    if kind == "safety":
        weight = 1.2 if context.is_defensive else 1.0
    elif kind == "risk":
        weight = 1.0
        if context.is_defensive:
            weight += 0.4
        if context.drawdown_fraction >= 0.05:
            weight += 0.2
    elif kind == "opportunity":
        if context.market_regime == "trending":
            weight = 1.2
        elif context.market_regime in ("indecisive", "range"):
            weight = 0.7
        else:
            weight = 1.0
        if context.is_defensive:
            weight *= 0.6  # damp opportunity when the system is hurting
    else:  # info / background
        weight = 0.8
    return max(0.3, min(1.5, weight))


def apply_attention(
    contributions: list[WorkspaceContribution], context: AttentionContext
) -> list[WorkspaceContribution]:
    """Return the contributions with urgency & relevance re-weighted by attention (clamped to [0,1]);
    `is_critical` is preserved so a critical safety signal still wins the workspace regardless."""
    attended: list[WorkspaceContribution] = []
    for c in contributions:
        weight = attention_weight(c, context)
        attended.append(replace(
            c,
            urgency=max(0.0, min(1.0, c.urgency * weight)),
            relevance=max(0.0, min(1.0, c.relevance * weight)),
        ))
    return attended
