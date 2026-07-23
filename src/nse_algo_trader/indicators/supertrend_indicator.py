"""Supertrend — ATR band trailing stop with trend direction.

Standard construction (matches pandas-ta / TradingView): basic bands at
(high+low)/2 ± multiplier * ATR(period) (Wilder ATR); bands ratchet
(upper only moves down while price stays below it, lower only moves up
while price stays above); direction flips when close crosses the active
band. The supertrend line rides the lower band in an uptrend (+1) and
the upper band in a downtrend (-1).
"""

from dataclasses import dataclass

from nse_algo_trader.indicators.average_true_range import compute_average_true_range
from nse_algo_trader.market_data import PriceBar


@dataclass(frozen=True)
class SupertrendSeries:
    supertrend_line: list[float | None]
    trend_direction: list[int | None]  # +1 uptrend, -1 downtrend


def compute_supertrend(
    price_bars: list[PriceBar],
    atr_period: int = 10,
    band_multiplier: float = 3.0,
) -> SupertrendSeries:
    bar_count = len(price_bars)
    supertrend_line: list[float | None] = [None] * bar_count
    trend_direction: list[int | None] = [None] * bar_count
    atr_series = compute_average_true_range(price_bars, atr_period)

    previous_final_upper_band: float | None = None
    previous_final_lower_band: float | None = None
    previous_direction = 1

    for bar_index in range(bar_count):
        atr_value = atr_series[bar_index]
        if atr_value is None:
            continue
        bar = price_bars[bar_index]
        band_midpoint = (bar.high_price + bar.low_price) / 2.0
        basic_upper_band = band_midpoint + band_multiplier * atr_value
        basic_lower_band = band_midpoint - band_multiplier * atr_value
        previous_close = price_bars[bar_index - 1].close_price

        if previous_final_upper_band is None:
            final_upper_band, final_lower_band = basic_upper_band, basic_lower_band
        else:
            final_upper_band = (
                basic_upper_band
                if basic_upper_band < previous_final_upper_band
                or previous_close > previous_final_upper_band
                else previous_final_upper_band
            )
            final_lower_band = (
                basic_lower_band
                if basic_lower_band > previous_final_lower_band
                or previous_close < previous_final_lower_band
                else previous_final_lower_band
            )

        if bar.close_price > final_upper_band:
            current_direction = 1
        elif bar.close_price < final_lower_band:
            current_direction = -1
        else:
            current_direction = previous_direction

        trend_direction[bar_index] = current_direction
        supertrend_line[bar_index] = (
            final_lower_band if current_direction == 1 else final_upper_band
        )
        previous_final_upper_band = final_upper_band
        previous_final_lower_band = final_lower_band
        previous_direction = current_direction

    return SupertrendSeries(supertrend_line, trend_direction)
