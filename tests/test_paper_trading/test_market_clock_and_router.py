from datetime import date, datetime
from pathlib import Path

from nse_algo_trader.market_data import BarInterval, MarketDataSqliteStore, PriceBar
from nse_algo_trader.paper_trading import (
    DataSourceMode,
    HistoricalBarReplaySource,
    INDIA_MARKET_TIMEZONE,
    MarketClockGatedDataSourceRouter,
    NseMarketClock,
)


def _ist(*args) -> datetime:
    return datetime(*args, tzinfo=INDIA_MARKET_TIMEZONE)


# 2026-07-15 is a real NSE holiday (used to prove holiday gating works).
CLOCK_WITH_ONE_HOLIDAY = NseMarketClock(frozenset({date(2026, 7, 15)}))


class TestNseMarketClock:
    def test_open_during_session_on_a_real_trading_wednesday(self):
        # 2026-07-22 was a Wednesday trading day
        assert CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 22, 11, 0))

    def test_closed_before_open_and_after_close(self):
        assert not CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 22, 9, 0))
        assert not CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 22, 15, 31))

    def test_open_exactly_at_bounds(self):
        assert CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 22, 9, 15))
        assert CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 22, 15, 30))

    def test_closed_on_weekend(self):
        assert not CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 25, 11, 0))  # Sat
        assert not CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 26, 11, 0))  # Sun

    def test_closed_on_injected_holiday(self):
        assert not CLOCK_WITH_ONE_HOLIDAY.is_market_open(_ist(2026, 7, 15, 11, 0))

    def test_next_open_skips_weekend(self):
        # Friday after close -> next open is Monday 09:15
        next_open = CLOCK_WITH_ONE_HOLIDAY.next_session_open(_ist(2026, 7, 24, 16, 0))
        assert next_open == _ist(2026, 7, 27, 9, 15)

    def test_naive_datetime_treated_as_ist(self):
        assert CLOCK_WITH_ONE_HOLIDAY.is_market_open(datetime(2026, 7, 22, 11, 0))


def _bar(token: int, minute: int, close: float) -> PriceBar:
    return PriceBar(
        instrument_token=token,
        timestamp=_ist(2026, 7, 22, 9, minute),
        interval=BarInterval.MINUTE_5,
        open_price=close, high_price=close, low_price=close,
        close_price=close, volume=100,
    )


class TestHistoricalBarReplaySource:
    def _store_with_two_instruments(self, tmp_path: Path) -> MarketDataSqliteStore:
        store = MarketDataSqliteStore(tmp_path / "replay.sqlite3")
        store.save_price_bars([_bar(1, 20, 10.0), _bar(1, 15, 9.0)])
        store.save_price_bars([_bar(2, 17, 20.0)])
        return store

    def test_bars_stream_in_global_time_order_across_instruments(self, tmp_path):
        store = self._store_with_two_instruments(tmp_path)
        replay = HistoricalBarReplaySource(store, [1, 2], BarInterval.MINUTE_5)
        streamed = list(replay.stream_bars())
        store.close()
        assert [(b.instrument_token, b.timestamp.minute) for b in streamed] == [
            (1, 15), (2, 17), (1, 20),
        ]

    def test_loop_forever_restarts_from_the_beginning(self, tmp_path):
        store = self._store_with_two_instruments(tmp_path)
        replay = HistoricalBarReplaySource(store, [1], BarInterval.MINUTE_5)
        streamed_minutes = []
        for price_bar in replay.stream_bars(loop_forever=True):
            streamed_minutes.append(price_bar.timestamp.minute)
            if len(streamed_minutes) == 5:  # 2 bars, so it must have looped
                break
        store.close()
        assert streamed_minutes == [15, 20, 15, 20, 15]


class TestMarketClockGatedRouter:
    def test_closed_market_routes_to_replay(self, tmp_path):
        store = MarketDataSqliteStore(tmp_path / "r.sqlite3")
        store.save_price_bars([_bar(1, 15, 9.0)])
        router = MarketClockGatedDataSourceRouter(
            CLOCK_WITH_ONE_HOLIDAY,
            HistoricalBarReplaySource(store, [1], BarInterval.MINUTE_5),
            live_bar_source=None,
        )
        sunday = _ist(2026, 7, 26, 11, 0)
        assert router.current_data_mode(sunday) is DataSourceMode.REPLAY
        first_bar = next(router.next_bars(sunday, loop_replay_forever=False))
        store.close()
        assert first_bar.close_price == 9.0

    def test_open_market_with_live_source_routes_live(self, tmp_path):
        store = MarketDataSqliteStore(tmp_path / "r.sqlite3")

        class FakeLiveBarSource:
            def stream_bars(self):
                yield _bar(1, 30, 111.0)

        router = MarketClockGatedDataSourceRouter(
            CLOCK_WITH_ONE_HOLIDAY,
            HistoricalBarReplaySource(store, [1], BarInterval.MINUTE_5),
            live_bar_source=FakeLiveBarSource(),
        )
        open_moment = _ist(2026, 7, 22, 11, 0)
        assert router.current_data_mode(open_moment) is DataSourceMode.LIVE
        first_bar = next(router.next_bars(open_moment))
        store.close()
        assert first_bar.close_price == 111.0

    def test_open_market_without_live_source_falls_back_to_replay(self, tmp_path):
        store = MarketDataSqliteStore(tmp_path / "r.sqlite3")
        store.save_price_bars([_bar(1, 15, 9.0)])
        router = MarketClockGatedDataSourceRouter(
            CLOCK_WITH_ONE_HOLIDAY,
            HistoricalBarReplaySource(store, [1], BarInterval.MINUTE_5),
            live_bar_source=None,
        )
        open_moment = _ist(2026, 7, 22, 11, 0)
        assert router.current_data_mode(open_moment) is DataSourceMode.REPLAY
        store.close()
