"""Walks REAL NSE trading days from today BACKWARD to a segment's inception —
the archive-walk controller for the 24/7 market-open simulation (research/62
part P1; research/53 §10.1).

The simulation replays *every real trading day that ever happened*, not just
the days the bot personally traded live. This walker is the day-selection
spine: given a start date and an inception date, it yields each actual NSE
trading day (weekends and holidays skipped via `NseMarketClock`) newest-first,
so the sim can rewind to that day's 09:15 and replay it. A forward walk and an
"most-recent trading day on/before" helper support bootstrap and resume.

It holds no data and does no I/O — it only sequences dates — so which real
holiday calendar backs `NseMarketClock` (e.g. the `XNSE` calendar from
`pandas_market_calendars`, research/61) is the caller's choice, and this stays
pure and testable against the real calendar.
"""

from collections.abc import Iterator
from datetime import date, timedelta

from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock

# NSE has never had more than a handful of consecutive non-trading calendar
# days (a long weekend around a holiday); 15 is a safe bound for scans that
# must land on a real trading day.
_MAX_CONSECUTIVE_NON_TRADING_DAYS_SCAN = 15


class HistoricalTradingDayWalker:
    def __init__(self, nse_market_clock: NseMarketClock) -> None:
        self._nse_market_clock = nse_market_clock

    def walk_backward(
        self, from_date: date, to_inception_date: date
    ) -> Iterator[date]:
        """Yield each real NSE trading day from `from_date` back to
        `to_inception_date` (both inclusive), newest first. Non-trading days
        are skipped. Empty if `from_date` precedes `to_inception_date`."""
        current_date = from_date
        while current_date >= to_inception_date:
            if self._nse_market_clock.is_trading_day(current_date):
                yield current_date
            current_date -= timedelta(days=1)

    def walk_forward(
        self, from_inception_date: date, to_date: date
    ) -> Iterator[date]:
        """Yield each real NSE trading day from `from_inception_date` forward
        to `to_date` (both inclusive), oldest first — the accelerated bootstrap
        direction (research/53 §11.5)."""
        current_date = from_inception_date
        while current_date <= to_date:
            if self._nse_market_clock.is_trading_day(current_date):
                yield current_date
            current_date += timedelta(days=1)

    def most_recent_trading_day_on_or_before(self, calendar_date: date) -> date:
        """The latest real NSE trading day at or before `calendar_date` — the
        session to rewind to when the walk starts from a weekend/holiday."""
        current_date = calendar_date
        for _ in range(_MAX_CONSECUTIVE_NON_TRADING_DAYS_SCAN):
            if self._nse_market_clock.is_trading_day(current_date):
                return current_date
            current_date -= timedelta(days=1)
        raise ValueError(
            "no NSE trading day found within "
            f"{_MAX_CONSECUTIVE_NON_TRADING_DAYS_SCAN} days on/before "
            f"{calendar_date} — is the holiday calendar wrong?"
        )
