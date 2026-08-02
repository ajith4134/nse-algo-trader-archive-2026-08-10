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


#: B16: how much to size down a trade taken in the INDECISIVE band. Conviction is genuinely lower
#: when the regime is unclear, so the structure is permitted but the position is smaller.
INDECISIVE_REGIME_SIZE_DOWN = 0.60


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
    # B16: the INDECISIVE band (ADX 20-25) is not "we know nothing" — it is "we know it is NOT
    # trending", which is the textbook condition for a NON-DIRECTIONAL, defined-risk structure.
    # Treating it as no-tradable-structure stood 20-72 underlyings aside every pass (BANKNIFTY sat
    # at ADX 24.96 live on 2026-07-27, inside the band, and never traded). Conviction genuinely IS
    # lower here, so the caller sizes it down via INDECISIVE_REGIME_SIZE_DOWN — but a defined-risk
    # spread is a legitimate expression of "no trend", not a gamble.
    if adx_value is not None and regime is MarketRegime.INDECISIVE:
        return V1SessionStrategyChoice.CREDIT_SPREAD
    # STAND_ASIDE is RETAINED for the case it was really for: no usable ADX at all.
    return V1SessionStrategyChoice.STAND_ASIDE
