"""Layer 3 — Indicator / Feature Engineering.

v1 price-series set (PLAN §7 + §8a.3): EMA, RSI, ATR, ADX, Supertrend,
session-anchored VWAP. Every function consumes Layer 2's list[PriceBar]
and returns per-bar series aligned 1:1 with the input (None during
warmup) so downstream code can zip bars and indicator values directly.
"""

from nse_algo_trader.indicators.average_directional_index import (
    AdxSeries,
    compute_average_directional_index,
)
from nse_algo_trader.indicators.black_scholes_implied_volatility import (
    OptionRightForPricing,
    compute_black_scholes_delta,
    compute_black_scholes_option_price,
    compute_implied_volatility,
)
from nse_algo_trader.indicators.end_of_day_atm_implied_volatility import (
    AtmImpliedVolatilitySnapshot,
    compute_end_of_day_atm_implied_volatility,
)
from nse_algo_trader.indicators.implied_volatility_rank import (
    compute_implied_volatility_rank,
)
from nse_algo_trader.indicators.put_call_ratio import (
    PutCallOpenInterestRatio,
    compute_put_call_open_interest_ratio,
)
from nse_algo_trader.indicators.average_true_range import (
    compute_average_true_range,
    compute_true_range_series,
)
from nse_algo_trader.indicators.exponential_moving_average import (
    compute_exponential_moving_average,
)
from nse_algo_trader.indicators.relative_strength_index import (
    compute_relative_strength_index,
)
from nse_algo_trader.indicators.session_anchored_vwap import (
    compute_session_anchored_vwap,
)
from nse_algo_trader.indicators.supertrend_indicator import (
    SupertrendSeries,
    compute_supertrend,
)

__all__ = [
    "AdxSeries",
    "AtmImpliedVolatilitySnapshot",
    "OptionRightForPricing",
    "PutCallOpenInterestRatio",
    "SupertrendSeries",
    "compute_black_scholes_delta",
    "compute_black_scholes_option_price",
    "compute_end_of_day_atm_implied_volatility",
    "compute_implied_volatility",
    "compute_implied_volatility_rank",
    "compute_put_call_open_interest_ratio",
    "compute_average_directional_index",
    "compute_average_true_range",
    "compute_exponential_moving_average",
    "compute_relative_strength_index",
    "compute_session_anchored_vwap",
    "compute_supertrend",
    "compute_true_range_series",
]
