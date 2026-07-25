"""task #14 — non-blocking high-fidelity replay prebuild (hermetic). The heavy high-
fidelity feed build runs off the startup path and ATOMICALLY swaps in for the store-5m
feed; a failed/empty build leaves the store feed untouched (no regression)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (
    HighFidelityReplayConfig,
)
from nse_algo_trader.paper_trading.replay_universe_feed import ReplayUniverseFeed
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")
_SESSION = date(2026, 7, 24)


def _instr(token=111) -> Instrument:
    return Instrument(
        instrument_token=token, trading_symbol="HF", exchange_segment=ExchangeSegment.NSE_CASH,
        kind=InstrumentKind.CASH_EQUITY, lot_size=1, tick_size=0.05,
    )


class _FakeHighFidelitySource:
    def __init__(self, bars):
        self._bars = bars

    def fetch_historical_bars(self, instrument, bar_interval, from_datetime, to_datetime):
        return list(self._bars)


def _one_second_bars(n=5):
    base = datetime(2026, 7, 24, 9, 15, 0, tzinfo=IST)
    return [PriceBar(
        instrument_token=111, timestamp=base + timedelta(seconds=i),
        interval=BarInterval.SECOND_1, open_price=100.0 + i, high_price=101.0 + i,
        low_price=99.0 + i, close_price=100.5 + i, volume=10, open_interest=None,
    ) for i in range(n)]


def _service_with_store_feed() -> LivePaperTradingService:
    service = LivePaperTradingService(object(), 1_000_000.0)
    base = datetime(2026, 7, 23, 9, 15, tzinfo=IST)
    store_bars = [PriceBar(
        instrument_token=999, timestamp=base + timedelta(minutes=5 * i),
        interval=BarInterval.MINUTE_5, open_price=100, high_price=101, low_price=99,
        close_price=100, volume=1, open_interest=None) for i in range(3)]
    feed = ReplayUniverseFeed({999: store_bars})
    service._replay_feed = feed
    service._replay_timestamps = feed.stored_session_timestamps()
    service._replay_cursor = 0
    return service


def test_swap_upgrades_feed_when_build_succeeds():
    service = _service_with_store_feed()
    store_feed = service._replay_feed
    service._high_fidelity_replay = HighFidelityReplayConfig(
        bar_source=_FakeHighFidelitySource(_one_second_bars(6)),
        focus_instruments=[_instr()], session_date=_SESSION,
        bar_interval=BarInterval.SECOND_1,
    )
    service._build_high_fidelity_replay_feed_and_swap()

    assert service._replay_feed is not store_feed  # swapped to the high-fidelity feed
    assert len(service._replay_timestamps) == 6  # the 1-second bars
    assert service._replay_cursor == 0


def test_empty_build_keeps_store_feed():
    service = _service_with_store_feed()
    store_feed = service._replay_feed
    service._high_fidelity_replay = HighFidelityReplayConfig(
        bar_source=_FakeHighFidelitySource([]),  # nothing fetched
        focus_instruments=[_instr()], session_date=_SESSION,
        bar_interval=BarInterval.SECOND_1,
    )
    service._build_high_fidelity_replay_feed_and_swap()
    assert service._replay_feed is store_feed  # untouched (no regression)


def test_failing_build_keeps_store_feed():
    service = _service_with_store_feed()
    store_feed = service._replay_feed

    class _Boom:
        def fetch_historical_bars(self, *a, **k):
            raise RuntimeError("network down")

    service._high_fidelity_replay = HighFidelityReplayConfig(
        bar_source=_Boom(), focus_instruments=[_instr()], session_date=_SESSION,
        bar_interval=BarInterval.SECOND_1,
    )
    service._build_high_fidelity_replay_feed_and_swap()  # must not raise
    assert service._replay_feed is store_feed


def test_advance_replay_pass_is_safe_across_a_swap():
    # cursor near the end of the long store feed, then swap to a shorter feed — the
    # locked read must not IndexError.
    service = _service_with_store_feed()
    service._replay_cursor = 2  # last index of the 3-bar store feed
    service._high_fidelity_replay = HighFidelityReplayConfig(
        bar_source=_FakeHighFidelitySource(_one_second_bars(2)),
        focus_instruments=[_instr()], session_date=_SESSION, bar_interval=BarInterval.SECOND_1,
    )
    service._build_high_fidelity_replay_feed_and_swap()  # now 2 timestamps, cursor reset to 0
    # a stale large cursor would IndexError without the modulo/lock guard:
    service._replay_cursor = 99
    service._advance_replay_pass()  # must not raise
    assert 0 <= service._replay_cursor < len(service._replay_timestamps)
