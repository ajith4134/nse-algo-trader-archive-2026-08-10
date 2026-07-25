"""HistoricalTradingDayWalker — the today→inception archive-walk spine
(research/62 P1). Verified against the REAL NSE trading calendar (XNSE via
pandas_market_calendars, research/61) — this is a Rule-F real-data pass on the
day-selection logic: the holidays it skips are the actual NSE holidays.
"""

from datetime import date, timedelta

import pandas_market_calendars as market_calendars

from nse_algo_trader.paper_trading.historical_trading_day_walker import (
    HistoricalTradingDayWalker,
)
from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock


def _real_nse_clock(from_year: int, to_year: int) -> tuple[NseMarketClock, set[date]]:
    """An NseMarketClock backed by the REAL XNSE calendar, plus the true set of
    trading days for cross-checking."""
    calendar = market_calendars.get_calendar("XNSE")
    schedule = calendar.schedule(
        start_date=f"{from_year}-01-01", end_date=f"{to_year}-12-31"
    )
    real_trading_days = {timestamp.date() for timestamp in schedule.index}
    # Holidays = weekdays that are not real trading days.
    holidays: set[date] = set()
    day = date(from_year, 1, 1)
    end = date(to_year, 12, 31)
    while day <= end:
        if day.weekday() < 5 and day not in real_trading_days:
            holidays.add(day)
        day += timedelta(days=1)
    return NseMarketClock(frozenset(holidays)), real_trading_days


def test_backward_walk_matches_real_nse_trading_days_of_2020():
    clock, real_trading_days = _real_nse_clock(2020, 2020)
    walker = HistoricalTradingDayWalker(clock)

    walked = list(walker.walk_backward(date(2020, 12, 31), date(2020, 1, 1)))

    # Every real 2020 NSE trading day, newest-first, nothing else.
    assert walked == sorted(real_trading_days, reverse=True)
    assert len(walked) == 250  # real count of NSE 2020 sessions


def test_backward_walk_skips_real_holidays_gandhi_jayanti_and_christmas():
    clock, _ = _real_nse_clock(2020, 2020)
    walker = HistoricalTradingDayWalker(clock)

    walked = set(walker.walk_backward(date(2020, 12, 31), date(2020, 1, 1)))

    assert date(2020, 10, 2) not in walked  # Gandhi Jayanti (a Friday)
    assert date(2020, 12, 25) not in walked  # Christmas (a Friday)
    assert date(2020, 3, 10) not in walked  # Holi (a Tuesday)
    assert date(2020, 1, 1) in walked  # real trading day


def test_walk_is_empty_when_start_precedes_inception():
    clock, _ = _real_nse_clock(2020, 2020)
    walker = HistoricalTradingDayWalker(clock)
    assert list(walker.walk_backward(date(2020, 1, 1), date(2020, 6, 1))) == []


def test_forward_walk_is_the_reverse_order_of_backward_walk():
    clock, _ = _real_nse_clock(2020, 2020)
    walker = HistoricalTradingDayWalker(clock)
    backward = list(walker.walk_backward(date(2020, 6, 30), date(2020, 6, 1)))
    forward = list(walker.walk_forward(date(2020, 6, 1), date(2020, 6, 30)))
    assert forward == list(reversed(backward))


def test_most_recent_trading_day_rewinds_over_a_weekend():
    clock, real_trading_days = _real_nse_clock(2020, 2020)
    walker = HistoricalTradingDayWalker(clock)
    # 2020-10-03 was a Saturday; the session to rewind to is Fri 2020-10-... but
    # Fri 2020-10-02 was Gandhi Jayanti, so the most recent is Thu 2020-10-01.
    assert walker.most_recent_trading_day_on_or_before(date(2020, 10, 3)) == date(
        2020, 10, 1
    )
    assert date(2020, 10, 1) in real_trading_days
