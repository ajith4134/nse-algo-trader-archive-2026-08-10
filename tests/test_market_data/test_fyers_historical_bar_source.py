"""§53 slice 4 task #11 — Fyers deep-history adapter (hermetic, Rule J).
An injected fake FyersModel stands in; the adapter never imports fyers_apiv3, so no
install is needed. Real-data (Rule F) is creds-gated (open blocker)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data.fyers_historical_bar_source import (
    FyersHistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

IST = ZoneInfo("Asia/Kolkata")


def _cash(symbol: str = "RELIANCE") -> Instrument:
    return Instrument(
        instrument_token=738561, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


class _FakeFyers:
    """history(data) → {"s":"ok","candles":[...]} serving candles whose epoch is in
    [range_from, range_to] (inclusive, to exercise boundary de-dup)."""

    def __init__(self, candles: list[list], status: str = "ok"):
        self._candles = candles
        self._status = status
        self.calls: list[dict] = []

    def history(self, data):
        self.calls.append(data)
        rf, rt = int(data["range_from"]), int(data["range_to"])
        served = [c for c in self._candles if rf <= c[0] <= rt]
        return {"s": self._status, "candles": served}


def _minute_candles(base: datetime, epochs_days: list[int]) -> list[list]:
    rows = []
    for i, day_offset in enumerate(epochs_days):
        epoch = int(base.timestamp()) + day_offset * 86400
        rows.append([epoch, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10 + i])
    return rows


def test_unsupported_second_interval_raises():
    source = FyersHistoricalBarSource(_FakeFyers([]))
    with pytest.raises(ValueError, match="does not serve"):
        source.fetch_historical_bars(
            _cash(), BarInterval.SECOND_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 25, tzinfo=IST),
        )


def test_cash_symbol_resolution_and_parse():
    base = datetime(2020, 1, 1, 9, 15, tzinfo=IST)
    epoch = int(base.timestamp())
    fake = _FakeFyers([[epoch, 100.0, 101.0, 99.0, 100.5, 500]])
    source = FyersHistoricalBarSource(fake)
    bars = source.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert fake.calls[0]["symbol"] == "NSE:RELIANCE-EQ"
    assert fake.calls[0]["resolution"] == "1"
    assert fake.calls[0]["oi_flag"] == "0"  # cash: no OI
    assert fake.calls[0]["date_format"] == "0"
    assert len(bars) == 1
    assert bars[0].close_price == 100.5 and bars[0].volume == 500
    assert bars[0].open_interest is None
    assert bars[0].timestamp == datetime.fromtimestamp(epoch, IST)


def test_option_symbol_needs_resolver_and_raises_by_default():
    option = Instrument(
        instrument_token=1, trading_symbol="NIFTY26JUL24500CE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=75, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=24500.0, option_right=OptionRight.CALL, expiry_date=date(2026, 7, 30),
    )
    source = FyersHistoricalBarSource(_FakeFyers([]))
    with pytest.raises(ValueError, match="symbol-master resolver"):
        source.fetch_historical_bars(
            option, BarInterval.MINUTE_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 24, 0, 1, tzinfo=IST),
        )


def test_minute_pull_chunks_at_100_days_and_dedupes():
    base = datetime(2020, 1, 1, tzinfo=IST)
    # candles at day 0, 100 (boundary), 200 (boundary), 249
    fake = _FakeFyers(_minute_candles(base, [0, 100, 200, 249]))
    source = FyersHistoricalBarSource(fake)
    bars = source.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(days=250)
    )
    assert len(fake.calls) == 3  # 250 days / 100-day window
    assert len(bars) == 4  # boundary candles de-duped despite inclusive overlap
    ts = [b.timestamp for b in bars]
    assert ts == sorted(ts) and len(set(ts)) == 4


def test_daily_pull_uses_366_day_window():
    base = datetime(2018, 1, 1, tzinfo=IST)
    fake = _FakeFyers(_minute_candles(base, [0, 400]))
    source = FyersHistoricalBarSource(fake)
    source.fetch_historical_bars(
        _cash(), BarInterval.DAY_1, base, base + timedelta(days=800)
    )
    assert len(fake.calls) == 3  # 800 / 366 -> 3 windows
    assert all(c["resolution"] == "D" for c in fake.calls)


def test_option_oi_parsed_via_injected_resolver():
    base = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
    epoch = int(base.timestamp())
    fake = _FakeFyers([[epoch, 10.0, 11.0, 9.0, 10.5, 300, 12500]])  # 7th col = OI
    option = Instrument(
        instrument_token=2, trading_symbol="NIFTY24JAN22000CE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=50, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=22000.0, option_right=OptionRight.CALL, expiry_date=date(2024, 1, 25),
    )
    source = FyersHistoricalBarSource(
        fake, fyers_symbol_resolver=lambda i: "NSE:NIFTY24JAN22000CE"
    )
    bars = source.fetch_historical_bars(
        option, BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert fake.calls[0]["oi_flag"] == "1"  # options request OI
    assert bars[0].open_interest == 12500


def test_non_ok_envelope_yields_no_bars():
    base = datetime(2020, 1, 1, tzinfo=IST)
    fake = _FakeFyers(_minute_candles(base, [0]), status="error")
    source = FyersHistoricalBarSource(fake)
    bars = source.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert bars == []
