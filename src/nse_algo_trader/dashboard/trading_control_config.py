"""The editable control config — the dashboard's knobs, read by the engine.

Makes the dashboard controls REAL rather than cosmetic: the operator edits
these values (paper capital, min/max capital per trade, which segments and
strategies are on), and the paper/live engine reads this same config. It
persists to a gitignored JSON file on the VPS, so the dashboard writes it
and the bot consumes it — a file-based control plane that needs no open
network port.
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

DEFAULT_TRADING_CONTROL_CONFIG_PATH = Path(
    "~/.nse_algo_trader/trading_control_config.json"
).expanduser()


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class TradableSegment(str, Enum):
    NSE_CASH_EQUITY = "nse_cash_equity"
    NSE_INDEX_OPTIONS = "nse_index_options"
    NSE_STOCK_OPTIONS = "nse_stock_options"


class SelectableStrategy(str, Enum):
    OPENING_RANGE_BREAKOUT = "opening_range_breakout"
    CREDIT_SPREAD = "credit_spread"


@dataclass
class TradingControlConfig:
    trading_mode: TradingMode = TradingMode.PAPER
    account_virtual_capital: float = 1_000_000.0  # editable paper money
    min_capital_per_trade: float = 10_000.0
    max_capital_per_trade: float = 250_000.0
    max_risk_per_trade_fraction: float = 0.01
    segment_enabled: dict[str, bool] = field(
        default_factory=lambda: {segment.value: True for segment in TradableSegment}
    )
    strategy_enabled: dict[str, bool] = field(
        default_factory=lambda: {s.value: True for s in SelectableStrategy}
    )

    def validate(self) -> None:
        if self.account_virtual_capital <= 0:
            raise ValueError("account_virtual_capital must be positive")
        if self.min_capital_per_trade <= 0:
            raise ValueError("min_capital_per_trade must be positive")
        if self.max_capital_per_trade < self.min_capital_per_trade:
            raise ValueError("max_capital_per_trade must be >= min_capital_per_trade")
        if not 0.0 < self.max_risk_per_trade_fraction <= 1.0:
            raise ValueError("max_risk_per_trade_fraction must be in (0, 1]")
        # LIVE mode is a loud, deliberate switch — never the silent default.
        if self.trading_mode is TradingMode.LIVE and not any(
            self.segment_enabled.values()
        ):
            raise ValueError("live mode with no segment enabled is meaningless")

    def is_segment_enabled(self, segment: TradableSegment) -> bool:
        return self.segment_enabled.get(segment.value, False)

    def is_strategy_enabled(self, strategy: SelectableStrategy) -> bool:
        return self.strategy_enabled.get(strategy.value, False)

    def to_json_dict(self) -> dict:
        payload = asdict(self)
        payload["trading_mode"] = self.trading_mode.value
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict) -> "TradingControlConfig":
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in payload.items() if k in known}
        if "trading_mode" in filtered:
            filtered["trading_mode"] = TradingMode(filtered["trading_mode"])
        config = cls(**filtered)
        config.validate()
        return config


def load_trading_control_config(
    config_path: Path = DEFAULT_TRADING_CONTROL_CONFIG_PATH,
) -> TradingControlConfig:
    if not config_path.exists():
        return TradingControlConfig()  # defaults on first run
    return TradingControlConfig.from_json_dict(json.loads(config_path.read_text()))


def save_trading_control_config(
    config: TradingControlConfig,
    config_path: Path = DEFAULT_TRADING_CONTROL_CONFIG_PATH,
) -> None:
    config.validate()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config.to_json_dict(), indent=2))
