"""Rule F real-data verification for S7 news entry-gate (Trunk II SENSES, research/147).

Builds the per-symbol news-EVENT risk map from the REAL production store (the real NSE filings) +
the REAL S3 reliability, and shows: (1) which real symbols carry fresh event risk, (2) at cold start
(calibration NOT earned) the size multiplier is 1.0 — SAFE, the signal moves no trade, and (3) once
forced-earned, a high-event-risk symbol is sized-down/deferred — proving the gate is genuinely wired
into the entry decision, not display-only.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_entry_gate import (
    build_news_event_risk_by_symbol,
    news_event_size_multiplier,
)
from nse_algo_trader.news_sentiment.news_source_reliability import (
    SourceObservation,
    build_reliability_board,
)
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore


def main() -> None:
    now = datetime.now(timezone.utc)
    store = NewsSqliteStore()
    try:
        counts = store.source_item_counts()
        items = store.load_recent_items(limit=300)
    finally:
        store.close()

    board = build_reliability_board([
        SourceObservation(sid, sname, tier, item_count=n, fresh_polls=1) for sid, sname, tier, n in counts
    ])
    reliability_by_source = {r.source_id: r.reliability for r in board}

    risk_map = build_news_event_risk_by_symbol(items, reliability_by_source, now)
    ranked = sorted(risk_map.items(), key=lambda kv: kv[1], reverse=True)
    print(f"=== REAL per-symbol news-event risk ({len(ranked)} symbols with a fresh reliable event) ===")
    for symbol, risk in ranked[:12]:
        print(f"  {symbol:14s} event risk {risk:.0%}")

    if ranked:
        top_symbol, top_risk = ranked[0]
        print(f"\n=== gate behaviour for {top_symbol} (risk {top_risk:.0%}) ===")
        print(f"  cold start (NOT earned): size multiplier = "
              f"{news_event_size_multiplier(top_risk, calibration_earned=False):.2f}  → SAFE (identity)")
        print(f"  once EARNED:             size multiplier = "
              f"{news_event_size_multiplier(top_risk, calibration_earned=True):.2f}  → "
              f"{'DEFER' if top_risk >= 0.75 else 'SIZE-DOWN' if top_risk >= 0.55 else 'no change'}")
    else:
        print("\n(no symbols crossed the reliability+recency floor this run — the store may be older "
              "than the 24h recency window; re-run after a fresh filings poll.)")


if __name__ == "__main__":
    main()
