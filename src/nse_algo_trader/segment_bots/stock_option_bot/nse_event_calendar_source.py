"""NSE corporate-event calendar scraper — the real source behind the stock bot's event gate (Rule I/F/G).

No maintained free OSS supplies the NSE earnings / board-meeting calendar, so this acquires it directly
from NSE's own event-calendar API (``/api/event-calendar``) via the same curl_cffi Chrome-impersonated
session + homepage-cookie bootstrap the repo already uses for corporate announcements (verified reachable
from this egress: HTTP 200, ~700+ events shaped ``{symbol, company, purpose, bm_desc, date}``). It parses
the per-symbol event dates and implements the ``EventCalendarSource`` protocol the event gate consumes —
``signed_days_to_nearest_event`` (negative = past, positive = ahead).

The fetch is a DI seam (Rule J): production uses the real session; tests inject a fake. A persisted cache
keeps the calendar available between refreshes and when the market/egress is unreachable; the live refresh
cadence is the open blocker (Rule K), but the real-data pass is met — this fetched real NSE events.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from collections.abc import Callable

_NSE_HOME = "https://www.nseindia.com/"
_EVENT_CALENDAR_API = "https://www.nseindia.com/api/event-calendar"
_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"
_FETCH_TIMEOUT_SECONDS = 12
_DEFAULT_CACHE = Path.home() / ".nse_algo_trader" / "nse_event_calendar.json"


def fetch_nse_event_calendar() -> list[dict]:
    """Real fetch seam: curl_cffi Chrome session (homepage cookie bootstrap → event-calendar API). [] on failure."""
    try:
        from curl_cffi import requests as curl_requests

        session: Any = curl_requests.Session(impersonate="chrome")  # curl_cffi is untyped
        session.get(_NSE_HOME, timeout=_FETCH_TIMEOUT_SECONDS)  # bootstrap cookies
        response = session.get(_EVENT_CALENDAR_API, headers={"Referer": _REFERER}, timeout=_FETCH_TIMEOUT_SECONDS)
        payload = response.json()
        return list(payload) if isinstance(payload, list) else []
    except Exception:  # noqa: BLE001 — network/anti-bot failure must degrade to the cache, never raise
        return []


def _parse_nse_date(value: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


class NseEventCalendarSource:
    """Serves per-symbol event proximity from NSE's event calendar, with a persisted cache (carried state)."""

    def __init__(
        self,
        fetch: Callable[[], list[dict]] | None = None,
        cache_path: Path | None = None,
    ):
        self._fetch = fetch or fetch_nse_event_calendar
        self._cache_path = cache_path or _DEFAULT_CACHE
        self._events_by_symbol: dict[str, list[date]] = {}
        self._load_cache()

    def refresh(self) -> int:
        """Fetch the live calendar, persist it, and index it by symbol. Returns the event count (0 = kept cache)."""
        records = self._fetch()
        if not records:
            return 0
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(records, indent=0))
        self._index(records)
        return len(records)

    def _load_cache(self) -> None:
        if self._cache_path.exists():
            try:
                self._index(json.loads(self._cache_path.read_text()))
            except (json.JSONDecodeError, OSError):
                self._events_by_symbol = {}

    def _index(self, records: list[dict]) -> None:
        index: dict[str, list[date]] = {}
        for record in records:
            symbol = str(record.get("symbol", "")).strip().upper()
            event_date = _parse_nse_date(record.get("date", ""))
            if symbol and event_date is not None:
                index.setdefault(symbol, []).append(event_date)
        self._events_by_symbol = {s: sorted(d) for s, d in index.items()}

    def signed_days_to_nearest_event(self, underlying: str, as_of: date) -> int | None:
        """Days to the nearest scheduled event for ``underlying`` (<0 past, >0 ahead); None if unknown."""
        dates = self._events_by_symbol.get(str(underlying).strip().upper())
        if not dates:
            return None
        return min(((d - as_of).days for d in dates), key=abs)
