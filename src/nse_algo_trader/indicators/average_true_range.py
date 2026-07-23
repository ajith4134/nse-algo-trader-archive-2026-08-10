"""True Range and Average True Range (Wilder).

Conventions: TR[0] = high-low (no previous close exists); TR[i] =
max(high-low, |high-prev_close|, |low-prev_close|). ATR seeded as the
SMA of the first `period` TRs, then Wilder-smoothed (alpha = 1/period);
first ATR value at index `period - 1`.
"""

from nse_algo_trader.market_data import PriceBar


def compute_true_range_series(price_bars: list[PriceBar]) -> list[float]:
    true_range_series: list[float] = []
    for bar_index, bar in enumerate(price_bars):
        if bar_index == 0:
            true_range_series.append(bar.high_price - bar.low_price)
            continue
        previous_close = price_bars[bar_index - 1].close_price
        true_range_series.append(
            max(
                bar.high_price - bar.low_price,
                abs(bar.high_price - previous_close),
                abs(bar.low_price - previous_close),
            )
        )
    return true_range_series


def compute_average_true_range(
    price_bars: list[PriceBar], period: int = 14
) -> list[float | None]:
    true_ranges = compute_true_range_series(price_bars)
    atr_series: list[float | None] = [None] * len(true_ranges)
    if len(true_ranges) < period:
        return atr_series
    previous_atr = sum(true_ranges[:period]) / period  # SMA seed
    atr_series[period - 1] = previous_atr
    for bar_index in range(period, len(true_ranges)):
        previous_atr = (previous_atr * (period - 1) + true_ranges[bar_index]) / period
        atr_series[bar_index] = previous_atr
    return atr_series
