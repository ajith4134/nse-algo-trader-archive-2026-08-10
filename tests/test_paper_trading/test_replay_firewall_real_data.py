"""Slice-1 REAL-DATA pass (Rule F): the causal leakage firewall + provenance
stamp, exercised over a REAL stored NSE session — not a fixture.

This closes the slice-1 open blocker for the data we already have (a real full
5-minute session in `~/.nse_algo_trader/market_data.sqlite3`). It auto-skips
where that real store / session is absent (CI, a fresh checkout), so it is a
real-data integration check, never a synthetic stand-in. Higher-fidelity
intraday (tick/1-second) replay remains a later-slice pass.
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from nse_algo_trader.market_data import BarInterval, MarketDataSqliteStore
from nse_algo_trader.paper_trading.causal_leakage_firewall import FutureLeakageError
from nse_algo_trader.paper_trading.nse_market_clock import INDIA_MARKET_TIMEZONE
from nse_algo_trader.paper_trading.replay_experience_provenance import (
    DataProvenance,
    ReplayFidelityTier,
)
from nse_algo_trader.paper_trading.replay_universe_feed import ReplayUniverseFeed
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

_REAL_STORE = Path("~/.nse_algo_trader/market_data.sqlite3").expanduser()
_REAL_SESSION_DATE = date(2026, 7, 24)  # a real full 5m session (225 tokens)


def _load_real_session():
    if not _REAL_STORE.exists():
        pytest.skip("real market_data store not present (CI / fresh checkout)")
    store = MarketDataSqliteStore(db_file_path=_REAL_STORE)
    try:
        day_start = datetime.combine(
            _REAL_SESSION_DATE, time(0, 0), INDIA_MARKET_TIMEZONE
        )
        day_end = day_start + timedelta(days=1)
        tokens = [
            row[0]
            for row in store._connection.execute(
                "SELECT DISTINCT instrument_token FROM price_bars"
                " WHERE bar_interval='5m' AND bar_timestamp>=? AND bar_timestamp<?",
                (day_start.isoformat(), day_end.isoformat()),
            )
        ]
        if len(tokens) < 50:
            pytest.skip("real session has too few instruments for a universe pass")
        bars_by_token = {
            token: store.load_price_bars(
                token, BarInterval.MINUTE_5, day_start, day_end
            )
            for token in tokens
        }
    finally:
        store.close()
    return bars_by_token


def _instrument(token: int) -> Instrument:
    return Instrument(
        instrument_token=token, trading_symbol=f"T{token}",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def test_firewall_never_leaks_future_bars_over_a_real_full_session():
    bars_by_token = _load_real_session()
    feed = ReplayUniverseFeed(bars_by_token)
    instruments = [_instrument(t) for t in bars_by_token]
    timestamps = feed.stored_session_timestamps()
    assert len(timestamps) >= 60  # a real full session's worth of 5m steps

    # Walk the replay clock forward across the whole real session. At every step
    # the firewall inside the feed must serve only bars at/<= the clock; any
    # leak raises FutureLeakageError (the call itself is the assertion).
    visible_count_progression = []
    for clock in timestamps:
        feed.set_replay_as_of(clock)
        prices = feed.latest_price_by_token(instruments)  # firewall-guarded
        # Every served price must come from a bar dated <= the clock.
        for inst in instruments:
            bars = feed.recent_intraday_bars(inst, clock, lookback_calendar_days=1)
            for bar in bars:
                assert bar.timestamp <= clock
        visible_count_progression.append(len(prices))

    # Visibility only grows as the clock advances (monotone reveal, no rewinding
    # the future into view).
    assert visible_count_progression == sorted(visible_count_progression)
    assert visible_count_progression[-1] > 0


def test_requesting_a_future_moment_raises_on_real_data():
    bars_by_token = _load_real_session()
    feed = ReplayUniverseFeed(bars_by_token)
    timestamps = feed.stored_session_timestamps()
    mid = timestamps[len(timestamps) // 2]
    feed.set_replay_as_of(mid)
    future_moment = timestamps[-1] + timedelta(minutes=5)
    with pytest.raises(FutureLeakageError):
        feed.recent_intraday_bars(_instrument(next(iter(bars_by_token))), future_moment)


def test_real_session_feed_carries_replay_provenance_stamp():
    feed = ReplayUniverseFeed(_load_real_session())
    stamp = feed.provenance_stamp()
    assert stamp.provenance is DataProvenance.REPLAY_FAITHFUL
    assert stamp.fidelity_tier is ReplayFidelityTier.BAR_ONLY
