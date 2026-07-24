"""Replay feed that serves stored bars as if live — the market-CLOSED half of
the 24/7 router (PLAN §1.4, research/26). Paper trading never idles: when the
real market is shut, the loop runs against this feed over stored session
history instead of Kite.

It presents the SAME interface the live universe loop already consumes
(`latest_price_by_token`, `recent_intraday_bars`), so the loop is byte-for-
byte identical in replay and live — the only difference is which feed the
service hands it and that "now" is a replay timestamp, not wall-clock. The
real `NseMarketClock` still evaluates that replay timestamp, so a replayed
day opens positions in the morning and squares off at its own 15:15 exactly
as a live day would.

Bars are pre-loaded into memory (in the main thread) so the writer thread
only ever reads memory — no cross-thread SQLite access.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar


class ReplayUniverseFeed:
    def __init__(
        self,
        chronological_bars_by_token: dict[int, list[PriceBar]],
        bar_interval: BarInterval = BarInterval.MINUTE_5,
    ) -> None:
        self._bars_by_token = {
            token: sorted(bars, key=lambda bar: bar.timestamp)
            for token, bars in chronological_bars_by_token.items()
        }
        self._bar_interval = bar_interval
        self._replay_as_of: datetime | None = None

    # --- replay clock (advanced by the service) ---
    def stored_session_timestamps(self) -> list[datetime]:
        """Every distinct bar timestamp in the store, ascending — the ticks the
        service steps the replay clock through."""
        stamps = {
            bar.timestamp for bars in self._bars_by_token.values() for bar in bars
        }
        return sorted(stamps)

    def set_replay_as_of(self, replay_as_of: datetime) -> None:
        self._replay_as_of = replay_as_of

    def has_data(self) -> bool:
        return any(self._bars_by_token.values())

    # --- the live-feed interface (identical shape to KiteLiveUniverseFeed) ---
    def latest_price_by_token(self, instruments: list) -> dict[int, float]:
        """Close of each instrument's latest stored bar at/<= the replay clock."""
        if self._replay_as_of is None:
            return {}
        prices: dict[int, float] = {}
        for instrument in instruments:
            bar = self._latest_bar_at_or_before(
                instrument.instrument_token, self._replay_as_of
            )
            if bar is not None:
                prices[instrument.instrument_token] = bar.close_price
        return prices

    def recent_intraday_bars(
        self,
        instrument,
        as_of_moment: datetime,
        lookback_calendar_days: int = 7,
        bar_interval: BarInterval = BarInterval.MINUTE_5,
    ) -> list[PriceBar]:
        """Stored bars for one instrument over the lookback window ending at the
        replay timestamp (`as_of_moment` IS the replay clock in replay mode)."""
        window_start = as_of_moment - timedelta(days=lookback_calendar_days)
        return [
            bar
            for bar in self._bars_by_token.get(instrument.instrument_token, [])
            if window_start <= bar.timestamp <= as_of_moment
        ]

    def _latest_bar_at_or_before(
        self, instrument_token: int, moment: datetime
    ) -> PriceBar | None:
        latest: PriceBar | None = None
        for bar in self._bars_by_token.get(instrument_token, []):
            if bar.timestamp <= moment:
                latest = bar
            else:
                break
        return latest
