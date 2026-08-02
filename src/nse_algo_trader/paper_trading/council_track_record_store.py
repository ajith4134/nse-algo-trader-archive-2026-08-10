"""Per-role reputation ledger for the prediction council (Layer 11 slice 5, research/104).

Each row is one RESOLVED council forecast: `(role, probability, is_true)` — the probability a
member assigned a proposition and whether it turned out TRUE. `role_log_loss()` returns each
role's mean log-loss in bits over its resolved forecasts (−log₂ of the probability it put on the
realised outcome; 1.0 bit = a coin-flip guess, lower = sharper-and-right). That reputation is what
`prediction_council.track_record_weights` reads to weight the council — accurate roles earn more
weight. Rows are recorded only when a proposition RESOLVES (the mechanism's next live trade
closes), so the reputation is prequential.

Its OWN small `.sqlite3` file (append-only). DI path seam so tests use a temp file.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_COUNCIL_TRACK_RECORD_DB_PATH = Path(
    "~/.nse_algo_trader/council_track_record.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS council_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    role TEXT NOT NULL,
    probability REAL NOT NULL,
    is_true INTEGER NOT NULL
)
"""

_LOG_LOSS_EPSILON = 1e-9


class CouncilTrackRecordStore:
    def __init__(
        self, db_file_path: Path = DEFAULT_COUNCIL_TRACK_RECORD_DB_PATH
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

    def record_resolved_forecast(
        self, role: str, probability: float, is_true: bool, recorded_at: datetime
    ) -> None:
        """Append one resolved forecast for `role` — a member's probability + the true outcome."""
        self._connection.execute(
            "INSERT INTO council_forecasts (recorded_at, role, probability, is_true) "
            "VALUES (?, ?, ?, ?)",
            (recorded_at.isoformat(), role, float(probability), 1 if is_true else 0),
        )
        self._connection.commit()

    def role_log_loss(self) -> dict[str, float | None]:
        """Each role's mean log-loss (bits) over its resolved forecasts — the reputation the
        council weighting reads. A role with no resolved forecasts is absent from the map
        (treated as the coin-flip baseline by the weighting)."""
        cursor = self._connection.execute(
            "SELECT role, probability, is_true FROM council_forecasts"
        )
        loss_sum: dict[str, float] = {}
        counts: dict[str, int] = {}
        for row in cursor.fetchall():
            probability = min(1.0 - _LOG_LOSS_EPSILON, max(_LOG_LOSS_EPSILON, row["probability"]))
            probability_of_outcome = probability if row["is_true"] else 1.0 - probability
            loss_sum[row["role"]] = loss_sum.get(row["role"], 0.0) + (
                -math.log2(probability_of_outcome)
            )
            counts[row["role"]] = counts.get(row["role"], 0) + 1
        return {role: loss_sum[role] / counts[role] for role in loss_sum}

    def resolved_forecast_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM council_forecasts"
        ).fetchone()[0]
