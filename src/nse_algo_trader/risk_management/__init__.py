"""Layer 5 — Risk Management: every signal passes the pre-trade gate or dies.

v1 policy: defined-risk only (undefined-risk combinations rejected),
MWPL ban-list enforcement, conservative over-stated margin estimates,
fixed-fractional sizing. Universe-wide by construction — lot sizes come
from instruments, ban status from NSE report data.
"""

from nse_algo_trader.risk_management.margin_requirement_estimator import (
    MarginEstimateConfig,
    estimate_defined_risk_spread_margin,
    estimate_intraday_cash_margin,
)
from nse_algo_trader.risk_management.option_combination_risk_profile import (
    OptionCombinationRiskProfile,
    PositionRiskCategory,
    assess_option_combination_risk,
)
from nse_algo_trader.risk_management.pre_trade_risk_gate import (
    RiskGateDecision,
    RiskRejectionReason,
    evaluate_credit_spread_signal,
    evaluate_opening_range_breakout_signal,
)
from nse_algo_trader.risk_management.risk_based_position_sizer import (
    RiskBudgetConfig,
    size_cash_position_by_stop_distance,
    size_defined_risk_spread_lots,
)

__all__ = [
    "MarginEstimateConfig",
    "OptionCombinationRiskProfile",
    "PositionRiskCategory",
    "RiskBudgetConfig",
    "RiskGateDecision",
    "RiskRejectionReason",
    "assess_option_combination_risk",
    "estimate_defined_risk_spread_margin",
    "estimate_intraday_cash_margin",
    "evaluate_credit_spread_signal",
    "evaluate_opening_range_breakout_signal",
    "size_cash_position_by_stop_distance",
    "size_defined_risk_spread_lots",
]
