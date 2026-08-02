"""Types for the news/sentiment sense (Trunk II SENSES; research/140). PURE — no I/O.

A `RawNewsItem` is one ingested headline (title + summary + link + timestamps + a dedup hash). A
`FeedFreshness` records whether a feed is live or stale (the Moneycontrol trap: HTTP 200 but content
frozen since 2024). A `NewsIngestionReport` summarises one polling pass for the dashboard.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NewsSourceTier(str, Enum):
    """Ingestion tiers (research/140) — each earns its own reliability score in a later slice."""

    PUBLIC_NEWS = "public_news"        # tier-1: mainstream financial-news RSS (S1)
    BROKER_RESEARCH = "broker_research"  # tier-2: broker / TradingView analyst levels (S4)
    SOCIAL = "social"                  # tier-3: X / Telegram, advisory-until-proven (S5)
    EXCHANGE_FILING = "exchange_filing"  # official NSE/BSE corporate filings (S4c) — highest trust


@dataclass(frozen=True)
class RawNewsItem:
    """One ingested news headline. `content_hash` is the dedup key (stable across re-polls)."""

    source_id: str
    source_name: str
    tier: str
    title: str
    summary: str
    url: str
    published_at: datetime | None   # UTC-aware; None when the feed omits per-item dates
    fetched_at: datetime            # UTC-aware, when this poll ran
    content_hash: str = ""

    @staticmethod
    def compute_content_hash(source_id: str, url: str, title: str) -> str:
        return hashlib.sha1(f"{source_id}|{url}|{title}".encode()).hexdigest()


@dataclass(frozen=True)
class FeedFreshness:
    """Per-feed staleness verdict — the guard against feeds that return 200 with stale content."""

    source_id: str
    newest_item_age_seconds: float | None  # None when no item carried a date
    is_stale: bool
    reason: str


@dataclass(frozen=True)
class FeedPollResult:
    """The outcome of polling ONE feed: its items, its freshness verdict, any fetch error."""

    source_id: str
    source_name: str
    tier: str
    items: tuple = ()               # tuple[RawNewsItem, ...]
    freshness: FeedFreshness | None = None
    fetch_error: str = ""

    @property
    def is_usable(self) -> bool:
        """A feed contributes items only when it fetched cleanly and is not stale."""
        return not self.fetch_error and self.freshness is not None and not self.freshness.is_stale


@dataclass(frozen=True)
class NewsIngestionReport:
    """One polling pass, summarised for the dashboard + downstream slices."""

    run_at: datetime
    feeds_total: int
    feeds_fresh: int
    feeds_stale: int
    stale_source_ids: tuple = ()    # tuple[str, ...]
    error_source_ids: tuple = ()    # tuple[str, ...]
    items_seen: int = 0
    items_new: int = 0              # after dedup against the store
    items_by_tier: dict = field(default_factory=dict)
    newest_titles: tuple = ()       # tuple[str, ...] — a few freshest headlines
    stored_total: int = 0           # running total rows in the news store
    summary: str = ""
