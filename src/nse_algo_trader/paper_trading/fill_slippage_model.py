"""Realistic fill slippage/spread model for paper trading (PLAN §1.2).

The gap every existing paper engine leaves unmodeled: options have much
wider bid-ask spreads than cash equity, and far-OTM / cheap-premium
strikes are wider still (a Rs.2 option can quote 1.8/2.2 — a 20% spread).
A paper fill that ignores this flatters every strategy. This model makes
the taker pay: buys fill above the reference, sells fill below, by a
half-spread that scales with instrument kind and (for options) how cheap
the premium is. Plugs into `SimulatedBrokerClient.fill_price_adjuster`.

Defaults are conservative v1 estimates, tunable, and — like every other
parameter — subject to later calibration against real fills (Rule F: once
live/paper fills exist, compare modeled vs realized slippage).
"""

from dataclasses import dataclass

from nse_algo_trader.broker_oms import OrderIntent, OrderSide
from nse_algo_trader.universe_registry import InstrumentKind

_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)


@dataclass(frozen=True)
class FillSlippageConfig:
    cash_equity_half_spread_bps: float = 3.0  # ~3 bps half-spread, liquid cash
    option_half_spread_bps: float = 50.0  # ~0.5% half-spread, near-ATM options
    cheap_option_premium_threshold: float = 10.0  # premium below this = illiquid/far-OTM
    cheap_option_extra_half_spread_fraction: float = 0.10  # +10% of premium
    minimum_half_spread_rupees: float = 0.025  # at least half a 0.05 tick


def estimate_slipped_fill_price(
    order_intent: OrderIntent,
    reference_price: float,
    config: FillSlippageConfig = FillSlippageConfig(),
) -> float:
    if order_intent.instrument.kind in _OPTION_INSTRUMENT_KINDS:
        half_spread = reference_price * config.option_half_spread_bps / 10_000.0
        if reference_price <= config.cheap_option_premium_threshold:
            half_spread += reference_price * config.cheap_option_extra_half_spread_fraction
    else:
        half_spread = reference_price * config.cash_equity_half_spread_bps / 10_000.0
    half_spread = max(half_spread, config.minimum_half_spread_rupees)

    taker_direction = 1.0 if order_intent.side is OrderSide.BUY else -1.0
    slipped_price = reference_price + taker_direction * half_spread
    return max(slipped_price, 0.05)  # never below one tick


def make_slippage_fill_adjuster(config: FillSlippageConfig = FillSlippageConfig()):
    """Returns a fill_price_adjuster(order_intent, reference_price) for
    SimulatedBrokerClient — the concrete wiring of this model into paper
    fills."""
    return lambda order_intent, reference_price: estimate_slipped_fill_price(
        order_intent, reference_price, config
    )
