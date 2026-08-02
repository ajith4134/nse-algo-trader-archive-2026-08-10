"""Rule F real-data verification for S2 index S/R level extraction (Trunk II SENSES, research/142).

Runs the REAL NewsLevelExtractionRunner over the REAL production news store (~/.nse_algo_trader/
news.sqlite3 — the same headlines S1 ingested from live feeds, and the same data the live loop
consumes). Proves the parser turns real headlines into correctly-attributed, correctly-classified
index support/resistance levels — and that noise (years, counts, point-moves, prices, Sensex) is
rejected. News is real-time regardless of market hours, so this is a genuine real-data pass.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_level_extraction_runner import NewsLevelExtractionRunner
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    store = NewsSqliteStore()  # the REAL production DB
    try:
        report = NewsLevelExtractionRunner(store).run(now_utc)
        print("=== S2 extraction report (REAL production news.sqlite3) ===")
        print(" ", report.summary)
        print("  items scanned:", report.items_scanned,
              "| items with levels:", report.items_with_levels,
              "| levels found:", report.levels_found,
              "| new rows:", report.level_sets_new)
        print("  by underlying:", report.levels_by_underlying or "none")

        print("\n=== every extracted level (from REAL headlines) ===")
        for s in store.load_recent_levels(limit=100):
            for lvl in s.levels:
                print(f"  {s.underlying:11s} {lvl.kind:10s} {lvl.value:>9,.0f}  conf={lvl.confidence}"
                      f"  << {s.title[:62]}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
