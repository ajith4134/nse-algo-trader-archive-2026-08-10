"""Order-rate throttle — hard self-imposed ceiling under SEBI's threshold.

SEBI's white-box algo framework treats >=10 orders/sec/exchange/client
as the registration-mandatory tier (`CLAUDE.md`). This bot self-limits
to half that by default, and the throttle sits INSIDE the live broker
client so no code path can bypass it. Clock/sleep are injectable purely
for tests.
"""

import time
from collections import deque
from collections.abc import Callable


class OrderRateLimiter:
    def __init__(
        self,
        max_orders_per_second: int = 5,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleep_function: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_orders_per_second = max_orders_per_second
        self._monotonic_clock = monotonic_clock
        self._sleep_function = sleep_function
        self._recent_order_timestamps: deque[float] = deque()

    def wait_for_order_slot(self) -> None:
        """Blocks until placing one more order stays under the ceiling."""
        while True:
            now = self._monotonic_clock()
            while (
                self._recent_order_timestamps
                and now - self._recent_order_timestamps[0] >= 1.0
            ):
                self._recent_order_timestamps.popleft()
            if len(self._recent_order_timestamps) < self._max_orders_per_second:
                self._recent_order_timestamps.append(now)
                return
            self._sleep_function(
                1.0 - (now - self._recent_order_timestamps[0])
            )
