"""Types for S2 structured index price-level extraction (Trunk II SENSES; research/142). PURE — no I/O.

An `ExtractedLevel` is one price level quoted in a headline (its numeric value, whether the text
frames it as support / resistance / a bare pivot, a confidence, and the text evidence). An
`ExtractedLevelSet` groups the levels one news item quotes for one index underlying. A
`NewsLevelExtractionReport` summarises one extraction pass for the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IndexUnderlying(str, Enum):
    """Phase-1 index-option underlyings (CLAUDE.md). Sensex is deliberately absent — BSE, out of scope."""

    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"
    FINNIFTY = "FINNIFTY"
    MIDCPNIFTY = "MIDCPNIFTY"
    NIFTYNXT50 = "NIFTYNXT50"


class LevelKind(str, Enum):
    """How the headline frames the number: an explicit floor, an explicit ceiling, or a bare key level."""

    SUPPORT = "support"       # "support at X", "holds X", "floor"
    RESISTANCE = "resistance"  # "resistance at X", "hurdle", "cap"
    PIVOT = "pivot"           # "key X level", "closes below X" — a real level, side unstated
    TARGET = "target"         # analyst price target ("target of Rs X") — a stock upside level


@dataclass(frozen=True)
class ExtractedLevel:
    """One price level parsed from a headline, classified by its surrounding text."""

    value: float
    kind: str            # LevelKind value
    confidence: float    # 0..1 — how explicitly the text attributes this as a level
    evidence: str        # the text snippet the level was read from


@dataclass(frozen=True)
class ExtractedLevelSet:
    """The levels one news item quotes for one index underlying."""

    content_hash: str
    source_id: str
    source_name: str
    title: str
    underlying: str      # IndexUnderlying value
    levels: tuple = ()   # tuple[ExtractedLevel, ...]
    published_at: datetime | None = None

    @property
    def best_confidence(self) -> float:
        return max((lvl.confidence for lvl in self.levels), default=0.0)


@dataclass(frozen=True)
class NewsLevelExtractionReport:
    """One extraction pass, summarised for the dashboard + the (queued) entry-gate consumer."""

    run_at: datetime
    items_scanned: int
    items_with_levels: int
    levels_found: int
    level_sets_new: int                        # rows genuinely new to the store (after dedup)
    levels_by_underlying: dict = field(default_factory=dict)  # underlying -> count
    top_level_lines: tuple = ()                # a few human-readable "NIFTY support 24,800" lines
    stored_level_total: int = 0
    summary: str = ""
