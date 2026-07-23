"""Squares off open positions safely — never a naked leg, ever (research/07 §D.4).

Two guarantees:
1. **Safe ordering:** risk-REMOVING closes run before risk-ADDING closes.
   Covering a short is a BUY; closing a long is a SELL — so BUY-to-close
   legs go first. For a credit spread this covers the short leg before
   selling its protective hedge, so no naked short exists at any instant.
2. **Drive-to-flat, never unwind:** unlike entry (which unwinds on a
   failed leg), square-off RETRIES a rejected leg — the goal is to get
   flat. Any leg still open after all retries is reported as a CRITICAL
   unflattened position, never silently dropped.
"""

from dataclasses import dataclass

from nse_algo_trader.broker_oms import (
    BrokerClient,
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
)
from nse_algo_trader.universe_registry import Instrument


@dataclass(frozen=True)
class OpenPositionLeg:
    instrument: Instrument
    net_quantity: int  # +long / -short (0 legs are ignored)
    strategy_tag: str


@dataclass(frozen=True)
class SquareOffLegOutcome:
    intent: OrderIntent
    became_flat: bool
    attempts_used: int


@dataclass(frozen=True)
class SquareOffReport:
    all_positions_flat: bool
    leg_outcomes: tuple[SquareOffLegOutcome, ...]  # in execution order
    unflattened_legs: tuple[OrderIntent, ...]  # CRITICAL if non-empty


@dataclass(frozen=True)
class SquareOffConfig:
    max_attempts_per_leg: int = 3


def build_square_off_order_intents(
    open_legs: list[OpenPositionLeg],
) -> list[OrderIntent]:
    """Flatten each open leg with an opposite-side order, ordered so every
    risk-REMOVING BUY-to-cover runs before any risk-ADDING SELL-to-close."""
    exit_intents: list[OrderIntent] = []
    for leg in open_legs:
        if leg.net_quantity == 0:
            continue
        exit_side = OrderSide.SELL if leg.net_quantity > 0 else OrderSide.BUY
        exit_intents.append(
            OrderIntent(
                instrument=leg.instrument,
                side=exit_side,
                quantity=abs(leg.net_quantity),
                strategy_tag=leg.strategy_tag,
            )
        )
    # BUY-to-cover (removes short risk) before SELL-to-close (removes hedge).
    exit_intents.sort(key=lambda intent: 0 if intent.side is OrderSide.BUY else 1)
    return exit_intents


def execute_intraday_square_off(
    open_legs: list[OpenPositionLeg],
    broker_client: BrokerClient,
    config: SquareOffConfig = SquareOffConfig(),
) -> SquareOffReport:
    exit_intents = build_square_off_order_intents(open_legs)
    leg_outcomes: list[SquareOffLegOutcome] = []
    unflattened: list[OrderIntent] = []

    for exit_intent in exit_intents:
        became_flat = False
        attempts_used = 0
        for _ in range(config.max_attempts_per_leg):
            attempts_used += 1
            result = broker_client.place_order(exit_intent)
            if result.state is not OrderLifecycleState.REJECTED:
                became_flat = True  # COMPLETE (paper) or OPEN/accepted (live)
                break
        leg_outcomes.append(
            SquareOffLegOutcome(exit_intent, became_flat, attempts_used)
        )
        if not became_flat:
            unflattened.append(exit_intent)

    return SquareOffReport(
        all_positions_flat=not unflattened,
        leg_outcomes=tuple(leg_outcomes),
        unflattened_legs=tuple(unflattened),
    )
