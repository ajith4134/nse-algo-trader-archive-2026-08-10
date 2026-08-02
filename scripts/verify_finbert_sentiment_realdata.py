"""Rule F real-data verification for the FinBERT sentiment scorer (Trunk II SENSES, research/150).

Loads the REAL ProsusAI/finbert model and scores the REAL stored headlines, showing FinBERT vs the
finance-VADER fallback side by side + the market-mood distribution — proving the accurate primary
scorer works on the actual data it will run on.
"""

from nse_algo_trader.news_sentiment.headline_sentiment import (
    FinanceVaderSentimentScorer,
    FinBertSentimentScorer,
)
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore


def main() -> None:
    finbert = FinBertSentimentScorer()
    vader = FinanceVaderSentimentScorer()

    store = NewsSqliteStore()
    try:
        items = store.load_recent_items(limit=40)
    finally:
        store.close()

    print("=== FinBERT vs finance-VADER on REAL headlines ===")
    print(f"  {'FinBERT':>22s} | {'VADER':>18s}  headline")
    mood = {"adverse": 0, "neutral": 0, "favourable": 0}
    for it in items[:18]:
        f = finbert.score(it.title)
        v = vader.score(it.title)
        mood[f.label] += 1
        print(f"  {f.label:>11s} {f.score:+.2f} | {v.label:>10s} {v.score:+.2f}  {it.title[:44]}")

    for it in items[18:]:
        mood[finbert.score(it.title).label] += 1
    print(f"\nFinBERT market mood over {len(items)} real headlines: {mood}")
    print("(FinBERT is the primary; it falls back to finance-VADER only if the model can't load.)")


if __name__ == "__main__":
    main()
