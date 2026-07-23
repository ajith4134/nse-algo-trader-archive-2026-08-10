"""Layer 6 — Broker Integration & OMS (paper/live parity boundary).

`BrokerClient` is the only surface strategies/risk/session code touch;
`SimulatedBrokerClient` (paper) and `KiteBrokerClient` (live) implement
it identically. Multi-leg atomicity and the SEBI order-rate throttle
live here.
"""

from nse_algo_trader.broker_oms.atomic_multi_leg_executor import (
    MultiLegExecutionReport,
    execute_multi_leg_order_atomically,
)
from nse_algo_trader.broker_oms.broker_client_protocol import BrokerClient
from nse_algo_trader.broker_oms.kite_broker_client import KiteBrokerClient
from nse_algo_trader.broker_oms.order_rate_limiter import OrderRateLimiter
from nse_algo_trader.broker_oms.order_types import (
    OrderExecutionResult,
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
    OrderType,
)
from nse_algo_trader.broker_oms.signal_to_order_intents import (
    build_order_intent_for_opening_range_breakout,
    build_order_intents_for_credit_spread,
)
from nse_algo_trader.broker_oms.simulated_broker_client import SimulatedBrokerClient

__all__ = [
    "BrokerClient",
    "KiteBrokerClient",
    "MultiLegExecutionReport",
    "OrderExecutionResult",
    "OrderIntent",
    "OrderLifecycleState",
    "OrderRateLimiter",
    "OrderSide",
    "OrderType",
    "SimulatedBrokerClient",
    "build_order_intent_for_opening_range_breakout",
    "build_order_intents_for_credit_spread",
    "execute_multi_leg_order_atomically",
]
