"""Hermetic tests for S7 news entry-gate (Trunk II SENSES, research/147).

Covers the PURE gate (per-symbol event risk + size multiplier) AND the load-bearing SAFETY property:
advisory (identity) until calibration earned, so an uncalibrated news signal never moves a real trade.
"""

from datetime import datetime, timedelta, timezone

from nse_algo_trader.news_sentiment.news_entry_gate import (
    NewsEventRiskConfig,
    build_news_event_risk_by_symbol,
    news_event_size_multiplier,
)
from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier, RawNewsItem

NOW = datetime(2026, 7, 26, 18, 0, 0, tzinfo=timezone.utc)


def _filing(symbol, subject, source_id, age_hours=1.0):
    title = f"{symbol}: {subject}"
    return RawNewsItem(
        source_id=source_id, source_name=source_id, tier=NewsSourceTier.EXCHANGE_FILING.value,
        title=title, summary="", url=f"https://x/{symbol}",
        published_at=NOW - timedelta(hours=age_hours), fetched_at=NOW,
        content_hash=RawNewsItem.compute_content_hash(source_id, symbol, title))


RELIABILITY = {"nse_announcements_equities": 0.91, "flaky_social": 0.2}


def test_fresh_reliable_filing_creates_event_risk():
    items = [_filing("HEROMOTOCO", "Outcome of Board Meeting", "nse_announcements_equities", age_hours=1)]
    risk = build_news_event_risk_by_symbol(items, RELIABILITY, NOW)
    assert "HEROMOTOCO" in risk and risk["HEROMOTOCO"] > 0.5


def test_low_reliability_source_alone_never_moves_gate():
    items = [_filing("PENNY", "Pump alert", "flaky_social", age_hours=0.1)]
    risk = build_news_event_risk_by_symbol(items, RELIABILITY, NOW)
    assert "PENNY" not in risk  # below the reliability floor → ignored


def test_stale_event_decays_out_of_window():
    items = [_filing("OLDCO", "Outcome", "nse_announcements_equities", age_hours=48)]
    risk = build_news_event_risk_by_symbol(items, RELIABILITY, NOW,
                                           NewsEventRiskConfig(recency_window=timedelta(hours=24)))
    assert "OLDCO" not in risk  # older than the recency window → no risk


def test_size_multiplier_is_identity_until_earned():
    # High risk but NOT earned → identity (the safety property).
    assert news_event_size_multiplier(0.95, calibration_earned=False) == 1.0
    assert news_event_size_multiplier(0.60, calibration_earned=False) == 1.0


def test_size_multiplier_acts_once_earned():
    assert news_event_size_multiplier(0.95, calibration_earned=True) == 0.0   # defer
    assert news_event_size_multiplier(0.60, calibration_earned=True) == 0.5   # size-down
    assert news_event_size_multiplier(0.10, calibration_earned=True) == 1.0   # low risk → no change


def test_loop_state_gate_wired_and_safe():
    """The gate is wired into the loop state and is identity until earned, acts once earned + counts."""
    from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState

    state = LiveUniversePaperState.__new__(LiveUniversePaperState)  # bypass heavy __init__
    state.news_event_risk_by_symbol = {"HEROMOTOCO": 0.95}
    state.news_event_calibration_earned = False
    state.news_event_deferred_count = 0
    state.news_event_sized_down_count = 0
    assert state.news_event_size_multiplier("HEROMOTOCO") == 1.0   # advisory → identity (safe)
    assert state.news_event_size_multiplier("UNKNOWN") == 1.0      # no event → identity

    state.news_event_calibration_earned = True
    assert state.news_event_size_multiplier("HEROMOTOCO") == 0.0   # earned + high risk → defer
    assert state.news_event_deferred_count == 1
