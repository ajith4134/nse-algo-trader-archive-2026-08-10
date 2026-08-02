"""Fetch + parse tier-1 RSS feeds, with per-feed STALENESS detection (Trunk II SENSES; research/140).

The network fetch sits behind a `fetch_bytes` DI seam (Rule J): production uses the real HTTP getter;
tests inject a fake returning canned RSS bytes, so parsing + staleness logic verify hermetically with
no network. The parse + freshness functions are PURE (bytes → items, items → verdict) and independently
testable.

Staleness is the load-bearing guard: several Indian feeds (Moneycontrol, some Zee Business) return
HTTP 200 with content frozen for months — a live-looking XML wrapper with dead content. We reject any
feed whose newest dated item is older than `stale_after` (default 24h), so dead feeds never pollute
the sense (research/138 §2.1).
"""

from __future__ import annotations

from calendar import timegm
from datetime import datetime, timedelta, UTC

import feedparser

from nse_algo_trader.news_sentiment.news_item_types import (
    FeedFreshness,
    FeedPollResult,
    RawNewsItem,
)

DEFAULT_STALE_AFTER = timedelta(hours=24)
_HTTP_TIMEOUT_SECONDS = 20
# A neutral browser UA — several feeds name-block ClaudeBot/GPTBot in robots.txt (research/138 §2.1).
_USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36"


def http_get_bytes(url: str) -> bytes:
    """The real network fetcher (production default behind the DI seam)."""
    import requests

    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def _entry_published_at_utc(entry) -> datetime | None:
    """feedparser's parsed time-struct → UTC-aware datetime (None when the entry omits a date)."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(timegm(parsed), tz=UTC)


def parse_feed_entries(raw_bytes: bytes, feed, fetched_at: datetime) -> tuple:
    """PURE: RSS bytes → tuple[RawNewsItem]. Deterministic given the same bytes + fetched_at."""
    parsed = feedparser.parse(raw_bytes)
    items = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        item = RawNewsItem(
            source_id=feed.source_id,
            source_name=feed.source_name,
            tier=feed.tier,
            title=title,
            summary=summary,
            url=url,
            published_at=_entry_published_at_utc(entry),
            fetched_at=fetched_at,
            content_hash=RawNewsItem.compute_content_hash(feed.source_id, url, title),
        )
        items.append(item)
    return tuple(items)


def assess_feed_freshness(
    source_id: str, items: tuple, now_utc: datetime, stale_after: timedelta = DEFAULT_STALE_AFTER
) -> FeedFreshness:
    """PURE: is this feed live? Stale when the newest DATED item is older than `stale_after`."""
    dated = [i.published_at for i in items if i.published_at is not None]
    if not dated:
        # No per-item dates (some BusinessLine feeds) — can't prove staleness; ingest but flag.
        return FeedFreshness(source_id, None, is_stale=False, reason="no per-item dates — freshness unknown")
    newest = max(dated)
    age_seconds = (now_utc - newest).total_seconds()
    is_stale = age_seconds > stale_after.total_seconds()
    if is_stale:
        days = age_seconds / 86400.0
        reason = f"STALE — newest item {days:.0f}d old (feed frozen behind HTTP 200)"
    else:
        reason = f"fresh — newest item {age_seconds / 3600.0:.1f}h old"
    return FeedFreshness(source_id, age_seconds, is_stale=is_stale, reason=reason)


class RssNewsFeedSource:
    """Polls the configured RSS feeds and returns a `FeedPollResult` per feed (items + freshness).

    `fetch_bytes` is the DI seam — defaults to the real HTTP getter; tests inject a fake. Fetch errors
    are captured per-feed (one dead feed never breaks the poll)."""

    def __init__(self, feeds: tuple, fetch_bytes=http_get_bytes, stale_after: timedelta = DEFAULT_STALE_AFTER):
        self._feeds = feeds
        self._fetch_bytes = fetch_bytes
        self._stale_after = stale_after

    def poll(self, now_utc: datetime) -> tuple:
        """Poll every feed. Returns tuple[FeedPollResult]. Never raises for a single bad feed."""
        results = []
        for feed in self._feeds:
            try:
                raw = self._fetch_bytes(feed.rss_url)
                items = parse_feed_entries(raw, feed, fetched_at=now_utc)
                freshness = assess_feed_freshness(feed.source_id, items, now_utc, self._stale_after)
                results.append(
                    FeedPollResult(feed.source_id, feed.source_name, feed.tier, items, freshness, "")
                )
            except Exception as fetch_error:  # network / parse failure on one feed
                results.append(
                    FeedPollResult(
                        feed.source_id, feed.source_name, feed.tier, (), None, str(fetch_error)[:200]
                    )
                )
        return tuple(results)
