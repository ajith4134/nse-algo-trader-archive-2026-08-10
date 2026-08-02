"""BLIND BUILD (rule-calibration experiment, research/157) — a limit order book + matching engine built
ONLY from the NautilusTrader README spec, following the current Rule P + building-engine-grade-features
skill, WITHOUT looking at NautilusTrader's real code. This is the artifact to diff against the real module.

README-derived spec: event-driven matching engine, order book management, order types (IOC/FOK/GTC/GTD/
DAY/AT_THE_OPEN/AT_THE_CLOSE), execution instructions (post-only, reduce-only, iceberg), contingency
orders (OCO/OUO/OTO), nanosecond-resolution timing, deterministic behaviour.
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(str, Enum):
    GTC = "GTC"   # good-till-cancel
    IOC = "IOC"   # immediate-or-cancel (fill what you can, cancel the rest)
    FOK = "FOK"   # fill-or-kill (all or nothing)
    DAY = "DAY"


@dataclass
class Order:
    order_id: int
    side: Side
    price: float
    quantity: float
    time_in_force: TimeInForce = TimeInForce.GTC
    post_only: bool = False
    reduce_only: bool = False
    ts_ns: int = 0                 # nanosecond timestamp (README: nanosecond-resolution timing)
    filled_quantity: float = 0.0

    @property
    def remaining(self) -> float:
        return self.quantity - self.filled_quantity

    @property
    def is_filled(self) -> bool:
        return self.remaining <= 0


@dataclass
class Fill:
    taker_order_id: int
    maker_order_id: int
    price: float
    quantity: float
    ts_ns: int


@dataclass
class MatchResult:
    fills: list = field(default_factory=list)
    accepted: bool = False
    resting_order_id: int | None = None   # if the remainder rested on the book
    rejected_reason: str = ""


class LimitOrderBook:
    """A price-time-priority limit order book with a matching engine.

    Bids sorted high→low, asks low→high; each price level is a FIFO queue (time priority). `submit`
    matches an incoming order against the opposite side, produces fills, and rests any remainder per its
    time-in-force. Deterministic given the same input sequence (README: deterministic runtime)."""

    def __init__(self, instrument: str):
        self.instrument = instrument
        self._bids: dict[float, deque] = {}   # price -> deque[Order]
        self._asks: dict[float, deque] = {}
        self._orders: dict[int, Order] = {}
        self._id_seq = itertools.count(1)

    # -- top of book ---------------------------------------------------------------------------------
    def best_bid(self) -> float | None:
        return max(self._bids) if self._bids else None

    def best_ask(self) -> float | None:
        return min(self._asks) if self._asks else None

    def spread(self) -> float | None:
        b, a = self.best_bid(), self.best_ask()
        return (a - b) if (b is not None and a is not None) else None

    # -- submit / match ------------------------------------------------------------------------------
    def submit(self, side: Side, price: float, quantity: float,
               time_in_force: TimeInForce = TimeInForce.GTC, post_only: bool = False,
               ts_ns: int = 0) -> MatchResult:
        if quantity <= 0 or price <= 0:
            return MatchResult(rejected_reason="quantity and price must be positive")

        order = Order(next(self._id_seq), side, price, quantity, time_in_force, post_only, ts_ns=ts_ns)
        opposite = self._asks if side is Side.BUY else self._bids

        # post-only: reject if it would cross (it must be a maker).
        if post_only and self._would_cross(side, price):
            return MatchResult(rejected_reason="post_only order would cross the spread")

        # FOK: only match if fully fillable now.
        if time_in_force is TimeInForce.FOK and self._available_liquidity(side, price) < quantity:
            return MatchResult(rejected_reason="FOK not fully fillable")

        fills = self._match(order, opposite)

        result = MatchResult(fills=fills, accepted=True)
        if not order.is_filled:
            if time_in_force is TimeInForce.IOC:
                pass  # cancel the remainder
            else:
                self._rest(order)
                result.resting_order_id = order.order_id
        return result

    def _would_cross(self, side: Side, price: float) -> bool:
        if side is Side.BUY:
            ask = self.best_ask()
            return ask is not None and price >= ask
        bid = self.best_bid()
        return bid is not None and price <= bid

    def _available_liquidity(self, side: Side, price: float) -> float:
        book = self._asks if side is Side.BUY else self._bids
        crosses = (lambda lvl: lvl <= price) if side is Side.BUY else (lambda lvl: lvl >= price)
        return sum(sum(o.remaining for o in q) for lvl, q in book.items() if crosses(lvl))

    def _match(self, order: Order, opposite: dict) -> list:
        fills = []
        while not order.is_filled and opposite:
            best_level = min(opposite) if order.side is Side.BUY else max(opposite)
            crosses = (order.price >= best_level) if order.side is Side.BUY else (order.price <= best_level)
            if not crosses:
                break
            queue = opposite[best_level]
            while queue and not order.is_filled:
                maker = queue[0]
                traded = min(order.remaining, maker.remaining)
                order.filled_quantity += traded
                maker.filled_quantity += traded
                fills.append(Fill(order.order_id, maker.order_id, best_level, traded, order.ts_ns))
                if maker.is_filled:
                    queue.popleft()
                    self._orders.pop(maker.order_id, None)
            if not queue:
                del opposite[best_level]
        return fills

    def _rest(self, order: Order) -> None:
        book = self._bids if order.side is Side.BUY else self._asks
        book.setdefault(order.price, deque()).append(order)
        self._orders[order.order_id] = order

    def cancel(self, order_id: int) -> bool:
        order = self._orders.get(order_id)
        if order is None:
            return False
        book = self._bids if order.side is Side.BUY else self._asks
        queue = book.get(order.price)
        if queue and order in queue:
            queue.remove(order)
            if not queue:
                del book[order.price]
        self._orders.pop(order_id, None)
        return True
