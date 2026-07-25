"""Persists the current CHAMPION ORB configuration (§53 slice 5c-i; research/87).

A promotion by the champion-challenger tournament must survive restarts, and the live loop
reads the champion here (fallback to the built-in default) to drive ORB decisions. A tiny
JSON file — the config is three scalar knobs. `time` is stored as "HH:MM".
"""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path

from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)

DEFAULT_CHAMPION_CONFIG_PATH = Path(
    "~/.nse_algo_trader/champion_orb_config.json"
).expanduser()


class ChampionConfigurationStore:
    def __init__(self, config_file_path: Path = DEFAULT_CHAMPION_CONFIG_PATH) -> None:
        self._config_file_path = config_file_path

    def load_champion_or_default(
        self, default: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig()
    ) -> OpeningRangeBreakoutConfig:
        """The stored champion, or `default` when nothing has been promoted yet / the file
        is unreadable (best-effort — a corrupt file must never break the live loop)."""
        try:
            if not self._config_file_path.exists():
                return default
            data = json.loads(self._config_file_path.read_text())
            hour, minute = (int(part) for part in data["latest_entry_time_ist"].split(":"))
            return OpeningRangeBreakoutConfig(
                opening_range_minutes=int(data["opening_range_minutes"]),
                target_risk_reward_ratio=float(data["target_risk_reward_ratio"]),
                latest_entry_time_ist=time(hour, minute),
            )
        except Exception:
            return default

    def save_champion(self, config: OpeningRangeBreakoutConfig) -> None:
        """Persist a promoted champion config (atomic-ish: write then replace)."""
        self._config_file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "opening_range_minutes": config.opening_range_minutes,
            "target_risk_reward_ratio": config.target_risk_reward_ratio,
            "latest_entry_time_ist": config.latest_entry_time_ist.strftime("%H:%M"),
        }
        self._config_file_path.write_text(json.dumps(payload, indent=2))
