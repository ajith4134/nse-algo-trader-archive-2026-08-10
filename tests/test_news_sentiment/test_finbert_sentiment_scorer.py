"""Hermetic tests for the FinBERT sentiment scorer + its safety fallback (Trunk II SENSES, research/150).

Does NOT load the real model (kept hermetic/fast). Verifies the FinBERT-label→polarity mapping and the
load-failure fallback to finance-VADER, so the scorer is always safe behind the seam.
"""

from nse_algo_trader.news_sentiment.headline_sentiment import (
    FinBertSentimentScorer,
    HeadlineSentiment,
)


def test_finbert_label_mapping_via_injected_pipeline():
    scorer = FinBertSentimentScorer()
    scorer._pipeline = lambda text: [{"label": "negative", "score": 0.96}]  # inject a fake pipeline
    s = scorer.score("Infosys shares settle lower on Q1 miss")
    assert s.label == "adverse" and s.score < 0

    scorer._pipeline = lambda text: [{"label": "positive", "score": 0.80}]
    s = scorer.score("Nifty surges to record high")
    assert s.label == "favourable" and s.score > 0

    scorer._pipeline = lambda text: [{"label": "neutral", "score": 0.93}]
    assert scorer.score("Board meeting outcome").label == "neutral"


def test_falls_back_to_vader_when_model_unavailable():
    scorer = FinBertSentimentScorer()
    scorer._load_failed = True  # simulate the model failing to load
    # Must still score (via the finance-VADER fallback), not crash.
    result = scorer.score("Infosys shares settle lower on Q1 miss, guidance cut")
    assert isinstance(result, HeadlineSentiment)
    assert result.label == "adverse"


def test_pipeline_exception_falls_back():
    scorer = FinBertSentimentScorer()

    def _boom(text):
        raise RuntimeError("inference error")

    scorer._pipeline = _boom
    result = scorer.score("Nifty rallies strongly")  # fallback handles it, no crash
    assert isinstance(result, HeadlineSentiment)


def test_empty_text_is_neutral():
    assert FinBertSentimentScorer().score("").label == "neutral"
