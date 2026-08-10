"""Event-proximity gate — the single-name feature that separates stock options from index options (Rule P).

Single-stock options live and die by scheduled events: an earnings print collapses implied vol ~30-40%
(the "vol crush"), and a naked short-premium book that ignores the event calendar gets run over by the
binary move. This gate turns a corporate-event calendar into a decision: sell the rich pre-event premium
but CAP the size (binary risk), buy the cheap post-crush vol, and size normally when far from any event.

The calendar itself is sourced through an injected ``EventCalendarSource`` (a DI seam — production wires an
NSE corporate-event scraper, tests inject a fake). No maintained free OSS supplies the NSE earnings/board-
meeting calendar (research §3 STOCK-OPT), so the scraper is a named acquisition blocker (Rule I/K); the
gate ships complete and simply reports ``unknown`` proximity until the source is wired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol

_PRE_EVENT_WINDOW_DAYS = 3  # within N days BEFORE an event → elevated IV / binary risk
_POST_EVENT_WINDOW_DAYS = 2  # within N days AFTER → vol crush regime


class EventPhase(str, Enum):
    PRE_EVENT = "pre_event"  # rich IV, binary risk ahead → sell premium but cap size
    POST_EVENT = "post_event"  # crushed IV → buy cheap vol
    CLEAR = "clear"  # far from any scheduled event → size normally
    UNKNOWN = "unknown"  # no calendar source wired → be conservative


class EventCalendarSource(Protocol):
    """DI seam for the corporate-event calendar. Production = NSE scraper; tests = fake. Returns signed days.

    ``signed_days_to_nearest_event`` returns days to the nearest scheduled event (earnings / board meeting /
    dividend record): negative = the event was that many days AGO, positive = that many days AHEAD, None =
    no known event / no source.
    """

    def signed_days_to_nearest_event(self, underlying: str, as_of: date) -> int | None: ...


@dataclass(frozen=True)
class EventProximity:
    """The event picture for one underlying on one date — drives the structure/size decision."""

    underlying: str
    phase: EventPhase
    signed_days_to_event: int | None  # <0 past, >0 future, None unknown
    size_cap_fraction: float  # multiply the structure's size by this (binary-risk cap)

    @property
    def blocks_naked_premium(self) -> bool:
        """A pre-event window forbids undefined-risk premium selling (defined-risk only through the event)."""
        return self.phase == EventPhase.PRE_EVENT


class EventProximityGate:
    """Turns the injected calendar into an ``EventProximity`` decision per underlying."""

    def assess(self, underlying: str, as_of: date, source: EventCalendarSource | None) -> EventProximity:
        if source is None:
            return EventProximity(underlying, EventPhase.UNKNOWN, None, 0.5)  # conservative without a calendar
        signed = source.signed_days_to_nearest_event(underlying, as_of)
        if signed is None:
            return EventProximity(underlying, EventPhase.UNKNOWN, None, 0.5)
        if 0 <= signed <= _PRE_EVENT_WINDOW_DAYS:
            # closer to the event → smaller cap (more binary risk); 0 days = event today
            cap = 0.25 + 0.15 * signed  # 0.25 at T-0 → up to ~0.70 at the window edge
            return EventProximity(underlying, EventPhase.PRE_EVENT, signed, min(cap, 0.7))
        if -_POST_EVENT_WINDOW_DAYS <= signed < 0:
            return EventProximity(underlying, EventPhase.POST_EVENT, signed, 1.0)
        return EventProximity(underlying, EventPhase.CLEAR, signed, 1.0)
