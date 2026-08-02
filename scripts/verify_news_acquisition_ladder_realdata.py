"""Rule F real-data verification for the S4b fast-first acquisition ladder (Trunk II SENSES, research/144).

Runs the REAL ladder (curl_cffi fast fetch → Crawl4AI render fallback) over the REAL Moneycontrol live
listing pages from THIS ARM64 box, through the SAME NewsIngestionRunner, into a throwaway SQLite DB.
Proves: the FAST rung wins (<1s/site, no Chromium), current headlines are stored, and a SECOND poll
reports the correct new-vs-seen delta (the store-dedup 'only new headlines' live signal). News is
real-time regardless of market hours → a genuine real-data pass with the market closed.
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from nse_algo_trader.news_sentiment.news_acquisition_ladder import LadderNewsAcquisitionSource
from nse_algo_trader.news_sentiment.news_ingestion_runner import NewsIngestionRunner
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.rendered_news_page_registry import RENDER_TARGET_SITES


def main() -> None:
    db_path = Path(mkdtemp()) / "ladder_verify.sqlite3"
    store = NewsSqliteStore(db_file_path=db_path)
    try:
        # --- Poll 1: everything is new ---
        t0 = time.time()
        source1 = LadderNewsAcquisitionSource(RENDER_TARGET_SITES)
        report1 = NewsIngestionRunner(source1, store).run(datetime.now(timezone.utc))
        dt = time.time() - t0
        print("=== poll 1 (REAL ladder) ===")
        print(f"  wall time: {dt:.1f}s   (fast rung avoids the ~40s/page Chromium render)")
        print("  method per site:", source1.last_methods)
        print(" ", report1.summary)
        print("  headlines:", report1.items_seen, "| NEW this poll:", report1.items_new)

        print("\n=== a few fresh real headlines stored ===")
        for item in store.load_recent_items(limit=6):
            print(f"  [{item.source_id:30s}] {item.title[:74]}")

        # --- Poll 2: the store-dedup delta — same headlines should be mostly 'not new' ---
        source2 = LadderNewsAcquisitionSource(RENDER_TARGET_SITES)
        report2 = NewsIngestionRunner(source2, store).run(datetime.now(timezone.utc))
        print("\n=== poll 2 (delta check) ===")
        print("  headlines:", report2.items_seen, "| NEW this poll:", report2.items_new,
              "(should be ~0 — the live-update delta works)")
    finally:
        store.close()


if __name__ == "__main__":
    main()
