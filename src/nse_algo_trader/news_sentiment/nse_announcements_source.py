"""Fetch + parse NSE corporate-announcement filings (Trunk II SENSES S4c; research/145).

The highest-signal news: official exchange filings (board-meeting outcomes, results, dividends,
director changes) straight from NSE's own JSON backend, seconds after they post. The network fetch
sits behind a `fetch_json` DI seam (Rule J): production uses a `curl_cffi` Chrome-impersonated session
(homepage cookie bootstrap → announcements API — verified reachable from this datacenter egress,
research/145); tests inject a fake returning canned records. `parse_announcement_records` is PURE
(records → RawNewsItems) and independently testable.

`.poll()` returns the same `FeedPollResult` shape as the RSS + ladder sources, so filings flow through
the existing `NewsIngestionRunner` → dedup store → S2 extraction, tagged tier EXCHANGE_FILING (the
highest reliability prior for the queued S3 source-scoring).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC

from nse_algo_trader.news_sentiment.news_item_types import (
    FeedPollResult,
    NewsSourceTier,
    RawNewsItem,
)
from nse_algo_trader.news_sentiment.rss_news_feed_source import (
    DEFAULT_STALE_AFTER,
    assess_feed_freshness,
)

_NSE_HOME = "https://www.nseindia.com/"
_NSE_ANNOUNCEMENTS_API = "https://www.nseindia.com/api/corporate-announcements?index={index}"
_NSE_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
_ANNOUNCEMENTS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
_FETCH_TIMEOUT_SECONDS = 25
_INDIA_TZ = timezone(timedelta(hours=5, minutes=30))  # NSE timestamps are IST (Asia/Kolkata)


def fetch_nse_announcements(index: str = "equities") -> list:
    """The real fetch seam: curl_cffi Chrome session (homepage cookie bootstrap → API). [] on failure."""
    try:
        from curl_cffi import requests as curl_requests
        from typing import Any

        session: Any = curl_requests.Session(impersonate="chrome")  # curl_cffi is untyped
        session.get(_NSE_HOME, timeout=_FETCH_TIMEOUT_SECONDS)  # bootstrap cookies
        response = session.get(
            _NSE_ANNOUNCEMENTS_API.format(index=index),
            headers={"Referer": _NSE_REFERER},
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _announcement_published_at_utc(record: dict) -> datetime | None:
    """Parse NSE's IST filing timestamp (`sort_date` 'YYYY-MM-DD HH:MM:SS', else `an_dt`) → UTC-aware."""
    sort_date = (record.get("sort_date") or "").strip()
    if sort_date:
        try:
            naive = datetime.strptime(sort_date, "%Y-%m-%d %H:%M:%S")
            return naive.replace(tzinfo=_INDIA_TZ).astimezone(UTC)
        except ValueError:
            pass
    an_dt = (record.get("an_dt") or "").strip()
    if an_dt:
        try:
            naive = datetime.strptime(an_dt, "%d-%b-%Y %H:%M:%S")
            return naive.replace(tzinfo=_INDIA_TZ).astimezone(UTC)
        except ValueError:
            pass
    return None


def parse_announcement_records(records, source_id: str, source_name: str, fetched_at: datetime) -> tuple:
    """PURE: NSE announcement dicts → tuple[RawNewsItem]. Title = 'SYMBOL: subject'."""
    items = []
    for record in records:
        symbol = (record.get("symbol") or "").strip()
        subject = (record.get("desc") or "").strip()
        if not symbol or not subject:
            continue
        title = f"{symbol}: {subject}"
        summary = (record.get("attchmntText") or "").strip()
        url = (record.get("attchmntFile") or "").strip() or _ANNOUNCEMENTS_PAGE
        items.append(
            RawNewsItem(
                source_id=source_id,
                source_name=source_name,
                tier=NewsSourceTier.EXCHANGE_FILING.value,
                title=title,
                summary=summary,
                url=url,
                published_at=_announcement_published_at_utc(record),
                fetched_at=fetched_at,
                content_hash=RawNewsItem.compute_content_hash(source_id, url, title),
            )
        )
    return tuple(items)


class NseAnnouncementsSource:
    """Polls NSE corporate-announcement filings per index and returns a `FeedPollResult` each.

    `fetch_json` is the DI seam — defaults to the real curl_cffi session fetch; tests inject a fake.
    A failed/empty fetch on one index never breaks the poll (mirrors RssNewsFeedSource)."""

    def __init__(self, indices: tuple = ("equities",), fetch_json=fetch_nse_announcements,
                 stale_after: timedelta = DEFAULT_STALE_AFTER):
        self._indices = indices
        self._fetch_json = fetch_json
        self._stale_after = stale_after

    def poll(self, now_utc: datetime) -> tuple:
        results = []
        for index in self._indices:
            source_id = f"nse_announcements_{index}"
            source_name = f"NSE corporate announcements ({index})"
            try:
                records = self._fetch_json(index)
                items = parse_announcement_records(records, source_id, source_name, fetched_at=now_utc)
                if not items:
                    results.append(FeedPollResult(
                        source_id, source_name, NewsSourceTier.EXCHANGE_FILING.value, (), None,
                        "no announcement records (empty fetch or all unparsable)"))
                    continue
                freshness = assess_feed_freshness(source_id, items, now_utc, self._stale_after)
                results.append(FeedPollResult(
                    source_id, source_name, NewsSourceTier.EXCHANGE_FILING.value, items, freshness, ""))
            except Exception as fetch_error:
                results.append(FeedPollResult(
                    source_id, source_name, NewsSourceTier.EXCHANGE_FILING.value, (), None,
                    str(fetch_error)[:200]))
        return tuple(results)
