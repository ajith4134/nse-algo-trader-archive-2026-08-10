"""Integer lot/tick rounding of continuous weights → tradeable whole lots (research/163 §5; research/162 §6).

A convex solver returns fractional weights; real orders are whole lots (options) / whole shares (cash).
We INTEGRATE PyPortfolioOpt's verified `DiscreteAllocation.greedy_portfolio()` (round-down then greedily
spend the residual cash on the position that most reduces the weight-tracking error — research/162 §6.1),
mapping each candidate to a synthetic "asset" whose price is its COST-PER-LOT so one allocated unit = one
lot. A bespoke greedy fallback (same algorithm, dependency-free) runs if PyPortfolioOpt errors, so the
engine never silently drops to naive truncation (Rule O.3). Never silent truncation — the residual is
always greedily filled and reported (research/162 §6.2).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate


@dataclass(frozen=True)
class LotAllocation:
    """The rounded, tradeable allocation + how much budget was actually deployed."""

    lots: dict[str, int]                 # candidate_id → whole lots (0 = not taken)
    capital_deployed: dict[str, float]   # candidate_id → ₹ actually committed
    leftover_capital: float              # ₹ of the budget left undeployed after rounding


def _cost_per_lot(candidate: AllocationCandidate) -> float:
    """₹ to buy one lot: per-unit entry price × lot size (cash lot size is 1)."""
    return max(candidate.entry_price, 0.0) * max(candidate.lot_or_tick_size, 1)


def round_weights_to_lots(candidates: list[AllocationCandidate], weights: dict[str, float],
                          account_capital: float) -> LotAllocation:
    """Round the continuous risk-budget weights to whole lots deploying ≈ Σweights·capital.

    The fraction of capital deployed equals Σweights (weights need not sum to 1 — the optimiser may hold
    cash); the nonzero weights are renormalised only to drive the greedy tracking, and the deployable
    total is scaled back by the original weight sum so we never over-deploy.
    """
    by_id = {c.candidate_id: c for c in candidates}
    active = {cid: w for cid, w in weights.items() if w > 1e-9 and cid in by_id and _cost_per_lot(by_id[cid]) > 0}
    if not active or account_capital <= 0.0:
        return LotAllocation({c.candidate_id: 0 for c in candidates},
                             {c.candidate_id: 0.0 for c in candidates}, float(max(account_capital, 0.0)))

    weight_sum = sum(active.values())
    deployable = account_capital * min(weight_sum, 1.0)
    normalised = {cid: w / weight_sum for cid, w in active.items()}
    cost_per_lot = {cid: _cost_per_lot(by_id[cid]) for cid in active}

    lots = _greedy_lot_allocation(normalised, cost_per_lot, deployable)

    capital_deployed = {cid: lots.get(cid, 0) * cost_per_lot[cid] for cid in active}
    for c in candidates:
        lots.setdefault(c.candidate_id, 0)
        capital_deployed.setdefault(c.candidate_id, 0.0)
    leftover = account_capital - sum(capital_deployed.values())
    return LotAllocation(lots=lots, capital_deployed=capital_deployed, leftover_capital=float(leftover))


def _greedy_lot_allocation(normalised_weights: dict[str, float], cost_per_lot: dict[str, float],
                           deployable_capital: float) -> dict[str, int]:
    """PyPortfolioOpt greedy allocation (integrated), with a dependency-free greedy fallback."""
    try:
        import pandas as pd
        from pypfopt.discrete_allocation import DiscreteAllocation

        ids = list(normalised_weights.keys())
        prices = pd.Series({cid: cost_per_lot[cid] for cid in ids})
        allocator = DiscreteAllocation(normalised_weights, prices,
                                       total_portfolio_value=max(deployable_capital, 1.0))
        allocation, _leftover = allocator.greedy_portfolio()
        return {cid: int(allocation.get(cid, 0)) for cid in ids}
    except Exception:
        return _bespoke_greedy(normalised_weights, cost_per_lot, deployable_capital)


def _bespoke_greedy(normalised_weights: dict[str, float], cost_per_lot: dict[str, float],
                    deployable_capital: float) -> dict[str, int]:
    """Round-down to whole lots, then spend the residual on the position most UNDER its target weight —
    the same greedy rule as PyPortfolioOpt, implemented directly so rounding never fails (Rule O.3)."""
    ids = list(normalised_weights.keys())
    lots = {cid: int(np.floor((deployable_capital * normalised_weights[cid]) / cost_per_lot[cid]))
            for cid in ids}
    spent = sum(lots[cid] * cost_per_lot[cid] for cid in ids)
    remaining = deployable_capital - spent
    # Greedily add one lot at a time to the most-underweighted affordable position.
    for _ in range(10_000):  # bounded — at most deployable/min_cost iterations
        affordable = [cid for cid in ids if cost_per_lot[cid] <= remaining + 1e-9]
        if not affordable:
            break
        deployed_total = sum(lots[cid] * cost_per_lot[cid] for cid in ids) or 1.0
        deficit = {cid: normalised_weights[cid] - (lots[cid] * cost_per_lot[cid]) / deployed_total
                   for cid in affordable}
        best = max(affordable, key=lambda cid: deficit[cid])
        if deficit[best] <= 0:
            break
        lots[best] += 1
        remaining -= cost_per_lot[best]
    return lots
