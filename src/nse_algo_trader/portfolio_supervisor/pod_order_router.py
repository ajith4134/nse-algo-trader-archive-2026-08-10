"""Pod order router — turns the supervisor's ``ArbitratedOrder``s into real broker orders (execution wiring).

The supervisor decides WHAT and HOW MUCH; this routes it to the execution seam. For each accepted order it
resolves the concrete tradable ``Instrument`` (a cash equity, or each option leg from its moneyness offset +
the reference spot + expiry) via an injected ``InstrumentResolver``, builds ``OrderIntent``s, and places
them through the injected ``BrokerClient`` (the SimulatedBrokerClient in paper, the live client in
production — both behind the same protocol). This is the consumer that makes the 3-bot pod actually trade.

Instrument resolution over the full live option universe is the injected seam (production wires it to
``live_tradable_universe``; tests inject a fake). Multi-leg option structures place leg-by-leg here; routing
them through the existing ``atomic_multi_leg_executor`` for all-or-nothing fills is a named refinement (Rule K).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from nse_algo_trader.broker_oms.order_types import OrderExecutionResult, OrderIntent, OrderSide
from nse_algo_trader.portfolio_supervisor.proposal_arbiter import ArbitratedOrder, ArbitrationOutcome
from nse_algo_trader.segment_bots.segment_bot_protocol import OptionStructureKind, TradeSide
from nse_algo_trader.universe_registry.instrument_types import Instrument


_INDEX_UNDERLYINGS = frozenset(
    {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX", "BANKEX"})


def _is_index(underlying: str) -> bool:
    return str(underlying) in _INDEX_UNDERLYINGS


class InstrumentResolver(Protocol):
    """DI seam resolving an abstract leg to a concrete tradable instrument. Production = universe registry."""

    def reference_spot(self, underlying: str) -> float | None: ...
    def resolve_cash(self, symbol: str) -> Instrument | None: ...
    def resolve_option_leg(
        self, underlying: str, option_right: str, moneyness_offset: float, expiry: str
    ) -> Instrument | None: ...


@dataclass(frozen=True)
class PlacedPodOrder:
    """The result of routing one arbitrated order: the intents built + the broker results."""

    arbitrated: ArbitratedOrder
    intents: tuple[OrderIntent, ...]
    results: tuple[OrderExecutionResult, ...]
    unresolved_legs: int = 0
    field_notes: dict = field(default_factory=dict)


class PodOrderRouter:
    """Routes accepted arbitrated orders to the broker via a resolver + the broker-client seam."""

    def __init__(self, broker_client, resolver: InstrumentResolver, strategy_tag: str = "segment_bot_pod",
                 live_instrument_resolver=None):
        self._broker = broker_client
        self._resolver = resolver
        self._tag = strategy_tag
        self._live_resolver = live_instrument_resolver  # resolves a synthesized leg to its REAL Kite contract

    def route(self, orders: list[ArbitratedOrder]) -> list[PlacedPodOrder]:
        placed: list[PlacedPodOrder] = []
        for order in orders:
            if order.outcome == ArbitrationOutcome.VETO or order.approved_lots <= 0:
                continue  # vetoed / zero-size orders never reach the broker
            if order.proposal.structure.kind == OptionStructureKind.NONE:
                placed.append(self._route_cash(order))
            else:
                placed.append(self._route_option_structure(order))
        return placed

    def _route_cash(self, order: ArbitratedOrder) -> PlacedPodOrder:
        instrument = self._resolver.resolve_cash(order.proposal.underlying)
        if instrument is None:
            return PlacedPodOrder(order, (), (), unresolved_legs=1, field_notes={"reason": "cash unresolved"})
        side = OrderSide.BUY if order.proposal.side == TradeSide.LONG else OrderSide.SELL
        intent = OrderIntent(
            instrument=instrument, side=side, quantity=order.approved_lots,  # cash: lots == shares
            strategy_tag=f"{self._tag}:{order.proposal.bot_name}",
        )
        result = self._broker.place_order(intent)
        return PlacedPodOrder(order, (intent,), (result,))

    def _resolve_real_leg(self, underlying: str, leg: dict, expiry: str):
        """Resolve a synthesized leg (real strike) to its true Kite contract via the live instrument resolver."""
        strike = leg.get("strike")
        if strike is None or self._live_resolver is None:
            return None
        found = self._live_resolver.resolve_instrument(underlying, str(leg.get("right")), float(strike), expiry)
        if not found:
            return None
        from datetime import date

        from nse_algo_trader.universe_registry.instrument_types import (
            ExchangeSegment,
            InstrumentKind,
            OptionRight,
        )

        kind = InstrumentKind.INDEX_OPTION if _is_index(underlying) else InstrumentKind.STOCK_OPTION
        opt_right = OptionRight.CALL if str(leg.get("right")).upper().startswith("C") else OptionRight.PUT
        try:
            exp_date = date.fromisoformat(str(expiry)[:10])
        except (ValueError, TypeError):
            return None
        return Instrument(
            int(found["instrument_token"]), str(found["tradingsymbol"]), ExchangeSegment.NSE_FO, kind,
            max(int(found.get("lot_size", 1) or 1), 1), 0.05,
            underlying_symbol=underlying, strike_price=float(strike), option_right=opt_right, expiry_date=exp_date)

    def _route_option_structure(self, order: ArbitratedOrder) -> PlacedPodOrder:
        plan = order.proposal.structure
        intents: list[OrderIntent] = []
        results: list[OrderExecutionResult] = []
        unresolved = 0
        for leg in plan.legs:
            instrument = self._resolve_real_leg(plan.underlying, leg, plan.expiry)  # real Kite contract if synthesized
            if instrument is None:
                instrument = self._resolver.resolve_option_leg(
                    plan.underlying, str(leg.get("right")), float(leg.get("moneyness_offset", 0.0)), plan.expiry
                )
            if instrument is None:
                unresolved += 1
                continue
            side = OrderSide.BUY if str(leg.get("side")).lower() == "buy" else OrderSide.SELL
            quantity = order.approved_lots * int(leg.get("lots", 1)) * max(instrument.lot_size, 1)
            intent = OrderIntent(instrument=instrument, side=side, quantity=quantity,
                                 strategy_tag=f"{self._tag}:{order.proposal.bot_name}")
            intents.append(intent)
            results.append(self._broker.place_order(intent))
        return PlacedPodOrder(order, tuple(intents), tuple(results), unresolved_legs=unresolved)
