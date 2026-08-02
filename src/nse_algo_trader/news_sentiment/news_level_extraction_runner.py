"""Compose the S2 level-extraction pass (Trunk II SENSES; research/142).

One `run(now_utc)`: load the most-recent stored news items → run the pure `extract_level_sets` over
each → persist the structured index levels → return a `NewsLevelExtractionReport` for the dashboard.
Thin orchestrator the live service's cadence calls; the parser and the store stay independently
testable. Consumes what S1 already stored, so it needs no network of its own.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.news_sentiment.news_level_extraction import extract_level_sets
from nse_algo_trader.news_sentiment.news_level_types import NewsLevelExtractionReport


class NewsLevelExtractionRunner:
    def __init__(self, store, scan_limit: int = 300):
        self._store = store
        self._scan_limit = scan_limit

    def run(self, now_utc: datetime) -> NewsLevelExtractionReport:
        items = self._store.load_recent_items(limit=self._scan_limit)

        all_sets = []
        for item in items:
            all_sets.extend(
                extract_level_sets(
                    content_hash=item.content_hash,
                    source_id=item.source_id,
                    source_name=item.source_name,
                    title=item.title,
                    summary=item.summary,
                    published_at=item.published_at,
                )
            )

        level_sets_new = self._store.save_extracted_levels(all_sets) if all_sets else 0

        levels_found = sum(len(s.levels) for s in all_sets)
        items_with_levels = len({s.content_hash for s in all_sets})
        levels_by_underlying: dict = {}
        for s in all_sets:
            levels_by_underlying[s.underlying] = levels_by_underlying.get(s.underlying, 0) + len(s.levels)

        # A few human-readable lines from the freshest/most-confident stored levels for the surface.
        top_lines = []
        for s in self._store.load_recent_levels(limit=8):
            for lvl in s.levels:
                top_lines.append(f"{s.underlying} {lvl.kind} {lvl.value:,.0f}")
        top_level_lines = tuple(top_lines[:6])

        stored_level_total = self._store.level_count()
        summary = (
            f"scanned {len(items)} items → {items_with_levels} with levels, {levels_found} levels "
            f"({level_sets_new} new); stored {stored_level_total}."
        )
        if levels_by_underlying:
            summary += " By underlying: " + ", ".join(
                f"{u} {n}" for u, n in sorted(levels_by_underlying.items())
            ) + "."

        return NewsLevelExtractionReport(
            run_at=now_utc,
            items_scanned=len(items),
            items_with_levels=items_with_levels,
            levels_found=levels_found,
            level_sets_new=level_sets_new,
            levels_by_underlying=levels_by_underlying,
            top_level_lines=top_level_lines,
            stored_level_total=stored_level_total,
            summary=summary,
        )
