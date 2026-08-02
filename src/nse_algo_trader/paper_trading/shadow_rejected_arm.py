"""SHADOW-REJECTED control arm of the skill-vs-luck lab (Layer 7.5 slice 2; research/106).

"What would the trades the gate REFUSED have done?" The gate refuses entries on VETOED mechanisms
(the Layer-10 antibody). Those mechanisms' real outcomes are already in memory — their pre-veto
experiences plus the Layer-10 shadow-probe trickle — so the SHADOW-REJECTED arm is simply the
aggregate performance of the VETOED mechanisms, and the TAKEN arm is the NON-vetoed ones, both
read from the calibration board split by the veto set. If the refused (vetoed) mechanisms perform
WORSE than the taken ones, the gate's rejection adds skill; if better, the gate is over-rejecting.
PURE (no I/O); reads only the injected `ExperienceMemory` read-model.
"""

from __future__ import annotations

from dataclasses import dataclass

_CALIBRATION_BOARD_SCAN = 50


@dataclass(frozen=True)
class ArmPerformance:
    """One arm's experiment-weighted performance over its mechanisms."""

    arm_name: str
    mechanisms: int
    experiments: int
    win_rate: float
    mean_return: float


@dataclass(frozen=True)
class ShadowRejectedAnalysis:
    """The TAKEN arm (gate allows) vs the SHADOW-REJECTED arm (gate refuses = vetoed mechanisms).
    `rejection_adds_skill` is True when the refused mechanisms earned a worse mean return than the
    taken ones (the gate correctly refused the losers); None when nothing is vetoed yet."""

    taken: ArmPerformance
    shadow_rejected: ArmPerformance
    rejection_adds_skill: bool | None
    detail: str


def analyze_shadow_rejected_arm(
    experience_memory, vetoed: set[str]
) -> ShadowRejectedAnalysis:
    """Split the calibration board into TAKEN (mechanism not vetoed) vs SHADOW-REJECTED (vetoed),
    aggregate each experiment-weighted, and judge whether refusing the vetoed set added skill."""
    board = experience_memory.calibration_board(
        minimum_experiments=1, limit=_CALIBRATION_BOARD_SCAN
    )
    taken_rows = [row for row in board if row.mechanism_name not in vetoed]
    rejected_rows = [row for row in board if row.mechanism_name in vetoed]
    taken = _aggregate("taken (gate allows)", taken_rows)
    shadow_rejected = _aggregate("shadow-rejected (gate refuses)", rejected_rows)

    if not rejected_rows:
        rejection_adds_skill: bool | None = None
        detail = "nothing vetoed yet — no shadow-rejected arm to judge"
    else:
        rejection_adds_skill = shadow_rejected.mean_return < taken.mean_return
        verdict = "adds skill" if rejection_adds_skill else "over-rejecting"
        detail = (
            f"refused mechanisms mean {shadow_rejected.mean_return:+.2%}/trade vs taken "
            f"{taken.mean_return:+.2%} — gate {verdict}"
        )
    return ShadowRejectedAnalysis(
        taken=taken,
        shadow_rejected=shadow_rejected,
        rejection_adds_skill=rejection_adds_skill,
        detail=detail,
    )


def _aggregate(arm_name: str, rows: list) -> ArmPerformance:
    experiments = sum(row.experiment_count for row in rows)
    if experiments == 0:
        return ArmPerformance(arm_name, 0, 0, 0.0, 0.0)
    win = sum(row.actual_win_rate * row.experiment_count for row in rows)
    ret = sum(row.mean_return_fraction * row.experiment_count for row in rows)
    return ArmPerformance(
        arm_name=arm_name,
        mechanisms=len(rows),
        experiments=experiments,
        win_rate=win / experiments,
        mean_return=ret / experiments,
    )
