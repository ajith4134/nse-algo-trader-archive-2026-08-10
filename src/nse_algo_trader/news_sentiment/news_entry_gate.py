"""S7 — the news entry-gate consumer (Trunk II SENSES; research/147). PURE — no I/O.

The PRIMARY consumer of the news sense: turns acquired + trust-weighted news into an entry-gate
decision. A candidate entry on a symbol with a FRESH, HIGH-RELIABILITY news/filing EVENT faces
elevated event uncertainty → the loop sizes-down / defers it (don't open into an unresolved material
event). Needs no adverse/favourable sentiment — the PRESENCE of a fresh material event is the risk;
directional sentiment is a queued refinement (research/147 §Rule K).

`news_event_size_multiplier` mirrors `live_universe_paper_loop.debate_risk_size_multiplier` exactly:
identity (1.0) until the signal is calibration-EARNED, so an uncalibrated news signal can never move a
real trade (the project's universal safety pattern).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# Mirror the debate-risk gate thresholds so news risk composes consistently with it.
NEWS_EVENT_DEFER_THRESHOLD = 0.75
NEWS_EVENT_SIZE_DOWN_THRESHOLD = 0.55
NEWS_EVENT_SIZE_DOWN_MULTIPLIER = 0.5

# A low-trust source alone never moves the gate (research/140): ignore items below this reliability.
_MIN_SOURCE_RELIABILITY = 0.5


@dataclass(frozen=True)
class NewsEventRiskConfig:
    recency_window: timedelta = timedelta(hours=24)  # a material event stays "fresh" this long
    min_source_reliability: float = _MIN_SOURCE_RELIABILITY


def _symbol_of(item) -> str:
    """A filing's title is 'SYMBOL: subject' (S4c); the leading token before ':' is the NSE symbol.

    Headlines without that shape yield '' (matched only once the stock-symbol gazetteer lands, task #2)."""
    title = item.title or ""
    if ":" in title:
        head = title.split(":", 1)[0].strip()
        if head and " " not in head and head.upper() == head:
            return head
    return ""


def _symbols_of(item, gazetteer) -> set:
    """The symbols an item concerns: the "SYMBOL:" filing prefix, else gazetteer name-matches on the
    title (research/148) so headlines like "Buy InterGlobe Aviation; target …" attribute to INDIGO."""
    prefix_symbol = _symbol_of(item)
    if prefix_symbol:
        return {prefix_symbol}
    if gazetteer is not None:
        return gazetteer.match_symbols(item.title or "")
    return set()


# Directional sentiment factor (research/150): the gate leans on BAD news — an adverse-sentiment event
# is riskier than a neutral one; a favourable event is dampened.
_ADVERSE_RISK_FACTOR = 1.5
_FAVOURABLE_RISK_FACTOR = 0.7


def _sentiment_risk_factor(title: str, sentiment_scorer) -> float:
    """1.0 with no scorer; else scale by polarity — adverse ↑, favourable ↓ (research/150)."""
    if sentiment_scorer is None:
        return 1.0
    label = sentiment_scorer.score(title or "").label
    if label == "adverse":
        return _ADVERSE_RISK_FACTOR
    if label == "favourable":
        return _FAVOURABLE_RISK_FACTOR
    return 1.0


def build_news_event_risk_by_symbol(items, reliability_by_source, now_utc: datetime,
                                    config: NewsEventRiskConfig = NewsEventRiskConfig(),
                                    gazetteer=None, sentiment_scorer=None) -> dict:
    """Per-symbol event risk in [0,1] from FRESH, reliable news/filings.

    risk(symbol) = clamp( Σ over recent items of reliability × recency-weight × sentiment-factor ).
    Items from sources below the reliability floor, or older than the recency window, contribute 0.
    A "SYMBOL:" filing attributes to that symbol; other headlines via the `gazetteer` (research/148).
    With a `sentiment_scorer` (research/150) the gate is DIRECTIONAL — adverse news weighs more."""
    window_seconds = config.recency_window.total_seconds()
    risk_by_symbol: dict = {}
    for item in items:
        symbols = _symbols_of(item, gazetteer)
        if not symbols:
            continue
        reliability = reliability_by_source.get(item.source_id, 0.0)
        if reliability < config.min_source_reliability:
            continue
        stamp = item.published_at or item.fetched_at
        if stamp is None:
            continue
        age_seconds = (now_utc - stamp).total_seconds()
        if age_seconds < 0 or age_seconds > window_seconds:
            continue
        recency_weight = 1.0 - (age_seconds / window_seconds)  # 1 at now → 0 at the window edge
        contribution = reliability * recency_weight * _sentiment_risk_factor(item.title, sentiment_scorer)
        for symbol in symbols:
            risk_by_symbol[symbol] = min(1.0, risk_by_symbol.get(symbol, 0.0) + contribution)
    return risk_by_symbol


def news_event_size_multiplier(risk: float, calibration_earned: bool,
                               defer_threshold: float = NEWS_EVENT_DEFER_THRESHOLD,
                               size_down_threshold: float = NEWS_EVENT_SIZE_DOWN_THRESHOLD,
                               size_down_multiplier: float = NEWS_EVENT_SIZE_DOWN_MULTIPLIER) -> float:
    """1.0 (identity) until EARNED or below size-down; then 0.0 (defer) at/above the defer threshold,
    `size_down_multiplier` at/above size-down. Mirrors the debate-risk gate so it is safe by default."""
    if risk is None or not calibration_earned:
        return 1.0
    if risk >= defer_threshold:
        return 0.0
    if risk >= size_down_threshold:
        return size_down_multiplier
    return 1.0
