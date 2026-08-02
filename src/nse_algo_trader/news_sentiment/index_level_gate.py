"""S2-index-levels entry gate — index-option S/R proximity caution (Trunk II SENSES; research/151). PURE.

Closes the last news decision gap: the S2 index `news_levels` were display-only. Opening an index-option
position right at a fresh, reliable analyst S/R level is elevated reversal/whipsaw risk. Direction-agnostic
(levels are where reversals happen, either way). Mirrors the S7 gate: identity until calibration earned,
so an uncalibrated signal never moves a real trade.
"""

from __future__ import annotations

# Proximity bands as a fraction of spot.
INDEX_LEVEL_DEFER_PCT = 0.003      # within 0.3% of a level → defer (0.0)
INDEX_LEVEL_SIZE_DOWN_PCT = 0.010  # within 1.0% → size-down (0.5)
INDEX_LEVEL_SIZE_DOWN_MULTIPLIER = 0.5


def nearest_level_distance_pct(spot: float, level_values) -> float | None:
    """Fractional distance from spot to the NEAREST level (None when no levels / bad spot)."""
    if not level_values or spot is None or spot <= 0:
        return None
    return min(abs(spot - float(lvl)) / spot for lvl in level_values)


def index_level_size_multiplier(spot: float, level_values, calibration_earned: bool,
                                defer_pct: float = INDEX_LEVEL_DEFER_PCT,
                                size_down_pct: float = INDEX_LEVEL_SIZE_DOWN_PCT,
                                size_down_multiplier: float = INDEX_LEVEL_SIZE_DOWN_MULTIPLIER) -> float:
    """1.0 (identity) until EARNED or no nearby level; then 0.0 (defer) within `defer_pct` of the
    nearest level, `size_down_multiplier` within `size_down_pct`. Mirrors the S7 safety pattern."""
    if not calibration_earned:
        return 1.0
    distance = nearest_level_distance_pct(spot, level_values)
    if distance is None:
        return 1.0
    if distance <= defer_pct:
        return 0.0
    if distance <= size_down_pct:
        return size_down_multiplier
    return 1.0
