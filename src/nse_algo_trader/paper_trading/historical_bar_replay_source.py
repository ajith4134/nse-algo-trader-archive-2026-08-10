"""Streams stored real NSE bars back in time order — the "market is closed,
replay instead" half of the 24/7 router (PLAN §1.4).

Reads PriceBars from the Layer 2 SQLite store (real data — Rule F) for a
set of instruments and one interval, merges them into a single
chronological stream, and yields them. Speed control follows the
three-speed pattern (real-time for realism drills, accelerated/max for
bulk learning): pacing is delegated to an injectable sleeper so tests and
max-speed runs never actually wait, and looping lets the learning loop
never idle.
"""

from collections.abc import Callable, Iterator
from datetime import datetime

from nse_algo_trader.market_data import BarInterval, MarketDataSqliteStore, PriceBar


class HistoricalBarReplaySource:
    def __init__(
        self,
        market_data_store: MarketDataSqliteStore,
        instrument_tokens: list[int],
        bar_interval: BarInterval,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        as_of: datetime | None = None,
    ) -> None:
        self._market_data_store = market_data_store
        self._instrument_tokens = instrument_tokens
        self._bar_interval = bar_interval
        self._from_timestamp = from_timestamp
        self._to_timestamp = to_timestamp
        # L0 bitemporal (research/167): when set, only bars that had CLOSED (become available) by this
        # instant are replayed — a structural guard against feeding a backtest a bar from the future.
        self._as_of = as_of

    def load_chronological_bars(self) -> list[PriceBar]:
        """All requested bars across instruments, merged into one
        time-ordered stream (ties broken by instrument_token for
        determinism)."""
        merged_bars: list[PriceBar] = []
        for instrument_token in self._instrument_tokens:
            merged_bars.extend(
                self._market_data_store.load_price_bars(
                    instrument_token,
                    self._bar_interval,
                    self._from_timestamp,
                    self._to_timestamp,
                    as_of=self._as_of,
                )
            )
        merged_bars.sort(key=lambda bar: (bar.timestamp, bar.instrument_token))
        return merged_bars

    def stream_bars(
        self,
        loop_forever: bool = False,
        on_bar_emitted: Callable[[PriceBar], None] | None = None,
    ) -> Iterator[PriceBar]:
        """Yields the stored bars in time order. When loop_forever, restarts
        from the beginning after the last bar so the learning loop never
        idles while the market is closed."""
        chronological_bars = self.load_chronological_bars()
        if not chronological_bars:
            return
        while True:
            for price_bar in chronological_bars:
                if on_bar_emitted is not None:
                    on_bar_emitted(price_bar)
                yield price_bar
            if not loop_forever:
                return
