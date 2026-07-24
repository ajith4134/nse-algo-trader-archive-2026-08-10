"""Generates monitoring alerts from observable engine state (Layer 9).

Surfaces what needs attention at a glance: real-capital (live) mode, a
position left open (no-overnight breach), a miscalibrated confidence
model, an expired Kite token, or missing market data. The dashboard
renders CRITICAL alerts prominently. Pure over its inputs, so it is
testable against real state.
"""

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum

from nse_algo_trader.dashboard.trading_control_config import (
    TradingControlConfig,
    TradingMode,
)

# From this IST time, a still-open position is a genuine no-overnight risk
# (square-off is scheduled at 15:15); before it, open positions are the
# normal intraday state and must NOT raise a CRITICAL "overnight" alarm.
_SQUARE_OFF_DEADLINE_IST = time(15, 15)


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
    paper_trading_summary,
    prediction_table_summaries: list,
    kite_access_token_valid: bool,
    stored_bar_count: int,
    generated_at: datetime | None = None,
    open_position_count: int = 0,
    assumption_tripwires: list | None = None,
    information_diet: dict | None = None,
) -> list[MonitoringAlert]:
    alerts: list[MonitoringAlert] = []

    # Information-diet health (§10, research/52): the loud failure is the whole
    # Layer-10 learning apparatus not influencing any trades — surface it.
    if information_diet and information_diet.get("health_status") == "warning":
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "information-diet",
                f"Information diet — {information_diet.get('note', '')}",
            )
        )

    # Layer-10 assumption tripwires (slice 2): a mechanism whose thesis the
    # memory has significantly refuted — the bot flagging its own bad edge.
    # Verdicts arrive as dicts (server) or dataclasses (tests) — handle both.
    def _field(verdict, name):
        return verdict[name] if isinstance(verdict, dict) else getattr(verdict, name)

    def _is_violated(verdict) -> bool:
        status = _field(verdict, "status")
        return str(getattr(status, "value", status)) == "violated"

    for verdict in [v for v in (assumption_tripwires or []) if _is_violated(v)][:3]:
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "assumption",
                f"Tripwire — {_field(verdict, 'assumption_name')} on "
                f"{_field(verdict, 'scope')}: {_field(verdict, 'detail')}",
            )
        )

    if control_config.trading_mode is TradingMode.LIVE:
        alerts.append(
            MonitoringAlert(
                AlertLevel.WARNING, "mode",
                "LIVE mode is selected — real capital would be at risk. Live "
                "orders still require a funded account and an exchange Algo-ID.",
            )
        )

    positions_open = open_position_count > 0 or not paper_trading_summary.is_flat
    past_square_off = (
        generated_at is not None
        and generated_at.timetz().replace(tzinfo=None) >= _SQUARE_OFF_DEADLINE_IST
    )
    if positions_open and past_square_off:
        alerts.append(
            MonitoringAlert(
                AlertLevel.CRITICAL, "position",
                "A position is still open after 15:15 — the intraday-only rule "
                "requires flat by close. Check square-off immediately.",
            )
        )
    elif positions_open:
        alerts.append(
            MonitoringAlert(
                AlertLevel.INFO, "position",
                f"{open_position_count} paper positions open intraday — normal; "
                "Layer 8 flattens all at 15:15.",
            )
        )

    win = _summary_for(prediction_table_summaries, "confident_win")
    loss = _summary_for(prediction_table_summaries, "confident_loss")
    if (
        win is not None and loss is not None
        and win.actual_win_rate is not None and loss.actual_win_rate is not None
        and win.actual_win_rate <= loss.actual_win_rate
    ):
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

    if not any(a.level is not AlertLevel.INFO for a in alerts):
        alerts.append(
            MonitoringAlert(
                AlertLevel.INFO, "status",
                "All systems nominal — paper sandbox healthy on the live feed.",
            )
        )
    return alerts


def _summary_for(prediction_table_summaries: list, table_name: str):
    for summary in prediction_table_summaries:
        if summary.table == table_name:
            return summary
    return None
