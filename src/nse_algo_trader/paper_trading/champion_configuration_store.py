"""Persists the CHAMPION ORB configuration(s) (§53 slice 5c-i, 5c-iii; research/87, 90).

A promotion by the champion-challenger tournament must survive restarts, and the live loop
reads the champion here (fallback to the built-in default) to drive ORB decisions. Since
5c-iii the store holds a GLOBAL champion plus an optional champion PER market regime:

    {"global": {config}, "by_regime": {"trending": {config}, "range_bound": {config}, …}}

The old flat format (a bare config dict) is still read as the global champion (back-compat).
A tiny JSON file — each config is three scalar knobs; `time` is stored as "HH:MM".
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


def _config_to_dict(config: OpeningRangeBreakoutConfig) -> dict:
    return {
        "opening_range_minutes": config.opening_range_minutes,
        "target_risk_reward_ratio": config.target_risk_reward_ratio,
        "latest_entry_time_ist": config.latest_entry_time_ist.strftime("%H:%M"),
    }


def _config_from_dict(data: dict) -> OpeningRangeBreakoutConfig:
    hour, minute = (int(part) for part in data["latest_entry_time_ist"].split(":"))
    return OpeningRangeBreakoutConfig(
        opening_range_minutes=int(data["opening_range_minutes"]),
        target_risk_reward_ratio=float(data["target_risk_reward_ratio"]),
        latest_entry_time_ist=time(hour, minute),
    )


class ChampionConfigurationStore:
    def __init__(self, config_file_path: Path = DEFAULT_CHAMPION_CONFIG_PATH) -> None:
        self._config_file_path = config_file_path

    def _read_raw(self) -> dict:
        """The stored JSON normalised to `{"global": dict|None, "by_regime": {...}}`.
        The old flat format (a bare config dict) is promoted to the global slot."""
        if not self._config_file_path.exists():
            return {"global": None, "by_regime": {}}
        data = json.loads(self._config_file_path.read_text())
        if "opening_range_minutes" in data:  # legacy flat format = the global champion
            return {"global": data, "by_regime": {}}
        return {"global": data.get("global"), "by_regime": data.get("by_regime", {})}

    def load_champion_or_default(
        self,
        default: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
        market_regime: str | None = None,
    ) -> OpeningRangeBreakoutConfig:
        """The champion for `market_regime` if one is stored, else the global champion, else
        `default`. `market_regime=None` asks only for the global champion. Best-effort — a
        corrupt/absent file returns `default` (never breaks the live loop)."""
        try:
            raw = self._read_raw()
            if market_regime is not None:
                regime_config = raw["by_regime"].get(market_regime)
                if regime_config is not None:
                    return _config_from_dict(regime_config)
            if raw["global"] is not None:
                return _config_from_dict(raw["global"])
            return default
        except Exception:
            return default

    def save_champion(
        self, config: OpeningRangeBreakoutConfig, market_regime: str | None = None
    ) -> None:
        """Persist `config` as the global champion (`market_regime=None`) or the champion for
        one regime — preserving the other slots already stored."""
        self._config_file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = self._read_raw()
        except Exception:
            raw = {"global": None, "by_regime": {}}
        if market_regime is None:
            raw["global"] = _config_to_dict(config)
        else:
            raw["by_regime"][market_regime] = _config_to_dict(config)
        self._config_file_path.write_text(json.dumps(raw, indent=2))
