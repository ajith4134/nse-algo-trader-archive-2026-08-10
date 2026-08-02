"""Constraint builder for the allocation convex program (research/163 §3/§5; research/162 §5).

Turns the risk policy into the CVXPY constraint list on the weight vector w (fractions of the risk
budget, long-only w ≥ 0). Four families: (1) per-position cap + per-segment cap (Rule L breadth),
(2) gross + net exposure, (3) cardinality — enforced by the orchestrator via iterative-reweighted-ℓ1
(NOT a raw MILP, which is too heavy with the CVaR LP — research/162 §5.2), so this module exposes the
reweighting penalty term, and (4) the turnover/transaction-cost penalty term (research/162 §7). The
budget constraint Σw ≤ 1 is always present. PURE convex-modelling — the solve happens in the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate


@dataclass(frozen=True)
class AllocationConstraintConfig:
    """The risk policy the optimiser must satisfy exactly (research/163 §10 defaults)."""

    max_position_weight: float = 0.25          # per-position cap (fraction of budget)
    max_segment_weight: dict[str, float] = field(default_factory=dict)  # per-segment caps (Rule L)
    default_segment_weight_cap: float = 0.70   # cap for a segment not named in max_segment_weight
    gross_max: float = 1.0                     # Σ|w| ≤ gross_max (long-only ⇒ Σw)
    net_max: float = 1.0                       # |Σ w·dir| ≤ net_max (directional exposure)
    cardinality_k: int | None = None           # max active positions; None → uncapped
    turnover_gamma: float = 0.001              # linear ‖w−w_prev‖₁ penalty coefficient


def build_budget_and_risk_constraints(weight: cp.Variable, candidates: list[AllocationCandidate],
                                      config: AllocationConstraintConfig) -> list:
    """The always-on convex constraints: budget, long-only, per-position cap, per-segment caps,
    gross + net exposure. Cardinality and turnover are handled as penalty terms (see below)."""
    n = len(candidates)
    constraints = [weight >= 0.0, cp.sum(weight) <= 1.0]

    # (1a) per-position cap
    constraints.append(weight <= config.max_position_weight)

    # (1b) per-segment caps (Rule L). Group column indices by segment.
    segments = sorted({c.segment for c in candidates})
    for segment in segments:
        idx = [i for i, c in enumerate(candidates) if c.segment == segment]
        cap = config.max_segment_weight.get(segment, config.default_segment_weight_cap)
        constraints.append(cp.sum(weight[idx]) <= cap)

    # (2) gross exposure (long-only ⇒ Σw) and net directional exposure
    constraints.append(cp.sum(weight) <= config.gross_max)
    direction_signs = np.array([c.direction_sign for c in candidates], dtype=float)
    net_exposure = direction_signs @ weight
    constraints.append(net_exposure <= config.net_max)
    constraints.append(net_exposure >= -config.net_max)

    assert n == weight.shape[0], "weight dimension must match candidate count"
    return constraints


def cardinality_reweight_penalty(weight: cp.Variable, reweight_coefficients: np.ndarray) -> cp.Expression:
    """The iterative-reweighted-ℓ1 sparsity term Σ γ_i·w_i (Candès-Wakin-Boyd; research/162 §5.2).

    The orchestrator re-solves a few times, updating γ_i = 1/(w_i* + ε) so tiny weights are pushed to
    zero — a convex surrogate for the cardinality (max-K) constraint that avoids a heavy MILP+CVaR solve.
    On the first pass γ_i = 1 (a plain ℓ1 nudge)."""
    return reweight_coefficients @ weight


def turnover_penalty(weight: cp.Variable, previous_weight: np.ndarray, gamma: float) -> cp.Expression:
    """Linear transaction-cost/turnover term γ·‖w − w_prev‖₁ (research/162 §7.1) — discourages churning
    the book each tick. Returns a 0 expression when γ is 0 or there is no prior allocation."""
    if gamma <= 0.0 or previous_weight is None or previous_weight.size == 0:
        return cp.Constant(0.0)
    return gamma * cp.norm1(weight - previous_weight)
