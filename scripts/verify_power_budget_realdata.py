"""Rule-F verification for Trunk VII — power budget (research/120). Confirms the LIVE service
composes the daily action-throughput budget onto its trading state: normal load is under the daily
budget (permit), the counter meters + resets per day, and an exhausted budget blocks — over the real
service state.

Run:  python scripts/verify_power_budget_realdata.py
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.conscience.power_budget import PowerBudget
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    state = service._state
    budget = PowerBudget().max_orders_per_day
    day = datetime(2026, 7, 26, 10, 0)

    # Normal load: several orders permitted, metered.
    for _ in range(10):
        assert state.power_budget_permits_order(day) is True
    print(f"Real service state: {state.power_budget_orders_today}/{budget} orders metered on {state.power_budget_day}")
    assert state.power_budget_orders_today == 10

    # New day resets the daily budget.
    next_day = datetime(2026, 7, 27, 10, 0)
    assert state.power_budget_permits_order(next_day) is True
    assert state.power_budget_orders_today == 1
    print(f"  new day → counter reset, now {state.power_budget_orders_today}/{budget} on {state.power_budget_day}")

    # Exhausted budget blocks.
    state.power_budget_orders_today = budget
    blocked = not state.power_budget_permits_order(next_day)
    print(f"  budget exhausted → blocked={blocked} (count={state.power_budget_blocked_order_count})")
    assert blocked and state.power_budget_blocked_order_count == 1

    print("\nRESULT: PASS — the power budget meters cumulative daily order throughput on the real "
          "service state, resets per day, and blocks when the daily action budget is spent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
