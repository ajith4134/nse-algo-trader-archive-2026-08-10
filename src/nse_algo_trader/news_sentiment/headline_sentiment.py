"""Headline sentiment scoring — the polarity half of the news sense (Trunk II SENSES; research/150).

A `HeadlineSentimentScorer` DI seam so scorers are swappable: the installed default is a finance-
lexicon-boosted VADER (light, no torch); FinBERT (ProsusAI/finbert, ~1.75 GB — user-gated, research/138)
drops in behind the SAME seam later with no rewiring. Base VADER is weak on finance ("Buy … target"
scored 0.0); seeding its lexicon with market terms fixes that class. Score ∈ [-1, 1] (negative = adverse).
"""

from __future__ import annotations

from dataclasses import dataclass

# Market terms VADER's general lexicon misses or under-weights (VADER scale ≈ [-4, +4]).
_FINANCE_LEXICON: dict = {
    # adverse
    "miss": -2.0, "misses": -2.0, "cut": -1.6, "cuts": -1.6, "downgrade": -2.6, "downgraded": -2.6,
    "fall": -1.6, "falls": -1.6, "fell": -1.6, "slump": -2.2, "slumps": -2.2, "plunge": -2.6,
    "plunges": -2.6, "tumble": -2.4, "tumbles": -2.4, "drag": -1.6, "drags": -1.6, "weak": -1.6,
    "loss": -2.0, "losses": -2.0, "warning": -1.6, "warns": -1.6, "decline": -1.6, "declines": -1.6,
    "bearish": -2.2, "selloff": -2.2, "correction": -1.4, "underperform": -2.0, "lower": -1.2,
    "sinks": -2.2, "erodes": -1.8, "bearishness": -2.2, "breakdown": -1.8,
    # favourable
    "beat": 2.0, "beats": 2.0, "upgrade": 2.6, "upgraded": 2.6, "buy": 1.6, "surge": 2.4,
    "surges": 2.4, "rally": 2.0, "rallies": 2.0, "gain": 1.6, "gains": 1.6, "profit": 1.4,
    "jumps": 2.2, "tops": 1.6, "bullish": 2.2, "outperform": 2.2, "outperforms": 2.2, "strong": 1.6,
    "record": 1.4, "higher": 1.2, "target": 0.8, "accumulate": 1.4, "breakout": 1.6, "reclaims": 1.4,
}

_POSITIVE_LABEL_THRESHOLD = 0.15
_NEGATIVE_LABEL_THRESHOLD = -0.15


def label_for(score: float) -> str:
    if score >= _POSITIVE_LABEL_THRESHOLD:
        return "favourable"
    if score <= _NEGATIVE_LABEL_THRESHOLD:
        return "adverse"
    return "neutral"


@dataclass(frozen=True)
class HeadlineSentiment:
    score: float   # [-1, 1]; negative = adverse
    label: str     # "adverse" | "neutral" | "favourable"


class FinanceVaderSentimentScorer:
    """Finance-lexicon-boosted VADER. Lazy-instantiates the analyzer once (no torch, ~instant)."""

    def __init__(self):
        self._analyzer = None

    def _get_analyzer(self):
        if self._analyzer is None:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            analyzer = SentimentIntensityAnalyzer()
            analyzer.lexicon.update(_FINANCE_LEXICON)  # seed the finance terms
            self._analyzer = analyzer
        return self._analyzer

    def score(self, text: str) -> HeadlineSentiment:
        if not (text or "").strip():
            return HeadlineSentiment(0.0, "neutral")
        compound = float(self._get_analyzer().polarity_scores(text)["compound"])  # already in [-1,1]
        return HeadlineSentiment(compound, label_for(compound))


# FinBERT (ProsusAI/finbert) label → our polarity (research/150, research/138: 91-93% F1 on India news).
_FINBERT_LABEL_MAP = {"positive": "favourable", "negative": "adverse", "neutral": "neutral"}


class FinBertSentimentScorer:
    """The accurate primary scorer: ProsusAI/finbert (transformers). Lazy-loads the model once; if the
    model can't load, it transparently FALLS BACK to finance-VADER — so it is always safe to use. Drop-in
    behind the same `HeadlineSentimentScorer` seam as the VADER scorer (no rewiring)."""

    def __init__(self):
        self._pipeline = None
        self._load_failed = False
        self._fallback = FinanceVaderSentimentScorer()

    def _get_pipeline(self):
        if self._pipeline is None and not self._load_failed:
            try:
                from transformers import pipeline

                self._pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
            except Exception:
                self._load_failed = True  # model unavailable → use the VADER fallback
        return self._pipeline

    def score(self, text: str) -> HeadlineSentiment:
        if not (text or "").strip():
            return HeadlineSentiment(0.0, "neutral")
        pipe = self._get_pipeline()
        if pipe is None:
            return self._fallback.score(text)
        try:
            result = pipe(text[:512])[0]
            label = _FINBERT_LABEL_MAP.get(result["label"].lower(), "neutral")
            confidence = float(result["score"])
            score = confidence if label == "favourable" else -confidence if label == "adverse" else 0.0
            return HeadlineSentiment(score, label)
        except Exception:
            return self._fallback.score(text)

