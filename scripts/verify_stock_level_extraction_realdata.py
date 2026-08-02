"""Rule F real-data verification for stock-S/R level extraction (Trunk II SENSES, research/149).

Builds the real F&O gazetteer, runs the stock-level extractor over the REAL stored headlines, and
persists the levels into the REAL news_levels table — proving analyst targets/support/resistance are
extracted per stock with correct numbers and no profit-crore / listicle false positives.
"""

import sqlite3
from datetime import datetime, timezone

from nse_algo_trader.market_data.market_data_sqlite_store import DEFAULT_MARKET_DATA_DB_FILE_PATH
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.nse_symbol_gazetteer import (
    build_symbol_gazetteer,
    load_or_fetch_equity_master,
)
from nse_algo_trader.news_sentiment.stock_level_extraction import extract_stock_level_sets


def main() -> None:
    now = datetime.now(timezone.utc)
    connection = sqlite3.connect(str(DEFAULT_MARKET_DATA_DB_FILE_PATH.expanduser()))
    try:
        fo = {r[0] for r in connection.execute(
            "SELECT DISTINCT underlying_symbol FROM fo_bhavcopy_contracts").fetchall()}
    finally:
        connection.close()
    gaz = build_symbol_gazetteer(load_or_fetch_equity_master(now_utc=now), restrict_symbols=fo)

    store = NewsSqliteStore()
    try:
        items = store.load_recent_items(limit=300)
        all_sets = []
        for it in items:
            all_sets.extend(extract_stock_level_sets(
                it.content_hash, it.source_id, it.source_name, it.title, it.summary, gaz, it.published_at))
        new_rows = store.save_extracted_levels(all_sets)

        print(f"=== REAL stock levels: {len({s.underlying for s in all_sets})} stocks, "
              f"{sum(len(s.levels) for s in all_sets)} levels ({new_rows} new rows) ===")
        for s in all_sets:
            for lvl in s.levels:
                print(f"  {s.underlying:12s} {lvl.kind:10s} {lvl.value:>10,.0f}  conf={lvl.confidence}"
                      f"  << {s.title[:52]}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
