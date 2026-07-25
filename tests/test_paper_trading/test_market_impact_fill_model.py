"""§53 slice 5c-ii — market-impact fill model (hermetic). Square-root monotonicity, the
unknown-liquidity safety (ADQ≤0 → no impact), taker direction, and the backward-compatible
composition into the fill-slippage path."""

import math

import pytest

from nse_algo_trader.broker_oms import OrderIntent, OrderSide
from nse_algo_trader.paper_trading.fill_slippage_model import (
    estimate_slipped_fill_price,
    slipped_fill_price,
)
from nse_algo_trader.paper_trading.market_impact_fill_model import (
    MarketImpactConfig,
    apply_market_impact_to_price,
    estimate_market_impact_bps,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

_CFG = MarketImpactConfig(impact_coefficient_bps=30.0, max_impact_bps=150.0)


def _cash() -> Instrument:
    return Instrument(
        instrument_token=1, trading_symbol="INFY",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def test_impact_is_zero_when_liquidity_unknown():
    assert estimate_market_impact_bps(1000, 0, _CFG) == 0.0
    assert estimate_market_impact_bps(1000, -5, _CFG) == 0.0
    assert estimate_market_impact_bps(0, 1_000_000, _CFG) == 0.0


def test_square_root_law_value_and_monotonicity():
    adq = 1_000_000
    # 100% participation -> coefficient exactly; sqrt law.
    assert estimate_market_impact_bps(adq, adq, _CFG) == pytest.approx(30.0)
    assert estimate_market_impact_bps(adq // 4, adq, _CFG) == pytest.approx(30.0 * 0.5)  # 25%->sqrt .5
    small = estimate_market_impact_bps(adq // 100, adq, _CFG)
    big = estimate_market_impact_bps(adq // 2, adq, _CFG)
    assert small < big  # bigger order -> more impact


def test_impact_is_capped():
    # order 100x the ADV -> sqrt(100)=10x coefficient=300bps, capped to 150.
    assert estimate_market_impact_bps(100_000_000, 1_000_000, _CFG) == 150.0


def test_apply_impact_taker_direction():
    assert apply_market_impact_to_price(100.0, OrderSide.BUY, 50.0) > 100.0   # buy fills higher
    assert apply_market_impact_to_price(100.0, OrderSide.SELL, 50.0) < 100.0  # sell fills lower


def test_fill_price_backward_compatible_without_adq():
    # No ADQ passed -> identical to the old spread-only fill.
    intent = OrderIntent(_cash(), OrderSide.BUY, 100, "x")
    assert estimate_slipped_fill_price(intent, 100.0) == estimate_slipped_fill_price(
        intent, 100.0, average_daily_quantity=None
    )


def test_fill_price_adds_impact_and_grows_with_size():
    small = slipped_fill_price(_cash(), OrderSide.BUY, 100.0, order_quantity=100,
                               average_daily_quantity=1_000_000)
    large = slipped_fill_price(_cash(), OrderSide.BUY, 100.0, order_quantity=200_000,
                               average_daily_quantity=1_000_000)
    spread_only = slipped_fill_price(_cash(), OrderSide.BUY, 100.0, order_quantity=100)
    assert small >= spread_only            # impact only adds cost to a buy
    assert large > small                   # a bigger buy pays more
