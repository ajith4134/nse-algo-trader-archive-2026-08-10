"""Contradiction resolution (Trunk XIII; research/132) — reconcile conflicting beliefs/evidence.

The system's GLOBAL belief about a strategy can be CONTRADICTED by regime-conditional evidence
(globally the hit-rate is X, but in a specific regime the evidence says materially otherwise). This
organ detects the significant divergences with a two-proportion z-test and RESOLVES them toward the
more-specific evidence (regime-conditional belief wins — the epistemic-entrenchment principle: the
better-evidenced, more-specific claim prevails on conflict). Sourcing (research/132): TMS/AGM/
Dempster-Shafer are symbolic — wrong shape; built the z-test on scipy (statsmodels evaluated, heavy).
PURE (no I/O); reads the injected regime cohorts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scipy.stats import norm


@dataclass(frozen=True)
class Contradiction:
    regime: str
    global_hit_rate: float
    regime_hit_rate: float
    experiment_count: int
    z_score: float
    p_value: float
    resolution: str


@dataclass(frozen=True)
class ContradictionReport:
    contradictions: tuple[Contradiction, ...] = field(default_factory=tuple)
    global_hit_rate: float = 0.0
    global_experiments: int = 0
    summary: str = ""

    @property
    def has_contradiction(self) -> bool:
        return bool(self.contradictions)


def _two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> tuple[float, float]:
    """Two-proportion z-test. Returns (z, two-sided p). Pooled proportion under H0: p1 == p2."""
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = (pooled * (1 - pooled) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    p = 2 * norm.sf(abs(z))
    return z, float(p)


def resolve_contradictions(
    regime_cohorts: list,
    significance: float = 0.05,
    min_experiments: int = 8,
) -> ContradictionReport:
    """Detect regime cohorts whose hit-rate significantly contradicts the GLOBAL belief and resolve
    each toward the regime-specific evidence. `regime_cohorts` = MarketRegimeCalibration-like objects
    with `.market_regime`, `.experiment_count`, `.hit_rate`."""
    usable = [c for c in regime_cohorts
              if c.hit_rate is not None and c.experiment_count >= min_experiments]
    total_n = sum(c.experiment_count for c in usable)
    if total_n == 0 or len(usable) < 2:
        return ContradictionReport(
            summary="insufficient regime cohorts to check for belief contradictions")
    global_hit = sum(c.hit_rate * c.experiment_count for c in usable) / total_n

    contradictions: list[Contradiction] = []
    for c in usable:
        others_n = total_n - c.experiment_count
        if others_n <= 0:
            continue
        rest_hit = (global_hit * total_n - c.hit_rate * c.experiment_count) / others_n
        z, p = _two_proportion_z(c.hit_rate, c.experiment_count, rest_hit, others_n)
        if p <= significance:
            contradictions.append(Contradiction(
                regime=c.market_regime, global_hit_rate=global_hit, regime_hit_rate=c.hit_rate,
                experiment_count=c.experiment_count, z_score=z, p_value=p,
                resolution=(f"adopt regime-conditional belief for '{c.market_regime}' "
                            f"({c.hit_rate:.0%} vs global {global_hit:.0%}) — specific evidence wins"),
            ))
    contradictions.sort(key=lambda x: x.p_value)
    summary = (
        f"{len(contradictions)} belief contradiction(s) across regimes (global hit {global_hit:.0%}, "
        f"n={total_n})"
        + (": " + "; ".join(f"{x.regime} {x.regime_hit_rate:.0%} (p={x.p_value:.3f})"
                            for x in contradictions[:3]) if contradictions
           else " — beliefs are regime-consistent")
    )
    return ContradictionReport(
        contradictions=tuple(contradictions), global_hit_rate=global_hit,
        global_experiments=total_n, summary=summary,
    )
