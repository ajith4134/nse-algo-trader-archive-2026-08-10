"""Tests for the pod order router — ArbitratedOrder → OrderIntent → broker (paper) placement."""

from __future__ import annotations

from datetime import date

import pytest

from nse_algo_trader.broker_oms.order_types import OrderSide
from nse_algo_trader.broker_oms.simulated_broker_client import SimulatedBrokerClient
from nse_algo_trader.portfolio_supervisor.pod_order_router import PodOrderRouter
from nse_algo_trader.portfolio_supervisor.proposal_arbiter import ArbitratedOrder, ArbitrationOutcome
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    MarketSegment,
    OptionStructureKind,
    OptionStructurePlan,
    TradeProposal,
    TradeSide,
)
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)


class _FakeResolver:
    """Resolves abstract legs to synthetic instruments and hands the broker their prices (Rule J seam)."""

    def __init__(self, broker: SimulatedBrokerClient):
        self._broker = broker
        self._token = 1000

    def reference_spot(self, underlying):
        return 20000.0

    def resolve_cash(self, symbol):
        self._token += 1
        inst = Instrument(self._token, symbol, ExchangeSegment.NSE_CASH, InstrumentKind.CASH_EQUITY, 1, 0.05)
        self._broker.update_market_price(self._token, 500.0)
        return inst

    def resolve_option_leg(self, underlying, option_right, moneyness_offset, expiry):
        self._token += 1
        right = OptionRight.CALL if option_right.upper().startswith("C") else OptionRight.PUT
        inst = Instrument(self._token, f"{underlying}{option_right}", ExchangeSegment.NSE_FO,
                          InstrumentKind.INDEX_OPTION, lot_size=50, tick_size=0.05,
                          underlying_symbol=underlying, strike_price=20000.0 * (1 + moneyness_offset),
                          option_right=right, expiry_date=date(2026, 8, 28))
        self._broker.update_market_price(self._token, 120.0)
        return inst


def _cash_order(side, lots) -> ArbitratedOrder:
    p = TradeProposal(MarketSegment.CASH_INTRADAY, "cash_intraday_bot:INFY", "INFY", side,
                      OptionStructurePlan(OptionStructureKind.NONE, "INFY", ""), lots, 0.7, 0.6, 0.02, 0.02,
                      1e12, "cross_sectional")
    return ArbitratedOrder(p, lots, ArbitrationOutcome.ACCEPT, "accepted")


def _option_order(lots) -> ArbitratedOrder:
    legs = ({"right": "PE", "moneyness_offset": -0.05, "side": "buy", "lots": 1},
            {"right": "PE", "moneyness_offset": -0.02, "side": "sell", "lots": 1},
            {"right": "CE", "moneyness_offset": +0.02, "side": "sell", "lots": 1},
            {"right": "CE", "moneyness_offset": +0.05, "side": "buy", "lots": 1})
    plan = OptionStructurePlan(OptionStructureKind.IRON_CONDOR, "NIFTY", "2026-08-28", legs, True, 0.0, -1.0, 1.0)
    p = TradeProposal(MarketSegment.INDEX_OPTION, "index_option_bot:NIFTY", "NIFTY", TradeSide.NEUTRAL,
                      plan, lots, 0.8, 0.6, 0.05, 0.05, 1e12, "calm")
    return ArbitratedOrder(p, lots, ArbitrationOutcome.ACCEPT, "accepted")


def test_routes_cash_order_to_broker():
    broker = SimulatedBrokerClient()
    router = PodOrderRouter(broker, _FakeResolver(broker))
    placed = router.route([_cash_order(TradeSide.LONG, 40)])
    assert len(placed) == 1
    assert placed[0].intents[0].side == OrderSide.BUY
    assert placed[0].intents[0].quantity == 40  # cash: lots == shares
    assert placed[0].results[0].filled_quantity == 40


def test_routes_all_four_option_legs():
    broker = SimulatedBrokerClient()
    router = PodOrderRouter(broker, _FakeResolver(broker))
    placed = router.route([_option_order(3)])
    assert len(placed[0].intents) == 4  # one intent per leg
    # 3 lots × lot_size 50 = 150 shares per leg
    assert all(i.quantity == 150 for i in placed[0].intents)
    buys = sum(1 for i in placed[0].intents if i.side == OrderSide.BUY)
    assert buys == 2  # the two wings are buys


def test_vetoed_and_zero_orders_are_not_routed():
    broker = SimulatedBrokerClient()
    router = PodOrderRouter(broker, _FakeResolver(broker))
    veto = ArbitratedOrder(_cash_order(TradeSide.LONG, 10).proposal, 0, ArbitrationOutcome.VETO, "expired")
    assert router.route([veto]) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
