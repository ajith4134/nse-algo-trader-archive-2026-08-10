"""Core data model for a tradable NSE instrument (phase 1: cash equity + options)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class ExchangeSegment(str, Enum):
    NSE_CASH = "NSE_CASH"
    NSE_FO = "NSE_FO"


class InstrumentKind(str, Enum):
    CASH_EQUITY = "CASH_EQUITY"
    INDEX_OPTION = "INDEX_OPTION"
    STOCK_OPTION = "STOCK_OPTION"


class OptionRight(str, Enum):
    CALL = "CE"
    PUT = "PE"


_OPTION_KINDS = (InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION)


@dataclass(frozen=True)
class Instrument:
    """One tradable NSE instrument as registered with the broker.

    Option-specific fields (`option_right`, `strike_price`, `expiry_date`)
    are required when `kind` is INDEX_OPTION or STOCK_OPTION, and must be
    left as None for CASH_EQUITY.
    """

    instrument_token: int
    trading_symbol: str
    exchange_segment: ExchangeSegment
    kind: InstrumentKind
    lot_size: int
    tick_size: float
    underlying_symbol: str | None = None
    strike_price: float | None = None
    option_right: OptionRight | None = None
    expiry_date: date | None = None

    def __post_init__(self) -> None:
        if self.kind in _OPTION_KINDS and (
            self.option_right is None
            or self.expiry_date is None
            or self.strike_price is None
            or self.underlying_symbol is None
        ):
            raise ValueError(
                f"{self.trading_symbol}: {self.kind.value} instruments require "
                "underlying_symbol, option_right, expiry_date, and strike_price"
            )
