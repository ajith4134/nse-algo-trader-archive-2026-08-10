"""Rule F real-data verification for the news-ingestion base (Trunk II SENSES S1, research/140).

Runs the REAL RssNewsFeedSource against the REAL live tier-1 RSS feeds (network) and stores into a
throwaway SQLite DB. Proves: fresh feeds (ET Markets, BusinessLine) ingest real current headlines,
and the staleness detector REJECTS Moneycontrol (frozen at 2024-04-23 behind HTTP 200). News is
real-time regardless of market hours, so this is a genuine real-data pass with the market closed.
"""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from nse_algo_trader.news_sentiment.news_feed_registry import TIER1_RSS_FEEDS
from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.rss_news_feed_source import RssNewsFeedSource


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    source = RssNewsFeedSource(TIER1_RSS_FEEDS)

    print("=== per-feed poll (REAL network) ===")
    for result in source.poll(now_utc):
        if result.fetch_error:
            verdict = f"UNREACHABLE ({result.fetch_error[:60]})"
        elif result.freshness is None:
            verdict = "no freshness"
        elif result.freshness.is_stale:
            verdict = f"STALE-REJECTED — {result.freshness.reason}"
        else:
            verdict = f"FRESH ({len(result.items)} items) — {result.freshness.reason}"
        print(f"  {result.source_id:22s} {verdict}")

    db_path = Path(mkdtemp()) / "news_verify.sqlite3"
    store = NewsSqliteStore(db_file_path=db_path)
    try:
        report = NewsIngestionRunner(source, store).run(now_utc)
        print("\n=== ingestion report ===")
        print(" ", report.summary)
        print("  fresh feeds:", report.feeds_fresh, "/", report.feeds_total,
              "| new items:", report.items_new, "| stored:", report.stored_total)
        print("  stale rejected:", report.stale_source_ids or "none")
        print("\n=== newest real headlines stored ===")
        for item in store.load_recent_items(limit=6):
            when = item.published_at.strftime("%Y-%m-%d %H:%M") if item.published_at else "  (no date)  "
            print(f"  [{item.source_id:18s} {when}] {item.title[:80]}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
