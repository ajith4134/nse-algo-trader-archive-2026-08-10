"""Persisted state for the curiosity engine (research/164; Trunk XII). Carried STATE (Rule P.2).

Holds the per-cell `CellLearningState` (Q_LP, boredom counter, sample watermark, recent-error mean) and
the cumulative trade count that anneals the selection temperature — everything that must evolve across
decision ticks / process restarts so learning progress is TRACKED, not recomputed from scratch each time.
Atomic write (temp-file + os.replace), mirroring the other engines' stores.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from nse_algo_trader.intrinsic_motivation.learning_progress_estimator import CellLearningState

DEFAULT_CURIOSITY_STATE_PATH = Path.home() / ".nse_algo_trader" / "curiosity_state.json"


@dataclass
class CuriosityState:
    """The evolving engine state: per-cell learning state (keyed "strategy||regime") + trade watermark."""

    cell_states: dict[str, CellLearningState] = field(default_factory=dict)
    total_trades_seen: int = 0     # anneals the softmax temperature (more data → more exploit)

    @staticmethod
    def cell_state_key(strategy_tag: str, market_regime: str) -> str:
        return f"{strategy_tag}||{market_regime}"

    def state_for(self, strategy_tag: str, market_regime: str) -> CellLearningState:
        return self.cell_states.get(self.cell_state_key(strategy_tag, market_regime), CellLearningState())


class CuriosityEngineStore:
    """Atomic JSON persistence for `CuriosityState`."""

    def __init__(self, state_path: Path = DEFAULT_CURIOSITY_STATE_PATH):
        self._state_path = state_path

    def load(self) -> CuriosityState:
        try:
            raw = json.loads(self._state_path.read_text())
            cells = {
                key: CellLearningState(
                    q_learning_progress=float(v.get("q_learning_progress", 0.0)),
                    consecutive_bored_windows=int(v.get("consecutive_bored_windows", 0)),
                    samples_at_last_update=int(v.get("samples_at_last_update", 0)),
                    last_recent_error_mean=float(v.get("last_recent_error_mean", 1.0)),
                )
                for key, v in raw.get("cell_states", {}).items()
            }
            return CuriosityState(cell_states=cells,
                                  total_trades_seen=int(raw.get("total_trades_seen", 0)))
        except (FileNotFoundError, ValueError, OSError):
            return CuriosityState()

    def save(self, state: CuriosityState) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cell_states": {
                key: {
                    "q_learning_progress": cs.q_learning_progress,
                    "consecutive_bored_windows": cs.consecutive_bored_windows,
                    "samples_at_last_update": cs.samples_at_last_update,
                    "last_recent_error_mean": cs.last_recent_error_mean,
                }
                for key, cs in state.cell_states.items()
            },
            "total_trades_seen": state.total_trades_seen,
        }
        temp_path = self._state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, indent=2))
        os.replace(temp_path, self._state_path)
