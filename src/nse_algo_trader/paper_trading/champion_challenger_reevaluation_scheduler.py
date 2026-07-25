"""Schedules the champion-challenger tournament and holds its search grid (§53 slice
5c-i.b; research/88).

The evaluator/store/live-read (research/87) exist but nothing runs the tournament; this
gates it to at most once per calendar day and defines the challenger grid to try. Pure —
the service owns the last-run bookkeeping and the store I/O.
"""

from __future__ import annotations

from datetime import date, time

from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)

# A modest fixed grid of ORB variants to challenge the champion with. Kept small so the
# Deflated-Sharpe multiple-testing deflation (number_of_strategy_trials) stays meaningful.
DEFAULT_ORB_CHALLENGER_GRID: list[OpeningRangeBreakoutConfig] = [
    OpeningRangeBreakoutConfig(opening_range_minutes=30, target_risk_reward_ratio=2.0),
    OpeningRangeBreakoutConfig(opening_range_minutes=15, target_risk_reward_ratio=1.5),
    OpeningRangeBreakoutConfig(opening_range_minutes=45, target_risk_reward_ratio=3.0),
    OpeningRangeBreakoutConfig(
        opening_range_minutes=15, target_risk_reward_ratio=2.0,
        latest_entry_time_ist=time(12, 0),
    ),
]


def is_reevaluation_due(last_run_date: date | None, today: date) -> bool:
    """True when the tournament should run now — never run yet, or the calendar day rolled
    over since the last run (so it fires at most once per day)."""
    return last_run_date is None or last_run_date < today
