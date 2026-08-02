"""Hermetic test for the incident post-mortem (Trunk VII.14; research/113): the forensic store
persists safety incidents append-only + idempotently, and the pure summariser reduces them to a
reviewable post-mortem. Uses a temp-file SQLite store (the DI seam) — never touches the real
forensic record.
"""

from __future__ import annotations

from nse_algo_trader.conscience.incident_post_mortem import (
    INCIDENT_TYPE_CONSTITUTION_BLOCK,
    INCIDENT_TYPE_OFF_SWITCH_HALT,
    INCIDENT_TYPE_WIREHEADING_TRIP,
    SafetyIncident,
    summarize_incident_post_mortem,
)
from nse_algo_trader.conscience.incident_post_mortem_store import IncidentPostMortemStore


def _incident(kind, severity, when, trace_id, subject="scope", detail="d"):
    return SafetyIncident(
        incident_type=kind, severity=severity, occurred_at=when,
        subject=subject, detail=detail, trace_id=trace_id,
    )


def test_empty_record_summarizes_clean():
    pm = summarize_incident_post_mortem([])
    assert pm.total == 0 and pm.is_clean
    assert pm.critical_count == 0 and pm.first_seen is None and pm.last_seen is None
    assert "clean forensic record" in pm.headline


def test_summary_counts_by_type_and_severity_and_recency():
    incidents = [
        _incident(INCIDENT_TYPE_CONSTITUTION_BLOCK, "hard", "2026-07-20T10:00:00", "a"),
        _incident(INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", "2026-07-21T11:00:00", "b"),
        _incident(INCIDENT_TYPE_WIREHEADING_TRIP, "critical", "2026-07-22T12:00:00", "c"),
    ]
    pm = summarize_incident_post_mortem(incidents)
    # is_critical counts both "critical" and "hard" (a blocked constitutional violation is
    # forensically critical) → all 3 here are critical-severity.
    assert pm.total == 3 and pm.critical_count == 3
    assert pm.count_by_type[INCIDENT_TYPE_CONSTITUTION_BLOCK] == 1
    assert pm.count_by_severity["critical"] == 2 and pm.count_by_severity["hard"] == 1
    assert pm.first_seen == "2026-07-20T10:00:00" and pm.last_seen == "2026-07-22T12:00:00"
    # most_recent is newest-first
    assert pm.most_recent[0].trace_id == "c"
    assert "3 critical" in pm.headline


def test_store_persists_append_only_and_reloads(tmp_path):
    db = tmp_path / "safety_incidents.sqlite3"
    store = IncidentPostMortemStore(db)
    assert store.record_incident(
        _incident(INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", "2026-07-21T11:00:00", "h1")
    ) is True
    assert store.incident_count() == 1
    store.close()

    # reopen from disk — durability across "restart"
    reopened = IncidentPostMortemStore(db)
    reloaded = reopened.all_incidents()
    assert len(reloaded) == 1 and reloaded[0].trace_id == "h1"
    pm = summarize_incident_post_mortem(reloaded)
    assert pm.total == 1 and pm.critical_count == 1
    reopened.close()


def test_record_incident_is_idempotent_per_type_and_trace_id(tmp_path):
    store = IncidentPostMortemStore(tmp_path / "s.sqlite3")
    first = store.record_incident(
        _incident(INCIDENT_TYPE_CONSTITUTION_BLOCK, "hard", "2026-07-20T10:00:00", "same")
    )
    second = store.record_incident(  # same (type, trace_id) → ignored
        _incident(INCIDENT_TYPE_CONSTITUTION_BLOCK, "hard", "2026-07-20T10:05:00", "same")
    )
    assert first is True and second is False
    assert store.incident_count() == 1
    # a different type with the same trace_id is a distinct incident
    assert store.record_incident(
        _incident(INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", "2026-07-20T10:00:00", "same")
    ) is True
    assert store.incident_count() == 2
    store.close()


def test_recorded_trace_ids_scopes_to_type(tmp_path):
    store = IncidentPostMortemStore(tmp_path / "s.sqlite3")
    store.record_incident(_incident(INCIDENT_TYPE_CONSTITUTION_BLOCK, "hard", "t", "block-1"))
    store.record_incident(_incident(INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", "t", "halt-1"))
    assert store.recorded_trace_ids(INCIDENT_TYPE_CONSTITUTION_BLOCK) == {"block-1"}
    assert store.recorded_trace_ids(INCIDENT_TYPE_OFF_SWITCH_HALT) == {"halt-1"}
    store.close()
