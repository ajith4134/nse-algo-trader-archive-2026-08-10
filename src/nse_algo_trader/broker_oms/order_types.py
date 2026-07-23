"""Order data model for Layer 6 — what the OMS places and reports.

An `OrderIntent` is the broker-neutral instruction built from an
approved signal; an `OrderExecutionResult` is what any BrokerClient
reports back. Both are identical across paper and live — the parity
contract (`docs/PLAN.md` §1) lives in these types.
"""

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.universe_registry import Instrument


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderLifecycleState(str, Enum):
    OPEN = "open"  # accepted by broker, not yet fully filled
    COMPLETE = "complete"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class OrderIntent:
    instrument: Instrument
    side: OrderSide
    quantity: int  # always shares, never lots
    strategy_tag: str
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("order quantity must be at least 1 share")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require a limit_price")


@dataclass(frozen=True)
class OrderExecutionResult:
    broker_order_id: str
    state: OrderLifecycleState
    filled_quantity: int
    average_fill_price: float | None
    rejection_message: str | None = None
