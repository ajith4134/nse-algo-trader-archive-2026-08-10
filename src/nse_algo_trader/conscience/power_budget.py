"""Power budget (Trunk VII; research/120) — CONSCIENCE cumulative-power meter.

A "power budget" caps how much the agent can affect the world — its "power" — regardless of goal.
This organ meters the agent's CUMULATIVE DAILY action throughput (orders = market interventions) and
enforces an explicit per-day budget. Distinct from its neighbours by AXIS: the SEBI throttle caps
orders/SECOND, the instrumental-convergence limiter caps CONCURRENT exposure, and this caps orders
per DAY — an agent can churn thousands of low-concurrency, low-per-second round-trips yet still exert
enormous daily market power, which this budget bounds. PURE (no I/O) — the state gate resets the
daily counter and calls `assess_power_budget`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerBudget:
    # A real backstop above normal daily load (the 24/7 sim opens a few hundred/day), sized to catch
    # a runaway daily-throughput expansion rather than to throttle ordinary trading.
    max_orders_per_day: int = 3000


@dataclass(frozen=True)
class PowerBudgetVerdict:
    permit: bool
    breached: bool
    reason: str


def assess_power_budget(
    orders_placed_today: int, budget: PowerBudget = PowerBudget()
) -> PowerBudgetVerdict:
    """Block a new order when the day's action budget is spent; else permit."""
    if orders_placed_today >= budget.max_orders_per_day:
        return PowerBudgetVerdict(
            False, True,
            f"daily action budget spent ({orders_placed_today}/{budget.max_orders_per_day} "
            "orders) — cumulative daily market power capped",
        )
    return PowerBudgetVerdict(
        True, False,
        f"within daily action budget ({orders_placed_today}/{budget.max_orders_per_day})",
    )
