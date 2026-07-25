"""Market-impact fill model — the size-dependent half of realistic fills (§53 slice
5c-ii; research/89).

`fill_slippage_model` charges a bid-ask half-spread but ignores order size. This adds the
missing piece: a larger order moves the price more, per the standard practitioner
**square-root law** — temporary impact grows with the square root of participation
(order size / average daily volume). The taker pays it in the trade direction, on TOP of
the half-spread. Defaults are conservative v1 estimates, tunable and later calibrated
against real realized fills (Rule F, like the slippage model). PURE (no I/O).

Queue-position fills (the other realism gap) need L2 depth — recorded-forward P4b,
market-gated — and are a separate slice; this covers the impact half, buildable now from
real VOLUME.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nse_algo_trader.broker_oms import OrderSide


@dataclass(frozen=True)
class MarketImpactConfig:
    impact_coefficient_bps: float = 30.0  # bps of impact at 100% participation (sqrt=1)
    max_impact_bps: float = 150.0  # cap — never model more than a 1.5% move from impact


def estimate_market_impact_bps(
    order_quantity: float,
    average_daily_quantity: float,
    config: MarketImpactConfig = MarketImpactConfig(),
) -> float:
    """Temporary market-impact in basis points for an order of `order_quantity` against an
    instrument trading `average_daily_quantity` per day. 0 when liquidity is unknown/non-
    positive (ADQ ≤ 0) or the order is empty — unknown liquidity must not invent impact."""
    if average_daily_quantity <= 0 or order_quantity <= 0:
        return 0.0
    participation_rate = order_quantity / average_daily_quantity
    impact_bps = config.impact_coefficient_bps * math.sqrt(participation_rate)
    return min(impact_bps, config.max_impact_bps)


def apply_market_impact_to_price(
    reference_price: float, side: OrderSide, impact_bps: float
) -> float:
    """Move `reference_price` against the taker by `impact_bps` (buys fill higher, sells
    lower). Never returns below one tick."""
    taker_direction = 1.0 if side is OrderSide.BUY else -1.0
    impacted = reference_price * (1.0 + taker_direction * impact_bps / 10_000.0)
    return max(impacted, 0.05)
