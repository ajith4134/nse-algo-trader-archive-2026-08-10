"""Layer 9 — Dashboard, Monitoring & Alerting.

A read-model that OBSERVES the engine (never trades) plus an editable
control config the engine reads. The dashboard's two views — operator
(positions/P&L/risk/session) and project/AI (layer roadmap, §9 lab
calibration, the 16-trunk/~200-branch concept tree) — are generated from
`build_dashboard_snapshot`.
"""

from nse_algo_trader.dashboard.config_enforced_paper_run import (
    clamp_quantity_to_capital_limits,
    is_orb_cash_trading_enabled,
    map_control_config_to_risk_budget,
    run_config_enforced_orb_paper_lab,
)
from nse_algo_trader.dashboard.dashboard_read_model import (
    DashboardSnapshot,
    build_dashboard_snapshot,
)
from nse_algo_trader.dashboard.render_dashboard_html import render_dashboard_html
from nse_algo_trader.dashboard.trading_control_config import (
    SelectableStrategy,
    TradableSegment,
    TradingControlConfig,
    TradingMode,
    load_trading_control_config,
    save_trading_control_config,
)

__all__ = [
    "DashboardSnapshot",
    "SelectableStrategy",
    "TradableSegment",
    "TradingControlConfig",
    "TradingMode",
    "build_dashboard_snapshot",
    "clamp_quantity_to_capital_limits",
    "is_orb_cash_trading_enabled",
    "map_control_config_to_risk_budget",
    "render_dashboard_html",
    "run_config_enforced_orb_paper_lab",
    "load_trading_control_config",
    "save_trading_control_config",
]
