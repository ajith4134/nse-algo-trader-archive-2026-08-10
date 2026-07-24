"""The live-session data feed for the whole tradable universe.

Two access patterns the universe loop needs during an open session, sized
to Kite's rate limits (`docs/research/38`):

1. **Breadth — `latest_price_by_token`:** one live price for every
   instrument in the universe, fetched with batched `ltp()` calls (up to a
   few hundred symbols per call, a handful of calls for the whole
   universe). Cheap enough to run every scan interval.

2. **Depth — `todays_session_bars`:** today's intraday candles (09:15 → now)
   for a single instrument, so the ORB strategy sees the real opening
   range and the bars since. This delegates to `KiteHistoricalBarSource`
   (one `historical_data` call per instrument) — used to *seed* an
   instrument once, not polled for the whole universe each interval.

This is the object attached to `MarketClockGatedDataSourceRouter` as its
live source: once present, the router reports LIVE while the market is open
(the clock stays the sole mode authority). Kite specifics live here; the
loop above consumes broker-neutral `PriceBar`s and a token->price dict.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.market_data.kite_historical_bar_source import (
    KiteHistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.nse_market_clock import (
    INDIA_MARKET_TIMEZONE,
    NSE_REGULAR_SESSION_OPEN_IST,
)
from nse_algo_trader.universe_registry import Instrument


class KiteLiveUniverseFeed:
    def __init__(
        self,
        authenticated_kite_client,
        ltp_batch_size: int = 400,
    ) -> None:
        self._kite_client = authenticated_kite_client
        self._historical_bar_source = KiteHistoricalBarSource(authenticated_kite_client)
        self._ltp_batch_size = ltp_batch_size

    def _kite_ltp_symbol(self, instrument: Instrument) -> str:
        exchange = "NFO" if instrument.exchange_segment.value == "NSE_FO" else "NSE"
        return f"{exchange}:{instrument.trading_symbol}"

    def latest_price_by_token(
        self, instruments: list[Instrument]
    ) -> dict[int, float]:
        """Live LTP for every instrument, keyed by instrument_token. Symbols
        Kite has no quote for (halted/illiquid) are simply absent."""
        symbol_by_quote_key = {
            self._kite_ltp_symbol(instrument): instrument.instrument_token
            for instrument in instruments
        }
        quote_keys = list(symbol_by_quote_key.keys())
        price_by_token: dict[int, float] = {}
        for batch_start in range(0, len(quote_keys), self._ltp_batch_size):
            batch = quote_keys[batch_start : batch_start + self._ltp_batch_size]
            for quote_key, quote in self._kite_client.ltp(batch).items():
                token = symbol_by_quote_key.get(quote_key)
                if token is not None:
                    price_by_token[token] = quote["last_price"]
        return price_by_token

    def todays_session_bars(
        self,
        instrument: Instrument,
        as_of_moment: datetime,
        bar_interval: BarInterval = BarInterval.MINUTE_5,
    ) -> list[PriceBar]:
        """Today's candles from the 09:15 open through `as_of_moment` — the
        real opening range plus every bar since, for one instrument."""
        session_open = as_of_moment.astimezone(INDIA_MARKET_TIMEZONE).replace(
            hour=NSE_REGULAR_SESSION_OPEN_IST.hour,
            minute=NSE_REGULAR_SESSION_OPEN_IST.minute,
            second=0,
            microsecond=0,
        )
        return self._historical_bar_source.fetch_historical_bars(
            instrument, bar_interval, session_open, as_of_moment
        )

    def stream_bars(self, loop_forever: bool = False):
        """Present so the router can treat this as its live bar source. The
        universe loop uses `latest_price_by_token` / `todays_session_bars`
        directly (universe-granularity), so this single-stream shim is not
        the primary path and yields nothing by itself."""
        return iter(())
