"""Hermetic test for the power budget (Trunk VII; research/120): meters daily order throughput,
blocks when the budget is spent, and resets the counter on a new day. Pure, no I/O.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.conscience.power_budget import PowerBudget, assess_power_budget
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def test_assess_permits_under_budget_and_blocks_at_budget():
    assert assess_power_budget(0, PowerBudget(3)).permit
    assert assess_power_budget(2, PowerBudget(3)).permit
    blocked = assess_power_budget(3, PowerBudget(3))
    assert not blocked.permit and blocked.breached


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )


def test_state_gate_counts_and_resets_daily():
    state = _state()
    day1 = datetime(2026, 7, 26, 10, 0)
    for _ in range(5):
        assert state.power_budget_permits_order(day1) is True  # well under the daily budget
    assert state.power_budget_orders_today == 5
    assert state.power_budget_day == day1.date()
    # a new day resets the daily action counter
    day2 = datetime(2026, 7, 27, 10, 0)
    assert state.power_budget_permits_order(day2) is True
    assert state.power_budget_orders_today == 1
    assert state.power_budget_day == day2.date()


def test_state_gate_blocks_when_budget_exhausted():
    state = _state()
    day = datetime(2026, 7, 26, 10, 0)
    from nse_algo_trader.conscience.power_budget import PowerBudget

    # pre-set the counter to the budget ceiling → the next order is blocked
    state.power_budget_day = day.date()
    state.power_budget_orders_today = PowerBudget().max_orders_per_day
    assert state.power_budget_permits_order(day) is False
    assert state.power_budget_blocked_order_count == 1
