"""Session-anchored VWAP — volume-weighted average price, reset per day.

Convention (matches pandas-ta vwap with daily anchor): typical price =
(high+low+close)/3; VWAP = cumulative(typical*volume)/cumulative(volume)
within each session, anchoring on the bar timestamp's calendar date. A
zero-volume opening bar yields None until the session has any volume.
"""

from nse_algo_trader.market_data import PriceBar


def compute_session_anchored_vwap(
    price_bars: list[PriceBar],
) -> list[float | None]:
    vwap_series: list[float | None] = [None] * len(price_bars)
    current_session_date = None
    cumulative_price_volume = 0.0
    cumulative_volume = 0

    for bar_index, bar in enumerate(price_bars):
        bar_session_date = bar.timestamp.date()
        if bar_session_date != current_session_date:
            current_session_date = bar_session_date
            cumulative_price_volume = 0.0
            cumulative_volume = 0
        typical_price = (bar.high_price + bar.low_price + bar.close_price) / 3.0
        cumulative_price_volume += typical_price * bar.volume
        cumulative_volume += bar.volume
        if cumulative_volume > 0:
            vwap_series[bar_index] = cumulative_price_volume / cumulative_volume
    return vwap_series
