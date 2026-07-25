"""§53 slice 5a — historical-session market-regime classifier (hermetic, Rule J).
Synthetic-but-shaped sessions: a strongly trending series → TRENDING; a choppy series
→ RANGE_BOUND/INDECISIVE; a too-short series → INDECISIVE (never crashes). Real-data
verification (classify the 22 stored INFY sessions) is scripts/verify_replay_curriculum_realdata.py."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.historical_session_market_regime_classifier import (
    classify_session_market_regime,
    latest_session_adx,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime

IST = ZoneInfo("Asia/Kolkata")
_OPEN = datetime(2026, 7, 24, 9, 15, tzinfo=IST)


def _bar(i, o, h, l, c) -> PriceBar:
    return PriceBar(
        instrument_token=1, timestamp=_OPEN + timedelta(minutes=5 * i),
        interval=BarInterval.MINUTE_5, open_price=o, high_price=h, low_price=l,
        close_price=c, volume=1000, open_interest=None,
    )


def _trending_session(n=80) -> list[PriceBar]:
    # a clean monotic climb -> high ADX -> TRENDING
    bars = []
    price = 100.0
    for i in range(n):
        o = price
        c = price + 1.0
        bars.append(_bar(i, o, c + 0.2, o - 0.2, c))
        price = c
    return bars


def _choppy_session(n=80) -> list[PriceBar]:
    # oscillate in a tight band -> low ADX -> RANGE_BOUND / INDECISIVE
    bars = []
    for i in range(n):
        base = 100.0 + (1.0 if i % 2 == 0 else -1.0)
        bars.append(_bar(i, base, base + 0.3, base - 0.3, base))
    return bars


def test_trending_session_classifies_trending():
    assert classify_session_market_regime(_trending_session()) is MarketRegime.TRENDING


def test_choppy_session_is_not_trending():
    regime = classify_session_market_regime(_choppy_session())
    assert regime in (MarketRegime.RANGE_BOUND, MarketRegime.INDECISIVE)
    assert regime is not MarketRegime.TRENDING


def test_too_short_session_is_indecisive_not_crash():
    assert latest_session_adx(_trending_session(n=3)) is None
    assert classify_session_market_regime(_trending_session(n=3)) is MarketRegime.INDECISIVE


def test_latest_session_adx_is_the_last_nonnull_value():
    adx = latest_session_adx(_trending_session())
    assert adx is not None and adx > 25.0  # a clean trend is well above the threshold
