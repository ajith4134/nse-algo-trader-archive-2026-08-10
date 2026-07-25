"""HistoricalArchiveReplayPlanner — the slice-2 survivorship filter that puts the
point-in-time universe into the replay feed (research/62 P2, research/53 §11.1).
Verified on REAL stored bhavcopy (Rule F); auto-skips where the store is absent.
"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data import BarInterval, MarketDataSqliteStore, PriceBar
from nse_algo_trader.paper_trading.historical_archive_replay_planner import (
    HistoricalArchiveReplayPlanner,
)
from nse_algo_trader.paper_trading.point_in_time_universe_resolver import (
    PointInTimeUniverseResolver,
)

IST = ZoneInfo("Asia/Kolkata")
_REAL_STORE = Path("~/.nse_algo_trader/market_data.sqlite3").expanduser()
_RESOLVED_DATE = date(2026, 7, 23)  # a completed session with real cash bhavcopy
_UNRESOLVED_DATE = date(2005, 1, 3)  # far pre-ingestion — never has bhavcopy


def _planner() -> tuple[HistoricalArchiveReplayPlanner, MarketDataSqliteStore]:
    if not _REAL_STORE.exists():
        pytest.skip("real market_data store not present (CI / fresh checkout)")
    store = MarketDataSqliteStore(db_file_path=_REAL_STORE)
    return HistoricalArchiveReplayPlanner(PointInTimeUniverseResolver(store)), store


def _bar(trade_date: date, token: int, price: float) -> PriceBar:
    ts = datetime(trade_date.year, trade_date.month, trade_date.day, 10, 0, tzinfo=IST)
    return PriceBar(token, ts, BarInterval.MINUTE_5, price, price, price, price, 100)


def test_real_eq_name_is_eligible_and_a_non_universe_name_is_not_on_a_resolved_date():
    planner, store = _planner()
    try:
        assert planner.symbol_is_eligible_on("RELIANCE", _RESOLVED_DATE) is True
        assert planner.symbol_is_eligible_on("ZZ_NOT_A_LISTED_EQ", _RESOLVED_DATE) is False
    finally:
        store.close()


def test_unresolved_date_passes_through_every_symbol():
    planner, store = _planner()
    try:
        # No cash bhavcopy for this date → cannot adjudicate → never drop.
        assert planner.symbol_is_eligible_on("ZZ_NOT_A_LISTED_EQ", _UNRESOLVED_DATE) is True
        assert planner.symbol_is_eligible_on("RELIANCE", _UNRESOLVED_DATE) is True
    finally:
        store.close()


def test_filter_drops_non_universe_bars_on_resolved_date_keeps_eligible_and_passthrough():
    planner, store = _planner()
    try:
        symbol_by_token = {10: "RELIANCE", 20: "ZZ_NOT_A_LISTED_EQ", 30: "TCS"}
        bars_by_token = {
            10: [_bar(_RESOLVED_DATE, 10, 1400.0)],  # eligible on resolved date → kept
            20: [_bar(_RESOLVED_DATE, 20, 5.0)],  # not in that day's universe → dropped
            30: [_bar(_UNRESOLVED_DATE, 30, 3500.0)],  # unresolved date → passed through
        }
        filtered = planner.filter_bars_to_point_in_time_universe(
            bars_by_token, symbol_by_token
        )
        assert 10 in filtered  # RELIANCE kept
        assert 20 not in filtered  # bogus name erased from that real day
        assert 30 in filtered  # pass-through on unresolved date
    finally:
        store.close()


def test_token_with_no_known_symbol_is_dropped():
    planner, store = _planner()
    try:
        bars_by_token = {99: [_bar(_UNRESOLVED_DATE, 99, 1.0)]}
        filtered = planner.filter_bars_to_point_in_time_universe(bars_by_token, {})
        assert filtered == {}
    finally:
        store.close()
