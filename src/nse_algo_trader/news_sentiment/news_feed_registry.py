"""The tier-1 RSS feed registry (Trunk II SENSES; research/140, sourced in research/138 + 139).

Only feeds verified reachable + fresh from this server on 2026-07-26 are marked live-verified.
Moneycontrol is included DELIBERATELY as a known-stale feed (frozen at 2024-04-23 behind HTTP 200):
it proves the staleness detector rejects dead feeds, and auto-includes Moneycontrol again if it ever
revives — never a silent gap. Feed-less / Akamai-blocked sites (Business Standard, NDTV Profit) are
deferred to the crawl4ai rendering slice (S4); see docs/BACKLOG.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier


@dataclass(frozen=True)
class NewsFeed:
    source_id: str
    source_name: str
    tier: str
    rss_url: str
    note: str = ""


# Tier-1 public financial-news RSS. URLs confirmed against research/138 §2.1 + live-fetched 2026-07-26.
TIER1_RSS_FEEDS: tuple = (
    NewsFeed(
        source_id="et_markets",
        source_name="Economic Times — Markets",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        rss_url="https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        note="live-verified fresh 2026-07-26 (pubDate current)",
    ),
    NewsFeed(
        source_id="et_stocks",
        source_name="Economic Times — Stocks",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        rss_url="https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        note="ET stocks sub-feed (research/138)",
    ),
    NewsFeed(
        source_id="businessline_stocks",
        source_name="The Hindu BusinessLine — Stock Markets",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        rss_url="https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss",
        note="live-verified reachable 2026-07-26 (freshest source per research/138)",
    ),
    NewsFeed(
        source_id="businessline_markets",
        source_name="The Hindu BusinessLine — Markets",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        rss_url="https://www.thehindubusinessline.com/markets/feeder/default.rss",
        note="BusinessLine markets firehose",
    ),
    NewsFeed(
        source_id="moneycontrol_latest",
        source_name="Moneycontrol — Latest News",
        tier=NewsSourceTier.PUBLIC_NEWS.value,
        rss_url="https://www.moneycontrol.com/rss/latestnews.xml",
        note="KNOWN STALE (frozen 2024-04-23) — staleness-detector demonstrator; auto-revives if fixed",
    ),
)
