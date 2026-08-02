"""Forensic safety-incident store — the durable persistence behind the incident post-mortem
(Trunk VII.14; research/113).

Append-only SQLite forensic log: each row is one `SafetyIncident` (a Referee block, an off-switch
halt, a posture breach, or a critical alignment tripwire trip). Its OWN small `.sqlite3` file so a
safety record can never be lost inside the busy market-data DB. A UNIQUE index on
`(incident_type, trace_id)` makes `record_incident` idempotent — the daily recording cadence can
re-run without double-logging the same day's verdict. DI path seam so tests use a temp file and the
fake never touches the real forensic store (Rule J hermetic isolation).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from nse_algo_trader.conscience.incident_post_mortem import SafetyIncident

DEFAULT_SAFETY_INCIDENT_DB_PATH = Path(
    "~/.nse_algo_trader/safety_incidents.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS safety_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    subject TEXT NOT NULL,
    detail TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    UNIQUE (incident_type, trace_id)
)
"""


class IncidentPostMortemStore:
    """Append-only forensic store for safety incidents. `record_incident` is idempotent per
    `(incident_type, trace_id)`; reads return the record oldest-first for the post-mortem."""

    def __init__(self, db_file_path: Path = DEFAULT_SAFETY_INCIDENT_DB_PATH) -> None:
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        # B25a: reached from BOTH the trading thread and the feature-plane thread.
        # SQLite refuses cross-thread use by default; access is short, immediately
        # committed writes plus reads, which SQLite serialises safely.
        self._connection = sqlite3.connect(str(db_file_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(_CREATE_TABLE)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def record_incident(self, incident: SafetyIncident) -> bool:
        """Append one incident. Returns True if a new forensic row was written, False if the same
        `(incident_type, trace_id)` was already recorded (idempotent — never disturbs the record)."""
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO safety_incidents "
            "(incident_type, severity, occurred_at, subject, detail, trace_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                incident.incident_type, incident.severity, incident.occurred_at,
                incident.subject, incident.detail, incident.trace_id,
            ),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def all_incidents(self) -> list[SafetyIncident]:
        """Every recorded incident, oldest first — the post-mortem summariser's input."""
        cursor = self._connection.execute(
            "SELECT incident_type, severity, occurred_at, subject, detail, trace_id "
            "FROM safety_incidents ORDER BY id"
        )
        return [
            SafetyIncident(
                incident_type=row["incident_type"], severity=row["severity"],
                occurred_at=row["occurred_at"], subject=row["subject"],
                detail=row["detail"], trace_id=row["trace_id"],
            )
            for row in cursor.fetchall()
        ]

    def recent_incidents(self, limit: int = 5) -> list[SafetyIncident]:
        """The most recent incidents, newest first."""
        return list(reversed(self.all_incidents()))[:limit]

    def incident_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM safety_incidents"
        ).fetchone()[0]

    def recorded_trace_ids(self, incident_type: str) -> set[str]:
        """The `trace_id`s already persisted for a type — lets the daily referee-block drain skip
        blocks it has already logged without a failed INSERT per row."""
        cursor = self._connection.execute(
            "SELECT trace_id FROM safety_incidents WHERE incident_type = ?", (incident_type,)
        )
        return {row["trace_id"] for row in cursor.fetchall()}
