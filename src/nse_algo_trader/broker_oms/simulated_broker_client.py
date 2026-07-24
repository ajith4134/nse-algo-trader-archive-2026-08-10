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
    OrderType,
    convert_option_stop_market_to_buffered_limit,
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
        # SL / SL-M orders accepted but awaiting their trigger price.
        self._pending_trigger_orders: dict[str, OrderIntent] = {}

    def update_market_price(self, instrument_token: int, last_price: float) -> None:
        self._last_known_price_by_token[instrument_token] = last_price
        self._evaluate_pending_triggers(instrument_token, last_price)

    def _trigger_is_crossed(self, order_intent: OrderIntent, price: float) -> bool:
        # BUY stop fires when price rises to/through the trigger; SELL stop
        # fires when price falls to/through it (research/40).
        if order_intent.side is OrderSide.BUY:
            return price >= order_intent.trigger_price
        return price <= order_intent.trigger_price

    def _evaluate_pending_triggers(self, instrument_token: int, price: float) -> None:
        for order_id, order_intent in list(self._pending_trigger_orders.items()):
            if order_intent.instrument.instrument_token != instrument_token:
                continue
            if self._trigger_is_crossed(order_intent, price):
                del self._pending_trigger_orders[order_id]
                # SL -> LIMIT at limit_price; SL-M -> MARKET at current price.
                reference = (
                    order_intent.limit_price
                    if order_intent.order_type is OrderType.STOP_LIMIT
                    else price
                )
                self._results_by_order_id[order_id] = self._execute_fill(
                    order_id, order_intent, reference
                )

    def net_position_quantity(self, instrument_token: int) -> int:
        return self._net_position_by_token.get(instrument_token, 0)

    def place_order(self, order_intent: OrderIntent) -> OrderExecutionResult:
        # Model the same exchange rule the live path applies (research/40):
        # an option SL-M becomes a buffered SL-limit, so paper == live.
        order_intent = convert_option_stop_market_to_buffered_limit(order_intent)
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

        # SL / SL-M: if the trigger is not yet crossed, hold trigger-pending
        # (fills later via update_market_price); if already crossed, fill now.
        if order_intent.is_stop_order() and not self._trigger_is_crossed(
            order_intent, known_price
        ):
            self._pending_trigger_orders[simulated_order_id] = order_intent
            pending = OrderExecutionResult(
                broker_order_id=simulated_order_id,
                state=OrderLifecycleState.TRIGGER_PENDING,
                filled_quantity=0,
                average_fill_price=None,
            )
            self._results_by_order_id[simulated_order_id] = pending
            return pending

        reference_price = (
            order_intent.limit_price
            if order_intent.limit_price is not None
            and order_intent.order_type is not OrderType.STOP_MARKET
            else known_price
        )
        result = self._execute_fill(simulated_order_id, order_intent, reference_price)
        self._results_by_order_id[simulated_order_id] = result
        return result

    def _execute_fill(
        self, order_id: str, order_intent: OrderIntent, reference_price: float
    ) -> OrderExecutionResult:
        fill_price = reference_price
        if self._fill_price_adjuster is not None:
            fill_price = self._fill_price_adjuster(order_intent, fill_price)
        signed_quantity = (
            order_intent.quantity
            if order_intent.side is OrderSide.BUY
            else -order_intent.quantity
        )
        token = order_intent.instrument.instrument_token
        self._net_position_by_token[token] = (
            self._net_position_by_token.get(token, 0) + signed_quantity
        )
        return OrderExecutionResult(
            broker_order_id=order_id,
            state=OrderLifecycleState.COMPLETE,
            filled_quantity=order_intent.quantity,
            average_fill_price=fill_price,
        )

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
