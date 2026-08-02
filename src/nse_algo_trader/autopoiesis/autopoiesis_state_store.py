"""Trunk X AUTOPOIESIS — the homeostat's carried STATE (append-only SQLite).

Why persistence is load-bearing here, not incidental:

  · **Censored survival data only exists across restarts.** A component's lifetime is measured from when
    it was last known-new until it fails or "now". If the ledger were in memory, every process restart
    would reset every lifetime to zero and the Weibull-AFT fit would never see a real failure. The
    survival model's entire input is history.
  · **The safety organs currently LOSE their state on restart** — `conscience/incident_post_mortem`
    names this gap explicitly (Referee, off-switch and tripwires hold incident state in memory only).
    The repair ledger here is append-only precisely so a repair storm is still visible after the crash
    it caused.
  · **Circuit-breaker state must outlive the process** — otherwise every restart silently re-closes
    every breaker and the organism re-attacks the failing dependency it had just isolated.

Schema (4 tables, all append-only except the breaker-state upsert):
  `component_telemetry_sample`  — raw vital signs per component per cycle (the health-index input)
  `component_lifetime_event`    — lifetime observations WITH the right-censoring flag (survival input)
  `component_repair_action`     — every repair/replace/quarantine attempted, its outcome and cost
  `component_breaker_state`     — current circuit-breaker state per component (upserted, not appended)

Follows the repo's established SQLite idiom (`memory_reflection/sqlite_experience_memory`,
`conscience/incident_post_mortem_store`): one connection per store instance, WAL journal mode,
`CREATE TABLE IF NOT EXISTS` at init, additive `PRAGMA table_info` migration for older databases.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nse_algo_trader.autopoiesis.component_registry import ComponentClass

DEFAULT_AUTOPOIESIS_DB_PATH = Path("~/.nse_algo_trader/autopoiesis_homeostat.sqlite3").expanduser()


@dataclass(frozen=True)
class PersistedTelemetrySample:
    component_id: str
    captured_at: datetime
    signal_name: str
    signal_value: float


@dataclass(frozen=True)
class PersistedLifetimeEvent:
    """One survival observation. `observed_failure=False` means RIGHT-CENSORED (still alive).

    Right-censoring is the dominant case and must never be confused with "no data": a component that
    has run 700 hours without failing is strong evidence about its lifetime distribution, and the
    Weibull-AFT likelihood uses it. Dropping censored rows would bias every estimate catastrophically.
    """

    component_id: str
    # The typed currency across this package. Persisted as its `.value` TEXT and parsed back on read,
    # so a caller never has to remember which side of the store speaks enum and which speaks str —
    # a mismatch here crashes the survival fit at wiring time (caught by a real-data pass, 2026-07-27).
    component_class: ComponentClass
    recorded_at: datetime
    uptime_hours: float
    observed_failure: bool
    restart_count: int
    degradation_trend: float
    failure_reason: str = ""


@dataclass(frozen=True)
class PersistedRepairAction:
    component_id: str
    attempted_at: datetime
    action_kind: str
    succeeded: bool
    detail: str
    duration_seconds: float


class AutopoiesisStateStore:
    """Durable memory of the organism's own health, failures and repairs."""

    def __init__(self, database_path: Path = DEFAULT_AUTOPOIESIS_DB_PATH) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        # DELIBERATELY single-threaded (check_same_thread left at the stdlib default True).
        # `test_real_state_store_is_single_threaded_by_construction` pins this as a SAFETY property,
        # not an oversight: cross-thread access RAISES, and the repair executor turns that raise into
        # a budget REFUSAL rather than an unmetered repair. B25a moved the homeostat onto the
        # feature-plane thread, where it is now both created and used consistently — so the
        # single-thread guarantee is preserved rather than needing to be relaxed.
        self._connection = sqlite3.connect(str(database_path))
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._create_schema_if_absent()
        self._apply_additive_migrations()

    # -- schema ------------------------------------------------------------------------------------

    def _create_schema_if_absent(self) -> None:
        cursor = self._connection.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS component_telemetry_sample (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   component_id TEXT NOT NULL,
                   captured_at TEXT NOT NULL,
                   signal_name TEXT NOT NULL,
                   signal_value REAL NOT NULL)"""
        )
        cursor.execute(
            """CREATE INDEX IF NOT EXISTS idx_telemetry_component_time
                   ON component_telemetry_sample (component_id, captured_at)"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS component_lifetime_event (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   component_id TEXT NOT NULL,
                   component_class TEXT NOT NULL,
                   recorded_at TEXT NOT NULL,
                   uptime_hours REAL NOT NULL,
                   observed_failure INTEGER NOT NULL,
                   restart_count INTEGER NOT NULL,
                   degradation_trend REAL NOT NULL,
                   failure_reason TEXT NOT NULL DEFAULT '')"""
        )
        cursor.execute(
            """CREATE INDEX IF NOT EXISTS idx_lifetime_class
                   ON component_lifetime_event (component_class, observed_failure)"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS component_repair_action (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   component_id TEXT NOT NULL,
                   attempted_at TEXT NOT NULL,
                   action_kind TEXT NOT NULL,
                   succeeded INTEGER NOT NULL,
                   detail TEXT NOT NULL DEFAULT '',
                   duration_seconds REAL NOT NULL DEFAULT 0.0)"""
        )
        cursor.execute(
            """CREATE INDEX IF NOT EXISTS idx_repair_component_time
                   ON component_repair_action (component_id, attempted_at)"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS component_breaker_state (
                   component_id TEXT PRIMARY KEY,
                   breaker_state TEXT NOT NULL,
                   consecutive_failure_count INTEGER NOT NULL DEFAULT 0,
                   updated_at TEXT NOT NULL)"""
        )
        self._connection.commit()

    def _apply_additive_migrations(self) -> None:
        """Add columns missing from databases created by an earlier version (repo idiom).

        Never drops or rewrites: an append-only forensic ledger must not lose history to a migration.
        """
        expected_columns = {
            "component_lifetime_event": {"failure_reason": "TEXT NOT NULL DEFAULT ''"},
            "component_repair_action": {"duration_seconds": "REAL NOT NULL DEFAULT 0.0"},
        }
        cursor = self._connection.cursor()
        for table_name, columns in expected_columns.items():
            present = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")}
            for column_name, column_definition in columns.items():
                if column_name not in present:
                    cursor.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                    )
        self._connection.commit()

    # -- writes ------------------------------------------------------------------------------------

    def record_telemetry_samples(self, samples: Iterable[PersistedTelemetrySample]) -> int:
        """Append raw vital signs. Returns the row count written (surfaced, never assumed — Rule O.3)."""
        rows = [
            (s.component_id, _as_utc_text(s.captured_at), s.signal_name, float(s.signal_value))
            for s in samples
        ]
        if not rows:
            return 0
        self._connection.executemany(
            """INSERT INTO component_telemetry_sample
                   (component_id, captured_at, signal_name, signal_value) VALUES (?, ?, ?, ?)""",
            rows,
        )
        self._connection.commit()
        return len(rows)

    def record_lifetime_event(self, event: PersistedLifetimeEvent) -> None:
        self._connection.execute(
            """INSERT INTO component_lifetime_event
                   (component_id, component_class, recorded_at, uptime_hours, observed_failure,
                    restart_count, degradation_trend, failure_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.component_id, event.component_class.value, _as_utc_text(event.recorded_at),
             float(event.uptime_hours), int(event.observed_failure), int(event.restart_count),
             float(event.degradation_trend), event.failure_reason),
        )
        self._connection.commit()

    def record_repair_action(self, action: PersistedRepairAction) -> None:
        self._connection.execute(
            """INSERT INTO component_repair_action
                   (component_id, attempted_at, action_kind, succeeded, detail, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?)""",
            (action.component_id, _as_utc_text(action.attempted_at), action.action_kind,
             int(action.succeeded), action.detail, float(action.duration_seconds)),
        )
        self._connection.commit()

    def upsert_breaker_state(self, component_id: str, breaker_state: str,
                             consecutive_failure_count: int, updated_at: datetime) -> None:
        """Breaker state is CURRENT state, not history — the one upserted table."""
        self._connection.execute(
            """INSERT INTO component_breaker_state
                   (component_id, breaker_state, consecutive_failure_count, updated_at)
                   VALUES (?, ?, ?, ?)
               ON CONFLICT(component_id) DO UPDATE SET
                   breaker_state=excluded.breaker_state,
                   consecutive_failure_count=excluded.consecutive_failure_count,
                   updated_at=excluded.updated_at""",
            (component_id, breaker_state, int(consecutive_failure_count), _as_utc_text(updated_at)),
        )
        self._connection.commit()

    # -- reads -------------------------------------------------------------------------------------

    def read_recent_telemetry(self, component_id: str, limit: int = 500
                              ) -> tuple[tuple[datetime, str, float], ...]:
        """Most-recent-first telemetry for one component — the health index's baseline window."""
        rows = self._connection.execute(
            """SELECT captured_at, signal_name, signal_value FROM component_telemetry_sample
                   WHERE component_id = ? ORDER BY id DESC LIMIT ?""",
            (component_id, int(limit)),
        ).fetchall()
        return tuple((_parse_utc_text(r[0]), str(r[1]), float(r[2])) for r in rows)

    def read_lifetime_events(self, component_class: ComponentClass | None = None
                             ) -> tuple[PersistedLifetimeEvent, ...]:
        """Survival-model input. Class-filtered when pooling a single population."""
        if component_class is None:
            rows = self._connection.execute(
                """SELECT component_id, component_class, recorded_at, uptime_hours, observed_failure,
                          restart_count, degradation_trend, failure_reason
                       FROM component_lifetime_event ORDER BY id"""
            ).fetchall()
        else:
            rows = self._connection.execute(
                """SELECT component_id, component_class, recorded_at, uptime_hours, observed_failure,
                          restart_count, degradation_trend, failure_reason
                       FROM component_lifetime_event WHERE component_class = ? ORDER BY id""",
                (component_class.value,),
            ).fetchall()
        return tuple(
            PersistedLifetimeEvent(
                component_id=str(r[0]), component_class=ComponentClass(str(r[1])),
                recorded_at=_parse_utc_text(r[2]),
                uptime_hours=float(r[3]), observed_failure=bool(r[4]), restart_count=int(r[5]),
                degradation_trend=float(r[6]), failure_reason=str(r[7]),
            )
            for r in rows
        )

    def count_observed_failures_by_class(self) -> Mapping[ComponentClass, int]:
        """How many REAL failures each class has seen — drives the Rule-Q maturity ladder."""
        rows = self._connection.execute(
            """SELECT component_class, SUM(observed_failure) FROM component_lifetime_event
                   GROUP BY component_class"""
        ).fetchall()
        return {ComponentClass(str(r[0])): int(r[1] or 0) for r in rows}

    def count_repairs_since(self, since: datetime) -> int:
        """Repairs attempted since a cutoff — the repair-budget meter's input."""
        row = self._connection.execute(
            "SELECT COUNT(*) FROM component_repair_action WHERE attempted_at >= ?",
            (_as_utc_text(since),),
        ).fetchone()
        return int(row[0]) if row else 0

    def read_repair_history(self, component_id: str, limit: int = 50
                            ) -> tuple[PersistedRepairAction, ...]:
        rows = self._connection.execute(
            """SELECT component_id, attempted_at, action_kind, succeeded, detail, duration_seconds
                   FROM component_repair_action WHERE component_id = ?
                   ORDER BY id DESC LIMIT ?""",
            (component_id, int(limit)),
        ).fetchall()
        return tuple(
            PersistedRepairAction(
                component_id=str(r[0]), attempted_at=_parse_utc_text(r[1]), action_kind=str(r[2]),
                succeeded=bool(r[3]), detail=str(r[4]), duration_seconds=float(r[5]),
            )
            for r in rows
        )

    def read_breaker_state(self, component_id: str) -> tuple[str, int] | None:
        row = self._connection.execute(
            """SELECT breaker_state, consecutive_failure_count FROM component_breaker_state
                   WHERE component_id = ?""",
            (component_id,),
        ).fetchone()
        return (str(row[0]), int(row[1])) if row else None

    def telemetry_sample_count(self, component_id: str) -> int:
        """Sample count for the maturity ladder's `have N / need M` display."""
        row = self._connection.execute(
            "SELECT COUNT(*) FROM component_telemetry_sample WHERE component_id = ?",
            (component_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._connection.close()


def _as_utc_text(moment: datetime) -> str:
    """Store timestamps UTC-explicit (Rule O.5 — IST/UTC confusion is a documented past bug class)."""
    if moment.tzinfo is None:
        raise ValueError(f"naive datetime rejected — timestamps must be timezone-aware: {moment!r}")
    return moment.astimezone(UTC).isoformat()


def _parse_utc_text(text: str) -> datetime:
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
