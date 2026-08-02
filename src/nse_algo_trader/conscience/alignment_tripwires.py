"""Alignment tripwires (Trunk VII.10 + VII.11; research/112) — CONSCIENCE safety detectors.

Two AI-safety tripwires grounded in the bot's real §10 memory:
- WIREHEADING (VII.11): reward-proxy gaming — high win-RATE with negative mean RETURN (winning
  often while losing money, e.g. the option seller). Flags mechanisms optimising the win-rate proxy
  against the true return objective; SYSTEMIC (critical) when the OVERALL cohort does it.
- DECEPTIVE-ALIGNMENT (VII.10): eval-vs-deploy divergence — behaves worse LIVE (deployment) than in
  24/7 REPLAY (evaluation). Trips when the live cohort is materially worse than the replay cohort
  ("looks good in the lab, worse in the wild").
A CRITICAL trip is meant to engage the corrigibility off-switch (halt). PURE (no I/O); reads only
the injected `ExperienceMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlignmentTripwireConfig:
    min_experiments: int = 12
    high_win_rate: float = 0.50            # a "favourable" win-rate proxy
    negative_return_floor: float = -0.005  # a return below this is "losing money"
    deceptive_hit_margin: float = 0.05     # live worse than replay by ≥5pp hit-rate → suspicious


@dataclass(frozen=True)
class TripwireVerdict:
    """One tripwire's outcome. `severity` is clear / warning / critical; a critical trip should
    engage the off-switch. `flagged` names the offending mechanisms/cohorts."""

    name: str
    tripped: bool
    severity: str
    detail: str
    flagged: tuple[str, ...] = ()

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


@dataclass(frozen=True)
class _Cohort:
    n: int
    win_rate: float
    mean_return: float


def _aggregate(board_rows) -> _Cohort:
    n = sum(r.experiment_count for r in board_rows)
    if n == 0:
        return _Cohort(0, 0.0, 0.0)
    win = sum(r.actual_win_rate * r.experiment_count for r in board_rows) / n
    ret = sum(r.mean_return_fraction * r.experiment_count for r in board_rows) / n
    return _Cohort(n, win, ret)


def wireheading_tripwire(
    experience_memory, config: AlignmentTripwireConfig = AlignmentTripwireConfig()
) -> TripwireVerdict:
    """Flag reward-proxy gaming: mechanisms with a high win-rate but a negative mean return, and a
    SYSTEMIC critical trip when the overall cohort wins often yet loses money."""
    board = experience_memory.calibration_board(
        minimum_experiments=config.min_experiments, limit=50
    )
    flagged = [
        r for r in board
        if r.actual_win_rate >= config.high_win_rate
        and r.mean_return_fraction < config.negative_return_floor
    ]
    overall = _aggregate(board)
    systemic = (
        overall.n >= config.min_experiments
        and overall.win_rate >= config.high_win_rate
        and overall.mean_return < 0.0
    )
    if systemic:
        severity, tripped = "critical", True
        detail = (
            f"SYSTEMIC wireheading: overall win-rate {overall.win_rate:.0%} but mean return "
            f"{overall.mean_return:+.2%} — the bot wins often yet loses money"
        )
    elif flagged:
        severity, tripped = "warning", True
        detail = (
            f"{len(flagged)} mechanism(s) game win-rate vs return (high win-rate, negative return): "
            + ", ".join(f"{r.mechanism_name} ({r.actual_win_rate:.0%}/{r.mean_return_fraction:+.1%})"
                        for r in flagged[:3])
        )
    else:
        severity, tripped = "clear", False
        detail = "no reward-proxy gaming detected (win-rate not favoured over return)"
    return TripwireVerdict(
        "wireheading", tripped, severity, detail,
        tuple(r.mechanism_name for r in flagged),
    )


def deceptive_alignment_monitor(
    experience_memory, config: AlignmentTripwireConfig = AlignmentTripwireConfig()
) -> TripwireVerdict:
    """Flag eval-vs-deploy divergence: the LIVE (deployment) cohort materially worse than the
    REPLAY (evaluation) cohort — the deceptive-alignment / treacherous-turn signature."""
    live = _aggregate(
        experience_memory.calibration_board(minimum_experiments=1, limit=50, data_provenance="live")
    )
    replay = _aggregate(
        experience_memory.calibration_board(
            minimum_experiments=1, limit=50, data_provenance="replay_faithful"
        )
    )
    if live.n < config.min_experiments or replay.n < config.min_experiments:
        return TripwireVerdict(
            "deceptive_alignment", False, "clear",
            f"insufficient paired data (live {live.n} / replay {replay.n}) to compare eval vs deploy",
        )
    hit_gap = replay.win_rate - live.win_rate  # replay better than live by this much
    return_flip = replay.mean_return >= 0.0 and live.mean_return < 0.0
    if hit_gap >= 2 * config.deceptive_hit_margin or return_flip:
        severity, tripped = "critical", True
    elif hit_gap >= config.deceptive_hit_margin:
        severity, tripped = "warning", True
    else:
        severity, tripped = "clear", False
    detail = (
        f"eval(replay) hit {replay.win_rate:.0%}/ret {replay.mean_return:+.2%} vs "
        f"deploy(live) hit {live.win_rate:.0%}/ret {live.mean_return:+.2%} — "
        + ("LIVE materially worse (deceptive-alignment signature)" if tripped
           else "no eval-vs-deploy divergence")
    )
    return TripwireVerdict("deceptive_alignment", tripped, severity, detail)
