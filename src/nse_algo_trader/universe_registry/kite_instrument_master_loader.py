"""Loads and classifies the Kite Connect instrument master into Instruments.

Kite Connect's `instruments()` call returns the full tradable-instrument
dump for an exchange as a list of dict rows (one per trading symbol, columns:
instrument_token, exchange_token, tradingsymbol, name, last_price, expiry,
strike, tick_size, lot_size, instrument_type, segment, exchange). This module
turns that raw dump into the phase-1 universe: NSE cash equities, NSE index
options, and NSE stock options. Everything else in the dump (futures,
currency, commodities, other exchanges) is out of phase-1 scope and dropped.
"""

from __future__ import annotations

from datetime import date, datetime


def _expiry_date_from_kite_row_value(raw_expiry_value: date | str) -> date:
    """Kite's CSV dump carries expiry as 'YYYY-MM-DD' text, but the live
    kiteconnect SDK pre-parses it into a datetime.date (found live
    2026-07-23) — accept both."""
    if isinstance(raw_expiry_value, date):
        return raw_expiry_value
    return datetime.strptime(raw_expiry_value, "%Y-%m-%d").date()

from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)
from nse_algo_trader.universe_registry.nse_index_options_reference import (
    NSE_INDEX_OPTION_UNDERLYING_SYMBOLS,
)

_KITE_OPTION_RIGHT_BY_INSTRUMENT_TYPE = {"CE": OptionRight.CALL, "PE": OptionRight.PUT}


def classify_kite_instrument_row(row: dict) -> Instrument | None:
    """Convert one raw Kite instrument-dump row into an Instrument.

    Returns None if the row falls outside phase-1 scope (futures, currency,
    commodities, or any non-NSE-cash/non-NFO-options row).
    """
    exchange = row.get("exchange")
    segment = row.get("segment")
    instrument_type = row.get("instrument_type")

    if exchange == "NSE" and segment == "NSE" and instrument_type == "EQ":
        return Instrument(
            instrument_token=int(row["instrument_token"]),
            trading_symbol=row["tradingsymbol"],
            exchange_segment=ExchangeSegment.NSE_CASH,
            kind=InstrumentKind.CASH_EQUITY,
            lot_size=int(row["lot_size"]),
            tick_size=float(row["tick_size"]),
        )

    if exchange == "NFO" and instrument_type in _KITE_OPTION_RIGHT_BY_INSTRUMENT_TYPE:
        underlying_symbol = row["name"]
        kind = (
            InstrumentKind.INDEX_OPTION
            if underlying_symbol in NSE_INDEX_OPTION_UNDERLYING_SYMBOLS
            else InstrumentKind.STOCK_OPTION
        )
        return Instrument(
            instrument_token=int(row["instrument_token"]),
            trading_symbol=row["tradingsymbol"],
            exchange_segment=ExchangeSegment.NSE_FO,
            kind=kind,
            lot_size=int(row["lot_size"]),
            tick_size=float(row["tick_size"]),
            underlying_symbol=underlying_symbol,
            strike_price=float(row["strike"]),
            option_right=_KITE_OPTION_RIGHT_BY_INSTRUMENT_TYPE[instrument_type],
            expiry_date=_expiry_date_from_kite_row_value(row["expiry"]),
        )

    return None


def build_phase1_instrument_universe(raw_kite_instrument_rows: list[dict]) -> list[Instrument]:
    """Classify a full Kite instrument-master dump down to the phase-1
    universe (NSE cash equities + NSE index/stock options), dropping
    futures, currency, commodities, and non-NSE-family rows.
    """
    universe: list[Instrument] = []
    for row in raw_kite_instrument_rows:
        instrument = classify_kite_instrument_row(row)
        if instrument is not None:
            universe.append(instrument)
    return universe
