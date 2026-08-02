"""Rule F real-data verification for the NSE symbol gazetteer + S7 headline matching (research/148).

Fetches the REAL NSE equity master, bounds it to the REAL F&O underlyings from the stored bhavcopy,
and runs it over the REAL stored headlines — proving company names resolve to symbols and that S7
event risk now covers headline-mentioned stocks (not just "SYMBOL:" filings).
"""

import sqlite3
from datetime import datetime, timezone

from nse_algo_trader.market_data.market_data_sqlite_store import DEFAULT_MARKET_DATA_DB_FILE_PATH
from nse_algo_trader.news_sentiment.news_entry_gate import build_news_event_risk_by_symbol
from nse_algo_trader.news_sentiment.news_source_reliability import (
    SourceObservation,
    build_reliability_board,
)
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.nse_symbol_gazetteer import (
    build_symbol_gazetteer,
    load_or_fetch_equity_master,
)


def main() -> None:
    now = datetime.now(timezone.utc)

    connection = sqlite3.connect(str(DEFAULT_MARKET_DATA_DB_FILE_PATH.expanduser()))
    try:
        fo_symbols = {r[0] for r in connection.execute(
            "SELECT DISTINCT underlying_symbol FROM fo_bhavcopy_contracts").fetchall()}
    finally:
        connection.close()

    rows = load_or_fetch_equity_master(now_utc=now)
    gaz = build_symbol_gazetteer(rows, restrict_symbols=fo_symbols)
    print(f"=== gazetteer built: {len(rows)} equity-master rows → {len(gaz.tickers)} F&O symbols, "
          f"{len(gaz.name_phrases)} name phrases ===")
    print("  InterGlobe Aviation →", gaz.match_symbols("Buy InterGlobe Aviation; target Rs 6580") or "—")

    store = NewsSqliteStore()
    try:
        counts = store.source_item_counts()
        items = store.load_recent_items(limit=300)
    finally:
        store.close()
    reliability = {r.source_id: r.reliability for r in build_reliability_board(
        [SourceObservation(sid, sname, tier, item_count=n, fresh_polls=1) for sid, sname, tier, n in counts])}

    without = build_news_event_risk_by_symbol(items, reliability, now)
    withgaz = build_news_event_risk_by_symbol(items, reliability, now, gazetteer=gaz)
    new_symbols = set(withgaz) - set(without)
    print(f"\n=== S7 event-risk coverage: {len(without)} symbols (filings only) → {len(withgaz)} "
          f"(+ {len(new_symbols)} from headline matching) ===")
    for sym in sorted(new_symbols, key=lambda s: withgaz[s], reverse=True)[:12]:
        hit = next((it.title for it in items if sym in gaz.match_symbols(it.title)), "")
        print(f"  {sym:12s} risk {withgaz[sym]:.0%}   << {hit[:56]}")


if __name__ == "__main__":
    main()
