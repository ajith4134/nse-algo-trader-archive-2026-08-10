"""Rule F real-data verification for S3 source reliability (Trunk II SENSES, research/146).

Builds the reliability board over the REAL sources in the production news store, and runs a REAL
tier-1 RSS poll so the known-stale Moneycontrol feed is observed and PENALISED — proving the freshness
track works on real data, not just the tier prior. Confirms the trust ladder: NSE filings
(EXCHANGE_FILING) rank above fresh public news, which ranks above the stale-rejected feed.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_feed_registry import TIER1_RSS_FEEDS
from nse_algo_trader.news_sentiment.news_source_reliability import (
    SourceObservation,
    build_reliability_board,
    combine_source_confidences,
)
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.news_sentiment.rss_news_feed_source import RssNewsFeedSource


def main() -> None:
    now = datetime.now(timezone.utc)

    # Real freshness signal: which configured feeds are stale RIGHT NOW (Moneycontrol should be).
    poll = RssNewsFeedSource(TIER1_RSS_FEEDS).poll(now)
    stale_ids = {r.source_id for r in poll if r.freshness is not None and r.freshness.is_stale}
    print("REAL stale feeds this poll:", stale_ids or "none")

    store = NewsSqliteStore()  # the real production store
    try:
        counts = store.source_item_counts()
    finally:
        store.close()

    # Include the configured feeds too, so a stale-rejected feed (0 stored items) still appears.
    seen = {c[0] for c in counts}
    observations = [
        SourceObservation(sid, sname, tier, item_count=n,
                          fresh_polls=0 if sid in stale_ids else 1,
                          stale_polls=1 if sid in stale_ids else 0)
        for sid, sname, tier, n in counts
    ]
    for feed in TIER1_RSS_FEEDS:
        if feed.source_id not in seen:
            is_stale = feed.source_id in stale_ids
            observations.append(SourceObservation(
                feed.source_id, feed.source_name, feed.tier, item_count=0,
                fresh_polls=0 if is_stale else 0, stale_polls=1 if is_stale else 0))

    board = build_reliability_board(observations)
    print("\n=== REAL source-reliability board (most trusted first) ===")
    for r in board:
        flag = " [PROVISIONAL]" if r.is_provisional else ""
        print(f"  {r.reliability:5.0%}  {r.tier:16s} {r.source_name[:46]:46s} items={r.item_count}{flag}")

    # Stouffer: two independent PUBLIC_NEWS sources corroborating one story.
    news_rel = [r.reliability for r in board if r.tier == "public_news"][:2]
    if len(news_rel) >= 2:
        print(f"\nStouffer corroboration: two news sources {news_rel} → combined "
              f"{combine_source_confidences(news_rel):.0%} (> either alone)")


if __name__ == "__main__":
    main()
