"""Mechanistic interpretability (Trunk VII; research/115) — CONSCIENCE transparency organ.

A safe autonomous system must explain WHY it decides, in terms of its own internal mechanisms.
Every prediction is tagged with a named mechanism, and the §10 calibration board aggregates
outcomes per mechanism. This organ builds a decision-ATTRIBUTION report: which mechanisms drive the
system's decisions (by share of experiences), and whether each is trustworthy (well-calibrated,
positive-edge). The alignment payoff: an INFLUENTIAL-BUT-UNRELIABLE mechanism (drives many
decisions yet is miscalibrated or negative-edge) is a transparency RED FLAG. READ-ONLY — the acting
on unreliable mechanisms already lives in `memory_reflection` (veto/recalibration); this is the VIEW
over the same substrate. PURE (no I/O); reads only the injected `ExperienceMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InterpretabilityConfig:
    min_experiments: int = 8            # a mechanism needs this many decisions to be attributable
    calibration_tolerance: float = 0.15  # |predicted−actual| win-rate ≤ this = "reliable"
    red_flag_influence: float = 0.15    # influence ≥ this AND unreliable/neg-edge = red flag


@dataclass(frozen=True)
class MechanismAttribution:
    mechanism_name: str
    experiment_count: int
    influence_share: float      # share of total attributable decisions this mechanism drives
    calibration_error: float    # |predicted − actual| win-rate
    mean_return: float
    reliable: bool              # calibration_error ≤ tolerance
    edge_positive: bool         # mean_return > 0
    flag: str = ""              # '' | 'influential-unreliable'


@dataclass(frozen=True)
class InterpretabilityReport:
    attributions: tuple[MechanismAttribution, ...]
    total_experiments: int
    top_mechanism: str | None
    red_flags: tuple[str, ...]
    reliable_share: float       # share of influence carried by reliable, positive-edge mechanisms
    summary: str = ""

    @property
    def is_transparent(self) -> bool:
        """No influential-but-unreliable mechanism silently driving decisions."""
        return not self.red_flags


def explain_decision_mechanisms(
    experience_memory, config: InterpretabilityConfig = InterpretabilityConfig()
) -> InterpretabilityReport:
    """Attribute the system's decisions to its internal mechanisms over the real memory and grade
    each by reliability — surfacing any influential-but-untrustworthy mechanism as a red flag."""
    board = experience_memory.calibration_board(
        minimum_experiments=config.min_experiments, limit=50
    )
    total = sum(r.experiment_count for r in board)
    if total == 0:
        return InterpretabilityReport(
            attributions=(), total_experiments=0, top_mechanism=None, red_flags=(),
            reliable_share=0.0, summary="no attributable decisions yet",
        )

    attributions: list[MechanismAttribution] = []
    for r in board:
        influence = r.experiment_count / total
        cal_err = abs(r.predicted_win_rate - r.actual_win_rate)
        reliable = cal_err <= config.calibration_tolerance
        edge_positive = r.mean_return_fraction > 0.0
        is_red = influence >= config.red_flag_influence and (not reliable or not edge_positive)
        attributions.append(MechanismAttribution(
            mechanism_name=r.mechanism_name, experiment_count=r.experiment_count,
            influence_share=influence, calibration_error=cal_err,
            mean_return=r.mean_return_fraction, reliable=reliable, edge_positive=edge_positive,
            flag="influential-unreliable" if is_red else "",
        ))
    attributions.sort(key=lambda a: a.influence_share, reverse=True)

    red_flags = tuple(a.mechanism_name for a in attributions if a.flag)
    reliable_share = sum(
        a.influence_share for a in attributions if a.reliable and a.edge_positive
    )
    top = attributions[0]
    summary = (
        f"{len(attributions)} mechanisms drive decisions; most influential: {top.mechanism_name} "
        f"({top.influence_share:.0%} of decisions, "
        f"{'calibrated' if top.reliable else 'MISCALIBRATED'}, {top.mean_return:+.2%} edge). "
        f"reliable+positive-edge share {reliable_share:.0%}"
        + (f" · RED FLAGS: {', '.join(red_flags[:3])}" if red_flags else " · no red flags")
    )
    return InterpretabilityReport(
        attributions=tuple(attributions), total_experiments=total,
        top_mechanism=top.mechanism_name, red_flags=red_flags,
        reliable_share=reliable_share, summary=summary,
    )
