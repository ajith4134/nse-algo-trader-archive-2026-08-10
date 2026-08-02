"""Registry of render-target news LISTING pages (Trunk II SENSES S4a; research/143). PURE — no I/O.

These are pages we fetch by RENDERING (headless Chromium via Crawl4AI) rather than via RSS — either
because the site's RSS is stale (Moneycontrol's feed is frozen at 2024 behind HTTP 200, but its live
HTML page is current) or because it has no usable feed. Only sites REACHABLE from our datacenter
egress are listed; Business Standard + NDTV Profit return Akamai-403 on datacenter IPs and need a
residential proxy — deferred to S4d (docs/BACKLOG.md), not silently dropped.

An anchor on a listing page is treated as a headline only when its href contains `article_url_substring`
AND its visible text has at least `min_title_words` words — the precision guard that filters nav/promo
links from real story links (derived by inspecting the real rendered DOM, research/143 S4a).
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier


@dataclass(frozen=True)
class RenderTargetSite:
    source_id: str
    source_name: str
    tier: str
    listing_url: str
    article_url_substring: str   # an anchor is a headline only if its href contains this
    min_title_words: int = 5
    note: str = ""


# Egress-reachable render targets (verified rendering current headlines from this box, 2026-07-26).
RENDER_TARGET_SITES: tuple = (
    RenderTargetSite(
        source_id="moneycontrol_markets_rendered",
        source_name="Moneycontrol — Markets (rendered)",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        listing_url="https://www.moneycontrol.com/news/business/markets/",
        article_url_substring="/news/business/",
        min_title_words=5,
        note="RSS frozen 2024 behind HTTP 200 → render the LIVE page for current headlines (S4a)",
    ),
    RenderTargetSite(
        source_id="moneycontrol_stocks_rendered",
        source_name="Moneycontrol — Stocks (rendered)",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        listing_url="https://www.moneycontrol.com/news/business/stocks/",
        article_url_substring="/news/business/",
        min_title_words=5,
        note="stock-specific listing, same live-render fix as markets (S4a)",
    ),
)
