"""Persistence for the world-model's carried counts (research/167 §3/§6; Trunk IX). Carried STATE.

Atomically persists `WorldModelCounts` (the transition tensor + reward sums/counts + observation total) so
the generative model LEARNS across sessions/restarts instead of recomputing from scratch. JSON + temp-file
os.replace, mirroring the other engine stores.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from nse_algo_trader.predictive_core.generative_market_transition_model import WorldModelCounts
from nse_algo_trader.predictive_core.market_state_discretizer import ACTIONS, STATE_COUNT

DEFAULT_WORLD_MODEL_STATE_PATH = Path.home() / ".nse_algo_trader" / "world_model_counts.json"


class WorldModelTransitionStore:
    """Atomic JSON persistence for `WorldModelCounts`."""

    def __init__(self, state_path: Path = DEFAULT_WORLD_MODEL_STATE_PATH):
        self._state_path = state_path

    def load(self) -> WorldModelCounts:
        try:
            raw = json.loads(self._state_path.read_text())
            transition = raw.get("transition_counts")
            reward_sums = raw.get("reward_sums")
            reward_counts = raw.get("reward_counts")
            # shape guard: a stale file from a different STATE_COUNT is discarded, not trusted (Rule O.4)
            if (not isinstance(transition, list) or len(transition) != STATE_COUNT
                    or any(len(row) != STATE_COUNT for row in transition)):
                return WorldModelCounts()
            return WorldModelCounts(
                transition_counts=[[float(x) for x in row] for row in transition],
                reward_sums=[{a: float(d.get(a, 0.0)) for a in ACTIONS} for d in reward_sums],
                reward_counts=[{a: float(d.get(a, 0.0)) for a in ACTIONS} for d in reward_counts],
                total_observations=int(raw.get("total_observations", 0)),
            )
        except (FileNotFoundError, ValueError, OSError, TypeError, KeyError):
            return WorldModelCounts()

    def save(self, counts: WorldModelCounts) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "transition_counts": counts.transition_counts,
            "reward_sums": counts.reward_sums,
            "reward_counts": counts.reward_counts,
            "total_observations": counts.total_observations,
        }
        temp_path = self._state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload))
        os.replace(temp_path, self._state_path)
