"""Order data model for Layer 6 — what the OMS places and reports.

An `OrderIntent` is the broker-neutral instruction built from an
approved signal; an `OrderExecutionResult` is what any BrokerClient
reports back. Both are identical across paper and live — the parity
contract (`docs/PLAN.md` §1) lives in these types.
"""

from dataclasses import dataclass, replace
from enum import Enum

from nse_algo_trader.universe_registry import Instrument, InstrumentKind


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Kite order_type values (research/40)."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "sl"  # SL: on trigger -> LIMIT at limit_price
    STOP_MARKET = "sl-m"  # SL-M: on trigger -> MARKET


class ProductType(str, Enum):
    """Kite product. Intraday (MIS) is the project default + non-negotiable;
    others are modelled for completeness but not used by the intraday loop."""

    INTRADAY = "MIS"
    DELIVERY = "CNC"
    CARRY_FORWARD = "NRML"
    MARGIN_FUNDED = "MTF"


class TimeInForce(str, Enum):
    DAY = "DAY"
    IMMEDIATE_OR_CANCEL = "IOC"
    TIME_TO_LIVE = "TTL"  # needs validity_ttl_minutes


class OrderVariety(str, Enum):
    REGULAR = "regular"
    AFTER_MARKET = "amo"
    COVER = "co"  # entry + compulsory SL leg (needs trigger_price)
    ICEBERG = "iceberg"  # needs iceberg_legs 2..50
    AUCTION = "auction"


class OrderLifecycleState(str, Enum):
    OPEN = "open"  # accepted by broker, not yet fully filled
    TRIGGER_PENDING = "trigger_pending"  # SL/SL-M accepted, awaiting trigger
    COMPLETE = "complete"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


_TRIGGER_ORDER_TYPES = frozenset({OrderType.STOP_LIMIT, OrderType.STOP_MARKET})
_LIMIT_PRICE_ORDER_TYPES = frozenset({OrderType.LIMIT, OrderType.STOP_LIMIT})


@dataclass(frozen=True)
class OrderIntent:
    instrument: Instrument
    side: OrderSide
    quantity: int  # always shares, never lots
    strategy_tag: str
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    trigger_price: float | None = None  # required for SL / SL-M / CO
    product: ProductType = ProductType.INTRADAY  # intraday-only project default
    variety: OrderVariety = OrderVariety.REGULAR
    time_in_force: TimeInForce = TimeInForce.DAY
    validity_ttl_minutes: int | None = None
    disclosed_quantity: int | None = None
    iceberg_legs: int | None = None

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("order quantity must be at least 1 share")
        if self.order_type in _LIMIT_PRICE_ORDER_TYPES and self.limit_price is None:
            raise ValueError(
                f"{self.order_type.value} orders require a limit_price"
            )
        if self.order_type in _TRIGGER_ORDER_TYPES and self.trigger_price is None:
            raise ValueError(
                f"{self.order_type.value} orders require a trigger_price"
            )
        if (
            self.time_in_force is TimeInForce.TIME_TO_LIVE
            and not self.validity_ttl_minutes
        ):
            raise ValueError("TTL validity requires validity_ttl_minutes")
        if self.variety is OrderVariety.ICEBERG and not (
            self.iceberg_legs and 2 <= self.iceberg_legs <= 50
        ):
            raise ValueError("iceberg orders require iceberg_legs in 2..50")
        if self.variety is OrderVariety.COVER and self.trigger_price is None:
            raise ValueError("cover orders require a trigger_price (SL leg)")

    def is_stop_order(self) -> bool:
        return self.order_type in _TRIGGER_ORDER_TYPES


@dataclass(frozen=True)
class OrderExecutionResult:
    broker_order_id: str
    state: OrderLifecycleState
    filled_quantity: int
    average_fill_price: float | None
    rejection_message: str | None = None


# NSE has BLOCKED SL-M (stop-loss-market) for OPTIONS since 2021 (index
# options included) to curb freak trades (research/40). A raw SL-M on an
# option is rejected live. The standard workaround (Zerodha's own): send an
# SL-limit whose limit price sits a buffer BEYOND the trigger in the fill
# direction, so it fills like a market order. Cash/futures keep true SL-M.
_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)
DEFAULT_OPTION_STOP_LIMIT_BUFFER_FRACTION = 0.05


def convert_option_stop_market_to_buffered_limit(
    order_intent: OrderIntent,
    buffer_fraction: float = DEFAULT_OPTION_STOP_LIMIT_BUFFER_FRACTION,
) -> OrderIntent:
    """If (and only if) this is an SL-M on an option, return an equivalent
    buffered SL-limit; otherwise return the intent unchanged. A SELL (long
    exit) puts the limit BELOW the trigger; a BUY (short cover) ABOVE it —
    the side that guarantees a fill once the trigger is hit."""
    if (
        order_intent.order_type is not OrderType.STOP_MARKET
        or order_intent.instrument.kind not in _OPTION_INSTRUMENT_KINDS
        or order_intent.trigger_price is None
    ):
        return order_intent
    trigger = order_intent.trigger_price
    if order_intent.side is OrderSide.SELL:
        raw_limit = trigger * (1.0 - buffer_fraction)
    else:
        raw_limit = trigger * (1.0 + buffer_fraction)
    tick = order_intent.instrument.tick_size or 0.05
    buffered_limit = round(round(raw_limit / tick) * tick, 2)
    return replace(
        order_intent,
        order_type=OrderType.STOP_LIMIT,
        limit_price=buffered_limit,
    )
