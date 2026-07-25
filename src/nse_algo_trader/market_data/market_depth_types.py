"""Broker-neutral order-book DEPTH model (§53 slice 4 P4b).

Historical L2 depth cannot be bought — the only way to ever have it is to record
our own forward during live sessions (research/70). These are the recorded shapes:
a `MarketDepthSnapshot` is one instrument's 5-level book at one instant.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketDepthLevel:
    """One price level of the order book."""

    price: float
    quantity: int
    orders: int


@dataclass(frozen=True)
class MarketDepthSnapshot:
    """One instrument's order book at `captured_at`. `bids` is the buy side
    (best/highest price first), `asks` the sell side (best/lowest price first)."""

    instrument_token: int
    captured_at: datetime
    bids: tuple[MarketDepthLevel, ...]
    asks: tuple[MarketDepthLevel, ...]
