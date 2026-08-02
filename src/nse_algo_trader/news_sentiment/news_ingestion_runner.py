"""Compose the news-ingestion pass (Trunk II SENSES; research/140, slice S1).

One `run(now_utc)`: poll the tier-1 feeds → keep only items from USABLE (fetched-clean, non-stale)
feeds → dedupe-store → return a `NewsIngestionReport` for the dashboard. This is the thin orchestrator
the live service's cadence calls; source, staleness, and store each stay independently testable.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.news_sentiment.news_item_types import NewsIngestionReport


class NewsIngestionRunner:
    def __init__(self, rss_source, store):
        self._rss_source = rss_source
        self._store = store

    def run(self, now_utc: datetime) -> NewsIngestionReport:
        poll_results = self._rss_source.poll(now_utc)

        usable = [r for r in poll_results if r.is_usable]
        stale = [r for r in poll_results if r.freshness is not None and r.freshness.is_stale]
        errored = [r for r in poll_results if r.fetch_error]

        usable_items = [item for r in usable for item in r.items]
        items_new = self._store.save_news_items(usable_items) if usable_items else 0

        items_by_tier: dict = {}
        for item in usable_items:
            items_by_tier[item.tier] = items_by_tier.get(item.tier, 0) + 1

        # A few freshest headlines (dated items first) for the surface.
        dated = sorted(
            (i for i in usable_items if i.published_at is not None),
            key=lambda i: i.published_at, reverse=True,
        )
        newest_titles = tuple(i.title[:80] for i in (dated or usable_items)[:3])

        stored_total = self._store.total_item_count()
        summary = (
            f"{len(usable)}/{len(poll_results)} feeds fresh, {len(usable_items)} items "
            f"({items_new} new); stored {stored_total}."
        )
        if stale:
            summary += " Stale (rejected): " + ", ".join(r.source_id for r in stale) + "."
        if errored:
            summary += " Unreachable: " + ", ".join(r.source_id for r in errored) + "."

        return NewsIngestionReport(
            run_at=now_utc,
            feeds_total=len(poll_results),
            feeds_fresh=len(usable),
            feeds_stale=len(stale),
            stale_source_ids=tuple(r.source_id for r in stale),
            error_source_ids=tuple(r.source_id for r in errored),
            items_seen=len(usable_items),
            items_new=items_new,
            items_by_tier=items_by_tier,
            newest_titles=newest_titles,
            stored_total=stored_total,
            summary=summary,
        )
