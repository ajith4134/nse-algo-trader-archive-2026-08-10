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

# SME-platform trading-symbol suffixes — not part of the mainboard intraday
# universe (kept out of the loop, not out of the registry).
_SME_PLATFORM_TRADING_SYMBOL_SUFFIXES: tuple[str, ...] = ("-SM", "-ST")


@dataclass(frozen=True)
class TradableUniverse:
    """The concrete instruments the live loop scans this session."""

    cash_equity_instruments: tuple[Instrument, ...]
    option_ladder_instruments: tuple[Instrument, ...]
    near_expiry_date: date

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
    return TradableUniverse(
        cash_equity_instruments=tuple(cash_equities),
        option_ladder_instruments=tuple(option_ladder),
        near_expiry_date=expiry_date,
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
