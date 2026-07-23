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
    "SupertrendSeries",
    "compute_average_directional_index",
    "compute_average_true_range",
    "compute_exponential_moving_average",
    "compute_relative_strength_index",
    "compute_session_anchored_vwap",
    "compute_supertrend",
    "compute_true_range_series",
]
