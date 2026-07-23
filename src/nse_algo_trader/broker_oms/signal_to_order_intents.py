"""Bridges Layer 4 signals + Layer 5 approvals into broker-neutral orders.

The ONLY place signal objects become OrderIntents, so quantities
(risk-approved, converted lots -> shares here), strategy tags, and leg
ordering rules live in exactly one spot.
"""

from nse_algo_trader.broker_oms.order_types import OrderIntent, OrderSide
from nse_algo_trader.strategy_engine import (
    CreditSpreadSignal,
    OpeningRangeBreakoutSignal,
    OptionLegAction,
    SignalDirection,
)


def build_order_intent_for_opening_range_breakout(
    signal: OpeningRangeBreakoutSignal, risk_approved_share_quantity: int
) -> OrderIntent:
    return OrderIntent(
        instrument=signal.instrument,
        side=(
            OrderSide.BUY
            if signal.direction is SignalDirection.LONG
            else OrderSide.SELL
        ),
        quantity=risk_approved_share_quantity,
        strategy_tag=signal.strategy_tag,
    )


def build_order_intents_for_credit_spread(
    signal: CreditSpreadSignal, risk_approved_lots: int
) -> list[OrderIntent]:
    """Hedge BUY first, short SELL second — the atomic executor preserves
    this ordering guarantee (and re-enforces it defensively)."""
    intents = []
    for leg in (signal.hedge_leg, signal.short_leg):
        intents.append(
            OrderIntent(
                instrument=leg.instrument,
                side=(
                    OrderSide.BUY
                    if leg.action is OptionLegAction.BUY
                    else OrderSide.SELL
                ),
                quantity=risk_approved_lots * leg.instrument.lot_size,
                strategy_tag=signal.strategy_tag,
            )
        )
    return intents
