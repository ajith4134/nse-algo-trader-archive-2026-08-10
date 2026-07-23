from datetime import date

import pytest

from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)


def test_cash_equity_instrument_does_not_require_option_fields():
    instrument = Instrument(
        instrument_token=123,
        trading_symbol="RELIANCE",
        exchange_segment=ExchangeSegment.NSE_CASH,
        kind=InstrumentKind.CASH_EQUITY,
        lot_size=1,
        tick_size=0.05,
    )
    assert instrument.option_right is None


def test_option_instrument_missing_option_fields_is_rejected():
    with pytest.raises(ValueError):
        Instrument(
            instrument_token=456,
            trading_symbol="NIFTY26JUL25000CE",
            exchange_segment=ExchangeSegment.NSE_FO,
            kind=InstrumentKind.INDEX_OPTION,
            lot_size=65,
            tick_size=0.05,
        )


def test_option_instrument_with_full_option_fields_succeeds():
    instrument = Instrument(
        instrument_token=456,
        trading_symbol="NIFTY26JUL25000CE",
        exchange_segment=ExchangeSegment.NSE_FO,
        kind=InstrumentKind.INDEX_OPTION,
        lot_size=65,
        tick_size=0.05,
        underlying_symbol="NIFTY",
        strike_price=25000.0,
        option_right=OptionRight.CALL,
        expiry_date=date(2026, 7, 30),
    )
    assert instrument.option_right == OptionRight.CALL
