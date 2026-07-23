import pytest

from nse_algo_trader.broker_oms import OrderIntent, OrderSide, SimulatedBrokerClient
from nse_algo_trader.paper_trading import (
    FillSlippageConfig,
    estimate_slipped_fill_price,
    make_slippage_fill_adjuster,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)
from datetime import date

CASH = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)


def _option(premium_kind_price_ignored=True) -> Instrument:
    return Instrument(
        instrument_token=1, trading_symbol="NIFTY25000CE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=65, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=25000.0, option_right=OptionRight.CALL, expiry_date=date(2026, 7, 30),
    )


def _buy(instrument):
    return OrderIntent(instrument, OrderSide.BUY, instrument.lot_size, "t")


def _sell(instrument):
    return OrderIntent(instrument, OrderSide.SELL, instrument.lot_size, "t")


class TestSlippageDirection:
    def test_buyer_pays_up_seller_receives_less(self):
        buy_fill = estimate_slipped_fill_price(_buy(CASH), 1000.0)
        sell_fill = estimate_slipped_fill_price(_sell(CASH), 1000.0)
        assert buy_fill > 1000.0 > sell_fill
        assert buy_fill - 1000.0 == pytest.approx(1000.0 - sell_fill)  # symmetric

    def test_cash_half_spread_is_3bps(self):
        assert estimate_slipped_fill_price(_buy(CASH), 1000.0) == pytest.approx(1000.3)


class TestOptionSpreadsAreWider:
    def test_atm_option_spread_far_exceeds_cash(self):
        option_slip = estimate_slipped_fill_price(_buy(_option()), 200.0) - 200.0
        cash_slip = estimate_slipped_fill_price(_buy(CASH), 200.0) - 200.0
        assert option_slip > cash_slip * 5

    def test_cheap_far_otm_option_has_the_widest_relative_spread(self):
        cheap_premium = 2.0
        fill = estimate_slipped_fill_price(_buy(_option()), cheap_premium)
        # base 0.5% + extra 10% of premium -> ~10.5% half-spread on Rs.2
        relative_half_spread = (fill - cheap_premium) / cheap_premium
        assert relative_half_spread > 0.10

    def test_minimum_half_spread_is_at_least_half_a_tick(self):
        # a Rs.0.10 option: bps spread is tiny, floor kicks in
        fill = estimate_slipped_fill_price(_buy(_option()), 0.10)
        assert fill - 0.10 == pytest.approx(0.025)

    def test_fill_never_goes_below_one_tick(self):
        assert estimate_slipped_fill_price(_sell(_option()), 0.05) >= 0.05


class TestWiringIntoSimulatedBroker:
    def test_adjuster_shifts_broker_fills(self):
        broker = SimulatedBrokerClient(fill_price_adjuster=make_slippage_fill_adjuster())
        broker.update_market_price(408065, 1000.0)
        result = broker.place_order(_buy(CASH))
        assert result.average_fill_price == pytest.approx(1000.3)
