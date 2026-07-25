"""The causal leakage firewall — makes look-ahead leakage STRUCTURALLY
impossible in replay, instead of something we remember to avoid (research/62
part P5; research/53 §8.3).

When the sim's virtual clock sits at time T on a replayed day, the bot must be
able to observe data timestamped at or before T and NOTHING after it. A single
leaked future bar (tomorrow's price, a later headline, the day's closing VWAP)
silently turns honest replay into cheating and every lesson learnt from it is
worthless.

This firewall enforces two invariants on any replay stream:
  1. **No future leak** — a datum timestamped after the current virtual-now can
     never pass through, and any attempt to observe one raises.
  2. **Monotonic virtual time** — within a session the virtual clock only moves
     forward; it can never rewind to re-reveal the past out of order.

It is deliberately data-shape-agnostic (it guards on a `timestamp` only), so the
same gate protects price bars today and news/depth records in later slices. It
is meant to sit at the replay DI seam (Rule J): production selects the real live
adapter, replay selects a source wrapped by this firewall.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol


class HasTimestamp(Protocol):
    timestamp: datetime


class FutureLeakageError(AssertionError):
    """Raised when a datum timestamped after the current virtual-now would be
    observed — a look-ahead leak the firewall exists to make impossible."""


class CausalOrderingViolation(AssertionError):
    """Raised when the virtual clock is asked to move backward within a session
    (out-of-order reveal) — the input stream was not truly chronological."""


def assert_no_future_leak(timestamp: datetime, virtual_now: datetime) -> None:
    """Stateless causal guard: raise `FutureLeakageError` if `timestamp` is
    after `virtual_now`. The single home of the no-future-leak check, reused by
    both `CausalLeakageFirewall` and stateless replay consumers (e.g. the
    replay universe feed) so the guarantee is defined in exactly one place."""
    if timestamp > virtual_now:
        raise FutureLeakageError(
            f"future-data leak blocked: {timestamp} is after virtual-now {virtual_now}"
        )


class CausalLeakageFirewall:
    def __init__(self, session_open: datetime, session_close: datetime) -> None:
        if session_close < session_open:
            raise ValueError(
                f"session_close {session_close} precedes session_open {session_open}"
            )
        self._session_open = session_open
        self._session_close = session_close
        self._virtual_now = session_open

    @property
    def virtual_now(self) -> datetime:
        return self._virtual_now

    def assert_observable(self, timestamp: datetime) -> None:
        """Guard any peek: raise if `timestamp` is in the future relative to the
        current virtual-now. Consumers that reach for data directly (a feature,
        a store query) call this so even out-of-band reads stay causal."""
        assert_no_future_leak(timestamp, self._virtual_now)

    def advance_to(self, timestamp: datetime) -> None:
        """Move the virtual clock forward to `timestamp`. Never rewinds
        (raises `CausalOrderingViolation`); clamps to the session window so the
        clock cannot step past the close."""
        if timestamp < self._virtual_now:
            raise CausalOrderingViolation(
                f"virtual clock cannot rewind from {self._virtual_now} to {timestamp}"
            )
        self._virtual_now = min(timestamp, self._session_close)

    def stream_causally(
        self, chronological_data: Iterator[HasTimestamp] | list[HasTimestamp]
    ) -> Iterator[HasTimestamp]:
        """Release each datum in strict timestamp order, advancing the virtual
        clock to a datum's own time at the instant it is revealed — so at the
        moment anything is observed, virtual-now equals its timestamp and no
        later datum has been seen. Data outside [session_open, session_close]
        is dropped (it belongs to another session). Out-of-order input raises."""
        for datum in chronological_data:
            timestamp = datum.timestamp
            if timestamp < self._session_open or timestamp > self._session_close:
                continue
            self.advance_to(timestamp)
            yield datum
