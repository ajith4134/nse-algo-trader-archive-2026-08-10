"""Layer 2 — Market Data (real-time + historical), multi-broker by design.

Public surface: the broker-neutral data model, the swappable data-source
protocols, the Kite adapters (first of several planned broker sources),
and the secondary NSE official-reports ingestion.
"""

from nse_algo_trader.market_data.broker_data_source_protocols import (
    HistoricalBarSource,
    LiveTickStreamSource,
)
from nse_algo_trader.market_data.kite_historical_bar_source import (
    KiteHistoricalBarSource,
)
from nse_algo_trader.market_data.kite_live_tick_stream_source import (
    KiteLiveTickStreamSource,
    parse_kite_ticker_payload,
)
from nse_algo_trader.market_data.market_data_types import (
    BarInterval,
    MarketTick,
    PriceBar,
)

__all__ = [
    "BarInterval",
    "HistoricalBarSource",
    "KiteHistoricalBarSource",
    "KiteLiveTickStreamSource",
    "LiveTickStreamSource",
    "MarketTick",
    "PriceBar",
    "parse_kite_ticker_payload",
]
