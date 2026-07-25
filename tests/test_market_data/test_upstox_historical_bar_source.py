"""§53 task #17 — Upstox historical adapter (hermetic, Rule J). Injected fake v3
history client; adapter never imports upstox_client. Real-data (Rule F) needs an
Upstox token (OAuth or the 1-year Analytics token) — creds-gated."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data.upstox_historical_bar_source import (
    UpstoxHistoricalBarSource,
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


class _FakeUpstoxHistory:
    def __init__(self, candles, as_object=False):
        self._candles = candles
        self._as_object = as_object
        self.calls = []

    def get_historical_candle_data(self, instrument_key, unit, interval, to_date, from_date):
        self.calls.append(
            {"instrument_key": instrument_key, "unit": unit, "interval": interval,
             "to_date": to_date, "from_date": from_date}
        )
        start = datetime.strptime(from_date, "%Y-%m-%d").date()
        end = datetime.strptime(to_date, "%Y-%m-%d").date()
        served = [c for c in self._candles
                  if start <= datetime.fromisoformat(c[0]).date() <= end]
        if self._as_object:  # mimic the SDK's response.data.candles object
            return type("R", (), {"data": type("D", (), {"candles": served})()})()
        return {"data": {"candles": served}}


def _candles(base: datetime, day_offsets, oi=0):
    return [
        [(base + timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%S+05:30"),
         100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10 + i, oi]
        for i, d in enumerate(day_offsets)
    ]


def test_unsupported_second_interval_raises():
    src = UpstoxHistoricalBarSource(_FakeUpstoxHistory([]), lambda i: "NSE_EQ|X")
    with pytest.raises(ValueError, match="does not serve"):
        src.fetch_historical_bars(
            _cash(), BarInterval.SECOND_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 25, tzinfo=IST),
        )


def test_default_resolver_requires_instrument_key():
    src = UpstoxHistoricalBarSource(_FakeUpstoxHistory([]))
    with pytest.raises(ValueError, match="instrument_key"):
        src.fetch_historical_bars(
            _cash(), BarInterval.MINUTE_1,
            datetime(2026, 7, 24, tzinfo=IST), datetime(2026, 7, 24, 0, 1, tzinfo=IST),
        )


def test_cash_call_shape_unit_interval_and_oi_parse():
    base = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
    fake = _FakeUpstoxHistory(_candles(base, [0], oi=1234))
    src = UpstoxHistoricalBarSource(fake, lambda i: "NSE_EQ|INE002A01018")
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert fake.calls[0]["instrument_key"] == "NSE_EQ|INE002A01018"
    assert (fake.calls[0]["unit"], fake.calls[0]["interval"]) == ("minutes", "1")
    assert len(bars) == 1 and bars[0].close_price == 100.5
    assert bars[0].open_interest == 1234  # OI is the 7th field


def test_sdk_object_response_shape_is_handled():
    base = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
    fake = _FakeUpstoxHistory(_candles(base, [0]), as_object=True)
    src = UpstoxHistoricalBarSource(fake, lambda i: "NSE_EQ|INE002A01018")
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(minutes=1)
    )
    assert len(bars) == 1  # response.data.candles object path parsed


def test_minute_chunks_at_30_days_and_dedupes():
    base = datetime(2024, 1, 1, tzinfo=IST)
    fake = _FakeUpstoxHistory(_candles(base, [0, 30, 60, 79]))
    src = UpstoxHistoricalBarSource(fake, lambda i: "NSE_EQ|INE002A01018")
    bars = src.fetch_historical_bars(
        _cash(), BarInterval.MINUTE_1, base, base + timedelta(days=80)
    )
    assert len(fake.calls) == 3  # 30-day window
    assert len(bars) == 4
    ts = [b.timestamp for b in bars]
    assert ts == sorted(ts) and len(set(ts)) == 4
