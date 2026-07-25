"""task #20 — multi-broker failover source (hermetic, Rule J). Injected fake sources
exercise every branch: served / empty→failover / raise→failover / all-fail→[] /
priority order / observer callback. Real failover across live Upstox+Angel is the
Rule-F pass (scripts/verify_multi_broker_failover_realdata.py)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.market_data.multi_broker_historical_bar_source import (
    MultiBrokerHistoricalBarSource,
    NamedHistoricalBarSource,
    SourceAttempt,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")
_FROM = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
_TO = datetime(2026, 7, 24, 15, 30, tzinfo=IST)


def _cash(symbol="RELIANCE") -> Instrument:
    return Instrument(
        instrument_token=738561, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _bar(minute_offset=0) -> PriceBar:
    return PriceBar(
        instrument_token=738561,
        timestamp=_FROM + timedelta(minutes=minute_offset),
        interval=BarInterval.MINUTE_1,
        open_price=100.0, high_price=101.0, low_price=99.0, close_price=100.5,
        volume=10, open_interest=None,
    )


class _FakeSource:
    """Returns preset bars, or raises the given exception. Records that it was called."""

    def __init__(self, bars=None, raises=None):
        self._bars = bars or []
        self._raises = raises
        self.called = False

    def fetch_historical_bars(self, instrument, bar_interval, from_datetime, to_datetime):
        self.called = True
        if self._raises is not None:
            raise self._raises
        return list(self._bars)


def _multi(*named, observer=None):
    return MultiBrokerHistoricalBarSource(list(named), on_source_attempt=observer)


def test_empty_ordered_sources_rejected():
    with pytest.raises(ValueError, match="at least one source"):
        MultiBrokerHistoricalBarSource([])


def test_primary_serves_and_secondary_not_called():
    primary, secondary = _FakeSource([_bar(0)]), _FakeSource([_bar(1)])
    bars = _multi(
        NamedHistoricalBarSource("upstox", primary),
        NamedHistoricalBarSource("angel", secondary),
    ).fetch_historical_bars(_cash(), BarInterval.MINUTE_1, _FROM, _TO)
    assert len(bars) == 1 and bars[0].timestamp == _FROM  # primary's bar
    assert primary.called and not secondary.called  # short-circuits on first non-empty


def test_empty_primary_fails_over_to_secondary():
    primary, secondary = _FakeSource([]), _FakeSource([_bar(0)])
    bars = _multi(
        NamedHistoricalBarSource("upstox", primary),
        NamedHistoricalBarSource("angel", secondary),
    ).fetch_historical_bars(_cash(), BarInterval.MINUTE_1, _FROM, _TO)
    assert len(bars) == 1 and secondary.called


def test_raising_primary_fails_over_to_secondary():
    primary = _FakeSource(raises=KeyError("symbol not in master"))
    secondary = _FakeSource([_bar(0)])
    bars = _multi(
        NamedHistoricalBarSource("angel", primary),
        NamedHistoricalBarSource("upstox", secondary),
    ).fetch_historical_bars(_cash(), BarInterval.MINUTE_1, _FROM, _TO)
    assert len(bars) == 1 and secondary.called  # resolver KeyError -> failover


def test_all_sources_fail_returns_empty_not_raise():
    a = _FakeSource(raises=RuntimeError("outage"))
    b = _FakeSource([])
    bars = _multi(
        NamedHistoricalBarSource("a", a), NamedHistoricalBarSource("b", b)
    ).fetch_historical_bars(_cash(), BarInterval.MINUTE_1, _FROM, _TO)
    assert bars == []  # never a hard crash


def test_priority_order_reported():
    multi = _multi(
        NamedHistoricalBarSource("fyers", _FakeSource([_bar()])),
        NamedHistoricalBarSource("upstox", _FakeSource([_bar()])),
    )
    assert multi.source_names_in_priority_order() == ["fyers", "upstox"]


def test_observer_receives_one_attempt_per_source_tried():
    attempts: list[SourceAttempt] = []
    primary = _FakeSource(raises=RuntimeError("boom"))
    secondary = _FakeSource([_bar(0), _bar(1)])
    _multi(
        NamedHistoricalBarSource("angel", primary),
        NamedHistoricalBarSource("upstox", secondary),
        observer=attempts.append,
    ).fetch_historical_bars(_cash("INFY"), BarInterval.MINUTE_1, _FROM, _TO)

    assert [a.outcome for a in attempts] == ["error", "served"]
    assert attempts[0].source_name == "angel" and attempts[0].error_repr is not None
    assert attempts[1].source_name == "upstox" and attempts[1].bar_count == 2
    assert all(a.instrument_trading_symbol == "INFY" for a in attempts)
