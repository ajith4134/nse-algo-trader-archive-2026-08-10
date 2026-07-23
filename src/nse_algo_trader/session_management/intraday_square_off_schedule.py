"""Decides WHEN open intraday positions must be force-squared-off.

The no-overnight non-negotiable (CLAUDE.md): everything is flat before
the 15:30 IST close. This schedules a hard square-off inside a window
before close (default 15:15) so there is time to complete — and to retry
— every leg. The NseMarketClock is the single authority on session state.
"""

from dataclasses import dataclass
from datetime import datetime, time

from nse_algo_trader.paper_trading.nse_market_clock import (
    NSE_REGULAR_SESSION_CLOSE_IST,
    INDIA_MARKET_TIMEZONE,
    NseMarketClock,
)


@dataclass(frozen=True)
class IntradaySquareOffSchedule:
    forced_square_off_time_ist: time = time(15, 15)  # 15 min before the 15:30 close

    def should_force_square_off_now(
        self, at_moment: datetime, market_clock: NseMarketClock
    ) -> bool:
        moment_ist = (
            at_moment.replace(tzinfo=INDIA_MARKET_TIMEZONE)
            if at_moment.tzinfo is None
            else at_moment.astimezone(INDIA_MARKET_TIMEZONE)
        )
        if not market_clock.is_trading_day(moment_ist.date()):
            return False
        current_time = moment_ist.timetz().replace(tzinfo=None)
        return (
            self.forced_square_off_time_ist
            <= current_time
            <= NSE_REGULAR_SESSION_CLOSE_IST
        )
