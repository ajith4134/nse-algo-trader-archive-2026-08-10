"""Atomic multi-leg execution — a spread is one unit or nothing (PLAN §1.3).

Guarantees, on ANY BrokerClient (paper and live identically):
1. BUY legs always execute before SELL legs — a credit spread acquires
   its hedge first, so at no instant does a naked short exist.
2. If any leg fails, every already-executed leg is immediately unwound
   with an opposite market order, and the failure is reported with the
   unwind outcomes — never a silent half-position.
"""

from dataclasses import dataclass

from nse_algo_trader.broker_oms.broker_client_protocol import BrokerClient
from nse_algo_trader.broker_oms.order_types import (
    OrderExecutionResult,
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
    OrderType,
)


@dataclass(frozen=True)
class MultiLegExecutionReport:
    all_legs_executed: bool
    leg_results: tuple[OrderExecutionResult, ...]  # in execution order
    failed_leg_intent: OrderIntent | None
    unwind_results: tuple[OrderExecutionResult, ...]  # empty when successful


def _hedge_first_execution_order(legs: list[OrderIntent]) -> list[OrderIntent]:
    return sorted(legs, key=lambda leg: 0 if leg.side is OrderSide.BUY else 1)


def _opposite_unwind_intent(executed_leg: OrderIntent) -> OrderIntent:
    return OrderIntent(
        instrument=executed_leg.instrument,
        side=(
            OrderSide.SELL
            if executed_leg.side is OrderSide.BUY
            else OrderSide.BUY
        ),
        quantity=executed_leg.quantity,
        strategy_tag=executed_leg.strategy_tag,
        order_type=OrderType.MARKET,  # unwind at market — speed over price
    )


def execute_multi_leg_order_atomically(
    legs: list[OrderIntent], broker_client: BrokerClient
) -> MultiLegExecutionReport:
    if not legs:
        raise ValueError("cannot execute an empty leg list")
    executed_legs: list[tuple[OrderIntent, OrderExecutionResult]] = []
    for leg_intent in _hedge_first_execution_order(legs):
        leg_result = broker_client.place_order(leg_intent)
        if leg_result.state is OrderLifecycleState.REJECTED:
            unwind_results = tuple(
                broker_client.place_order(_opposite_unwind_intent(executed_intent))
                for executed_intent, _ in reversed(executed_legs)
            )
            return MultiLegExecutionReport(
                all_legs_executed=False,
                leg_results=tuple(result for _, result in executed_legs)
                + (leg_result,),
                failed_leg_intent=leg_intent,
                unwind_results=unwind_results,
            )
        executed_legs.append((leg_intent, leg_result))
    return MultiLegExecutionReport(
        all_legs_executed=True,
        leg_results=tuple(result for _, result in executed_legs),
        failed_leg_intent=None,
        unwind_results=(),
    )
