"""Generates monitoring alerts from observable engine state (Layer 9).

Surfaces what needs attention at a glance: real-capital (live) mode, a
position left open (no-overnight breach), a miscalibrated confidence
model, an expired Kite token, or missing market data. The dashboard
renders CRITICAL alerts prominently. Pure over its inputs, so it is
testable against real state.
"""

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.dashboard.trading_control_config import (
    TradingControlConfig,
    TradingMode,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import (
    PredictionLabeledTable,
    PredictionTableScoreboard,
)


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MonitoringAlert:
    level: AlertLevel
    category: str
    message: str


def generate_dashboard_alerts(
    control_config: TradingControlConfig,
    paper_ledger: PaperTradingLedger,
    prediction_scoreboard: PredictionTableScoreboard,
    kite_access_token_valid: bool,
    stored_bar_count: int,
) -> list[MonitoringAlert]:
    alerts: list[MonitoringAlert] = []

    if control_config.trading_mode is TradingMode.LIVE:
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "mode",
                "LIVE mode is selected — real capital would be at risk. Live "
                "orders still require a funded account and an exchange Algo-ID.",
            )
        )

    if not paper_ledger.is_flat():
        alerts.append(
            MonitoringAlert(
                AlertLevel.CRITICAL, "position",
                "A position is open — the intraday-only rule requires flat by "
                "close. Check square-off.",
            )
        )

    win = prediction_scoreboard.score_for_table(PredictionLabeledTable.CONFIDENT_WIN)
    loss = prediction_scoreboard.score_for_table(PredictionLabeledTable.CONFIDENT_LOSS)
    if win is not None and loss is not None and win.actual_win_rate <= loss.actual_win_rate:
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "calibration",
                "CONFIDENT-WIN is not beating CONFIDENT-LOSS — the confidence "
                "model may be miscalibrated; review before trusting signals.",
            )
        )

    if not kite_access_token_valid:
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "auth",
                "Kite access token is expired or missing — market data and "
                "trading will fail until the daily login refresh runs.",
            )
        )

    if stored_bar_count == 0:
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "data",
                "No stored market bars found — the ingestion job may not have "
                "run; the paper lab has nothing to replay.",
            )
        )

    if not alerts:
        alerts.append(
            MonitoringAlert(
                AlertLevel.INFO, "status",
                "All systems nominal — paper sandbox healthy, positions flat.",
            )
        )
    return alerts
