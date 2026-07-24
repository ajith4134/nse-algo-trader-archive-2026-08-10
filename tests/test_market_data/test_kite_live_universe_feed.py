"""Unit tests for the live universe feed (fake Kite client).

Live-data coverage (3,714 instruments priced in 0.4s, INFY session bars,
2026-07-24) is the Rule-F sign-off, recorded in the flowchart note.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data import BarInterval
from nse_algo_trader.market_data.kite_live_universe_feed import KiteLiveUniverseFeed
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

IST = ZoneInfo("Asia/Kolkata")

CASH = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05,
)
OPTION = Instrument(
    instrument_token=12345, trading_symbol="NIFTY2673023600CE",
    exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
    lot_size=75, tick_size=0.05, underlying_symbol="NIFTY", strike_price=23600.0,
    option_right=OptionRight.CALL, expiry_date=date(2026, 7, 30),
)


class _FakeKiteClient:
    def __init__(self):
        self.ltp_calls: list[list[str]] = []
        self.historical_calls: list[tuple] = []

    def ltp(self, symbols):
        self.ltp_calls.append(list(symbols))
        prices = {"NSE:INFY": 1023.9, "NFO:NIFTY2673023600CE": 88.5}
        return {s: {"last_price": prices[s]} for s in symbols if s in prices}

    def historical_data(self, token, frm, to, interval, oi=False):
        self.historical_calls.append((token, frm, to, interval, oi))
        return [{
            "date": frm, "open": 1030.0, "high": 1042.6, "low": 1023.0,
            "close": 1025.0, "volume": 10000,
        }]


class TestLatestPriceByToken:
    def test_maps_cash_and_option_to_correct_exchange_prefix(self):
        client = _FakeKiteClient()
        feed = KiteLiveUniverseFeed(client)
        prices = feed.latest_price_by_token([CASH, OPTION])
        assert prices == {408065: 1023.9, 12345: 88.5}
        # cash used NSE:, option used NFO:
        assert "NSE:INFY" in client.ltp_calls[0]
        assert "NFO:NIFTY2673023600CE" in client.ltp_calls[0]

    def test_batches_respect_ltp_batch_size(self):
        client = _FakeKiteClient()
        feed = KiteLiveUniverseFeed(client, ltp_batch_size=1)
        feed.latest_price_by_token([CASH, OPTION])
        assert len(client.ltp_calls) == 2  # one per instrument at batch size 1

    def test_missing_quotes_are_absent_not_zero(self):
        client = _FakeKiteClient()
        feed = KiteLiveUniverseFeed(client)
        halted = Instrument(
            instrument_token=999, trading_symbol="HALTED",
            exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
            lot_size=1, tick_size=0.05,
        )
        prices = feed.latest_price_by_token([halted])
        assert 999 not in prices


class TestTodaysSessionBars:
    def test_requests_from_the_0915_open_through_now(self):
        client = _FakeKiteClient()
        feed = KiteLiveUniverseFeed(client)
        now = datetime(2026, 7, 24, 10, 50, tzinfo=IST)
        bars = feed.todays_session_bars(CASH, now, BarInterval.MINUTE_5)
        assert len(bars) == 1
        _, frm, to, interval, _ = client.historical_calls[0]
        assert (frm.hour, frm.minute) == (9, 15)
        assert to == now
        assert interval == "5minute"
