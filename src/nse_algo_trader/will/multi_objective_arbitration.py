"""Multi-objective arbitration (Trunk III WILL; research/154). PURE — no I/O.

When the trading objectives conflict — a mechanism can win on RETURN yet lose on RISK or CONFIDENCE —
this arbitrates them: it builds each mechanism's `ObjectiveProfile` (utility from XIV AXIOLOGY, mean
return, negative risk, sample-confidence), computes the Pareto NON-DOMINATED set (mechanisms not beaten
on every objective), and scores each by a production-grade MCDM scalarization.

Production-grade (not a naive weighted-sum): objectives live on very different scales (utility ≈ −4,
return ≈ 0.01, confidence ∈ [0,1]), so a raw weighted-sum would let the largest-scale objective swamp
the rest. So we (1) MIN-MAX NORMALIZE each objective across the mechanism set, then score by (2) an
AUGMENTED CHEBYSHEV (Tchebysheff) scalarization — the robust MCDM method (rewards BALANCED high
performance across all objectives via a max-min term + a small weighted-sum tie-breaker; reaches the
non-convex Pareto front that plain weighted-sum cannot). The weighted-sum is also exposed for reference.
pymoo/objective-weights-mcda rejected as heavy evolutionary optimisers (research/154 §Sourcing) —
double-checkable; the scalarizations here are the same MCDM primitives, implemented directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_AUGMENTATION_RHO = 0.05  # the small weighted-sum term that guarantees Pareto-optimality + breaks ties


@dataclass(frozen=True)
class ObjectiveWeights:
    """How much the WILL cares about each objective when they conflict (the arbitration preference).

    Weights are normalised to sum to 1 internally, so they are comparable across the scalarizations."""

    w_utility: float = 1.0      # the XIV explicit utility (values-aware) — the anchor objective
    w_return: float = 0.5       # raw mean return
    w_risk: float = 0.5         # low risk (enters as a positive since risk is stored negative)
    w_confidence: float = 0.8   # sample-confidence — don't chase a thin high-return sample

    def as_vector(self) -> tuple:
        raw = (self.w_utility, self.w_return, self.w_risk, self.w_confidence)
        total = sum(raw) or 1.0
        return tuple(w / total for w in raw)


@dataclass(frozen=True)
class ObjectiveProfile:
    """One mechanism scored on every objective (all 'higher is better')."""

    mechanism: str
    utility: float          # XIV explicit utility over this mechanism's returns
    mean_return: float
    neg_risk: float         # −volatility (higher = calmer)
    confidence: float       # in [0,1], ∝ √sample_size (thin samples score low)
    sample_size: int

    def objective_vector(self) -> tuple:
        return (self.utility, self.mean_return, self.neg_risk, self.confidence)


@dataclass(frozen=True)
class ArbitratedMechanism:
    mechanism: str
    arbitration_score: float           # augmented-Chebyshev score (the primary ranking)
    weighted_sum_score: float          # normalised weighted-sum (reference)
    is_non_dominated: bool
    dominated_by: tuple = field(default_factory=tuple)
    normalized_objectives: tuple = field(default_factory=tuple)  # each objective in [0,1]
    profile: ObjectiveProfile | None = None


@dataclass(frozen=True)
class ArbitrationResult:
    ranked: tuple = field(default_factory=tuple)        # ArbitratedMechanism, best first
    pareto_front: tuple = field(default_factory=tuple)  # mechanism names on the non-dominated front
    summary: str = ""


def _dominates(a: ObjectiveProfile, b: ObjectiveProfile) -> bool:
    """a Pareto-dominates b iff a is ≥ b on every objective and strictly > on at least one."""
    av, bv = a.objective_vector(), b.objective_vector()
    return all(x >= y for x, y in zip(av, bv, strict=True)) and any(x > y for x, y in zip(av, bv, strict=True))


def confidence_from_sample(sample_size: int, full_confidence_at: int = 50) -> float:
    """Sample-confidence in [0,1], ∝ √n, saturating at `full_confidence_at` trades."""
    if sample_size <= 0:
        return 0.0
    return min(1.0, (sample_size / full_confidence_at) ** 0.5)


def _min_max_normalize_columns(vectors) -> list:
    """Min-max normalise each objective column to [0,1] across the mechanism set (all higher=better).
    A column with no spread maps to 0.5 (no discriminating information)."""
    if not vectors:
        return []
    n_obj = len(vectors[0])
    mins = [min(v[j] for v in vectors) for j in range(n_obj)]
    maxs = [max(v[j] for v in vectors) for j in range(n_obj)]
    normalized = []
    for v in vectors:
        row = []
        for j in range(n_obj):
            spread = maxs[j] - mins[j]
            row.append(0.5 if spread == 0 else (v[j] - mins[j]) / spread)
        normalized.append(tuple(row))
    return normalized


def _augmented_chebyshev(normalized_objectives, weights) -> float:
    """Augmented Chebyshev (Tchebysheff) achievement for MAXIMISATION objectives in [0,1]:
        score = min_i(w_i · z_i) + ρ · Σ_i(w_i · z_i)
    The max-min term rewards BALANCED strength across all objectives (a mechanism weak on any one is
    penalised); the ρ-weighted sum breaks ties and guarantees Pareto-optimality. Higher is better."""
    weighted = [w * z for w, z in zip(weights, normalized_objectives, strict=True)]
    return min(weighted) + _AUGMENTATION_RHO * sum(weighted)


def arbitrate(profiles, weights: ObjectiveWeights = ObjectiveWeights()) -> ArbitrationResult:
    """Pareto non-dominated set + augmented-Chebyshev arbitration ranking over the mechanism profiles."""
    profiles = list(profiles)
    if not profiles:
        return ArbitrationResult(summary="no mechanisms to arbitrate")

    weight_vector = weights.as_vector()
    normalized = _min_max_normalize_columns([p.objective_vector() for p in profiles])

    arbitrated = []
    for p, norm in zip(profiles, normalized, strict=True):
        dominators = tuple(o.mechanism for o in profiles if o is not p and _dominates(o, p))
        chebyshev = _augmented_chebyshev(norm, weight_vector)
        weighted_sum = sum(w * z for w, z in zip(weight_vector, norm, strict=True))
        arbitrated.append(ArbitratedMechanism(
            mechanism=p.mechanism, arbitration_score=chebyshev, weighted_sum_score=weighted_sum,
            is_non_dominated=not dominators, dominated_by=dominators,
            normalized_objectives=norm, profile=p))

    arbitrated.sort(key=lambda m: m.arbitration_score, reverse=True)
    pareto = tuple(m.mechanism for m in arbitrated if m.is_non_dominated)
    winner = arbitrated[0]
    summary = (f"arbitrated {len(arbitrated)} mechanisms (augmented-Chebyshev, normalised); "
               f"Pareto front {len(pareto)}; winner '{winner.mechanism}' "
               f"(score {winner.arbitration_score:.3f})")
    return ArbitrationResult(ranked=tuple(arbitrated), pareto_front=pareto, summary=summary)
