"""Exponential Moving Average over bar closes.

Convention (matches pandas-ta / TradingView): alpha = 2/(period+1),
seeded with the SMA of the first `period` closes; earlier positions are
None (warmup).
"""

from nse_algo_trader.market_data import PriceBar


def compute_exponential_moving_average(
    price_bars: list[PriceBar], period: int
) -> list[float | None]:
    close_prices = [bar.close_price for bar in price_bars]
    ema_series: list[float | None] = [None] * len(close_prices)
    if len(close_prices) < period:
        return ema_series
    smoothing_alpha = 2.0 / (period + 1)
    previous_ema = sum(close_prices[:period]) / period  # SMA seed
    ema_series[period - 1] = previous_ema
    for bar_index in range(period, len(close_prices)):
        previous_ema = (
            smoothing_alpha * close_prices[bar_index]
            + (1.0 - smoothing_alpha) * previous_ema
        )
        ema_series[bar_index] = previous_ema
    return ema_series
