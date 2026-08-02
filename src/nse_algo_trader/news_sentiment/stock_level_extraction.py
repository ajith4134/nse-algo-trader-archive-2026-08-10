"""Extract per-STOCK price levels from headlines (Trunk II SENSES; research/149). PURE, stdlib `re`.

Completes S2's S/R extraction from index-only to the ~211 F&O stock underlyings (Rule L). Stock prices
span ₹10–₹100k, so a global plausibility band can't gate (unlike the index band); precision comes from
requiring BOTH a resolved F&O symbol (via the research/148 gazetteer) AND a strong money/target cue
("target of Rs N", "support at Rs N", "₹N"). Emits the same `ExtractedLevelSet` as S2 → same
`news_levels` store table (underlying = the stock symbol). New `LevelKind.TARGET` for analyst targets.
"""

from __future__ import annotations

import re

from nse_algo_trader.news_sentiment.news_level_types import (
    ExtractedLevel,
    ExtractedLevelSet,
    LevelKind,
)

# A money-cued number: "Rs 6580" / "Rs. 6,580" / "₹6580" / "target of 6580". The number is either
# Indian-comma-grouped (6,580 / 1,07,500) OR a plain run of digits (6580) — the earlier comma-only
# form truncated "6580"→"658", so both forms are captured.
_MONEY_NUMBER_RE = re.compile(
    r"(?:rs\.?\s*|₹\s*|target(?:\s+price)?(?:\s+of)?\s+)"
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{2,6}(?:\.\d+)?)",
    re.IGNORECASE,
)
# A number followed by one of these is a financial MAGNITUDE (profit/revenue/move), not a price level.
_MAGNITUDE_SUFFIX_RE = re.compile(r"^\s*(cr\b|crore|lakh|billion|million|%|percent|bps|pts|points)",
                                  re.IGNORECASE)
_MIN_STOCK_LEVEL = 5.0
_MAX_STOCK_LEVEL = 200_000.0
_KEYWORD_WINDOW_CHARS = 24

_TARGET_KEYWORDS = ("target", "price target", "upside")
_SUPPORT_KEYWORDS = ("support", "supports", "buy zone", "accumulate near", "floor")
_RESISTANCE_KEYWORDS = ("resistance", "hurdle", "cap", "supply zone")


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _classify(text_lower: str, num_start: int) -> tuple[str, float] | None:
    """Classify a money-cued stock number by the nearest level keyword. Returns None when NO
    target/support/resistance word is near — a bare 'Rs N' is a price/figure, not a claimed level
    (kills profit/revenue false positives), so we require an explicit level intent."""
    window = text_lower[max(0, num_start - _KEYWORD_WINDOW_CHARS):num_start + _KEYWORD_WINDOW_CHARS]

    def nearest(keywords):
        best = None
        for kw in keywords:
            idx = window.find(kw)
            if idx != -1 and (best is None or idx < best):
                best = idx
        return best

    candidates = [
        (nearest(_SUPPORT_KEYWORDS), LevelKind.SUPPORT.value),
        (nearest(_RESISTANCE_KEYWORDS), LevelKind.RESISTANCE.value),
        (nearest(_TARGET_KEYWORDS), LevelKind.TARGET.value),
    ]
    present = [(pos, kind) for pos, kind in candidates if pos is not None]
    if not present:
        return None
    present.sort(key=lambda c: c[0])
    return present[0][1], 0.8


def extract_stock_level_sets(content_hash, source_id, source_name, title, summary, gazetteer,
                             published_at=None):
    """Extract one `ExtractedLevelSet` per F&O stock the item quotes a level for (empty if none)."""
    if gazetteer is None:
        return []
    text = f"{title}  {summary}".strip()
    symbols = gazetteer.match_symbols(text)
    # Single-stock precision guard: analyst-level headlines name ONE stock. A multi-symbol headline
    # (a listicle / bonus-dividend roundup) would cross-attribute figures to every named stock, so skip.
    if len(symbols) != 1:
        return []
    symbol = next(iter(symbols))

    text_lower = text.lower()
    levels = []
    for match in _MONEY_NUMBER_RE.finditer(text_lower):
        value = _parse_number(match.group(1))
        if not (_MIN_STOCK_LEVEL <= value <= _MAX_STOCK_LEVEL):
            continue
        if _MAGNITUDE_SUFFIX_RE.match(text_lower[match.end():]):
            continue  # "Rs 1,000 cr" is a profit figure, not a price level
        classified = _classify(text_lower, match.start())
        if classified is None:
            continue  # money cue but no target/support/resistance intent → not a level
        kind, confidence = classified
        levels.append(ExtractedLevel(value=value, kind=kind, confidence=confidence,
                                     evidence=text[max(0, match.start() - 20):match.end() + 4].strip()))
    if not levels:
        return []

    deduped = {}
    for lvl in levels:
        key = (lvl.value, lvl.kind)
        if key not in deduped or lvl.confidence > deduped[key].confidence:
            deduped[key] = lvl
    ordered_levels = tuple(sorted(deduped.values(), key=lambda x: x.value))
    return [ExtractedLevelSet(
        content_hash=content_hash, source_id=source_id, source_name=source_name, title=title,
        underlying=symbol, levels=ordered_levels, published_at=published_at)]
