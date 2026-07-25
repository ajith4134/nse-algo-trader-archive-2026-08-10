"""§53 task #19 — Groww historical adapter (hermetic, Rule J).
Injected fake client; the adapter never imports growwapi. Real-data (Rule F) uses
the thin GrowwRestHistoricalClient with the user's token (creds-gated)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data.groww_historical_bar_source import (
    GrowwHistoricalBarSource,
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


class _FakeGroww:
    """get_historical_candles → {"candles":[...]} serving rows whose ts is in
    [start_time, end_time] (inclusive → exercises boundary de-dup). `wrap` nests the
    result under a "payload" key to test both response shapes."""

    def __init__(self, candles: list[list], wrap: bool = False):
        self._candles = candles
        self._wrap = wrap
        self.calls: list[dict] = []

    def get_historical_candles(self, **kwargs):
        self.calls.append(kwargs)
        start = datetime.strptime(kwargs["start_time"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(kwargs["end_time"], "%Y-%m-%d %H:%M:%S")
        served = [
            c for c in self._candles
            if start <= datetime.strptime(c[0], "%Y-%m-%d %H:%M:%S") <= end
        ]
        return {"payload": {"candles": served}} if self._wrap else {"candles": served}


def _candles(base: datetime, day_offsets: list[int], oi=None) -> list[list]:
    rows = []
    for i, d in enumerate(day_offsets):
        ts = (base + timedelta(days=d)).strftime("%Y-%m-%d %H:%M:%S")
        row = [ts, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10 + i]
        if oi is not None:
            row.append(oi)
        rows.append(row)
    return rows


def test_unsupported_second_interval_raises():
    src = GrowwHistoricalBarSource(_FakeGroww([]))
    with pytest.raises(ValueError, match="does not serve"):
        src.fetch_historical_bars(
            _cash(), BarInterval.SECOND_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 25, tzinfo=IST),
        )


def test_cash_symbol_segment_and_parse():
    base = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
    fake = _FakeGroww(_candles(base, [0]))
    src = GrowwHistoricalBarSource(fake)
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert fake.calls[0]["groww_symbol"] == "NSE-RELIANCE"
    assert fake.calls[0]["segment"] == "CASH"
    assert fake.calls[0]["exchange"] == "NSE"
    assert fake.calls[0]["candle_interval"] == "1minute"
    assert len(bars) == 1 and bars[0].close_price == 100.5
    assert bars[0].open_interest is None


def test_option_symbol_needs_resolver_and_raises_by_default():
    option = Instrument(
        instrument_token=1, trading_symbol="BANKNIFTY25DEC27000PE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=15, tick_size=0.05, underlying_symbol="BANKNIFTY",
        strike_price=27000.0, option_right=OptionRight.PUT, expiry_date=date(2025, 12, 30),
    )
    src = GrowwHistoricalBarSource(_FakeGroww([]))
    with pytest.raises(ValueError, match="instrument-\nCSV resolver|CSV resolver"):
        src.fetch_historical_bars(
            option, BarInterval.MINUTE_1,
            datetime(2025, 12, 1, tzinfo=IST), datetime(2025, 12, 1, 0, 1, tzinfo=IST),
        )


def test_minute_chunks_at_30_days_and_dedupes():
    base = datetime(2024, 1, 1, tzinfo=IST)
    fake = _FakeGroww(_candles(base, [0, 30, 60, 79]))  # 30/60 are window boundaries
    src = GrowwHistoricalBarSource(fake)
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(days=80)
    )
    assert len(fake.calls) == 3  # 80 days / 30-day window
    assert len(bars) == 4
    ts = [b.timestamp for b in bars]
    assert ts == sorted(ts) and len(set(ts)) == 4


def test_option_oi_parsed_and_payload_wrapper():
    base = datetime(2025, 12, 1, 9, 15, tzinfo=IST)
    fake = _FakeGroww(_candles(base, [0], oi=45000), wrap=True)  # payload-wrapped
    option = Instrument(
        instrument_token=2, trading_symbol="BANKNIFTY25DEC27000PE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=15, tick_size=0.05, underlying_symbol="BANKNIFTY",
        strike_price=27000.0, option_right=OptionRight.PUT, expiry_date=date(2025, 12, 30),
    )
    src = GrowwHistoricalBarSource(
        fake, groww_symbol_resolver=lambda i: "NSE-BANKNIFTY-30Dec25-27000-PE"
    )
    bars = src.fetch_historical_bars(
        option, BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert fake.calls[0]["segment"] == "FNO"
    assert bars[0].open_interest == 45000  # OI parsed from the 7th element


def test_empty_response_yields_no_bars():
    base = datetime(2024, 1, 1, tzinfo=IST)
    src = GrowwHistoricalBarSource(_FakeGroww([]))
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert bars == []
