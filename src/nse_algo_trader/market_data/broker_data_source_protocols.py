"""The swappable multi-broker data-source boundary for Layer 2.

Per `docs/PLAN.md` §8a.12, data sourcing is multi-broker: Kite Connect is
one interchangeable source among several (Upstox, Angel One, ICICI
Direct, Groww planned). Strategy / indicator / replay code depends only
on these protocols, never on a concrete broker adapter.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable

from nse_algo_trader.market_data.market_data_types import (
    BarInterval,
    MarketTick,
    PriceBar,
)
from nse_algo_trader.universe_registry import Instrument


@runtime_checkable
class HistoricalBarSource(Protocol):
    """Anything that can return historical candles for one instrument."""

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]: ...


@runtime_checkable
class LiveTickStreamSource(Protocol):
    """Anything that can stream live ticks for subscribed instruments.

    Implementations invoke every registered callback once per parsed
    `MarketTick`. Consumers must treat callbacks as fired from the
    source's own thread.
    """

    def register_tick_callback(
        self, on_market_tick: Callable[[MarketTick], None]
    ) -> None: ...

    def subscribe_instrument_tokens(
        self, instrument_tokens: list[int]
    ) -> None: ...

    def start_streaming(self) -> None: ...

    def stop_streaming(self) -> None: ...
