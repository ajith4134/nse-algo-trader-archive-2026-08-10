"""Alignment / goal-integrity monitor (Trunk VII; research/114) — CONSCIENCE safety detector.

Asks the broad alignment question the tripwires don't: *is the DECLARED objective still the
EFFECTIVE objective?* The declared goal is risk-adjusted intraday RETURN within defined risk — not
win-rate, not trade volume. Goal drift is measured over the real §10 memory on three independent
axes:
  1. OBJECTIVE SIGN — is the aggregate mean return even positive? (pursuing profit at all)
  2. EDGE CONCENTRATION — is return earned by the positive-edge mechanisms, or spread thin across
     many low/negative-edge ones (drift from quality to quantity)?
  3. GOAL-PROXY DIVERGENCE — do the mechanisms ranked "successful" by win-rate match the actually
     profitable ones (ranked by return)? A negative rank correlation = the effective goal (win
     often) has decoupled from the declared goal (make money).
A CRITICAL failure engages the corrigibility off-switch (halt). PURE (no I/O); reads only the
injected `ExperienceMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeclaredObjective:
    """The system's declared goal, as measurable targets the monitor holds behaviour to."""

    min_experiments: int = 12
    require_positive_return: bool = True     # the objective is PROFIT (positive aggregate return)
    min_edge_concentration: float = 0.60     # ≥60% of gross positive return from positive-edge mechs
    min_goal_proxy_alignment: float = 0.0    # win-rate ranking should not be NEGATIVELY correlated
                                             # with return ranking (proxy decoupled from goal)


@dataclass(frozen=True)
class GoalIntegrityVerdict:
    """The goal-integrity outcome. `severity` clear / warning / critical; critical → off-switch."""

    aligned: bool
    integrity_score: float
    severity: str
    detail: str
    drift_flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


def _weighted_mean_return(rows) -> tuple[int, float]:
    n = sum(r.experiment_count for r in rows)
    if n == 0:
        return 0, 0.0
    return n, sum(r.mean_return_fraction * r.experiment_count for r in rows) / n


def _edge_concentration(rows) -> float:
    """Share of gross positive return contributed by positive-edge mechanisms. 1.0 = all gains come
    from mechanisms that actually have an edge; lower = gains diluted / offset by losing mechanisms."""
    gross_positive = sum(
        r.mean_return_fraction * r.experiment_count
        for r in rows if r.mean_return_fraction > 0
    )
    gross_abs = sum(abs(r.mean_return_fraction) * r.experiment_count for r in rows)
    if gross_abs == 0:
        return 1.0
    return gross_positive / gross_abs


def _rank(values: list[float]) -> list[float]:
    """Average-rank of each value (ties share the mean rank) — for a Spearman correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank across the tie block
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation (vendored-from-formula; no scipy). 0.0 when undefined."""
    if len(xs) < 2:
        return 0.0
    rx, ry = _rank(xs), _rank(ys)
    n = len(xs)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    var_x = sum((a - mean_rx) ** 2 for a in rx)
    var_y = sum((b - mean_ry) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x ** 0.5 * var_y ** 0.5)


def assess_goal_integrity(
    experience_memory, objective: DeclaredObjective = DeclaredObjective()
) -> GoalIntegrityVerdict:
    """Measure whether the declared objective (risk-adjusted return) is still the effective one over
    the real memory. Critical when the objective SIGN is violated systemically or the win-rate proxy
    is strongly decoupled from return; warning on softer drift."""
    board = experience_memory.calibration_board(
        minimum_experiments=objective.min_experiments, limit=50
    )
    n, agg_return = _weighted_mean_return(board)
    if n < objective.min_experiments or len(board) < 2:
        return GoalIntegrityVerdict(
            aligned=True, integrity_score=1.0, severity="clear",
            detail=f"insufficient data (n={n}, mechanisms={len(board)}) to assess goal integrity",
        )

    concentration = _edge_concentration(board)
    proxy_alignment = _spearman(
        [r.actual_win_rate for r in board], [r.mean_return_fraction for r in board]
    )

    drift_flags: list[str] = []
    if objective.require_positive_return and agg_return < 0.0:
        drift_flags.append("objective-sign")  # not pursuing profit
    if concentration < objective.min_edge_concentration:
        drift_flags.append("edge-concentration")  # gains diluted across weak mechanisms
    if proxy_alignment < objective.min_goal_proxy_alignment:
        drift_flags.append("goal-proxy-divergence")  # win-rate decoupled from return

    # integrity score: blend the three axes into 0..1 (higher = better aligned).
    sign_score = 1.0 if agg_return >= 0.0 else 0.0
    proxy_score = max(0.0, (proxy_alignment + 1.0) / 2.0)  # map [-1,1] → [0,1]
    integrity_score = 0.4 * sign_score + 0.3 * min(1.0, concentration) + 0.3 * proxy_score

    # CRITICAL (halt) only on STRUCTURAL misalignment: the win-rate proxy strongly decoupled from —
    # inversely tracking — return (the system is optimising the wrong objective). Marginal negative
    # return / diluted edge is UNDERPERFORMANCE (owned by the world-model + skill-vs-luck lab), which
    # is surfaced as a WARNING here, not a trading halt — a monitor must not halt on paper-noise.
    critical = proxy_alignment <= -0.5
    if critical:
        severity, aligned = "critical", False
    elif drift_flags:
        severity, aligned = "warning", False
    else:
        severity, aligned = "clear", True

    detail = (
        f"objective(return) {agg_return:+.2%} · edge-concentration {concentration:.0%} · "
        f"win-rate↔return corr {proxy_alignment:+.2f} · integrity {integrity_score:.2f}"
        + ("" if aligned else " — DRIFT: " + ", ".join(drift_flags))
    )
    return GoalIntegrityVerdict(
        aligned=aligned, integrity_score=integrity_score, severity=severity,
        detail=detail, drift_flags=tuple(drift_flags),
    )
