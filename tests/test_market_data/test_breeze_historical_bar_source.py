"""§53 slice 4 P4a — Breeze 1-second historical adapter (hermetic, Rule J).

An in-memory fake stands in for the authenticated Breeze client (which is
injected — the adapter never imports `breeze_connect`, whose import fires network
I/O). The fake returns real-shaped v2 envelopes and filters candles by the
requested window, so chunking + de-dup are exercised for real. The fake lives only
here under tests/, never in src/ — production wires the real BreezeConnect.
"""

from datetime import date, datetime, timedelta

import pytest

from nse_algo_trader.market_data.breeze_historical_bar_source import (
    BreezeHistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)



def _cash_instrument() -> Instrument:
    return Instrument(
        instrument_token=738561, trading_symbol="RELIANCE",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _option_instrument() -> Instrument:
    return Instrument(
        instrument_token=12345, trading_symbol="NIFTY26JUL24500CE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=75, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=24500.0, option_right=OptionRight.CALL,
        expiry_date=date(2026, 7, 30),
    )


class _FakeBreezeClient:
    """Returns a v2 envelope; serves the 1-second candles whose datetime falls in
    the requested [from_date, to_date] window (inclusive both ends, to exercise
    the adapter's boundary de-dup)."""

    def __init__(self, candles: list[dict]):
        self._candles = candles
        self.calls: list[dict] = []

    def get_historical_data_v2(self, **kwargs):
        self.calls.append(kwargs)
        # The adapter sends IST wall-clock with a cosmetic 'Z'; parse it back to a
        # naive wall-clock time and filter the (wall-clock) candles.
        start = datetime.strptime(kwargs["from_date"], "%Y-%m-%dT%H:%M:%S.000Z")
        end = datetime.strptime(kwargs["to_date"], "%Y-%m-%dT%H:%M:%S.000Z")
        served = [
            c for c in self._candles
            if start <= datetime.strptime(c["datetime"], "%Y-%m-%d %H:%M:%S") <= end
        ]
        return {"Success": served, "Error": None, "Status": 200}


def _one_second_candles(base: datetime, count: int) -> list[dict]:
    rows = []
    for i in range(count):
        moment = base + timedelta(seconds=i)
        rows.append({
            "datetime": moment.strftime("%Y-%m-%d %H:%M:%S"),
            "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i,
            "volume": 10 + i, "open_interest": "",
        })
    return rows


def test_unsupported_interval_raises_clearly():
    source = BreezeHistoricalBarSource(_FakeBreezeClient([]))
    with pytest.raises(ValueError, match="does not serve"):
        source.fetch_historical_bars(
            _cash_instrument(), BarInterval.MINUTE_15,
            datetime(2026, 7, 24), datetime(2026, 7, 25),
        )


def test_cash_addressing_and_parsing():
    base = datetime(2026, 7, 24, 3, 45, 0)
    fake = _FakeBreezeClient(_one_second_candles(base, 5))
    source = BreezeHistoricalBarSource(fake)
    bars = source.fetch_historical_bars(
        _cash_instrument(), BarInterval.SECOND_1, base, base + timedelta(seconds=4)
    )
    assert fake.calls[0]["interval"] == "1second"
    assert fake.calls[0]["stock_code"] == "RELIANCE"
    assert fake.calls[0]["exchange_code"] == "NSE"
    assert fake.calls[0]["product_type"] == "cash"
    assert "expiry_date" not in fake.calls[0]
    assert len(bars) == 5
    assert bars[0].open_price == 100.0 and bars[0].volume == 10
    assert bars[0].interval is BarInterval.SECOND_1
    assert bars[0].open_interest is None  # empty-string OI -> None
    assert [b.timestamp for b in bars] == sorted(b.timestamp for b in bars)


def test_option_addressing():
    base = datetime(2026, 7, 24, 4, 0, 0)
    fake = _FakeBreezeClient(_one_second_candles(base, 2))
    source = BreezeHistoricalBarSource(fake)
    source.fetch_historical_bars(
        _option_instrument(), BarInterval.SECOND_1, base, base + timedelta(seconds=1)
    )
    call = fake.calls[0]
    assert call["exchange_code"] == "NFO" and call["product_type"] == "options"
    assert call["stock_code"] == "NIFTY"  # the underlying, not the tradingsymbol
    assert call["right"] == "call"
    assert call["strike_price"] == "24500.0"
    assert call["expiry_date"].startswith("2026-07-30")


def test_chunks_beyond_1000_candles_and_dedupes_boundaries():
    base = datetime(2026, 7, 24, 3, 0, 0)
    fake = _FakeBreezeClient(_one_second_candles(base, 2500))
    source = BreezeHistoricalBarSource(fake)
    bars = source.fetch_historical_bars(
        _cash_instrument(), BarInterval.SECOND_1, base, base + timedelta(seconds=2500)
    )
    # 2500 one-second candles at a 1000-candle cap -> 3 windows.
    assert len(fake.calls) == 3
    # Every candle present exactly once despite inclusive-boundary overlap.
    assert len(bars) == 2500
    timestamps = [b.timestamp for b in bars]
    assert len(set(timestamps)) == 2500
    assert timestamps == sorted(timestamps)


def test_empty_success_envelope_yields_no_bars():
    source = BreezeHistoricalBarSource(_FakeBreezeClient([]))
    bars = source.fetch_historical_bars(
        _cash_instrument(), BarInterval.SECOND_1,
        datetime(2026, 7, 24, 3, 0),
        datetime(2026, 7, 24, 3, 0, 30),
    )
    assert bars == []


def test_open_interest_parsed_for_options():
    base = datetime(2026, 7, 24, 4, 0, 0)
    candles = _one_second_candles(base, 1)
    candles[0]["open_interest"] = "1250"
    source = BreezeHistoricalBarSource(_FakeBreezeClient(candles))
    bars = source.fetch_historical_bars(
        _option_instrument(), BarInterval.SECOND_1, base, base + timedelta(seconds=1)
    )
    assert bars[0].open_interest == 1250
