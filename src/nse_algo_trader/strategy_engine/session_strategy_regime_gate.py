"""ADX regime gate — decides which v1 strategy is allowed to trade a session.

Per `docs/research/28`: ADX above the trending threshold -> directional
Opening-Range Breakout; at/below the range-bound threshold -> premium
selling via credit spreads; the dead zone between the thresholds ->
stand aside (no strategy has an environment it was designed for).
Thresholds (25/20) are the conventional Wilder bands — tunable, and
subject to Layer 7 validation like every other parameter.
"""

from dataclasses import dataclass
from enum import Enum


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGE_BOUND = "range_bound"
    INDECISIVE = "indecisive"


class V1SessionStrategyChoice(str, Enum):
    OPENING_RANGE_BREAKOUT = "opening_range_breakout"
    CREDIT_SPREAD = "credit_spread"
    STAND_ASIDE = "stand_aside"


@dataclass(frozen=True)
class AdxRegimeGateConfig:
    trending_adx_threshold: float = 25.0
    range_bound_adx_threshold: float = 20.0


def classify_adx_market_regime(
    adx_value: float | None,
    config: AdxRegimeGateConfig = AdxRegimeGateConfig(),
) -> MarketRegime:
    """None (ADX warmup) counts as INDECISIVE — never trade blind."""
    if adx_value is None:
        return MarketRegime.INDECISIVE
    if adx_value >= config.trending_adx_threshold:
        return MarketRegime.TRENDING
    if adx_value <= config.range_bound_adx_threshold:
        return MarketRegime.RANGE_BOUND
    return MarketRegime.INDECISIVE


def choose_v1_session_strategy(
    adx_value: float | None,
    config: AdxRegimeGateConfig = AdxRegimeGateConfig(),
) -> V1SessionStrategyChoice:
    regime = classify_adx_market_regime(adx_value, config)
    if regime is MarketRegime.TRENDING:
        return V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT
    if regime is MarketRegime.RANGE_BOUND:
        return V1SessionStrategyChoice.CREDIT_SPREAD
    return V1SessionStrategyChoice.STAND_ASIDE
