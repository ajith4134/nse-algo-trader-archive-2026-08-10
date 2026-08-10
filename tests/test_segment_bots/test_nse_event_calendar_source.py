"""Tests for the NSE corporate-event calendar scraper (hermetic fetch seam + gate integration)."""

from __future__ import annotations

from datetime import date

import pytest

from nse_algo_trader.segment_bots.stock_option_bot.event_calendar_gate import (
    EventPhase,
    EventProximityGate,
)
from nse_algo_trader.segment_bots.stock_option_bot.nse_event_calendar_source import (
    NseEventCalendarSource,
)

_FAKE_EVENTS = [
    {"symbol": "INFY", "company": "Infosys", "purpose": "Financial Results", "date": "10-Aug-2026"},
    {"symbol": "RELIANCE", "company": "Reliance", "purpose": "Board Meeting", "date": "05-Aug-2026"},
    {"symbol": "reliance", "company": "Reliance", "purpose": "Dividend", "date": "20-Aug-2026"},  # case + 2nd date
    {"symbol": "", "date": "bad"},  # junk row must be ignored
]


def _source(tmp_path):
    return NseEventCalendarSource(fetch=lambda: _FAKE_EVENTS, cache_path=tmp_path / "cal.json")


def test_refresh_indexes_by_symbol_and_persists(tmp_path):
    src = _source(tmp_path)
    assert src.refresh() == 4  # raw records fetched
    assert (tmp_path / "cal.json").exists()  # persisted cache


def test_signed_days_to_nearest_event(tmp_path):
    src = _source(tmp_path)
    src.refresh()
    # nearest RELIANCE event is 05-Aug (the 20-Aug one is further)
    assert src.signed_days_to_nearest_event("RELIANCE", date(2026, 8, 3)) == 2
    assert src.signed_days_to_nearest_event("INFY", date(2026, 8, 3)) == 7
    # a past event returns a negative signed distance
    assert src.signed_days_to_nearest_event("RELIANCE", date(2026, 8, 6)) == -1
    assert src.signed_days_to_nearest_event("UNKNOWNSYM", date(2026, 8, 3)) is None


def test_gate_reads_real_shape_events(tmp_path):
    src = _source(tmp_path)
    src.refresh()
    gate = EventProximityGate()
    pre = gate.assess("RELIANCE", date(2026, 8, 4), src)  # event next day
    assert pre.phase == EventPhase.PRE_EVENT and pre.blocks_naked_premium
    clear = gate.assess("INFY", date(2026, 7, 1), src)  # far out
    assert clear.phase == EventPhase.CLEAR


def test_empty_fetch_keeps_cache_and_returns_zero(tmp_path):
    good = _source(tmp_path)
    good.refresh()
    # a later empty fetch (network fail) must NOT wipe the cached calendar
    empty = NseEventCalendarSource(fetch=lambda: [], cache_path=tmp_path / "cal.json")
    assert empty.refresh() == 0
    assert empty.signed_days_to_nearest_event("INFY", date(2026, 8, 3)) == 7  # served from cache


def test_case_insensitive_symbol_lookup(tmp_path):
    src = _source(tmp_path)
    src.refresh()
    assert src.signed_days_to_nearest_event("reliance", date(2026, 8, 3)) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
