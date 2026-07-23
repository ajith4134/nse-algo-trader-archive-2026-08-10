"""Average Directional Index (Wilder's ADX with +DI / -DI).

The v1 shortlist's trend-vs-range regime gate (`docs/research/28`):
ADX above ~20-25 -> trending session (directional strategy allowed),
below -> range-bound (credit-spread strategy instead).

Conventions (Wilder): +DM/-DM from bar-to-bar high/low moves (only the
larger of the two counts, negatives clamp to 0); +DM, -DM and TR
Wilder-smoothed over `period`; DI = 100 * smoothed DM / smoothed TR;
DX = 100 * |+DI - -DI| / (+DI + -DI); ADX = Wilder-smoothed DX, so its
first value lands at index 2*period - 1.
"""

from dataclasses import dataclass

from nse_algo_trader.indicators.average_true_range import compute_true_range_series
from nse_algo_trader.market_data import PriceBar


@dataclass(frozen=True)
class AdxSeries:
    adx: list[float | None]
    plus_directional_indicator: list[float | None]
    minus_directional_indicator: list[float | None]


def compute_average_directional_index(
    price_bars: list[PriceBar], period: int = 14
) -> AdxSeries:
    bar_count = len(price_bars)
    adx_values: list[float | None] = [None] * bar_count
    plus_di_values: list[float | None] = [None] * bar_count
    minus_di_values: list[float | None] = [None] * bar_count
    if bar_count <= period:
        return AdxSeries(adx_values, plus_di_values, minus_di_values)

    true_ranges = compute_true_range_series(price_bars)
    plus_directional_moves: list[float] = [0.0]
    minus_directional_moves: list[float] = [0.0]
    for bar_index in range(1, bar_count):
        high_move = price_bars[bar_index].high_price - price_bars[bar_index - 1].high_price
        low_move = price_bars[bar_index - 1].low_price - price_bars[bar_index].low_price
        plus_directional_moves.append(
            high_move if high_move > low_move and high_move > 0.0 else 0.0
        )
        minus_directional_moves.append(
            low_move if low_move > high_move and low_move > 0.0 else 0.0
        )

    # Wilder smoothing, seeded with plain sums over changes 1..period.
    smoothed_plus_dm = sum(plus_directional_moves[1 : period + 1])
    smoothed_minus_dm = sum(minus_directional_moves[1 : period + 1])
    smoothed_true_range = sum(true_ranges[1 : period + 1])

    directional_index_values: list[float] = []

    def _record_directional_indicators(bar_index: int) -> None:
        if smoothed_true_range == 0.0:
            plus_di, minus_di = 0.0, 0.0
        else:
            plus_di = 100.0 * smoothed_plus_dm / smoothed_true_range
            minus_di = 100.0 * smoothed_minus_dm / smoothed_true_range
        plus_di_values[bar_index] = plus_di
        minus_di_values[bar_index] = minus_di
        di_sum = plus_di + minus_di
        directional_index_values.append(
            0.0 if di_sum == 0.0 else 100.0 * abs(plus_di - minus_di) / di_sum
        )

    _record_directional_indicators(period)
    for bar_index in range(period + 1, bar_count):
        smoothed_plus_dm = (
            smoothed_plus_dm - smoothed_plus_dm / period + plus_directional_moves[bar_index]
        )
        smoothed_minus_dm = (
            smoothed_minus_dm - smoothed_minus_dm / period + minus_directional_moves[bar_index]
        )
        smoothed_true_range = (
            smoothed_true_range - smoothed_true_range / period + true_ranges[bar_index]
        )
        _record_directional_indicators(bar_index)

    if len(directional_index_values) >= period:
        running_adx = sum(directional_index_values[:period]) / period
        adx_values[2 * period - 1] = running_adx
        for dx_index in range(period, len(directional_index_values)):
            running_adx = (
                running_adx * (period - 1) + directional_index_values[dx_index]
            ) / period
            adx_values[period + dx_index] = running_adx
    return AdxSeries(adx_values, plus_di_values, minus_di_values)
