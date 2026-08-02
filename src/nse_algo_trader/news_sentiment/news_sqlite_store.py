"""Persistent store for ingested news items (Trunk II SENSES; research/140, 142).

SQLite at ~/.nse_algo_trader/news.sqlite3. Dedup is by `content_hash` (PRIMARY KEY) — re-polling the
same feed never double-stores. Mirrors the `MarketDataSqliteStore` idiom (WAL, INSERT OR IGNORE).
The `news_levels` table (S2, research/142) holds the structured index support/resistance levels
extracted from stored headlines. Later slices add sentiment/materiality columns + a reliability table.
"""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from nse_algo_trader.news_sentiment.news_item_types import RawNewsItem
from nse_algo_trader.news_sentiment.news_level_types import ExtractedLevel, ExtractedLevelSet

DEFAULT_NEWS_DB_FILE_PATH = Path.home() / ".nse_algo_trader" / "news.sqlite3"

_CREATE_NEWS_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS news_items (
    content_hash TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    source_name  TEXT NOT NULL,
    tier         TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    url          TEXT NOT NULL,
    published_at TEXT,
    fetched_at   TEXT NOT NULL
)
"""

# S2 (research/142): one row per (news item, underlying, level value, kind). Keyed so re-extracting
# the same headline never double-stores. `content_hash` ties each level back to its source news item.
_CREATE_NEWS_LEVELS_TABLE = """
CREATE TABLE IF NOT EXISTS news_levels (
    content_hash TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    source_name  TEXT NOT NULL,
    title        TEXT NOT NULL,
    underlying   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    value        REAL NOT NULL,
    confidence   REAL NOT NULL,
    evidence     TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (content_hash, underlying, value, kind)
)
"""


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class NewsSqliteStore:
    def __init__(self, db_file_path: Path = DEFAULT_NEWS_DB_FILE_PATH):
        import sqlite3

        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        # B25a: reached from BOTH the trading thread and the feature-plane thread.
        # SQLite refuses cross-thread use by default; access is short, immediately
        # committed writes plus reads, which SQLite serialises safely.
        self._connection = sqlite3.connect(str(db_file_path), check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(_CREATE_NEWS_ITEMS_TABLE)
        self._connection.execute(_CREATE_NEWS_LEVELS_TABLE)
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS news_items_fetched_at ON news_items(fetched_at)"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS news_levels_underlying ON news_levels(underlying)"
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def save_news_items(self, items) -> int:
        """INSERT OR IGNORE — returns the count of genuinely NEW rows (after dedup)."""
        before = self.total_item_count()
        self._connection.executemany(
            """INSERT OR IGNORE INTO news_items
               (content_hash, source_id, source_name, tier, title, summary, url, published_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    i.content_hash, i.source_id, i.source_name, i.tier, i.title, i.summary, i.url,
                    _to_iso(i.published_at), _to_iso(i.fetched_at),
                )
                for i in items
            ],
        )
        self._connection.commit()
        return self.total_item_count() - before

    def total_item_count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM news_items").fetchone()[0])

    def source_item_counts(self) -> list:
        """Per-source item volume — (source_id, source_name, tier, count) — for S3 reliability scoring."""
        rows = self._connection.execute(
            """SELECT source_id, source_name, tier, COUNT(*) AS n
               FROM news_items GROUP BY source_id, source_name, tier ORDER BY n DESC"""
        ).fetchall()
        return [(r[0], r[1], r[2], int(r[3])) for r in rows]

    def save_extracted_levels(self, level_sets) -> int:
        """INSERT OR IGNORE each level of each set — returns the count of genuinely NEW level rows."""
        before = self.level_count()
        rows = [
            (
                s.content_hash, s.source_id, s.source_name, s.title, s.underlying,
                lvl.kind, lvl.value, lvl.confidence, lvl.evidence, _to_iso(s.published_at),
            )
            for s in level_sets
            for lvl in s.levels
        ]
        if rows:
            self._connection.executemany(
                """INSERT OR IGNORE INTO news_levels
                   (content_hash, source_id, source_name, title, underlying, kind, value,
                    confidence, evidence, published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            self._connection.commit()
        return self.level_count() - before

    def level_count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM news_levels").fetchone()[0])

    def load_recent_levels(self, limit: int = 50) -> list:
        """Most-recently-published index levels first, regrouped into `ExtractedLevelSet`s per item."""
        rows = self._connection.execute(
            """SELECT content_hash, source_id, source_name, title, underlying, kind, value,
                      confidence, evidence, published_at
               FROM news_levels
               ORDER BY (published_at IS NULL), published_at DESC, confidence DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        grouped: dict = {}
        order: list = []
        for r in rows:
            key = (r[0], r[4])  # (content_hash, underlying)
            if key not in grouped:
                grouped[key] = {
                    "content_hash": r[0], "source_id": r[1], "source_name": r[2], "title": r[3],
                    "underlying": r[4], "published_at": _from_iso(r[9]), "levels": [],
                }
                order.append(key)
            grouped[key]["levels"].append(
                ExtractedLevel(value=r[6], kind=r[5], confidence=r[7], evidence=r[8])
            )
        return [
            ExtractedLevelSet(
                content_hash=g["content_hash"], source_id=g["source_id"], source_name=g["source_name"],
                title=g["title"], underlying=g["underlying"],
                levels=tuple(sorted(g["levels"], key=lambda x: x.value)),
                published_at=g["published_at"],
            )
            for g in (grouped[k] for k in order)
        ]

    def load_recent_items(self, limit: int = 50) -> list:
        """Most-recently-fetched items first (published_at as tiebreak)."""
        rows = self._connection.execute(
            """SELECT content_hash, source_id, source_name, tier, title, summary, url,
                      published_at, fetched_at
               FROM news_items ORDER BY fetched_at DESC, published_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            RawNewsItem(
                source_id=r[1], source_name=r[2], tier=r[3], title=r[4], summary=r[5], url=r[6],
                published_at=_from_iso(r[7]), fetched_at=_from_iso(r[8]) or datetime.now(UTC),
                content_hash=r[0],
            )
            for r in rows
        ]
