"""Classify a real historical trading session into its ADX market regime — the atom of
the deficit-driven replay curriculum (§53 slice 5a; research/86).

Reuses the EXISTING indicator + gate (Rule I/C, no reinvention):
`indicators.compute_average_directional_index` over the session's bars, then
`strategy_engine.classify_adx_market_regime` on the session's final ADX. So a day the
market trended is labelled TRENDING, a choppy day RANGE_BOUND — the label vocabulary the
curriculum balances coverage across. PURE (no I/O) → hermetically testable and reusable
by both the curriculum selector and (slice 5b) experience regime-tagging.
"""

from __future__ import annotations

from nse_algo_trader.indicators.average_directional_index import (
    compute_average_directional_index,
)
from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import (
    AdxRegimeGateConfig,
    MarketRegime,
    classify_adx_market_regime,
)


def latest_session_adx(session_bars: list[PriceBar], period: int = 14) -> float | None:
    """The session's final ADX (last non-None value of the ADX series), or None when the
    session has too few bars for ADX to warm up."""
    adx_series = compute_average_directional_index(session_bars, period=period)
    for adx_value in reversed(adx_series.adx):
        if adx_value is not None:
            return adx_value
    return None


def classify_session_market_regime(
    session_bars: list[PriceBar],
    period: int = 14,
    config: AdxRegimeGateConfig = AdxRegimeGateConfig(),
) -> MarketRegime:
    """The ADX market regime for a whole session's bars (TRENDING / RANGE_BOUND /
    INDECISIVE). A session with too few bars for ADX classifies INDECISIVE (the gate's
    own None → INDECISIVE rule), so a thin day never crashes the curriculum."""
    return classify_adx_market_regime(latest_session_adx(session_bars, period), config)
