"""The BrokerClient protocol — the paper/live parity boundary (PLAN §1).

Strategy/risk/session code depends only on this interface. A single
config value decides whether the constructed implementation is
`SimulatedBrokerClient` (paper) or `KiteBrokerClient` (live); nothing
downstream can tell the difference.
"""

from typing import Protocol, runtime_checkable

from nse_algo_trader.broker_oms.order_types import OrderExecutionResult, OrderIntent


@runtime_checkable
class BrokerClient(Protocol):
    def place_order(self, order_intent: OrderIntent) -> OrderExecutionResult: ...

    def fetch_order_result(self, broker_order_id: str) -> OrderExecutionResult: ...

    def cancel_order(self, broker_order_id: str) -> None: ...
