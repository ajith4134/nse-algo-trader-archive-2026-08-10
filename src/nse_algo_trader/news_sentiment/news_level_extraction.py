"""S2 — extract structured index support/resistance levels from headlines (Trunk II SENSES; research/142).

PURE, stdlib-only (`re`). No OSS component does "analyst-quoted index levels from Indian financial
headlines" (research/142 §2: every S/R library works on a price series, not text) — so this is a
bespoke gazetteer + plausibility-band + keyword-adjacency parser.

Method: detect the index underlying (NIFTY / BANKNIFTY / …) a headline references, find every
Indian-format number in the drift-free plausibility band [5,000 – 100,000] (rejects years, counts,
point-moves, prices), and classify each number as SUPPORT / RESISTANCE / PIVOT only when a
level-context keyword sits within a small character window (the precision guard — a bare number is
never a level). `extract_level_set` returns one `ExtractedLevelSet` per (item, underlying), or none.
"""

from __future__ import annotations

import re

from nse_algo_trader.news_sentiment.news_level_types import (
    ExtractedLevel,
    ExtractedLevelSet,
    IndexUnderlying,
    LevelKind,
)

# Drift-free plausibility band: NIFTY ~24k, BANKNIFTY ~51k, NIFTYNXT50 ~65k all sit inside for years;
# years (2024/2026), counts ("5 factors"), point-moves ("2,000 points"), prices ("$95") fall outside.
_MIN_PLAUSIBLE_LEVEL = 5_000.0
_MAX_PLAUSIBLE_LEVEL = 100_000.0

# How close (in characters) a level-context keyword must sit to a number for it to count as a level.
_KEYWORD_WINDOW_CHARS = 28

# Index gazetteer: alias regex -> canonical underlying. Longer aliases first so "bank nifty" wins
# over "nifty". Sensex/BSE indices are intentionally NOT here (out of Phase-1 scope, CLAUDE.md).
_UNDERLYING_ALIASES: tuple[tuple[str, str], ...] = (
    (r"nifty\s*next\s*50|niftynxt50|nifty\s*nxt\s*50", IndexUnderlying.NIFTYNXT50.value),
    (r"bank\s*nifty|nifty\s*bank|banknifty", IndexUnderlying.BANKNIFTY.value),
    (r"fin\s*nifty|finnifty", IndexUnderlying.FINNIFTY.value),
    (r"midcap\s*nifty|midcpnifty|nifty\s*midcap", IndexUnderlying.MIDCPNIFTY.value),
    (r"nifty(?:\s*50)?", IndexUnderlying.NIFTY.value),
)

# Level-context keywords. Nearest keyword to a number decides its kind; window-scoped so an unrelated
# word elsewhere in the headline can't mis-tag a number.
_SUPPORT_KEYWORDS = (
    "support", "supports", "supported", "holds above", "hold above", "holds", "hold",
    "floor", "base", "cushion", "demand zone", "buy zone", "reclaims", "reclaim", "bounce",
)
_RESISTANCE_KEYWORDS = (
    "resistance", "resist", "hurdle", "cap", "ceiling", "supply zone", "target",
    "upside", "breakout above", "faces resistance",
)
# Bare-level markers: the text clearly names a key level but doesn't say which side.
_PIVOT_KEYWORDS = (
    "level", "key", "psychological", "mark", "breaks below", "broke below", "break below",
    "closes below", "closed below", "close below", "slips below", "slip below", "drags below",
    "falls below", "fell below", "closes above", "closed above", "crosses", "crossed", "above", "below",
)

_NUMBER_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{4,6}(?:\.\d+)?\b")


def _detect_underlying_mentions(text_lower: str) -> list[tuple[str, int]]:
    """Return (underlying, center_position) for EVERY index mention in the text.

    Aliases are matched most-specific-first and each matched span is masked out before the next
    alias searches — so "bank nifty" is claimed by BANKNIFTY and cannot also fire a bare NIFTY at
    the inner "nifty". Every mention (not just the first) is kept, so a number can later be attached
    to its NEAREST index.
    """
    chars = list(text_lower)
    mentions: list[tuple[str, int]] = []
    for alias_pattern, underlying in _UNDERLYING_ALIASES:
        masked = "".join(chars)
        for m in re.finditer(alias_pattern, masked):
            mentions.append((underlying, (m.start() + m.end()) // 2))
            for i in range(m.start(), m.end()):
                chars[i] = " "  # mask so a shorter alias can't re-match inside this span
    return mentions


def _governing_underlying(mentions: list[tuple[str, int]], num_center: int) -> str:
    """Attribute a number to the index that GOVERNS it — the nearest mention preceding it.

    Financial writing puts the index before its level ("Nifty ... 23,600", "Bank Nifty faces
    support at 55,800"), so a number belongs to the closest index name to its LEFT. When a number
    precedes every index name, fall back to the nearest mention overall.
    """
    preceding = [mn for mn in mentions if mn[1] <= num_center]
    if preceding:
        return max(preceding, key=lambda mn: mn[1])[0]  # closest one to the left
    return min(mentions, key=lambda mn: abs(mn[1] - num_center))[0]


def _classify_number(text_lower: str, num_start: int, num_end: int) -> tuple[str, float, str] | None:
    """Classify the number at [num_start:num_end] as SUPPORT/RESISTANCE/PIVOT via nearest keyword."""
    window_start = max(0, num_start - _KEYWORD_WINDOW_CHARS)
    window_end = min(len(text_lower), num_end + _KEYWORD_WINDOW_CHARS)
    window = text_lower[window_start:window_end]

    def nearest(keywords) -> int | None:
        best = None
        for kw in keywords:
            idx = window.find(kw)
            if idx != -1 and (best is None or idx < best):
                best = idx
        return best

    support_at = nearest(_SUPPORT_KEYWORDS)
    resistance_at = nearest(_RESISTANCE_KEYWORDS)

    # A directional keyword ALWAYS wins over a generic pivot marker ("key support at X" is support,
    # not a bare pivot) — pick support vs resistance by whichever sits nearer the number.
    directional = [
        (pos, kind) for pos, kind in
        ((support_at, LevelKind.SUPPORT.value), (resistance_at, LevelKind.RESISTANCE.value))
        if pos is not None
    ]
    if directional:
        directional.sort(key=lambda c: c[0])
        return directional[0][1], 0.8, window.strip()

    if nearest(_PIVOT_KEYWORDS) is not None:
        return LevelKind.PIVOT.value, 0.7, window.strip()

    return None  # no level keyword nearby -> this number is NOT a level (precision guard)


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_level_sets(content_hash, source_id, source_name, title, summary, published_at=None):
    """Extract one `ExtractedLevelSet` per index underlying the item references (empty list if none)."""
    text = f"{title}  {summary}".strip()
    text_lower = text.lower()

    mentions = _detect_underlying_mentions(text_lower)
    if not mentions:
        return []

    # Each classified number is attached to the NEAREST index mention (so a headline naming both
    # NIFTY and BANKNIFTY assigns 23,600 to NIFTY and 55,800 to BANKNIFTY, not both to both).
    levels_by_underlying: dict[str, list[ExtractedLevel]] = {}
    for m in _NUMBER_RE.finditer(text_lower):
        value = _parse_number(m.group())
        if not (_MIN_PLAUSIBLE_LEVEL <= value <= _MAX_PLAUSIBLE_LEVEL):
            continue
        classified = _classify_number(text_lower, m.start(), m.end())
        if classified is None:
            continue
        kind, confidence, evidence = classified
        num_center = (m.start() + m.end()) // 2
        underlying = _governing_underlying(mentions, num_center)
        levels_by_underlying.setdefault(underlying, []).append(
            ExtractedLevel(value=value, kind=kind, confidence=confidence, evidence=evidence)
        )

    level_sets = []
    for underlying, levels in levels_by_underlying.items():
        # Dedup identical (value, kind) pairs, keeping the highest confidence.
        deduped: dict[tuple[float, str], ExtractedLevel] = {}
        for lvl in levels:
            key = (lvl.value, lvl.kind)
            if key not in deduped or lvl.confidence > deduped[key].confidence:
                deduped[key] = lvl
        level_sets.append(
            ExtractedLevelSet(
                content_hash=content_hash,
                source_id=source_id,
                source_name=source_name,
                title=title,
                underlying=underlying,
                levels=tuple(sorted(deduped.values(), key=lambda x: x.value)),
                published_at=published_at,
            )
        )
    return level_sets
