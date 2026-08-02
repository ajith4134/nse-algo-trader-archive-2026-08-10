"""SQLite store for recorded order-book depth (§53 slice 4 P4b).

Its OWN `.db` file — depth is far higher-volume than bars, so it is kept off the
bars store. Each snapshot is one row keyed by (instrument_token, captured_at) with
the two sides as JSON; that is enough for the future microstructure/replay-depth
consumers (the recorded-forward depth's eventual purpose).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from nse_algo_trader.market_data.market_depth_types import (
    MarketDepthLevel,
    MarketDepthSnapshot,
)

DEFAULT_MARKET_DEPTH_DB_PATH = Path(
    "~/.nse_algo_trader/market_depth.sqlite3"
).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS market_depth_snapshots (
    instrument_token INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    PRIMARY KEY (instrument_token, captured_at)
)
"""


def _levels_to_json(levels: tuple[MarketDepthLevel, ...]) -> str:
    return json.dumps([[lvl.price, lvl.quantity, lvl.orders] for lvl in levels])


def _levels_from_json(text: str) -> tuple[MarketDepthLevel, ...]:
    return tuple(
        MarketDepthLevel(price=p, quantity=q, orders=o) for p, q, o in json.loads(text)
    )


class MarketDepthSnapshotStore:
    def __init__(self, db_file_path: Path = DEFAULT_MARKET_DEPTH_DB_PATH) -> None:
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

    def save_snapshots(self, snapshots: list[MarketDepthSnapshot]) -> int:
        rows = [
            (
                s.instrument_token,
                s.captured_at.isoformat(),
                _levels_to_json(s.bids),
                _levels_to_json(s.asks),
            )
            for s in snapshots
        ]
        self._connection.executemany(
            "INSERT OR REPLACE INTO market_depth_snapshots VALUES (?,?,?,?)", rows
        )
        self._connection.commit()
        return len(rows)

    def load_snapshots(
        self,
        instrument_token: int,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[MarketDepthSnapshot]:
        clause = "WHERE instrument_token = ?"
        params: list = [instrument_token]
        if from_timestamp is not None:
            clause += " AND captured_at >= ?"
            params.append(from_timestamp.isoformat())
        if to_timestamp is not None:
            clause += " AND captured_at <= ?"
            params.append(to_timestamp.isoformat())
        cursor = self._connection.execute(
            f"SELECT * FROM market_depth_snapshots {clause} ORDER BY captured_at",
            params,
        )
        return [
            MarketDepthSnapshot(
                instrument_token=row["instrument_token"],
                captured_at=datetime.fromisoformat(row["captured_at"]),
                bids=_levels_from_json(row["bids_json"]),
                asks=_levels_from_json(row["asks_json"]),
            )
            for row in cursor.fetchall()
        ]

    def snapshot_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) AS n FROM market_depth_snapshots"
        ).fetchone()["n"]
