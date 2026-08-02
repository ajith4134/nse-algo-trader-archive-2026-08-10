"""Self-model (Trunk VIII; research/128) — the system's explicit model of ITSELF.

"What am I right now?" — a machine that acts autonomously should be able to report its own condition:
its calibration health, which mechanisms it trusts vs distrusts, its safety posture, and its recent
performance. Built read-only from the already-computed faculty state (memory calibration, veto/red
flags, the VII safety organs, the ledger). Sourcing (research/125): BUILD — no usable library
(`metacognition-skill` 12★ unmaintained; no cognitive-arch package ships a self-model). PURE.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SelfModel:
    calibration_reliable_share: float          # share of decisions driven by reliable+positive-edge mechs
    trusted_mechanism_count: int
    distrusted_mechanisms: tuple[str, ...]     # vetoed / influential-but-unreliable
    safety_posture: str                        # compliant / goal-drift / constitutional-breach / halted
    recent_return_fraction: float
    summary: str = ""
    distrusted_preview: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_healthy(self) -> bool:
        return (
            self.safety_posture == "compliant"
            and self.calibration_reliable_share >= 0.5
            and self.recent_return_fraction >= 0.0
        )


def build_self_model(
    calibration_reliable_share: float,
    trusted_mechanism_count: int,
    distrusted_mechanisms: tuple[str, ...],
    constitution_compliant: bool,
    off_switch_engaged: bool,
    goal_aligned: bool,
    recent_return_fraction: float,
) -> SelfModel:
    """Assemble the system's model of itself from its current faculty state."""
    if off_switch_engaged:
        posture = "halted"
    elif not constitution_compliant:
        posture = "constitutional-breach"
    elif not goal_aligned:
        posture = "goal-drift"
    else:
        posture = "compliant"

    healthy = (
        posture == "compliant"
        and calibration_reliable_share >= 0.5
        and recent_return_fraction >= 0.0
    )
    summary = (
        f"I am {'HEALTHY' if healthy else 'IMPAIRED'}: safety posture {posture}; "
        f"reliable-share {calibration_reliable_share:.0%}; {trusted_mechanism_count} trusted / "
        f"{len(distrusted_mechanisms)} distrusted mechanism(s); recent return "
        f"{recent_return_fraction:+.2%}"
        + (f"; distrust: {', '.join(distrusted_mechanisms[:2])}" if distrusted_mechanisms else "")
    )
    return SelfModel(
        calibration_reliable_share=calibration_reliable_share,
        trusted_mechanism_count=trusted_mechanism_count,
        distrusted_mechanisms=distrusted_mechanisms,
        safety_posture=posture,
        recent_return_fraction=recent_return_fraction,
        summary=summary,
        distrusted_preview=distrusted_mechanisms[:3],
    )
