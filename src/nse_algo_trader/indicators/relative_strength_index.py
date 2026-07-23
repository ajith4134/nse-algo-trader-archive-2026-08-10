"""Relative Strength Index (Wilder's RSI) over bar closes.

Convention (Wilder, matches pandas-ta): average gain/loss seeded as the
simple mean of the first `period` close-to-close changes, then smoothed
with Wilder's RMA (alpha = 1/period). First value lands at index
`period`; earlier positions are None.
"""

from nse_algo_trader.market_data import PriceBar


def compute_relative_strength_index(
    price_bars: list[PriceBar], period: int = 14
) -> list[float | None]:
    close_prices = [bar.close_price for bar in price_bars]
    rsi_series: list[float | None] = [None] * len(close_prices)
    if len(close_prices) <= period:
        return rsi_series

    close_changes = [
        close_prices[i] - close_prices[i - 1] for i in range(1, len(close_prices))
    ]
    average_gain = sum(max(change, 0.0) for change in close_changes[:period]) / period
    average_loss = sum(max(-change, 0.0) for change in close_changes[:period]) / period
    rsi_series[period] = _rsi_from_averages(average_gain, average_loss)

    for change_index in range(period, len(close_changes)):
        change = close_changes[change_index]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        rsi_series[change_index + 1] = _rsi_from_averages(average_gain, average_loss)
    return rsi_series


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        return 100.0 if average_gain > 0.0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)
