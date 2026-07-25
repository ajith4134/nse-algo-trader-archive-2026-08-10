"""task #18/#22 — Angel One symboltoken resolver (hermetic, Rule J). Pure parser fed
trimmed REAL-shape OpenAPIScripMaster records (Rule F prefers real samples); no
network. The download function is exercised only by the real-data verify script."""

from datetime import date

import pytest

from nse_algo_trader.market_data.angel_one_symbol_token_resolver import (
    AngelOneSymbolTokenResolver,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

# Trimmed from the real OpenAPIScripMaster.json (strike is ×100; expiry DDMMMYYYY).
_MASTER_RECORDS = [
    {"token": "2885", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "expiry": "",
     "strike": "-1.000000", "instrumenttype": "", "exch_seg": "NSE"},
    {"token": "1594", "symbol": "INFY-EQ", "name": "INFY", "expiry": "",
     "strike": "-1.000000", "instrumenttype": "", "exch_seg": "NSE"},
    # Non-EQ NSE series (e.g. -BE / index) must NOT be picked up as cash.
    {"token": "99", "symbol": "RELIANCE-BL", "name": "RELIANCE", "expiry": "",
     "strike": "-1.000000", "instrumenttype": "", "exch_seg": "NSE"},
    {"token": "63925", "symbol": "NIFTY28JUL2623700CE", "name": "NIFTY",
     "expiry": "28JUL2026", "strike": "2370000.000000", "instrumenttype": "OPTIDX",
     "exch_seg": "NFO"},
    {"token": "63926", "symbol": "NIFTY28JUL2623700PE", "name": "NIFTY",
     "expiry": "28JUL2026", "strike": "2370000.000000", "instrumenttype": "OPTIDX",
     "exch_seg": "NFO"},
    # A future in NFO — must be ignored (options only).
    {"token": "55555", "symbol": "NIFTY28JUL26FUT", "name": "NIFTY",
     "expiry": "28JUL2026", "strike": "-1.000000", "instrumenttype": "FUTIDX",
     "exch_seg": "NFO"},
    # Other exchange — ignored.
    {"token": "77777", "symbol": "SENSEX28JUL2680000CE", "name": "SENSEX",
     "expiry": "28JUL2026", "strike": "8000000.000000", "instrumenttype": "OPTIDX",
     "exch_seg": "BFO"},
]

_NIFTY_28JUL26 = date(2026, 7, 28)


def _resolver() -> AngelOneSymbolTokenResolver:
    return AngelOneSymbolTokenResolver.from_scrip_master_records(_MASTER_RECORDS)


def _cash(symbol="RELIANCE") -> Instrument:
    return Instrument(
        instrument_token=0, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _nifty_option(right=OptionRight.CALL, strike=23700.0, expiry=_NIFTY_28JUL26) -> Instrument:
    return Instrument(
        instrument_token=0, trading_symbol=f"NIFTY{int(strike)}{right.value}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=75, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=strike, option_right=right, expiry_date=expiry,
    )


def test_counts_ignore_futures_non_eq_and_other_exchanges():
    resolver = _resolver()
    assert resolver.cash_symbol_count() == 2  # RELIANCE, INFY (not -BL, not BFO)
    assert resolver.option_contract_count() == 2  # CE + PE only, not the FUTIDX / BFO


def test_cash_symbol_resolves_to_token():
    assert _resolver().symbol_token_for(_cash("RELIANCE")) == "2885"
    assert _resolver()(_cash("INFY")) == "1594"


def test_option_resolves_with_strike_descaled_and_expiry_parsed():
    resolver = _resolver()
    assert resolver.symbol_token_for(_nifty_option(OptionRight.CALL)) == "63925"
    assert resolver.symbol_token_for(_nifty_option(OptionRight.PUT)) == "63926"


def test_unknown_cash_symbol_raises_keyerror():
    with pytest.raises(KeyError, match="no Angel symboltoken"):
        _resolver().symbol_token_for(_cash("DELISTEDCO"))


def test_unknown_option_contract_raises_keyerror():
    with pytest.raises(KeyError, match="no Angel symboltoken for option"):
        _resolver().symbol_token_for(_nifty_option(strike=99999.0))
