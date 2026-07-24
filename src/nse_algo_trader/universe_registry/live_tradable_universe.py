"""Assembles the concrete phase-1 tradable universe the live loop scans.

Two problems the raw instrument master does not solve on its own:

1. **Cash breadth vs. tradability.** The NSE EQ dump (~9,800 rows) includes
   SME-platform scrips (`-SM` / `-ST` suffixes) that are not part of the
   liquid mainboard intraday universe. `select_mainboard_cash_equities`
   keeps the full mainboard (thousands of names — never a hand-picked
   sample) and drops only the SME platform rows.

2. **Option combinatorics.** 38k+ option contracts across 215 underlyings
   is far too many to price every scan. The credit-spread strategy only
   needs, per underlying, the **near-expiry ATM/ITM/OTM ladder** around the
   live spot. `select_near_expiry_option_ladder` picks exactly that band of
   strikes (both CALL and PUT) for every one of the 215 underlyings.

The selection logic here is pure (testable with fixtures);
`fetch_live_tradable_universe` is the thin live adapter that reads the Kite
instrument master + live spot prices and applies it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nse_algo_trader.universe_registry.instrument_types import (
    Instrument,
    InstrumentKind,
)
from nse_algo_trader.universe_registry.kite_instrument_master_loader import (
    build_phase1_instrument_universe,
)

# Option-underlying name -> the NSE spot quote symbol used to find its ATM
# strike. Indices are quoted under their index name, not a tradable EQ.
NSE_INDEX_SPOT_QUOTE_SYMBOL_BY_OPTION_UNDERLYING: dict[str, str] = {
    "NIFTY": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "FINNIFTY": "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NSE:NIFTY MID SELECT",
    "NIFTYNXT50": "NSE:NIFTY NEXT 50",
}

# Option-underlying name -> the NSE INDICES-segment trading symbol whose
# candles are the underlying's spot price series (for regime/ADX). Indices
# have no tradable EQ row, so their spot is fetched via the index token.
NSE_INDEX_SPOT_MASTER_SYMBOL_BY_OPTION_UNDERLYING: dict[str, str] = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "FINNIFTY": "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MID SELECT",
    "NIFTYNXT50": "NIFTY NEXT 50",
}

# SME-platform trading-symbol suffixes — not part of the mainboard intraday
# universe (kept out of the loop, not out of the registry).
_SME_PLATFORM_TRADING_SYMBOL_SUFFIXES: tuple[str, ...] = ("-SM", "-ST")


def _index_spot_carrier_instrument(index_master_row: dict) -> Instrument:
    """A minimal Instrument carrying an INDEX's token so its spot candles can
    be fetched for regime/ADX. An index is not tradable itself; this carrier
    is used ONLY for historical bars/LTP, never for orders (marked CASH_EQUITY
    so the bar source requests no option OI)."""
    from nse_algo_trader.universe_registry.instrument_types import ExchangeSegment

    return Instrument(
        instrument_token=int(index_master_row["instrument_token"]),
        trading_symbol=index_master_row["tradingsymbol"],
        exchange_segment=ExchangeSegment.NSE_CASH,
        kind=InstrumentKind.CASH_EQUITY,
        lot_size=1,
        tick_size=0.05,
    )


def resolve_spot_instrument_by_option_underlying(
    raw_nse_instrument_rows: list[dict],
    cash_equities: list[Instrument],
    option_underlying_symbols: set[str],
) -> dict[str, Instrument]:
    """Map each option underlying to the instrument whose candles are its
    spot: a stock underlying → its cash equity; an index underlying → an
    INDICES-token carrier."""
    cash_by_symbol = {eq.trading_symbol: eq for eq in cash_equities}
    index_rows_by_symbol = {
        row["tradingsymbol"]: row
        for row in raw_nse_instrument_rows
        if row.get("segment") == "INDICES"
    }
    spot_by_underlying: dict[str, Instrument] = {}
    for underlying_symbol in option_underlying_symbols:
        if underlying_symbol in NSE_INDEX_SPOT_MASTER_SYMBOL_BY_OPTION_UNDERLYING:
            master_symbol = NSE_INDEX_SPOT_MASTER_SYMBOL_BY_OPTION_UNDERLYING[
                underlying_symbol
            ]
            row = index_rows_by_symbol.get(master_symbol)
            if row is not None:
                spot_by_underlying[underlying_symbol] = (
                    _index_spot_carrier_instrument(row)
                )
        elif underlying_symbol in cash_by_symbol:
            spot_by_underlying[underlying_symbol] = cash_by_symbol[underlying_symbol]
    return spot_by_underlying


@dataclass(frozen=True)
class TradableUniverse:
    """The concrete instruments the live loop scans this session."""

    cash_equity_instruments: tuple[Instrument, ...]
    option_ladder_instruments: tuple[Instrument, ...]
    near_expiry_date: date
    # underlying symbol -> the instrument whose candles are its spot (stock
    # cash equity or index carrier); used by the credit-spread regime gate.
    spot_instrument_by_option_underlying: dict[str, Instrument] = None

    def total_instrument_count(self) -> int:
        return len(self.cash_equity_instruments) + len(self.option_ladder_instruments)

    def option_underlying_symbols(self) -> tuple[str, ...]:
        return tuple(
            sorted({opt.underlying_symbol for opt in self.option_ladder_instruments})
        )


def is_mainboard_cash_trading_symbol(trading_symbol: str) -> bool:
    """False for SME-platform scrips (`-SM` / `-ST`), True for mainboard."""
    return not any(
        trading_symbol.endswith(suffix)
        for suffix in _SME_PLATFORM_TRADING_SYMBOL_SUFFIXES
    )


def select_mainboard_cash_equities(
    phase1_universe: list[Instrument],
) -> list[Instrument]:
    return [
        instrument
        for instrument in phase1_universe
        if instrument.kind is InstrumentKind.CASH_EQUITY
        and is_mainboard_cash_trading_symbol(instrument.trading_symbol)
    ]


def nearest_expiry_date(option_instruments: list[Instrument]) -> date | None:
    """The soonest option expiry present (the current weekly/monthly)."""
    expiries = {opt.expiry_date for opt in option_instruments if opt.expiry_date}
    return min(expiries) if expiries else None


def select_near_expiry_option_ladder(
    option_instruments: list[Instrument],
    spot_price_by_underlying_symbol: dict[str, float],
    strikes_each_side_of_atm: int,
    expiry_date: date,
) -> list[Instrument]:
    """For each underlying, keep the near-expiry ATM strike plus
    `strikes_each_side_of_atm` ITM and OTM strikes, both CALL and PUT.

    ATM is the listed strike closest to the underlying's live spot. An
    underlying with no known spot (price feed missing) is skipped rather
    than guessed.
    """
    options_by_underlying: dict[str, list[Instrument]] = {}
    for option in option_instruments:
        if option.expiry_date != expiry_date:
            continue
        options_by_underlying.setdefault(option.underlying_symbol, []).append(option)

    laddered: list[Instrument] = []
    for underlying_symbol, options in options_by_underlying.items():
        spot_price = spot_price_by_underlying_symbol.get(underlying_symbol)
        if spot_price is None:
            continue
        listed_strikes = sorted({opt.strike_price for opt in options})
        if not listed_strikes:
            continue
        atm_strike = min(listed_strikes, key=lambda strike: abs(strike - spot_price))
        atm_index = listed_strikes.index(atm_strike)
        low_index = max(0, atm_index - strikes_each_side_of_atm)
        high_index = min(len(listed_strikes), atm_index + strikes_each_side_of_atm + 1)
        selected_strikes = set(listed_strikes[low_index:high_index])
        laddered.extend(
            opt for opt in options if opt.strike_price in selected_strikes
        )
    return laddered


def assemble_tradable_universe(
    raw_nse_instrument_rows: list[dict],
    raw_nfo_instrument_rows: list[dict],
    spot_price_by_underlying_symbol: dict[str, float],
    strikes_each_side_of_atm: int = 3,
) -> TradableUniverse:
    """Pure assembly: raw Kite master rows + live spots -> the tradable set.

    Kept free of any Kite call so it is unit-testable with fixtures;
    `fetch_live_tradable_universe` supplies the live inputs.
    """
    cash_equities = select_mainboard_cash_equities(
        build_phase1_instrument_universe(raw_nse_instrument_rows)
    )
    all_options = [
        instrument
        for instrument in build_phase1_instrument_universe(raw_nfo_instrument_rows)
        if instrument.kind
        in (InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION)
    ]
    expiry_date = nearest_expiry_date(all_options)
    option_ladder: list[Instrument] = []
    if expiry_date is not None:
        option_ladder = select_near_expiry_option_ladder(
            all_options,
            spot_price_by_underlying_symbol,
            strikes_each_side_of_atm,
            expiry_date,
        )
    spot_by_underlying = resolve_spot_instrument_by_option_underlying(
        raw_nse_instrument_rows,
        cash_equities,
        {opt.underlying_symbol for opt in option_ladder},
    )
    return TradableUniverse(
        cash_equity_instruments=tuple(cash_equities),
        option_ladder_instruments=tuple(option_ladder),
        near_expiry_date=expiry_date,
        spot_instrument_by_option_underlying=spot_by_underlying,
    )


def _spot_quote_symbols_for_underlyings(underlying_symbols: set[str]) -> list[str]:
    """NSE spot quote symbols for ATM discovery: indices use their index
    quote symbol, stock underlyings use `NSE:<symbol>`."""
    quote_symbols: list[str] = []
    for underlying_symbol in underlying_symbols:
        quote_symbols.append(
            NSE_INDEX_SPOT_QUOTE_SYMBOL_BY_OPTION_UNDERLYING.get(
                underlying_symbol, f"NSE:{underlying_symbol}"
            )
        )
    return quote_symbols


def fetch_live_tradable_universe(
    kite_client,
    strikes_each_side_of_atm: int = 3,
    ltp_batch_size: int = 400,
) -> TradableUniverse:
    """Live adapter: read the Kite instrument master + live spot prices and
    assemble the tradable universe. `kite_client` is any object exposing
    kiteconnect's `instruments(exchange)` and `ltp(symbols)`.
    """
    raw_nse_rows = kite_client.instruments("NSE")
    raw_nfo_rows = kite_client.instruments("NFO")

    all_options = [
        instrument
        for instrument in build_phase1_instrument_universe(raw_nfo_rows)
        if instrument.kind
        in (InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION)
    ]
    underlying_symbols = {opt.underlying_symbol for opt in all_options}
    quote_symbols = _spot_quote_symbols_for_underlyings(underlying_symbols)

    spot_price_by_quote_symbol: dict[str, float] = {}
    for batch_start in range(0, len(quote_symbols), ltp_batch_size):
        batch = quote_symbols[batch_start : batch_start + ltp_batch_size]
        for quote_symbol, quote in kite_client.ltp(batch).items():
            spot_price_by_quote_symbol[quote_symbol] = quote["last_price"]

    spot_price_by_underlying_symbol: dict[str, float] = {}
    for underlying_symbol in underlying_symbols:
        quote_symbol = NSE_INDEX_SPOT_QUOTE_SYMBOL_BY_OPTION_UNDERLYING.get(
            underlying_symbol, f"NSE:{underlying_symbol}"
        )
        if quote_symbol in spot_price_by_quote_symbol:
            spot_price_by_underlying_symbol[underlying_symbol] = (
                spot_price_by_quote_symbol[quote_symbol]
            )

    return assemble_tradable_universe(
        raw_nse_rows,
        raw_nfo_rows,
        spot_price_by_underlying_symbol,
        strikes_each_side_of_atm,
    )
