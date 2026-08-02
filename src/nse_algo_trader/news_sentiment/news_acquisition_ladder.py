"""Fast-first news acquisition ladder (Trunk II SENSES S4b; research/144).

Per site, get headlines by the CHEAPEST method that works — the method-selection ladder from
research/143 Agent C:
  1. FAST  — `curl_cffi` static fetch (~0.3 s, Chrome-TLS-impersonated) → extract. If it yields
             headlines, done (the common case — the target pages carry headlines in static HTML).
  2. RENDER — fall back to S4a's Crawl4AI headless Chromium (~40 s) only when the fast fetch yields
             nothing (a genuinely JS-only page).
Both fetchers are DI seams (Rule J): tests inject fakes, prod uses the real curl_cffi / Chromium.
`poll()` returns the same `FeedPollResult` shape as the RSS + rendered sources, so it flows through
the existing `NewsIngestionRunner` → dedup store — and the store's `content_hash` dedup makes
`items_new` the "only NEW headlines since last poll" delta (the live-update signal), with no separate
change-detection service (research/144 §Sourcing).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from nse_algo_trader.news_sentiment.fast_news_fetch import fast_fetch_html
from nse_algo_trader.news_sentiment.news_item_types import FeedPollResult
from nse_algo_trader.news_sentiment.rendered_news_page_source import (
    extract_headlines_from_html,
    render_page_html,
)
from nse_algo_trader.news_sentiment.rss_news_feed_source import (
    DEFAULT_STALE_AFTER,
    assess_feed_freshness,
)

FETCH_METHOD_FAST = "fast"
FETCH_METHOD_RENDER = "render"


class LadderNewsAcquisitionSource:
    """Acquire each site's headlines via fast-static-first, Chromium-render fallback.

    `fast_fetch` / `render_fetch` are DI seams (default to the real curl_cffi + Crawl4AI fetchers;
    tests inject fakes). The winning method per site is recorded on the result's `fetch_error` field
    as an empty string on success, and exposed via `last_methods` for the dashboard. One failing site
    never breaks the poll (mirrors RssNewsFeedSource)."""

    def __init__(self, sites: tuple, fast_fetch=fast_fetch_html, render_fetch=render_page_html,
                 stale_after: timedelta = DEFAULT_STALE_AFTER):
        self._sites = sites
        self._fast_fetch = fast_fetch
        self._render_fetch = render_fetch
        self._stale_after = stale_after
        self.last_methods: dict = {}  # source_id -> "fast" | "render" | "none"

    def poll(self, now_utc: datetime) -> tuple:
        results = []
        for site in self._sites:
            try:
                items, method = self._acquire_site(site, now_utc)
                self.last_methods[site.source_id] = method
                if not items:
                    results.append(FeedPollResult(
                        site.source_id, site.source_name, site.tier, (), None,
                        "no headlines via fast or render (selector/layout drift or JS wall?)"))
                    continue
                freshness = assess_feed_freshness(site.source_id, items, now_utc, self._stale_after)
                results.append(FeedPollResult(
                    site.source_id, site.source_name, site.tier, items, freshness, ""))
            except Exception as acquisition_error:
                self.last_methods[site.source_id] = "none"
                results.append(FeedPollResult(
                    site.source_id, site.source_name, site.tier, (), None, str(acquisition_error)[:200]))
        return tuple(results)

    def _acquire_site(self, site, now_utc: datetime):
        """Fast rung first; render rung only if fast yields no headlines. Returns (items, method)."""
        fast_html = self._fast_fetch(site.listing_url)
        fast_items = extract_headlines_from_html(fast_html, site, fetched_at=now_utc)
        if fast_items:
            return fast_items, FETCH_METHOD_FAST

        rendered_html = self._render_fetch(site.listing_url)
        rendered_items = extract_headlines_from_html(rendered_html, site, fetched_at=now_utc)
        if rendered_items:
            return rendered_items, FETCH_METHOD_RENDER
        return (), "none"
