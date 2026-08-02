"""Earn-calibration harness for the debate `risk_score` (Layer 11 slice 2c, research/101).

The debate-as-risk-check panel (research/100) produces a per-mechanism `risk_score`, but an LLM
risk signal must NOT alter real entries until it is shown to predict worse outcomes
OUT-OF-SAMPLE. This module answers, purely and deterministically: "over the accrued PREQUENTIAL
observations — `(risk_score_at_entry, realized_win)` pairs from LIVE trades, where the risk_score
was computed BEFORE the trade — do higher-risk_score entries actually win less?"

It splits the observations into a HIGH-risk cohort (`risk_score ≥ split_threshold`) and a LOW-risk
cohort and asks whether the LOW cohort wins materially more than the HIGH cohort. Calibration is
`earned` only with enough total data, enough in BOTH cohorts, AND a real positive separation —
so a thin or one-sided sample leaves the gate safely inert. No LLM, no I/O here — the observation
accrual + gating live in the store and the paper loop.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_MIN_OBSERVATIONS = 40
_DEFAULT_MIN_COHORT = 15
_DEFAULT_MIN_SEPARATION = 0.05
_DEFAULT_SPLIT_THRESHOLD = 0.5


@dataclass(frozen=True)
class RiskOutcomeObservation:
    """One prequential pair: the debate `risk_score` a mechanism carried at entry, and whether
    that LIVE trade actually won. Non-circular because the risk_score predates the outcome."""

    risk_score: float
    is_win: bool


@dataclass(frozen=True)
class RiskCalibrationVerdict:
    """Whether the debate risk_score has earned the right to gate entries, with the evidence.
    `separation` = low-cohort win-rate − high-cohort win-rate (positive ⇒ risk_score flags the
    worse trades). `earned` is the flag the entry gate honours before it ever defers/sizes-down."""

    earned: bool
    observation_count: int
    high_cohort_count: int
    low_cohort_count: int
    high_cohort_win_rate: float
    low_cohort_win_rate: float
    separation: float
    split_threshold: float
    note: str


def score_risk_calibration(
    observations: list[RiskOutcomeObservation],
    min_observations: int = _DEFAULT_MIN_OBSERVATIONS,
    min_cohort: int = _DEFAULT_MIN_COHORT,
    min_separation: float = _DEFAULT_MIN_SEPARATION,
    split_threshold: float = _DEFAULT_SPLIT_THRESHOLD,
) -> RiskCalibrationVerdict:
    """Decide whether the risk_score separates winners from losers well enough to gate entries.
    Conservative: too little data, an absent HIGH or LOW cohort, or too small a separation all
    return `earned=False` — the gate then stays inert (advisory only)."""
    total = len(observations)
    high = [o for o in observations if o.risk_score >= split_threshold]
    low = [o for o in observations if o.risk_score < split_threshold]
    high_win = _win_rate(high)
    low_win = _win_rate(low)
    separation = low_win - high_win

    if total < min_observations:
        note = (
            f"learning: {total}/{min_observations} prequential observations accrued "
            "(need more live trades before the risk signal can gate)"
        )
        earned = False
    elif len(high) < min_cohort or len(low) < min_cohort:
        note = (
            f"one-sided sample: high-risk n={len(high)}, low-risk n={len(low)} "
            f"(need ≥{min_cohort} in each cohort to compare)"
        )
        earned = False
    elif separation < min_separation:
        note = (
            f"insufficient separation: low-risk wins {low_win:.0%} vs high-risk "
            f"{high_win:.0%} (gap {separation:+.0%} < {min_separation:.0%} required)"
        )
        earned = False
    else:
        note = (
            f"EARNED: low-risk wins {low_win:.0%} vs high-risk {high_win:.0%} "
            f"(gap {separation:+.0%}) over {total} prequential observations"
        )
        earned = True

    return RiskCalibrationVerdict(
        earned=earned,
        observation_count=total,
        high_cohort_count=len(high),
        low_cohort_count=len(low),
        high_cohort_win_rate=high_win,
        low_cohort_win_rate=low_win,
        separation=separation,
        split_threshold=split_threshold,
        note=note,
    )


def _win_rate(observations: list[RiskOutcomeObservation]) -> float:
    if not observations:
        return 0.0
    return sum(1 for o in observations if o.is_win) / len(observations)
