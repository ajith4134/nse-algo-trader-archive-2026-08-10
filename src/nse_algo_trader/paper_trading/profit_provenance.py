"""Profit provenance — P&L decomposition vs the control arms (Layer 7.5 slice 4; research/108).

"Where did the P&L come from?" Decomposes the real strategy's total return against the control
arms: how much is LUCK (the random-control baseline — random direction at the same triggers), how
much is DIRECTIONAL SKILL (real minus random), and what the GATE contributed (the per-trade loss it
avoided by refusing the vetoed mechanisms). Attributes profit to its real sources instead of taking
a positive P&L at face value. PURE (no I/O); consumes the slice-1 `ControlArmComparison` + the
slice-2 `ShadowRejectedAnalysis`.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.paper_trading.control_arm_comparison import ControlArmComparison
from nse_algo_trader.paper_trading.shadow_rejected_arm import ShadowRejectedAnalysis


@dataclass(frozen=True)
class ProfitProvenance:
    """The real arm's total return attributed to its sources. `gate_avoided_loss_per_trade` is the
    per-trade loss the gate refused (positive = the gate saved money); None when nothing vetoed."""

    total_real_return: float
    luck_baseline: float
    directional_skill: float
    gate_avoided_loss_per_trade: float | None
    dominant_source: str
    detail: str


def decompose_profit_provenance(
    control_arm_comparison: ControlArmComparison,
    shadow_rejected_analysis: ShadowRejectedAnalysis,
) -> ProfitProvenance:
    """Split the real arm's total return into luck (random-control) + directional skill (real −
    random), and report what the gate saved. `dominant_source` = whichever of luck / skill is
    larger in magnitude."""
    total = control_arm_comparison.real.total_return
    luck = control_arm_comparison.random_control.total_return
    directional = total - luck

    if shadow_rejected_analysis.rejection_adds_skill:
        gate_avoided = -shadow_rejected_analysis.shadow_rejected.mean_return  # loss refused
    elif shadow_rejected_analysis.rejection_adds_skill is False:
        gate_avoided = -shadow_rejected_analysis.shadow_rejected.mean_return  # negative = cost
    else:
        gate_avoided = None

    dominant_source = (
        "directional skill" if abs(directional) >= abs(luck) else "luck baseline"
    )
    gate_clause = (
        f"; gate saved {gate_avoided:+.2%}/refused-trade" if gate_avoided is not None else ""
    )
    detail = (
        f"total {total:+.1%} = luck {luck:+.1%} + directional skill {directional:+.1%}"
        f"{gate_clause}"
    )
    return ProfitProvenance(
        total_real_return=total,
        luck_baseline=luck,
        directional_skill=directional,
        gate_avoided_loss_per_trade=gate_avoided,
        dominant_source=dominant_source,
        detail=detail,
    )
