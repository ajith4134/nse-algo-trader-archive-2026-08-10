"""Prequential-observation store for the debate risk_score earn-calibration harness
(Layer 11 slice 2c, research/101).

Each row is one `(mechanism_name, risk_score, is_win)` pair recorded when a LIVE intraday trade
closes, where `risk_score` is the debate's per-mechanism score computed EARLIER THE SAME DAY
(from memory up to yesterday) — so it predates the outcome and the pair is non-circular. The
`debate_risk_calibration_harness` reads these to decide whether the risk signal has earned the
right to gate entries. Replay/unknown-mechanism outcomes are never recorded here (the service
filters them out before calling `record_observation`).

Its OWN small `.sqlite3` file (append-only; one row per closed live trade with a debated
mechanism). DI path seam so tests use a temp file and never touch the real store.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from nse_algo_trader.llm_strategy.debate_risk_calibration_harness import (
    RiskOutcomeObservation,
)

DEFAULT_DEBATE_RISK_OBSERVATION_DB_PATH = Path(
    "~/.nse_algo_trader/debate_risk_observations.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS debate_risk_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    mechanism_name TEXT NOT NULL,
    risk_score REAL NOT NULL,
    is_win INTEGER NOT NULL
)
"""


class DebateRiskPrequentialObservationStore:
    def __init__(
        self, db_file_path: Path = DEFAULT_DEBATE_RISK_OBSERVATION_DB_PATH
    ) -> None:
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

    def record_observation(
        self, mechanism_name: str, risk_score: float, is_win: bool, recorded_at: datetime
    ) -> None:
        """Append one prequential (risk_score, outcome) pair for a closed LIVE trade."""
        self._connection.execute(
            "INSERT INTO debate_risk_observations "
            "(recorded_at, mechanism_name, risk_score, is_win) VALUES (?, ?, ?, ?)",
            (recorded_at.isoformat(), mechanism_name, float(risk_score), 1 if is_win else 0),
        )
        self._connection.commit()

    def all_observations(self) -> list[RiskOutcomeObservation]:
        """Every accrued pair, oldest first — the harness's input."""
        cursor = self._connection.execute(
            "SELECT risk_score, is_win FROM debate_risk_observations ORDER BY id"
        )
        return [
            RiskOutcomeObservation(risk_score=row["risk_score"], is_win=bool(row["is_win"]))
            for row in cursor.fetchall()
        ]

    def observation_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM debate_risk_observations"
        ).fetchone()[0]
