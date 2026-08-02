"""Hermetic test for workspace rumination (Trunk VIII; research/129): a history dominated by one
concern flags rumination; a diverse or short history does not. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.sentience.global_workspace import WorkspaceBroadcast
from nse_algo_trader.sentience.workspace_rumination import ruminate


def _b(source, kind="safety"):
    return WorkspaceBroadcast(winner_source=source, kind=kind, content="c", salience=0.7, ignited=True)


def test_dominant_concern_flags_rumination():
    hist = [_b("goal_integrity")] * 5 + [_b("red_team", "risk")]
    r = ruminate(hist)
    assert r.dominant_recurring == "goal_integrity" and r.dominant_kind == "safety"
    assert r.recurrence_count == 5 and abs(r.recurrence_fraction - 5 / 6) < 1e-9
    assert r.is_ruminating and "RUMINATING" in r.summary


def test_diverse_history_is_not_rumination():
    hist = [_b("a"), _b("b"), _b("c"), _b("d")]
    r = ruminate(hist)
    assert not r.is_ruminating and r.distinct_concerns == 4


def test_short_history_never_ruminates():
    r = ruminate([_b("a"), _b("a")], min_history=4)  # dominant but too short
    assert not r.is_ruminating and r.dominant_recurring == "a"


def test_empty_history_handled():
    r = ruminate([])
    assert not r.is_ruminating and r.recurrence_count == 0 and r.dominant_recurring is None


def test_none_entries_ignored():
    r = ruminate([None, _b("x"), None, _b("x"), _b("x"), _b("x")])
    assert r.dominant_recurring == "x" and r.recurrence_count == 4 and r.is_ruminating
