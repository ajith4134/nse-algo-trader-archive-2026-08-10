"""Live BrokerClient over Zerodha Kite Connect.

Maps broker-neutral OrderIntents onto kite.place_order calls: MIS
product (intraday-only, per the project's non-negotiable), regular
variety, strategy tag carried in Kite's `tag` field (Kite caps tags at
20 chars — enforced here). Every placement passes the order-rate
throttle first; there is no untthrottled path.

Kite has no atomic multi-leg basket in its trading API (research/07 §D's
"needs verification" flag resolved: baskets are a Kite-web feature) —
atomicity is provided one level up by `atomic_multi_leg_executor`.
"""

from nse_algo_trader.broker_oms.order_rate_limiter import OrderRateLimiter
from nse_algo_trader.broker_oms.order_types import (
    OrderExecutionResult,
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
    OrderType,
    convert_option_stop_market_to_buffered_limit,
)
from nse_algo_trader.universe_registry import ExchangeSegment

_KITE_EXCHANGE_BY_SEGMENT = {
    ExchangeSegment.NSE_CASH: "NSE",
    ExchangeSegment.NSE_FO: "NFO",
}

_KITE_TAG_MAX_LENGTH = 20

_LIFECYCLE_STATE_BY_KITE_STATUS = {
    "COMPLETE": OrderLifecycleState.COMPLETE,
    "REJECTED": OrderLifecycleState.REJECTED,
    "CANCELLED": OrderLifecycleState.CANCELLED,
}


class KiteBrokerClient:
    def __init__(
        self,
        authenticated_kite_client,
        order_rate_limiter: OrderRateLimiter | None = None,
    ) -> None:
        self._kite_client = authenticated_kite_client
        self._order_rate_limiter = order_rate_limiter or OrderRateLimiter()

    def place_order(self, order_intent: OrderIntent) -> OrderExecutionResult:
        self._order_rate_limiter.wait_for_order_slot()
        # NSE blocks SL-M for options -> auto-convert to a buffered SL-limit
        # (research/40) BEFORE building the Kite payload, or the exchange
        # rejects it. No-op for cash/futures and non-SL-M orders.
        order_intent = convert_option_stop_market_to_buffered_limit(order_intent)
        # Kite order_type strings are the enum values upper-cased (market ->
        # MARKET, sl -> SL, sl-m -> SL-M). price only for LIMIT/SL;
        # trigger_price only for SL/SL-M. Product stays MIS (intraday-only).
        kite_order_type = order_intent.order_type.value.upper()
        send_price = (
            order_intent.limit_price
            if order_intent.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT)
            else None
        )
        send_trigger = (
            order_intent.trigger_price if order_intent.is_stop_order() else None
        )
        try:
            kite_order_id = self._kite_client.place_order(
                variety=order_intent.variety.value,
                exchange=_KITE_EXCHANGE_BY_SEGMENT[
                    order_intent.instrument.exchange_segment
                ],
                tradingsymbol=order_intent.instrument.trading_symbol,
                transaction_type=(
                    "BUY" if order_intent.side is OrderSide.BUY else "SELL"
                ),
                quantity=order_intent.quantity,
                product="MIS",  # intraday-only, always — project non-negotiable
                order_type=kite_order_type,
                price=send_price,
                trigger_price=send_trigger,
                validity=order_intent.time_in_force.value,
                tag=order_intent.strategy_tag[:_KITE_TAG_MAX_LENGTH],
            )
        except Exception as kite_error:  # kiteconnect raises typed exceptions
            return OrderExecutionResult(
                broker_order_id="",
                state=OrderLifecycleState.REJECTED,
                filled_quantity=0,
                average_fill_price=None,
                rejection_message=str(kite_error),
            )
        return OrderExecutionResult(
            broker_order_id=str(kite_order_id),
            state=OrderLifecycleState.OPEN,
            filled_quantity=0,
            average_fill_price=None,
        )

    def fetch_order_result(self, broker_order_id: str) -> OrderExecutionResult:
        order_history_entries = self._kite_client.order_history(broker_order_id)
        latest_entry = order_history_entries[-1]
        return OrderExecutionResult(
            broker_order_id=broker_order_id,
            state=_LIFECYCLE_STATE_BY_KITE_STATUS.get(
                latest_entry["status"], OrderLifecycleState.OPEN
            ),
            filled_quantity=int(latest_entry.get("filled_quantity", 0)),
            average_fill_price=(
                float(latest_entry["average_price"])
                if latest_entry.get("average_price")
                else None
            ),
            rejection_message=latest_entry.get("status_message") or None,
        )

    def cancel_order(self, broker_order_id: str) -> None:
        self._kite_client.cancel_order(variety="regular", order_id=broker_order_id)
