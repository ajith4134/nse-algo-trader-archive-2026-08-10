"""IV Rank — where today's IV sits inside its historical range.

Standard formula: 100 * (current - lowest) / (highest - lowest) over the
lookback window (252 trading days conventionally; shorter histories are
accepted but the caller should know the store only holds what has been
backfilled/accumulated so far).
"""


def compute_implied_volatility_rank(
    current_implied_volatility: float,
    historical_implied_volatilities: list[float],
) -> float | None:
    """None when history is too thin (<2 points) or perfectly flat."""
    if len(historical_implied_volatilities) < 2:
        return None
    lowest_iv = min(historical_implied_volatilities)
    highest_iv = max(historical_implied_volatilities)
    if highest_iv == lowest_iv:
        return None
    rank = 100.0 * (current_implied_volatility - lowest_iv) / (highest_iv - lowest_iv)
    return min(max(rank, 0.0), 100.0)
