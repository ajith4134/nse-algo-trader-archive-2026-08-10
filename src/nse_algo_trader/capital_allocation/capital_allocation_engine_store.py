"""Persisted state for the capital-allocation engine (research/163 §2/§8 module 8). Carried STATE (Rule P.2).

Holds what must survive across decision ticks / process restarts: the last allocation's weights keyed by
a STABLE candidate key (underlying·kind·direction) so the next tick can compute turnover ‖w−w_prev‖₁; the
earning-gate evidence (distinct session-dates of real history seen, last evaluation); and a rolling log of
the objective mode used (for the dashboard + mode-promotion honesty). Atomic write (temp-file + os.replace)
so a crash mid-write never corrupts the state (mirrors the win-probability model store idiom).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ALLOCATION_STATE_PATH = Path.home() / ".nse_algo_trader" / "capital_allocation_state.json"


@dataclass
class CapitalAllocationState:
    """The evolving engine state (mutable — updated each solve, then persisted)."""

    last_weights_by_key: dict[str, float] = field(default_factory=dict)  # stable-key → weight
    distinct_session_dates_seen: int = 0        # real trading days of history (the earning evidence)
    is_performance_earned: bool = False         # True → the allocation ACTS (moves real size)
    mode_history: list[str] = field(default_factory=list)   # objective modes used, most-recent last
    last_evaluation: dict = field(default_factory=dict)     # last real-data eval (CVaR-reduction etc.)

    def record_mode(self, mode: str, max_history: int = 200) -> None:
        self.mode_history.append(mode)
        if len(self.mode_history) > max_history:
            self.mode_history = self.mode_history[-max_history:]


class CapitalAllocationEngineStore:
    """Atomic JSON persistence for `CapitalAllocationState`."""

    def __init__(self, state_path: Path = DEFAULT_ALLOCATION_STATE_PATH):
        self._state_path = state_path

    def load(self) -> CapitalAllocationState:
        """Load the state, or a fresh un-earned state if none exists / the file is unreadable."""
        try:
            raw = json.loads(self._state_path.read_text())
            return CapitalAllocationState(
                last_weights_by_key=dict(raw.get("last_weights_by_key", {})),
                distinct_session_dates_seen=int(raw.get("distinct_session_dates_seen", 0)),
                is_performance_earned=bool(raw.get("is_performance_earned", False)),
                mode_history=list(raw.get("mode_history", [])),
                last_evaluation=dict(raw.get("last_evaluation", {})),
            )
        except (FileNotFoundError, ValueError, OSError):
            return CapitalAllocationState()

    def save(self, state: CapitalAllocationState) -> None:
        """Atomically persist the state (temp-file + os.replace — never a torn write)."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_weights_by_key": state.last_weights_by_key,
            "distinct_session_dates_seen": state.distinct_session_dates_seen,
            "is_performance_earned": state.is_performance_earned,
            "mode_history": state.mode_history,
            "last_evaluation": state.last_evaluation,
        }
        temp_path = self._state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, default=str))
        os.replace(temp_path, self._state_path)
