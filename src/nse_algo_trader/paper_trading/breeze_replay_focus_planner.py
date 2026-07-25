"""Rate-limit-aware focus selection for autonomous Breeze 1-second replay
(§53 slice 4 task #7; research/69).

Breeze allows only 5000 historical calls/day and caps a request at ~1000 candles,
so a 1-second session needs ~23 chunked calls PER instrument — the ~2000-name
universe is impossible to pull daily. This planner caps the focus set to what the
day's call budget actually affords, so autonomous 1s replay stays inside the limit.
"""

from __future__ import annotations

import math

from nse_algo_trader.market_data.breeze_historical_bar_source import (
    _MAX_CANDLES_PER_BREEZE_REQUEST,
    _SECONDS_PER_BAR_INTERVAL,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.universe_registry import Instrument

# An NSE session is 09:15–15:30 IST = 6h15m = 22,500 seconds.
NSE_SESSION_TRADING_SECONDS = 22_500


def chunks_per_instrument_for(
    bar_interval: BarInterval,
    session_trading_seconds: int = NSE_SESSION_TRADING_SECONDS,
) -> int:
    """The number of ≤1000-candle Breeze requests one instrument-session needs at
    this interval (how the adapter chunks the pull)."""
    window_seconds = _MAX_CANDLES_PER_BREEZE_REQUEST * _SECONDS_PER_BAR_INTERVAL[bar_interval]
    return max(1, math.ceil(session_trading_seconds / window_seconds))


def plan_breeze_replay_focus(
    candidate_instruments: list[Instrument],
    daily_call_budget: int,
    bar_interval: BarInterval = BarInterval.SECOND_1,
    session_trading_seconds: int = NSE_SESSION_TRADING_SECONDS,
) -> list[Instrument]:
    """The budget-capped focus set for one session: the candidates truncated to
    `daily_call_budget // chunks_per_instrument`. Order is preserved, so the caller
    ranks candidates (most liquid / actively-watched first); this only enforces the
    rate-limit ceiling."""
    chunks = chunks_per_instrument_for(bar_interval, session_trading_seconds)
    affordable_instrument_count = daily_call_budget // chunks
    if affordable_instrument_count <= 0:
        return []
    return candidate_instruments[:affordable_instrument_count]
