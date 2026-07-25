"""Broker-neutral data model for Layer 2 (Market Data).

Every data-source adapter (Kite today; Upstox / Angel One / ICICI Direct /
Groww planned) converts its broker-specific payloads into these types, so
nothing downstream ever sees a broker-specific dict.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class BarInterval(str, Enum):
    """Broker-neutral candle interval names.

    Each broker adapter owns its own mapping from these values to the
    broker API's interval strings (e.g. Kite calls MINUTE_5 "5minute").
    """

    SECOND_1 = "1s"  # sub-minute fidelity (ICICI Breeze v2; not offered by Kite)
    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_10 = "10m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    MINUTE_60 = "60m"
    DAY_1 = "1d"


@dataclass(frozen=True)
class PriceBar:
    """One OHLCV candle for one instrument.

    `instrument_token` is the same token the Layer 1 universe registry
    uses as instrument identity. `open_interest` is None for cash
    equities and for sources that don't provide OI on candles.
    """

    instrument_token: int
    timestamp: datetime
    interval: BarInterval
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    open_interest: int | None = None


@dataclass(frozen=True)
class MarketTick:
    """One live tick for one instrument.

    Only `instrument_token` and `last_price` are guaranteed (broker
    "LTP"-style modes send nothing else); every other field is None when
    the source's subscription mode doesn't include it.
    """

    instrument_token: int
    last_price: float
    exchange_timestamp: datetime | None = None
    last_traded_quantity: int | None = None
    cumulative_day_volume: int | None = None
    average_traded_price: float | None = None
    open_interest: int | None = None
