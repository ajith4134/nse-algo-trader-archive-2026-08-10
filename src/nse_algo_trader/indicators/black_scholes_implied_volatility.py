"""Black-Scholes European option pricing and implied-volatility inversion.

Used to derive an IV series from stored F&O bhavcopy settlement prices
(Kite provides no IV field — `docs/research/13`). European BS is exact
for NSE index options and the standard screening approximation for NSE
stock options. Inversion is by bisection: slower than Newton but immune
to the vega-collapse divergence of deep ITM/OTM strikes.
"""

import math
from enum import Enum

DEFAULT_RISK_FREE_INTEREST_RATE = 0.065  # ~RBI repo-rate ballpark

_BISECTION_VOLATILITY_LOWER_BOUND = 0.001
_BISECTION_VOLATILITY_UPPER_BOUND = 5.0
_BISECTION_PRICE_TOLERANCE = 1e-6
_BISECTION_MAX_ITERATIONS = 200


class OptionRightForPricing(str, Enum):
    CALL = "CE"
    PUT = "PE"


def _standard_normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_black_scholes_option_price(
    underlying_price: float,
    strike_price: float,
    time_to_expiry_years: float,
    volatility: float,
    option_right: OptionRightForPricing,
    risk_free_rate: float = DEFAULT_RISK_FREE_INTEREST_RATE,
) -> float:
    if time_to_expiry_years <= 0.0 or volatility <= 0.0:
        intrinsic = (
            underlying_price - strike_price
            if option_right is OptionRightForPricing.CALL
            else strike_price - underlying_price
        )
        return max(intrinsic, 0.0)
    volatility_sqrt_time = volatility * math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(underlying_price / strike_price)
        + (risk_free_rate + volatility**2 / 2.0) * time_to_expiry_years
    ) / volatility_sqrt_time
    d2 = d1 - volatility_sqrt_time
    discounted_strike = strike_price * math.exp(-risk_free_rate * time_to_expiry_years)
    if option_right is OptionRightForPricing.CALL:
        return underlying_price * _standard_normal_cdf(d1) - discounted_strike * _standard_normal_cdf(d2)
    return discounted_strike * _standard_normal_cdf(-d2) - underlying_price * _standard_normal_cdf(-d1)


def compute_implied_volatility(
    observed_option_price: float,
    underlying_price: float,
    strike_price: float,
    time_to_expiry_years: float,
    option_right: OptionRightForPricing,
    risk_free_rate: float = DEFAULT_RISK_FREE_INTEREST_RATE,
) -> float | None:
    """Bisection-inverted BS volatility, or None when the observed price
    sits outside no-arbitrage bounds (below intrinsic / above the
    max-volatility price) so no volatility can explain it."""
    if time_to_expiry_years <= 0.0 or observed_option_price <= 0.0:
        return None

    def _price_at(volatility: float) -> float:
        return compute_black_scholes_option_price(
            underlying_price, strike_price, time_to_expiry_years,
            volatility, option_right, risk_free_rate,
        )

    lower_volatility = _BISECTION_VOLATILITY_LOWER_BOUND
    upper_volatility = _BISECTION_VOLATILITY_UPPER_BOUND
    if not (_price_at(lower_volatility) <= observed_option_price <= _price_at(upper_volatility)):
        return None
    for _ in range(_BISECTION_MAX_ITERATIONS):
        midpoint_volatility = (lower_volatility + upper_volatility) / 2.0
        price_gap = _price_at(midpoint_volatility) - observed_option_price
        if abs(price_gap) < _BISECTION_PRICE_TOLERANCE:
            return midpoint_volatility
        if price_gap < 0.0:
            lower_volatility = midpoint_volatility
        else:
            upper_volatility = midpoint_volatility
    return (lower_volatility + upper_volatility) / 2.0
