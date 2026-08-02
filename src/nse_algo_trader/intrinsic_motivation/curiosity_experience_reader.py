"""Data pipeline for the curiosity engine (research/164; Trunk XII). Raw experience → per-cell error series.

Reads the raw `experience_nodes` closed-trade history and groups it into (strategy_tag × market_regime)
CELLS, each carrying its prediction-error samples in TIME ORDER (by `occurred_at`). The error per trade is
the Brier contribution `(win_probability − outcome)²` — the model's squared prediction error — which is
exactly the quantity whose RATE OF DECREASE is learning progress (research/164). The reader also reports
each cell's raw sample count (for count-based novelty + the LP min-samples gate) and the full set of
strategies × regimes SEEN (so the engine can score UNOBSERVED cells as maximally novel at cold-start).

The `experience_row_source` is a DI seam (Rule J): production reads the real sqlite `experience_nodes`
table; tests inject canned rows. Pure transformation otherwise. Non-finite / missing fields are dropped
(Rule O.4), never silently coerced to a wrong number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# The market regimes the bot classifies sessions into (the exploration axis alongside strategy).
KNOWN_MARKET_REGIMES = ("trending", "range_bound", "indecisive")


@dataclass(frozen=True)
class CellErrorSeries:
    """One (strategy × regime) cell's time-ordered prediction-error history."""

    strategy_tag: str
    market_regime: str
    errors_in_time_order: tuple[float, ...]   # Brier contributions, oldest → newest
    win_flags_in_time_order: tuple[int, ...]   # 1 = win, 0 = loss (same order) — for realized competence
    sample_count: int

    @property
    def cell_key(self) -> tuple[str, str]:
        return (self.strategy_tag, self.market_regime)


@dataclass(frozen=True)
class CuriosityObservation:
    """The full grouped view the curiosity engine scores: per-cell error series + the seen universe."""

    cells: tuple[CellErrorSeries, ...]
    strategies_seen: frozenset[str]
    regimes_seen: frozenset[str]
    total_samples: int
    cells_by_key: dict[tuple[str, str], CellErrorSeries] = field(default_factory=dict)


def default_experience_row_source(limit: int = 20000) -> list[dict]:
    """Production DI seam: read the raw `experience_nodes` rows (newest-first by occurred_at). [] on any
    failure so a data hiccup never breaks the loop (Rule O.3 — the empty result is visibly a cold-start)."""
    try:
        import sqlite3

        from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
            DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
        )

        path = DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()
        if not path.exists():
            return []
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT strategy_tag, market_regime, win_probability, actual_outcome, "
                "brier_contribution, occurred_at, session_date FROM experience_nodes "
                "ORDER BY occurred_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            connection.close()
    except Exception:
        return []


def _brier_error(row: dict) -> float | None:
    """The prediction error for one trade: the stored Brier contribution if present, else recomputed
    (win_probability − 1{win})². None when neither is derivable (Rule O.4 — drop, don't fabricate)."""
    stored = row.get("brier_contribution")
    if stored is not None and math.isfinite(stored):
        return float(stored)
    win_probability = row.get("win_probability")
    outcome = str(row.get("actual_outcome", "")).strip().lower()
    if win_probability is None or not math.isfinite(win_probability) or outcome not in ("win", "loss"):
        return None
    realized = 1.0 if outcome == "win" else 0.0
    return float((float(win_probability) - realized) ** 2)


def build_curiosity_observation(rows: list[dict]) -> CuriosityObservation:
    """Group raw experience rows (assumed ASC by occurred_at) into per-cell time-ordered error series."""
    grouped_errors: dict[tuple[str, str], list[float]] = {}
    grouped_wins: dict[tuple[str, str], list[int]] = {}
    strategies_seen: set[str] = set()
    regimes_seen: set[str] = set()
    total = 0

    for row in rows:
        strategy = str(row.get("strategy_tag") or "").strip()
        regime = str(row.get("market_regime") or "unknown").strip()
        if not strategy:
            continue
        error = _brier_error(row)
        if error is None:
            continue
        key = (strategy, regime)
        grouped_errors.setdefault(key, []).append(error)
        grouped_wins.setdefault(key, []).append(
            1 if str(row.get("actual_outcome", "")).strip().lower() == "win" else 0)
        strategies_seen.add(strategy)
        if regime in KNOWN_MARKET_REGIMES:
            regimes_seen.add(regime)
        total += 1

    cells = tuple(
        CellErrorSeries(
            strategy_tag=key[0], market_regime=key[1],
            errors_in_time_order=tuple(grouped_errors[key]),
            win_flags_in_time_order=tuple(grouped_wins[key]),
            sample_count=len(grouped_errors[key]),
        )
        for key in grouped_errors
    )
    return CuriosityObservation(
        cells=cells,
        strategies_seen=frozenset(strategies_seen),
        regimes_seen=frozenset(regimes_seen),
        total_samples=total,
        cells_by_key={c.cell_key: c for c in cells},
    )
