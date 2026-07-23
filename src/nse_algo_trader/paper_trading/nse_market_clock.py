"""The single component that knows whether 'now' is inside an NSE session.

Layer 7's 24/7 architecture (PLAN §1.4) hinges on one authority for
"is the market open?": the DataSourceRouter serves replay when this says
closed and live when it says open. NSE cash+F&O regular session is
09:15-15:30 IST, Mon-Fri, minus trading holidays. Holidays are injected
(the real NSE holiday list is loaded from data, per Rule F) so this
component stays pure and testable.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
NSE_REGULAR_SESSION_OPEN_IST = time(9, 15)
NSE_REGULAR_SESSION_CLOSE_IST = time(15, 30)


class NseMarketClock:
    def __init__(self, trading_holiday_dates: frozenset[date] = frozenset()) -> None:
        self._trading_holiday_dates = trading_holiday_dates

    def is_trading_day(self, calendar_date: date) -> bool:
        return (
            calendar_date.weekday() < 5  # Mon-Fri
            and calendar_date not in self._trading_holiday_dates
        )

    def is_market_open(self, at_moment: datetime) -> bool:
        moment_ist = self._to_india_time(at_moment)
        return (
            self.is_trading_day(moment_ist.date())
            and NSE_REGULAR_SESSION_OPEN_IST
            <= moment_ist.timetz().replace(tzinfo=None)
            <= NSE_REGULAR_SESSION_CLOSE_IST
        )

    def next_session_open(self, at_moment: datetime) -> datetime:
        moment_ist = self._to_india_time(at_moment)
        candidate = moment_ist
        while True:
            session_open = datetime.combine(
                candidate.date(), NSE_REGULAR_SESSION_OPEN_IST, INDIA_MARKET_TIMEZONE
            )
            if self.is_trading_day(candidate.date()) and moment_ist < session_open:
                return session_open
            candidate = datetime.combine(
                candidate.date() + timedelta(days=1),
                time(0, 0),
                INDIA_MARKET_TIMEZONE,
            )

    def next_session_close(self, at_moment: datetime) -> datetime:
        moment_ist = self._to_india_time(at_moment)
        candidate_date = moment_ist.date()
        while True:
            session_close = datetime.combine(
                candidate_date, NSE_REGULAR_SESSION_CLOSE_IST, INDIA_MARKET_TIMEZONE
            )
            if self.is_trading_day(candidate_date) and moment_ist <= session_close:
                return session_close
            candidate_date += timedelta(days=1)

    @staticmethod
    def _to_india_time(at_moment: datetime) -> datetime:
        if at_moment.tzinfo is None:
            return at_moment.replace(tzinfo=INDIA_MARKET_TIMEZONE)
        return at_moment.astimezone(INDIA_MARKET_TIMEZONE)
