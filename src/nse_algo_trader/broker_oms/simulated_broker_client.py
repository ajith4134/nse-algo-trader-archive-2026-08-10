"""Paper-mode BrokerClient — in-memory fills against known market prices.

v1 fills market orders instantly at the last known reference price. The
realistic options bid-ask/slippage model (PLAN §1.2) is a Layer 7
deliverable and will plug in via `fill_price_adjuster` — the hook exists
now so Layer 7 extends this client instead of forking it.
"""

import itertools
from collections.abc import Callable

from nse_algo_trader.broker_oms.order_types import (
    OrderExecutionResult,
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
)


class SimulatedBrokerClient:
    def __init__(
        self,
        fill_price_adjuster: Callable[[OrderIntent, float], float] | None = None,
    ) -> None:
        self._last_known_price_by_token: dict[int, float] = {}
        self._net_position_by_token: dict[int, int] = {}
        self._results_by_order_id: dict[str, OrderExecutionResult] = {}
        self._order_id_counter = itertools.count(1)
        self._fill_price_adjuster = fill_price_adjuster

    def update_market_price(self, instrument_token: int, last_price: float) -> None:
        self._last_known_price_by_token[instrument_token] = last_price

    def net_position_quantity(self, instrument_token: int) -> int:
        return self._net_position_by_token.get(instrument_token, 0)

    def place_order(self, order_intent: OrderIntent) -> OrderExecutionResult:
        simulated_order_id = f"SIM-{next(self._order_id_counter)}"
        token = order_intent.instrument.instrument_token
        known_price = self._last_known_price_by_token.get(token)
        if known_price is None:
            result = OrderExecutionResult(
                broker_order_id=simulated_order_id,
                state=OrderLifecycleState.REJECTED,
                filled_quantity=0,
                average_fill_price=None,
                rejection_message=(
                    f"no market price known for token {token} "
                    f"({order_intent.instrument.trading_symbol})"
                ),
            )
            self._results_by_order_id[simulated_order_id] = result
            return result

        fill_price = known_price
        if order_intent.limit_price is not None:
            fill_price = order_intent.limit_price
        if self._fill_price_adjuster is not None:
            fill_price = self._fill_price_adjuster(order_intent, fill_price)

        signed_quantity = (
            order_intent.quantity
            if order_intent.side is OrderSide.BUY
            else -order_intent.quantity
        )
        self._net_position_by_token[token] = (
            self._net_position_by_token.get(token, 0) + signed_quantity
        )
        result = OrderExecutionResult(
            broker_order_id=simulated_order_id,
            state=OrderLifecycleState.COMPLETE,
            filled_quantity=order_intent.quantity,
            average_fill_price=fill_price,
        )
        self._results_by_order_id[simulated_order_id] = result
        return result

    def fetch_order_result(self, broker_order_id: str) -> OrderExecutionResult:
        return self._results_by_order_id[broker_order_id]

    def cancel_order(self, broker_order_id: str) -> None:
        existing_result = self._results_by_order_id[broker_order_id]
        if existing_result.state is OrderLifecycleState.OPEN:
            self._results_by_order_id[broker_order_id] = OrderExecutionResult(
                broker_order_id=broker_order_id,
                state=OrderLifecycleState.CANCELLED,
                filled_quantity=existing_result.filled_quantity,
                average_fill_price=existing_result.average_fill_price,
            )
