"""Order-type taxonomy validation + SL/SL-M trigger emulation (research/40)."""

import pytest

from nse_algo_trader.broker_oms import (
    OrderIntent,
    OrderLifecycleState,
    OrderSide,
    OrderType,
    OrderVariety,
    SimulatedBrokerClient,
    TimeInForce,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

STOCK = Instrument(
    instrument_token=111, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05,
)


class TestOrderIntentValidation:
    def test_stop_limit_requires_limit_and_trigger(self):
        with pytest.raises(ValueError):
            OrderIntent(STOCK, OrderSide.SELL, 10, "t", order_type=OrderType.STOP_LIMIT,
                        trigger_price=95.0)  # missing limit_price
        with pytest.raises(ValueError):
            OrderIntent(STOCK, OrderSide.SELL, 10, "t", order_type=OrderType.STOP_LIMIT,
                        limit_price=95.0)  # missing trigger_price

    def test_stop_market_requires_trigger_only(self):
        ok = OrderIntent(STOCK, OrderSide.SELL, 10, "t",
                         order_type=OrderType.STOP_MARKET, trigger_price=95.0)
        assert ok.is_stop_order()
        with pytest.raises(ValueError):
            OrderIntent(STOCK, OrderSide.SELL, 10, "t", order_type=OrderType.STOP_MARKET)

    def test_ttl_requires_minutes_and_iceberg_requires_legs(self):
        with pytest.raises(ValueError):
            OrderIntent(STOCK, OrderSide.BUY, 10, "t", time_in_force=TimeInForce.TIME_TO_LIVE)
        with pytest.raises(ValueError):
            OrderIntent(STOCK, OrderSide.BUY, 10, "t", variety=OrderVariety.ICEBERG)
        with pytest.raises(ValueError):
            OrderIntent(STOCK, OrderSide.BUY, 10, "t", variety=OrderVariety.COVER)  # no trigger

    def test_plain_market_order_still_works(self):
        intent = OrderIntent(STOCK, OrderSide.BUY, 10, "t")
        assert intent.order_type is OrderType.MARKET
        assert not intent.is_stop_order()


class TestSimulatedStopOrders:
    def test_sell_stop_market_holds_then_fires_on_downtick(self):
        broker = SimulatedBrokerClient()
        broker.update_market_price(STOCK.instrument_token, 100.0)
        # protective sell stop below the market -> pending
        stop = OrderIntent(STOCK, OrderSide.SELL, 10, "stop",
                           order_type=OrderType.STOP_MARKET, trigger_price=95.0)
        result = broker.place_order(stop)
        assert result.state is OrderLifecycleState.TRIGGER_PENDING
        # price drifts down through the trigger -> fires at market
        broker.update_market_price(STOCK.instrument_token, 94.5)
        fired = broker.fetch_order_result(result.broker_order_id)
        assert fired.state is OrderLifecycleState.COMPLETE
        assert fired.average_fill_price == 94.5
        assert broker.net_position_quantity(STOCK.instrument_token) == -10

    def test_buy_stop_limit_fires_at_limit_on_uptick(self):
        broker = SimulatedBrokerClient()
        broker.update_market_price(STOCK.instrument_token, 100.0)
        stop = OrderIntent(STOCK, OrderSide.BUY, 5, "breakout",
                           order_type=OrderType.STOP_LIMIT, trigger_price=105.0,
                           limit_price=105.5)
        result = broker.place_order(stop)
        assert result.state is OrderLifecycleState.TRIGGER_PENDING
        broker.update_market_price(STOCK.instrument_token, 105.2)  # crosses trigger
        fired = broker.fetch_order_result(result.broker_order_id)
        assert fired.state is OrderLifecycleState.COMPLETE
        assert fired.average_fill_price == 105.5  # SL fills at limit

    def test_stop_already_crossed_fills_immediately(self):
        broker = SimulatedBrokerClient()
        broker.update_market_price(STOCK.instrument_token, 90.0)
        # sell stop trigger 95 with price already 90 (already below) -> fill now
        stop = OrderIntent(STOCK, OrderSide.SELL, 10, "stop",
                           order_type=OrderType.STOP_MARKET, trigger_price=95.0)
        result = broker.place_order(stop)
        assert result.state is OrderLifecycleState.COMPLETE
