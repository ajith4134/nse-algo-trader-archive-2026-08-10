"""Persistent coverage ledger for the deficit-driven replay curriculum (§53 slice 5a;
research/86).

Records the market regime of each historical session the curriculum has replayed, so
successive market-closed activations can ROTATE toward under-covered regimes instead of
re-picking the same day. Without persistence the curriculum has no memory of what it has
already learned from, so every activation would choose the same rarest-historical day.

Its OWN small `.sqlite3` file (one row per replayed session date; last write wins per
date, so re-replaying a day doesn't double-count it).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime

DEFAULT_REPLAY_CURRICULUM_DB_PATH = Path(
    "~/.nse_algo_trader/replay_curriculum.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS replayed_session_regimes (
    session_date TEXT PRIMARY KEY,
    market_regime TEXT NOT NULL
)
"""


class ReplayedSessionRegimeLedger:
    def __init__(self, db_file_path: Path = DEFAULT_REPLAY_CURRICULUM_DB_PATH) -> None:
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

    def record_replayed_session(self, session_date: date, market_regime: MarketRegime) -> None:
        """Persist that `session_date` was replayed as `market_regime` (idempotent per
        date — re-recording the same day updates rather than double-counts)."""
        self._connection.execute(
            "INSERT INTO replayed_session_regimes (session_date, market_regime) "
            "VALUES (?, ?) ON CONFLICT(session_date) DO UPDATE SET market_regime=excluded.market_regime",
            (session_date.isoformat(), market_regime.value),
        )
        self._connection.commit()

    def covered_regime_counts(self) -> dict[str, int]:
        """How many distinct replayed sessions fall in each market regime, keyed by
        `MarketRegime.value` — the deficit signal the selector minimises over."""
        cursor = self._connection.execute(
            "SELECT market_regime, COUNT(*) AS n FROM replayed_session_regimes "
            "GROUP BY market_regime"
        )
        return {row["market_regime"]: row["n"] for row in cursor.fetchall()}

    def replayed_session_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM replayed_session_regimes"
        ).fetchone()[0]
