"""Hermetic tests for the news-ingestion base (Trunk II SENSES S1, research/140).

The network fetch is injected (Rule J DI seam) — canned RSS bytes, no network. Verifies parsing,
the load-bearing STALENESS guard (a 2024-frozen feed is rejected), store dedup, and the runner's
report accounting.
"""

from datetime import datetime, timedelta, timezone

from nse_algo_trader.news_sentiment.news_feed_registry import NewsFeed
from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.rss_news_feed_source import (
    RssNewsFeedSource,
    assess_feed_freshness,
    parse_feed_entries,
)

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

FRESH_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>ET Markets</title>
<item><title>Nifty ends higher, support seen at 24800</title><link>https://et.example/a1</link>
<description>market wrap</description><pubDate>Sun, 26 Jul 2026 17:00:00 +0530</pubDate></item>
<item><title>Sensex gains 200 points</title><link>https://et.example/a2</link>
<pubDate>Sun, 26 Jul 2026 16:00:00 +0530</pubDate></item>
</channel></rss>"""

STALE_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Moneycontrol</title>
<item><title>Old frozen headline</title><link>https://mc.example/old</link>
<pubDate>Tue, 23 Apr 2024 13:41:02 +0530</pubDate></item>
</channel></rss>"""

NODATE_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>BusinessLine</title>
<item><title>Undated market note</title><link>https://bl.example/x</link></item>
</channel></rss>"""


def _feed(source_id, url):
    return NewsFeed(source_id=source_id, source_name=source_id, tier="public_news", rss_url=url)


def _fake_fetch(mapping):
    def _fetch(url):
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value
    return _fetch


def test_parse_feed_entries_extracts_fields_and_hash():
    items = parse_feed_entries(FRESH_RSS, _feed("et", "u"), fetched_at=NOW)
    assert len(items) == 2
    first = items[0]
    assert first.title.startswith("Nifty ends higher")
    assert first.url == "https://et.example/a1"
    assert first.published_at == datetime(2026, 7, 26, 11, 30, tzinfo=timezone.utc)  # 17:00 IST → UTC
    assert first.content_hash and first.content_hash == first.compute_content_hash("et", first.url, first.title)


def test_fresh_feed_is_not_stale():
    items = parse_feed_entries(FRESH_RSS, _feed("et", "u"), fetched_at=NOW)
    verdict = assess_feed_freshness("et", items, NOW)
    assert verdict.is_stale is False
    assert verdict.newest_item_age_seconds is not None and verdict.newest_item_age_seconds < 3600


def test_stale_feed_is_rejected():
    items = parse_feed_entries(STALE_RSS, _feed("mc", "u"), fetched_at=NOW)
    verdict = assess_feed_freshness("mc", items, NOW)
    assert verdict.is_stale is True
    assert "STALE" in verdict.reason


def test_undated_feed_is_freshness_unknown_not_stale():
    items = parse_feed_entries(NODATE_RSS, _feed("bl", "u"), fetched_at=NOW)
    verdict = assess_feed_freshness("bl", items, NOW)
    assert verdict.is_stale is False
    assert verdict.newest_item_age_seconds is None


def test_source_poll_marks_stale_feed_unusable():
    feeds = (_feed("et", "u_et"), _feed("mc", "u_mc"))
    source = RssNewsFeedSource(feeds, fetch_bytes=_fake_fetch({"u_et": FRESH_RSS, "u_mc": STALE_RSS}))
    results = {r.source_id: r for r in source.poll(NOW)}
    assert results["et"].is_usable is True
    assert results["mc"].is_usable is False  # stale → not usable


def test_source_poll_captures_fetch_error_without_raising():
    feeds = (_feed("et", "u_et"), _feed("bad", "u_bad"))
    source = RssNewsFeedSource(
        feeds, fetch_bytes=_fake_fetch({"u_et": FRESH_RSS, "u_bad": RuntimeError("403 blocked")})
    )
    results = {r.source_id: r for r in source.poll(NOW)}
    assert results["bad"].fetch_error and results["bad"].is_usable is False
    assert results["et"].is_usable is True


def test_store_dedupes_by_content_hash(tmp_path):
    store = NewsSqliteStore(db_file_path=tmp_path / "news.sqlite3")
    try:
        items = parse_feed_entries(FRESH_RSS, _feed("et", "u"), fetched_at=NOW)
        assert store.save_news_items(items) == 2
        assert store.save_news_items(items) == 0  # same items → no new rows
        assert store.total_item_count() == 2
    finally:
        store.close()


def test_runner_stores_only_fresh_and_reports(tmp_path):
    feeds = (_feed("et", "u_et"), _feed("mc", "u_mc"), _feed("bad", "u_bad"))
    source = RssNewsFeedSource(
        feeds,
        fetch_bytes=_fake_fetch({"u_et": FRESH_RSS, "u_mc": STALE_RSS, "u_bad": RuntimeError("boom")}),
    )
    store = NewsSqliteStore(db_file_path=tmp_path / "news.sqlite3")
    try:
        report = NewsIngestionRunner(source, store).run(NOW)
        assert report.feeds_total == 3
        assert report.feeds_fresh == 1          # only ET
        assert report.feeds_stale == 1          # Moneycontrol rejected
        assert "mc" in report.stale_source_ids
        assert "bad" in report.error_source_ids
        assert report.items_seen == 2 and report.items_new == 2
        assert report.stored_total == 2          # the stale feed's item never stored
    finally:
        store.close()
