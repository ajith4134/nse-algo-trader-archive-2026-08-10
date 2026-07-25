"""§53 task #18 — Angel One historical adapter (hermetic, Rule J). Injected fake
SmartConnect; adapter never imports SmartApi. Real-data (Rule F) needs client code +
PIN + TOTP (creds-gated)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data.angel_one_historical_bar_source import (
    AngelOneHistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _cash() -> Instrument:
    return Instrument(
        instrument_token=738561, trading_symbol="RELIANCE",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


class _FakeSmartApi:
    def __init__(self, candles):
        self._candles = candles
        self.calls = []

    def getCandleData(self, param):
        self.calls.append(param)
        start = datetime.fromisoformat(param["fromdate"].replace(" ", "T")).replace(tzinfo=None)
        end = datetime.fromisoformat(param["todate"].replace(" ", "T")).replace(tzinfo=None)
        served = [
            c for c in self._candles
            if start <= datetime.fromisoformat(c[0]).replace(tzinfo=None) <= end
        ]
        return {"status": True, "data": served}


def _candles(base: datetime, day_offsets):
    return [
        [(base + timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%S+05:30"),
         100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10 + i]
        for i, d in enumerate(day_offsets)
    ]


def test_unsupported_second_interval_raises():
    src = AngelOneHistoricalBarSource(_FakeSmartApi([]), lambda i: "3045")
    with pytest.raises(ValueError, match="does not serve"):
        src.fetch_historical_bars(
            _cash(), BarInterval.SECOND_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 25, tzinfo=IST),
        )


def test_default_resolver_requires_symboltoken():
    src = AngelOneHistoricalBarSource(_FakeSmartApi([]))  # no token resolver
    with pytest.raises(ValueError, match="symboltoken"):
        src.fetch_historical_bars(
            _cash(), BarInterval.MINUTE_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 24, 0, 1, tzinfo=IST),
        )


def test_cash_call_shape_and_parse():
    base = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
    fake = _FakeSmartApi(_candles(base, [0]))
    src = AngelOneHistoricalBarSource(fake, lambda i: "2885")
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert fake.calls[0]["exchange"] == "NSE"
    assert fake.calls[0]["symboltoken"] == "2885"
    assert fake.calls[0]["interval"] == "ONE_MINUTE"
    assert len(bars) == 1 and bars[0].close_price == 100.5
    assert bars[0].open_interest is None  # Angel historical has no OI


def test_minute_chunks_at_30_days_and_dedupes():
    base = datetime(2024, 1, 1, tzinfo=IST)
    fake = _FakeSmartApi(_candles(base, [0, 30, 60, 79]))
    src = AngelOneHistoricalBarSource(fake, lambda i: "2885")
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(days=80)
    )
    assert len(fake.calls) == 3  # 80 / 30-day window
    assert len(bars) == 4
    ts = [b.timestamp for b in bars]
    assert ts == sorted(ts) and len(set(ts)) == 4
