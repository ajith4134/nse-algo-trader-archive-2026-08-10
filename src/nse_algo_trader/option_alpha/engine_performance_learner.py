"""Self-learning engine re-weighting — the bot learns WHICH profit-engine actually pays and tilts toward it.

Closes the redesign loop: the opportunity scorer picks an engine → the optimizer synthesizes the structure →
the lifecycle closes it → its realised outcome is recorded per engine here → this learner turns each engine's
track record into a WEIGHT that multiplies its score next cycle. So selection shifts toward the engines that
have worked in THIS market — the bot learning its own edge.

Small-N honesty (Rule Q): the weight is a Bayesian shrinkage toward a neutral 1.0 by trade count, so a thin
engine stays neutral (no premature tilt) and only a proven edge moves capital; a losing engine is down-weighted
but floored so it still explores. The full algorithm ships now; the realised-trade accrual is the one open
blocker (few paper closes today) — weights arm themselves automatically as the track record grows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_BASE_WIN_RATE = 0.5     # neutral prior win-rate an engine is measured against
_SHRINK_PRIOR_N = 15.0   # trades at which realised edge and the neutral prior are weighted equally
_MAX_TILT = 0.8          # a fully-proven engine can up/down-weight by at most this (weight ∈ [1−·, 1+·])
_MIN_WEIGHT = 0.25       # a losing engine is never zeroed out → it still gets explored


@dataclass(frozen=True)
class EngineStats:
    engine: str
    trades: int
    wins: int
    mean_pnl: float
    weight: float  # multiplier applied to this engine's opportunity score


class EnginePerformanceStore:
    """Persists each closed pod trade's (engine, won, realized_pnl) — the substrate the learner re-weights."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "engine_performance.jsonl"

    def record(self, engine: str, won: bool, realized_pnl: float) -> None:
        if not engine:
            return
        with self._path.open("a") as fh:
            fh.write(json.dumps({"engine": str(engine), "won": bool(won),
                                 "pnl": float(realized_pnl)}) + "\n")

    def load(self) -> list[dict]:
        if not self._path.exists():
            return []
        rows = []
        for line in self._path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows


class EnginePerformanceLearner:
    """Turns each engine's realised track record into a score-weight (Bayesian shrinkage, Rule Q)."""

    def __init__(self, store: EnginePerformanceStore):
        self._store = store

    def engine_weights(self) -> dict[str, float]:
        """{engine: weight} — 1.0 for engines with no/thin history, tilted by proven realised edge."""
        return {s.engine: s.weight for s in self.engine_stats().values()}

    def engine_stats(self) -> dict[str, EngineStats]:
        by_engine: dict[str, list[dict]] = {}
        for row in self._store.load():
            by_engine.setdefault(str(row.get("engine", "")), []).append(row)
        out: dict[str, EngineStats] = {}
        for engine, rows in by_engine.items():
            if not engine:
                continue
            n = len(rows)
            wins = sum(1 for r in rows if r.get("won"))
            mean_pnl = sum(float(r.get("pnl", 0.0)) for r in rows) / n if n else 0.0
            out[engine] = EngineStats(engine, n, wins, round(mean_pnl, 2),
                                      self._weight(wins / n if n else _BASE_WIN_RATE, n))
        return out

    @staticmethod
    def _weight(win_rate: float, n: int) -> float:
        """weight = 1 + MAX_TILT · edge · shrink(n); edge = win_rate − base (∈ [−0.5,0.5] → scaled to [−1,1])."""
        edge = (win_rate - _BASE_WIN_RATE) / (1.0 - _BASE_WIN_RATE)  # normalize to [-1, 1]
        shrink = n / (n + _SHRINK_PRIOR_N)  # thin history → ~0 → weight ~1.0 (neutral)
        weight = 1.0 + _MAX_TILT * edge * shrink
        return round(max(_MIN_WEIGHT, weight), 4)
