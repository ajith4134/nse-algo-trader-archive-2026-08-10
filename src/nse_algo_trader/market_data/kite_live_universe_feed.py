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

from datetime import datetime, time, timedelta
from time import monotonic, sleep
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.kite_historical_bar_source import (
    KiteHistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument

# Layer 2 must not import Layer 7 (the market clock lives in paper_trading);
# the 09:15 IST open is a fixed exchange fact, defined locally here.
_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
_NSE_REGULAR_SESSION_OPEN_IST = time(9, 15)

# Kite caps historical_data at ~3 requests/second; pace below that and back
# off on the "Too many requests" NetworkException so a universe-wide seed
# does not trip the limit.
_HISTORICAL_MIN_SECONDS_BETWEEN_CALLS = 0.34
_HISTORICAL_MAX_RETRIES = 4


class KiteLiveUniverseFeed:
    def __init__(
        self,
        authenticated_kite_client,
        ltp_batch_size: int = 400,
        persist_todays_bars: bool = False,
    ) -> None:
        self._kite_client = authenticated_kite_client
        self._historical_bar_source = KiteHistoricalBarSource(authenticated_kite_client)
        self._ltp_batch_size = ltp_batch_size
        self._last_historical_call_monotonic = 0.0
        # When set, today's fetched session bars are persisted to the market-
        # data store so the replay-when-closed feed accumulates the days the
        # loop trades (research/41). The store is opened lazily in whatever
        # thread first fetches (the writer thread) — SQLite is per-thread.
        self._persist_todays_bars = persist_todays_bars
        self._persist_store = None

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
        session_open = as_of_moment.astimezone(_INDIA_MARKET_TIMEZONE).replace(
            hour=_NSE_REGULAR_SESSION_OPEN_IST.hour,
            minute=_NSE_REGULAR_SESSION_OPEN_IST.minute,
            second=0,
            microsecond=0,
        )
        return self._paced_fetch_historical_bars(
            instrument, bar_interval, session_open, as_of_moment
        )

    def recent_intraday_bars(
        self,
        instrument: Instrument,
        as_of_moment: datetime,
        lookback_calendar_days: int = 7,
        bar_interval: BarInterval = BarInterval.MINUTE_5,
    ) -> list[PriceBar]:
        """Intraday candles over the last `lookback_calendar_days` through
        `as_of_moment`, in ONE historical call. Enough bars to warm ADX
        (which needs ~2×period) before today's opening range — today's
        session is a slice of the tail (`bar.timestamp.date() == today`)."""
        window_start = as_of_moment - timedelta(days=lookback_calendar_days)
        bars = self._paced_fetch_historical_bars(
            instrument, bar_interval, window_start, as_of_moment
        )
        if self._persist_todays_bars and bars:
            self._persist_todays_session_bars(bars, as_of_moment.date())
        return bars

    def _persist_todays_session_bars(self, bars: list[PriceBar], today) -> None:
        """Save today's slice of a fetched window to the replay store
        (idempotent INSERT-OR-REPLACE). Prior days are already stored; only
        today's bars are new. Best-effort — never let persistence break a
        scan pass."""
        todays = [bar for bar in bars if bar.timestamp.date() == today]
        if not todays:
            return
        try:
            if self._persist_store is None:
                from nse_algo_trader.market_data.market_data_sqlite_store import (
                    MarketDataSqliteStore,
                )

                self._persist_store = MarketDataSqliteStore()
            self._persist_store.save_price_bars(todays)
        except Exception:
            pass  # persistence is best-effort; a scan pass must not fail on it

    def _paced_fetch_historical_bars(self, instrument, bar_interval, frm, to):
        """Fetch with ≤3 req/s pacing and exponential backoff on Kite's
        'Too many requests' NetworkException."""
        for attempt in range(_HISTORICAL_MAX_RETRIES):
            elapsed = monotonic() - self._last_historical_call_monotonic
            if elapsed < _HISTORICAL_MIN_SECONDS_BETWEEN_CALLS:
                sleep(_HISTORICAL_MIN_SECONDS_BETWEEN_CALLS - elapsed)
            try:
                bars = self._historical_bar_source.fetch_historical_bars(
                    instrument, bar_interval, frm, to
                )
                self._last_historical_call_monotonic = monotonic()
                return bars
            except Exception as kite_error:
                self._last_historical_call_monotonic = monotonic()
                if "Too many requests" not in str(kite_error) or (
                    attempt == _HISTORICAL_MAX_RETRIES - 1
                ):
                    raise
                sleep(0.5 * (2**attempt))
        return []

    def stream_bars(self, loop_forever: bool = False):
        """Present so the router can treat this as its live bar source. The
        universe loop uses `latest_price_by_token` / `todays_session_bars`
        directly (universe-granularity), so this single-stream shim is not
        the primary path and yields nothing by itself."""
        return iter(())
