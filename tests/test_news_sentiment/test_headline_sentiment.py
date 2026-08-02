"""Hermetic tests for headline sentiment + the directional S7 gate (Trunk II SENSES, research/150)."""

from datetime import datetime, timedelta, timezone

from nse_algo_trader.news_sentiment.headline_sentiment import (
    FinanceVaderSentimentScorer,
    label_for,
)
from nse_algo_trader.news_sentiment.news_entry_gate import build_news_event_risk_by_symbol
from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier, RawNewsItem

NOW = datetime(2026, 7, 26, 18, 0, 0, tzinfo=timezone.utc)
SCORER = FinanceVaderSentimentScorer()


def test_finance_terms_score_with_correct_sign():
    assert SCORER.score("Infosys shares settle lower on Q1 miss, guidance cut").label == "adverse"
    assert SCORER.score("Buy InterGlobe Aviation; target of Rs 6580, upgrade to overweight").label == "favourable"
    assert SCORER.score("Sensex sinks over 2,000 points as banks tumble").score < 0


def test_label_thresholds():
    assert label_for(0.5) == "favourable"
    assert label_for(-0.5) == "adverse"
    assert label_for(0.0) == "neutral"


class _FakeScorer:
    def __init__(self, label):
        self._label = label

    def score(self, text):
        from nse_algo_trader.news_sentiment.headline_sentiment import HeadlineSentiment
        return HeadlineSentiment(-0.9 if self._label == "adverse" else 0.9, self._label)


def _filing(symbol):
    title = f"{symbol}: some material event"
    return RawNewsItem(
        source_id="nse", source_name="nse", tier=NewsSourceTier.EXCHANGE_FILING.value,
        title=title, summary="", url="u", published_at=NOW - timedelta(hours=1), fetched_at=NOW,
        content_hash=symbol)


def test_adverse_sentiment_raises_gate_risk_above_neutral():
    reliability = {"nse": 0.9}
    item = _filing("ACME")
    neutral = build_news_event_risk_by_symbol([item], reliability, NOW)["ACME"]
    adverse = build_news_event_risk_by_symbol(
        [item], reliability, NOW, sentiment_scorer=_FakeScorer("adverse"))["ACME"]
    favourable = build_news_event_risk_by_symbol(
        [item], reliability, NOW, sentiment_scorer=_FakeScorer("favourable"))["ACME"]
    assert adverse > neutral > favourable  # directional: bad news weighs more, good news less
