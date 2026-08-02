"""Render feed-less / stale-RSS news pages with headless Chromium and extract fresh headlines
(Trunk II SENSES S4a; research/143, sourced via building-features-from-ideas → Crawl4AI).

The render sits behind a `render_page` DI seam (Rule J): production uses the real Crawl4AI headless
Chromium (JS executed, ARM64-verified on this box 2026-07-26); tests inject a fake returning canned
HTML, so the headline-extraction logic verifies hermetically with no browser/network. The extractor
is PURE (rendered HTML + site config → RawNewsItems) and independently testable.

`render_page_html` (the Chromium render) is the FALLBACK rung of the S4b acquisition ladder
(`news_acquisition_ladder`), used only when the fast static fetch yields nothing (a JS-only page);
`extract_headlines_from_html` is the shared extractor for both rungs — so both flow through the
existing `NewsIngestionRunner` → dedup store → S2 level extraction, no separate path (Rule G).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

from nse_algo_trader.news_sentiment.news_item_types import RawNewsItem

_RENDER_TIMEOUT_MS = 45000


def render_page_html(url: str) -> str:
    """The real render seam (production default): Crawl4AI headless Chromium → rendered HTML.

    JS is executed, so this returns the LIVE DOM a browser sees — the fix for stale-RSS/feed-less
    sites. Runs its own asyncio loop (the caller is the sync paper loop). Returns "" on failure so
    one bad page never breaks the poll."""
    import asyncio

    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    async def _run() -> str:
        async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
            result = await crawler.arun(url, config=CrawlerRunConfig(page_timeout=_RENDER_TIMEOUT_MS))
            return result.html or "" if result.success else ""

    return asyncio.run(_run())


def extract_headlines_from_html(html: str, site, fetched_at: datetime) -> tuple:
    """PURE: rendered HTML + a `RenderTargetSite` → tuple[RawNewsItem].

    An anchor is a headline only when its href contains `site.article_url_substring` AND its text has
    ≥ `site.min_title_words` words (filters nav/promo/section links). Relative hrefs are resolved
    against the listing URL; duplicates (same resolved URL) are collapsed, keeping the longest title.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    by_url: dict = {}
    for anchor in soup.find_all("a"):
        href_value = anchor.get("href")  # bs4 types this str | AttributeValueList (multi-valued attrs)
        href = (href_value if isinstance(href_value, str) else "").strip()
        title = anchor.get_text(strip=True)
        if not href or site.article_url_substring not in href:
            continue
        if len(title.split()) < site.min_title_words:
            continue
        url = urljoin(site.listing_url, href)
        existing = by_url.get(url)
        if existing is None or len(title) > len(existing):
            by_url[url] = title

    items = []
    for url, title in by_url.items():
        items.append(
            RawNewsItem(
                source_id=site.source_id,
                source_name=site.source_name,
                tier=site.tier,
                title=title,
                summary="",                 # listing pages give headline only; body is a later slice
                url=url,
                published_at=None,          # headline lists rarely carry machine dates → freshness-unknown
                fetched_at=fetched_at,
                content_hash=RawNewsItem.compute_content_hash(site.source_id, url, title),
            )
        )
    return tuple(items)
