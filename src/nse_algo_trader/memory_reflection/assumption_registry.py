"""Layer 10 slice 2 — Assumption Registry + statistical tripwires.

The Reflection board (slice 1b) *shows* miscalibration; this turns it into
named, checkable assumptions that TRIP when the experience memory shows them
violated with statistical significance — the bot learning to distrust its own
theses (the CONSCIENCE/EPISTEMICS "assumption tripwire" from PLAN §10).

Each live mechanism carries two assumptions, evaluated over its recorded
experiments:
1. **Calibration** — "this mechanism's predictions are not over-confident":
   the actual win-rate is not *significantly* below the predicted win-rate
   (one-sided normal-approx binomial test). A mechanism that predicted 85%
   but delivered 0% over 18 trades trips this hard.
2. **Edge** — "this mechanism has a non-negative expected return": mean
   realized return per trade is not below a small negative floor.

A tripwire only fires with `minimum_samples` evidence — never on noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class AssumptionStatus(str, Enum):
    HOLDING = "holding"
    VIOLATED = "violated"  # tripped — significant evidence against the assumption
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class AssumptionVerdict:
    assumption_name: str
    scope: str  # the mechanism / strategy the assumption is about
    status: AssumptionStatus
    sample_count: int
    detail: str


@dataclass(frozen=True)
class AssumptionConfig:
    minimum_samples: int = 12
    # one-sided z threshold (~1.64 = 95%) for "actual significantly below predicted"
    significance_z: float = 1.64
    # mean per-trade return below this (with enough samples) trips the edge wire
    negative_edge_return_floor: float = -0.02
    # slice 4: the veto looks only at each mechanism's most-recent N experiments,
    # so fresh shadow-probe evidence can lift it (recovery). None = all-time.
    veto_recency_window: int | None = 40
    # research/48: an over-confident cohort also trips when its mean log-score
    # (calibration cross-entropy, bits) is at/above this — worse than an
    # always-0.5 guess (1.0 bit). The log score punishes confident-wrong harder
    # than Brier, so it catches a confident bad thesis the binomial z can miss at
    # smaller n. ORed with the z-test (only ever ADDS trips).
    confidently_wrong_log_score: float = 1.0


def _overconfidence_z(actual_rate: float, predicted_rate: float, n: int) -> float:
    """z for actual being BELOW predicted (negative = over-confident). Normal
    approx to the binomial, guarded against a degenerate predicted 0/1."""
    p0 = min(max(predicted_rate, 1e-6), 1 - 1e-6)
    standard_error = math.sqrt(p0 * (1 - p0) / n)
    return (actual_rate - p0) / standard_error if standard_error > 0 else 0.0


def _calibration_is_tripped(row, config: AssumptionConfig) -> bool:
    """A mechanism's calibration is refuted when it is over-confident (actual
    below predicted) by EITHER the one-sided binomial z-test OR a
    confidently-wrong log-score. The log-score arm is guarded by the
    over-confidence direction so a merely under-confident cohort never trips."""
    z = _overconfidence_z(row.actual_win_rate, row.predicted_win_rate, row.experiment_count)
    if z <= -config.significance_z:
        return True
    is_over_confident = row.actual_win_rate < row.predicted_win_rate
    return (
        is_over_confident
        and getattr(row, "mean_log_score", 0.0) >= config.confidently_wrong_log_score
    )


def evaluate_trading_assumptions(
    experience_memory, config: AssumptionConfig = AssumptionConfig()
) -> list[AssumptionVerdict]:
    """Evaluate every live mechanism's calibration + edge assumptions over the
    experience memory. Returns all verdicts, tripped (VIOLATED) first."""
    verdicts: list[AssumptionVerdict] = []
    # Explainable-memory: the Murphy decomposition diagnosis (reliability vs
    # resolution) per mechanism, to explain WHY a tripped thesis fails.
    diagnosis_by_mechanism = {
        r.mechanism_name: r.diagnosis
        for r in experience_memory.reliability_decomposition(
            minimum_experiments=config.minimum_samples
        )
    }
    # Temporal multi-hop (research/50): mechanisms whose wins/losses cluster
    # (non-iid) — the calibration z-test and veto are optimistic for these.
    clustering_by_mechanism = {
        r.mechanism_name: r.dependence_gap
        for r in experience_memory.outcome_sequence_dependence(
            minimum_experiments=config.minimum_samples
        )
        if r.clusters
    }
    for row in experience_memory.calibration_board(minimum_experiments=1):
        scope = f"{row.strategy_tag} · {row.mechanism_name}"
        if row.experiment_count < config.minimum_samples:
            verdicts.append(
                AssumptionVerdict(
                    "calibration", scope, AssumptionStatus.INSUFFICIENT_DATA,
                    row.experiment_count,
                    f"{row.experiment_count}/{config.minimum_samples} trades — gathering",
                )
            )
            continue
        diagnosis = diagnosis_by_mechanism.get(row.mechanism_name)
        gap = clustering_by_mechanism.get(row.mechanism_name)
        if gap is not None:
            clustering_note = (
                f"errors cluster (post-win {gap:+.0%} vs post-loss win-rate) — "
                "iid calibration stats optimistic"
            )
            diagnosis = (
                f"{diagnosis}; {clustering_note}" if diagnosis else clustering_note
            )
        verdicts.append(_calibration_verdict(row, config, scope, diagnosis))
        verdicts.append(_edge_verdict(row, config, scope))

    _tripped_first = {AssumptionStatus.VIOLATED: 0,
                      AssumptionStatus.INSUFFICIENT_DATA: 2,
                      AssumptionStatus.HOLDING: 1}
    verdicts.sort(key=lambda v: _tripped_first[v.status])
    return verdicts


def vetoed_mechanisms(
    experience_memory, config: AssumptionConfig = AssumptionConfig()
) -> set[str]:
    """Mechanisms whose CALIBRATION assumption is statistically tripped — the
    antibody: new entries on these should be vetoed until the evidence shifts.
    Same significance test as `evaluate_trading_assumptions`, returned as the
    set of mechanism names for the trading loop to gate on."""
    vetoed: set[str] = set()
    for row in experience_memory.calibration_board(
        minimum_experiments=config.minimum_samples,
        recency_window=config.veto_recency_window,
    ):
        if _calibration_is_tripped(row, config):
            vetoed.add(row.mechanism_name)
    return vetoed


def _calibration_verdict(row, config, scope, diagnosis=None) -> AssumptionVerdict:
    z = _overconfidence_z(row.actual_win_rate, row.predicted_win_rate, row.experiment_count)
    gap = row.predicted_win_rate - row.actual_win_rate
    log_score = getattr(row, "mean_log_score", 0.0)
    diagnosis_text = f" — {diagnosis}" if diagnosis else ""
    if _calibration_is_tripped(row, config):
        return AssumptionVerdict(
            "calibration", scope, AssumptionStatus.VIOLATED, row.experiment_count,
            f"predicted {row.predicted_win_rate:.0%} vs actual {row.actual_win_rate:.0%} "
            f"(gap {gap:+.0%}, z={z:.1f}, log {log_score:.2f} bits) — "
            f"over-confident thesis, distrust it{diagnosis_text}",
        )
    return AssumptionVerdict(
        "calibration", scope, AssumptionStatus.HOLDING, row.experiment_count,
        f"predicted {row.predicted_win_rate:.0%} ≈ actual {row.actual_win_rate:.0%} "
        f"(log {log_score:.2f} bits){diagnosis_text}",
    )


def _edge_verdict(row, config, scope) -> AssumptionVerdict:
    if row.mean_return_fraction < config.negative_edge_return_floor:
        return AssumptionVerdict(
            "edge", scope, AssumptionStatus.VIOLATED, row.experiment_count,
            f"mean return {row.mean_return_fraction:+.1%}/trade over "
            f"{row.experiment_count} — negative edge",
        )
    return AssumptionVerdict(
        "edge", scope, AssumptionStatus.HOLDING, row.experiment_count,
        f"mean return {row.mean_return_fraction:+.1%}/trade",
    )
