"""§53 slice 4 P4a-wire — build the replay feed from an injected HistoricalBarSource
(hermetic, Rule J). A fake source stands in for Breeze; the fake lives only here.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (
    HighFidelityReplayConfig,
    build_replay_bars_by_token_from_source,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _instrument(token: int, symbol: str) -> Instrument:
    return Instrument(
        instrument_token=token, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _one_second_bars(token: int, base: datetime, count: int) -> list[PriceBar]:
    return [
        PriceBar(
            instrument_token=token, timestamp=base + timedelta(seconds=i),
            interval=BarInterval.SECOND_1, open_price=100.0 + i, high_price=101.0 + i,
            low_price=99.0 + i, close_price=100.5 + i, volume=10 + i,
        )
        for i in range(count)
    ]


class _FakeHistoricalBarSource:
    def __init__(self, bars_by_token: dict[int, list[PriceBar]]):
        self._bars_by_token = bars_by_token
        self.calls: list = []

    def fetch_historical_bars(self, instrument, bar_interval, from_datetime, to_datetime):
        self.calls.append((instrument.instrument_token, bar_interval, from_datetime, to_datetime))
        return list(self._bars_by_token.get(instrument.instrument_token, []))


def test_builder_keys_by_token_and_drops_empty_instruments():
    base = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
    with_bars = _instrument(1, "ITC")
    without_bars = _instrument(2, "DELISTED")
    fake = _FakeHistoricalBarSource({1: _one_second_bars(1, base, 3)})
    result = build_replay_bars_by_token_from_source(
        fake, [with_bars, without_bars], BarInterval.SECOND_1, base, base + timedelta(seconds=3)
    )
    assert set(result) == {1}  # the empty instrument is omitted, not a failure
    assert len(result[1]) == 3
    # each instrument was requested at the chosen interval + window
    assert [c[0] for c in fake.calls] == [1, 2]
    assert all(c[1] is BarInterval.SECOND_1 for c in fake.calls)


def test_service_builds_replay_feed_from_injected_high_fidelity_source():
    base = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
    instrument = _instrument(738561, "ITC")
    fake = _FakeHistoricalBarSource({738561: _one_second_bars(738561, base, 5)})
    config = HighFidelityReplayConfig(
        bar_source=fake, focus_instruments=[instrument], session_date=date(2026, 7, 24),
        bar_interval=BarInterval.SECOND_1,
    )
    service = LivePaperTradingService(object(), 1_000_000.0, high_fidelity_replay=config)
    service._build_replay_feed_from_store()  # picks the injected source, not the store

    feed = service._replay_feed
    assert feed is not None and feed.has_data()
    timestamps = feed.stored_session_timestamps()
    assert len(timestamps) == 5
    # the fake source was asked over the session window (09:15–15:30 IST)
    assert fake.calls[0][2].hour == 9 and fake.calls[0][2].minute == 15
    # the feed serves the injected 1-second closes
    feed.set_replay_as_of(timestamps[-1])
    prices = feed.latest_price_by_token([instrument])
    assert prices[738561] == 104.5  # close of the 5th (i=4) bar: 100.5 + 4
