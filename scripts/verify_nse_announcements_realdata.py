"""Rule F real-data verification for S4c NSE corporate filings (Trunk II SENSES, research/145).

Runs the REAL curl_cffi NSE session fetch from THIS ARM64 box through the SAME NewsIngestionRunner
into a throwaway SQLite DB. Proves: the cookie handshake clears NSE's bot wall from our datacenter
egress, real filings parse (SYMBOL: subject, IST→UTC timestamp, PDF url, EXCHANGE_FILING tier) and
store, and a second poll reports ~0 new (dedup). Filings post around the clock → a genuine real-data
pass with the market closed.
"""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.nse_announcements_source import NseAnnouncementsSource


def main() -> None:
    db_path = Path(mkdtemp()) / "filings_verify.sqlite3"
    store = NewsSqliteStore(db_file_path=db_path)
    try:
        report1 = NewsIngestionRunner(NseAnnouncementsSource(), store).run(datetime.now(timezone.utc))
        print("=== poll 1 (REAL NSE fetch) ===")
        print(" ", report1.summary)
        print("  filings:", report1.items_seen, "| NEW:", report1.items_new)

        print("\n=== real filings stored (symbol: subject | UTC time) ===")
        for item in store.load_recent_items(limit=10):
            when = item.published_at.strftime("%Y-%m-%d %H:%M UTC") if item.published_at else "(no date)"
            print(f"  [{when}] {item.title[:70]}")

        report2 = NewsIngestionRunner(NseAnnouncementsSource(), store).run(datetime.now(timezone.utc))
        print("\n=== poll 2 (delta check) ===")
        print("  filings:", report2.items_seen, "| NEW:", report2.items_new, "(should be ~0 — dedup)")
    finally:
        store.close()


if __name__ == "__main__":
    main()
