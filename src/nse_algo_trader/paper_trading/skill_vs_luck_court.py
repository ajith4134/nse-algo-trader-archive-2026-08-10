"""Skill-vs-Luck Court (Layer 7.5 slice 2; research/106) — the verdict pipeline over the control
arms.

It combines the two control-arm readings into one judgment:
  * DIRECTIONAL skill — does the real champion arm beat the RANDOM-CONTROL baseline (slice 1)?
    (Is the entry-timing/direction edge skill, not luck?)
  * REJECTION skill — did the gate refuse the WORSE trades (the SHADOW-REJECTED arm, slice 2)?
    (Is the gate's vetoing skillful, or is it over-rejecting winners?)
Then it states the SKILL DIAGONAL — what learning should TRUST: taken-and-won + rejected-and-
would-lose (the bot was right to act / right to refuse); distrust the off-diagonal. PURE (no I/O);
consumes the slice-1 `ControlArmComparison` + the slice-2 `ShadowRejectedAnalysis`.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.paper_trading.control_arm_comparison import ControlArmComparison
from nse_algo_trader.paper_trading.shadow_rejected_arm import ShadowRejectedAnalysis

_SKILL_DIAGONAL_NOTE = (
    "Train on the SKILL DIAGONAL: taken-and-won (right to act) + rejected-and-would-lose (right to "
    "refuse). Distrust the off-diagonal: taken-and-lost + rejected-and-would-win."
)


@dataclass(frozen=True)
class SkillVsLuckVerdict:
    """The court's combined judgment over the control arms."""

    directional_skill: bool
    directional_detail: str
    rejection_skill: bool | None  # None when nothing is vetoed yet
    rejection_detail: str
    overall_verdict: str
    skill_diagonal_note: str = _SKILL_DIAGONAL_NOTE


def convene_skill_vs_luck_court(
    control_arm_comparison: ControlArmComparison,
    shadow_rejected_analysis: ShadowRejectedAnalysis,
) -> SkillVsLuckVerdict:
    """Combine the RANDOM-CONTROL edge verdict and the SHADOW-REJECTED verdict into one judgment.
    Overall = 'skill' only when directional skill holds AND the gate is not over-rejecting."""
    directional = control_arm_comparison.has_edge
    rejection = shadow_rejected_analysis.rejection_adds_skill

    if not directional:
        overall = (
            "NO demonstrated skill — the real arm does not beat the random-control baseline; "
            "treat the P&L as luck until it clears the control"
        )
    elif rejection is False:
        overall = (
            "SKILL in direction, but the gate is OVER-REJECTING (refused trades would have done "
            "better than taken) — the edge is real yet the veto is costing winners"
        )
    else:  # directional skill, and rejection is helpful or not-yet-judged
        gate_clause = (
            "and the gate refuses the worse trades" if rejection
            else "(gate rejection not yet judged — nothing vetoed)"
        )
        overall = f"SKILL — the real arm beats random-control {gate_clause}"

    return SkillVsLuckVerdict(
        directional_skill=directional,
        directional_detail=control_arm_comparison.verdict,
        rejection_skill=rejection,
        rejection_detail=shadow_rejected_analysis.detail,
        overall_verdict=overall,
    )
