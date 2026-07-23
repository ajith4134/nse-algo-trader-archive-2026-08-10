from datetime import date, datetime

from nse_algo_trader.market_data import (
    BarInterval,
    HistoricalBarSource,
    KiteHistoricalBarSource,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

SAMPLE_CASH_INSTRUMENT = Instrument(
    instrument_token=408065,
    trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH,
    kind=InstrumentKind.CASH_EQUITY,
    lot_size=1,
    tick_size=0.05,
    underlying_symbol=None,
    strike_price=None,
    option_right=None,
    expiry_date=None,
)

SAMPLE_INDEX_OPTION_INSTRUMENT = Instrument(
    instrument_token=9604354,
    trading_symbol="NIFTY26JUL25000CE",
    exchange_segment=ExchangeSegment.NSE_FO,
    kind=InstrumentKind.INDEX_OPTION,
    lot_size=75,
    tick_size=0.05,
    underlying_symbol="NIFTY",
    strike_price=25000.0,
    option_right=OptionRight.CALL,
    expiry_date=date(2026, 7, 30),
)


class FakeKiteClientRecordingHistoricalDataCalls:
    """Stands in for an authenticated kiteconnect.KiteConnect in tests."""

    def __init__(self, raw_candles_to_return):
        self.raw_candles_to_return = raw_candles_to_return
        self.recorded_calls = []

    def historical_data(self, instrument_token, from_date, to_date, interval, oi=False):
        self.recorded_calls.append(
            {
                "instrument_token": instrument_token,
                "from_date": from_date,
                "to_date": to_date,
                "interval": interval,
                "oi": oi,
            }
        )
        return self.raw_candles_to_return


SAMPLE_KITE_CASH_CANDLE = {
    "date": datetime(2026, 7, 22, 9, 15),
    "open": 1520.0,
    "high": 1524.5,
    "low": 1519.2,
    "close": 1523.1,
    "volume": 184230,
}

SAMPLE_KITE_OPTION_CANDLE_WITH_OI = {
    "date": datetime(2026, 7, 22, 9, 15),
    "open": 105.0,
    "high": 112.4,
    "low": 103.6,
    "close": 110.2,
    "volume": 44775,
    "oi": 1235925,
}


def test_satisfies_historical_bar_source_protocol():
    kite_bar_source = KiteHistoricalBarSource(
        FakeKiteClientRecordingHistoricalDataCalls([])
    )
    assert isinstance(kite_bar_source, HistoricalBarSource)


def test_cash_fetch_maps_interval_name_and_omits_open_interest():
    fake_kite_client = FakeKiteClientRecordingHistoricalDataCalls(
        [SAMPLE_KITE_CASH_CANDLE]
    )
    fetched_bars = KiteHistoricalBarSource(fake_kite_client).fetch_historical_bars(
        SAMPLE_CASH_INSTRUMENT,
        BarInterval.MINUTE_5,
        datetime(2026, 7, 22, 9, 15),
        datetime(2026, 7, 22, 15, 30),
    )
    recorded_call = fake_kite_client.recorded_calls[0]
    assert recorded_call["interval"] == "5minute"
    assert recorded_call["oi"] is False
    assert recorded_call["instrument_token"] == 408065
    cash_bar = fetched_bars[0]
    assert cash_bar.interval == BarInterval.MINUTE_5
    assert cash_bar.close_price == 1523.1
    assert cash_bar.volume == 184230
    assert cash_bar.open_interest is None


def test_option_fetch_requests_open_interest_and_carries_it_through():
    fake_kite_client = FakeKiteClientRecordingHistoricalDataCalls(
        [SAMPLE_KITE_OPTION_CANDLE_WITH_OI]
    )
    fetched_bars = KiteHistoricalBarSource(fake_kite_client).fetch_historical_bars(
        SAMPLE_INDEX_OPTION_INSTRUMENT,
        BarInterval.MINUTE_1,
        datetime(2026, 7, 22, 9, 15),
        datetime(2026, 7, 22, 15, 30),
    )
    assert fake_kite_client.recorded_calls[0]["oi"] is True
    assert fake_kite_client.recorded_calls[0]["interval"] == "minute"
    assert fetched_bars[0].open_interest == 1235925
