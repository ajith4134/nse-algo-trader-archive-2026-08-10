"""Layer 7 — Backtesting & Paper Trading (24/7 always-on service).

Foundation: a MarketClock-gated DataSourceRouter (PLAN §1.4) — replay
stored NSE history when the market is closed, live feed when open, one
interface, seamless handoff. The prediction-labeled trade-tables lab
(PLAN §9/§10) and realistic options slippage build on top of this.
"""

from nse_algo_trader.paper_trading.historical_bar_replay_source import (
    HistoricalBarReplaySource,
)
from nse_algo_trader.paper_trading.market_clock_gated_data_source_router import (
    DataSourceMode,
    MarketClockGatedDataSourceRouter,
)
from nse_algo_trader.paper_trading.nse_market_clock import (
    INDIA_MARKET_TIMEZONE,
    NseMarketClock,
)
from nse_algo_trader.paper_trading.opening_range_breakout_paper_engine import (
    PaperSessionOutcome,
    PaperSessionResult,
    group_bars_into_sessions,
    run_opening_range_breakout_paper_session,
)
from nse_algo_trader.paper_trading.paper_trading_ledger import (
    PaperPosition,
    PaperTradingLedger,
    RecordedPaperFill,
)

__all__ = [
    "DataSourceMode",
    "HistoricalBarReplaySource",
    "INDIA_MARKET_TIMEZONE",
    "MarketClockGatedDataSourceRouter",
    "NseMarketClock",
    "PaperPosition",
    "PaperSessionOutcome",
    "PaperSessionResult",
    "PaperTradingLedger",
    "RecordedPaperFill",
    "group_bars_into_sessions",
    "run_opening_range_breakout_paper_session",
]
