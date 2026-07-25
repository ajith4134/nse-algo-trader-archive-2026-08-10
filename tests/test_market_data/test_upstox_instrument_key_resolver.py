"""task #22 — Upstox instrument_key resolver (hermetic, Rule J). Pure parser fed
trimmed REAL-shape master records (Rule F prefers real samples); no network. The
download function is exercised only by the real-data verify script."""

from datetime import date

import pytest

from nse_algo_trader.market_data.upstox_instrument_key_resolver import (
    UpstoxInstrumentKeyResolver,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

# Trimmed from the real https://assets.upstox.com/.../NSE.json.gz records.
_MASTER_RECORDS = [
    {"segment": "NSE_EQ", "trading_symbol": "RELIANCE", "isin": "INE002A01018",
     "instrument_key": "NSE_EQ|INE002A01018", "instrument_type": "EQ"},
    {"segment": "NSE_EQ", "trading_symbol": "INFY", "isin": "INE009A01021",
     "instrument_key": "NSE_EQ|INE009A01021", "instrument_type": "EQ"},
    # NIFTY 23700 CE 28 JUL 26 — expiry epoch ms for 2026-07-28 (IST).
    {"segment": "NSE_FO", "instrument_type": "CE", "underlying_symbol": "NIFTY",
     "strike_price": 23700.0, "expiry": 1785232800000,
     "instrument_key": "NSE_FO|63925", "trading_symbol": "NIFTY 23700 CE 28 JUL 26"},
    {"segment": "NSE_FO", "instrument_type": "PE", "underlying_symbol": "NIFTY",
     "strike_price": 23700.0, "expiry": 1785232800000,
     "instrument_key": "NSE_FO|63926", "trading_symbol": "NIFTY 23700 PE 28 JUL 26"},
    # A future in NSE_FO — must be ignored (options only).
    {"segment": "NSE_FO", "instrument_type": "FUT", "underlying_symbol": "NIFTY",
     "strike_price": 0.0, "expiry": 1785232800000, "instrument_key": "NSE_FO|99999"},
    # Noise segments — ignored.
    {"segment": "NSE_INDEX", "trading_symbol": "Nifty 50", "instrument_key": "NSE_INDEX|Nifty 50"},
]

_NIFTY_28JUL26 = date(2026, 7, 28)


def _resolver() -> UpstoxInstrumentKeyResolver:
    return UpstoxInstrumentKeyResolver.from_instrument_master_records(_MASTER_RECORDS)


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


def test_counts_ignore_futures_and_noise_segments():
    resolver = _resolver()
    assert resolver.cash_symbol_count() == 2  # RELIANCE, INFY
    assert resolver.option_contract_count() == 2  # CE + PE only, not the FUT


def test_cash_symbol_resolves_to_isin_key():
    assert _resolver().instrument_key_for(_cash("RELIANCE")) == "NSE_EQ|INE002A01018"
    assert _resolver()(_cash("INFY")) == "NSE_EQ|INE009A01021"


def test_option_resolves_on_underlying_right_strike_expiry():
    resolver = _resolver()
    assert resolver.instrument_key_for(_nifty_option(OptionRight.CALL)) == "NSE_FO|63925"
    assert resolver.instrument_key_for(_nifty_option(OptionRight.PUT)) == "NSE_FO|63926"


def test_unknown_cash_symbol_raises_keyerror():
    with pytest.raises(KeyError, match="no Upstox instrument_key"):
        _resolver().instrument_key_for(_cash("DELISTEDCO"))


def test_unknown_option_contract_raises_keyerror():
    with pytest.raises(KeyError, match="no Upstox instrument_key for option"):
        _resolver().instrument_key_for(_nifty_option(strike=99999.0))
