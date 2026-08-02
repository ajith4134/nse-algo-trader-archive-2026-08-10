"""Rule F real-data verification for headline sentiment + directional gate (Trunk II SENSES, research/150).

Scores the REAL stored headlines with finance-VADER and shows the directional effect on the S7 gate
(risk WITH sentiment vs without) — adverse-news symbols rise, favourable ones fall.
"""

import sqlite3
from datetime import datetime, timezone

from nse_algo_trader.market_data.market_data_sqlite_store import DEFAULT_MARKET_DATA_DB_FILE_PATH
from nse_algo_trader.news_sentiment.headline_sentiment import FinanceVaderSentimentScorer
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
    scorer = FinanceVaderSentimentScorer()

    store = NewsSqliteStore()
    try:
        counts = store.source_item_counts()
        items = store.load_recent_items(limit=300)
    finally:
        store.close()

    print("=== finance-VADER on real headlines (sample) ===")
    for it in items[:10]:
        s = scorer.score(it.title)
        print(f"  {s.score:+.2f} {s.label:11s} {it.title[:56]}")

    mood = {"adverse": 0, "neutral": 0, "favourable": 0}
    for it in items:
        mood[scorer.score(it.title).label] += 1
    print(f"\nmarket mood over {len(items)} headlines: {mood}")

    conn = sqlite3.connect(str(DEFAULT_MARKET_DATA_DB_FILE_PATH.expanduser()))
    try:
        fo = {r[0] for r in conn.execute(
            "SELECT DISTINCT underlying_symbol FROM fo_bhavcopy_contracts").fetchall()}
    finally:
        conn.close()
    gaz = build_symbol_gazetteer(load_or_fetch_equity_master(now_utc=now), restrict_symbols=fo)
    reliability = {r.source_id: r.reliability for r in build_reliability_board(
        [SourceObservation(sid, sname, tier, item_count=n, fresh_polls=1) for sid, sname, tier, n in counts])}

    plain = build_news_event_risk_by_symbol(items, reliability, now, gazetteer=gaz)
    directional = build_news_event_risk_by_symbol(items, reliability, now, gazetteer=gaz, sentiment_scorer=scorer)
    print("\n=== directional gate: symbols whose risk MOVED with sentiment ===")
    moved = [(s, plain.get(s, 0), directional.get(s, 0)) for s in directional
             if abs(directional.get(s, 0) - plain.get(s, 0)) > 0.01]
    for sym, p, d in sorted(moved, key=lambda x: x[2] - x[1], reverse=True)[:12]:
        arrow = "↑ adverse" if d > p else "↓ favourable"
        print(f"  {sym:12s} {p:.0%} → {d:.0%}   {arrow}")


if __name__ == "__main__":
    main()
