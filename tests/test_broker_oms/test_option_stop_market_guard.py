"""The SL-M-on-options guard (research/40): NSE blocks SL-M for options, so
the OMS must auto-convert an option SL-M to a buffered SL-limit. Cash/futures
keep true SL-M. Applied on BOTH broker clients so paper == live."""

from datetime import date

from nse_algo_trader.broker_oms import (
    OrderIntent,
    OrderSide,
    OrderType,
    convert_option_stop_market_to_buffered_limit,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

CASH = Instrument(
    instrument_token=1, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05,
)
OPTION = Instrument(
    instrument_token=2, trading_symbol="NIFTY2673023600CE",
    exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
    lot_size=75, tick_size=0.05, underlying_symbol="NIFTY", strike_price=23600.0,
    option_right=OptionRight.CALL, expiry_date=date(2026, 7, 30),
)


class TestOptionStopMarketGuard:
    def test_option_sell_slm_becomes_buffered_sl_limit_below_trigger(self):
        intent = OrderIntent(OPTION, OrderSide.SELL, 75, "spread",
                             order_type=OrderType.STOP_MARKET, trigger_price=100.0)
        out = convert_option_stop_market_to_buffered_limit(intent, buffer_fraction=0.05)
        assert out.order_type is OrderType.STOP_LIMIT
        assert out.limit_price is not None and out.limit_price < 100.0  # sell fills down

    def test_option_buy_slm_becomes_buffered_sl_limit_above_trigger(self):
        intent = OrderIntent(OPTION, OrderSide.BUY, 75, "cover",
                             order_type=OrderType.STOP_MARKET, trigger_price=100.0)
        out = convert_option_stop_market_to_buffered_limit(intent, buffer_fraction=0.05)
        assert out.order_type is OrderType.STOP_LIMIT
        assert out.limit_price is not None and out.limit_price > 100.0  # buy fills up

    def test_cash_slm_is_left_as_true_slm(self):
        intent = OrderIntent(CASH, OrderSide.SELL, 100, "orb",
                             order_type=OrderType.STOP_MARKET, trigger_price=1000.0)
        out = convert_option_stop_market_to_buffered_limit(intent)
        assert out.order_type is OrderType.STOP_MARKET  # cash keeps SL-M
        assert out is intent

    def test_option_limit_order_is_untouched(self):
        intent = OrderIntent(OPTION, OrderSide.SELL, 75, "spread",
                             order_type=OrderType.LIMIT, limit_price=88.0)
        out = convert_option_stop_market_to_buffered_limit(intent)
        assert out is intent

    def test_buffered_limit_is_rounded_to_tick(self):
        intent = OrderIntent(OPTION, OrderSide.SELL, 75, "spread",
                             order_type=OrderType.STOP_MARKET, trigger_price=100.0)
        out = convert_option_stop_market_to_buffered_limit(intent, buffer_fraction=0.05)
        # limit must land on a 0.05 tick
        assert abs((out.limit_price / 0.05) - round(out.limit_price / 0.05)) < 1e-9
