"""The pre-trade risk gate — every Layer 4 signal passes here or dies here.

Returns an explicit decision with machine-readable rejection reasons so
the dashboard (Layer 9) and memory layer (Layer 10) can learn from what
was blocked and why. v1 policy, applied to ANY underlying in the
universe (nothing symbol-specific):

- No undefined-risk combinations, ever (net short calls, unpaired
  short legs of either right).
- No fresh F&O positions on an underlying in the MWPL ban list.
- Fixed-fractional sizing; a trade the risk budget can't afford at
  least 1 share/lot of is rejected, not rounded up.
"""

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.risk_management.margin_requirement_estimator import (
    MarginEstimateConfig,
    estimate_defined_risk_spread_margin,
    estimate_intraday_cash_margin,
)
from nse_algo_trader.risk_management.option_combination_risk_profile import (
    PositionRiskCategory,
    assess_option_combination_risk,
)
from nse_algo_trader.risk_management.risk_based_position_sizer import (
    RiskBudgetConfig,
    size_cash_position_by_stop_distance,
    size_defined_risk_spread_lots,
)
from nse_algo_trader.strategy_engine import CreditSpreadSignal, OpeningRangeBreakoutSignal


class RiskRejectionReason(str, Enum):
    UNDEFINED_RISK_COMBINATION = "undefined_risk_combination"
    UNDERLYING_IN_FO_BAN_LIST = "underlying_in_fo_ban_list"
    RISK_BUDGET_TOO_SMALL_FOR_ONE_UNIT = "risk_budget_too_small_for_one_unit"
    STOP_DISTANCE_NOT_POSITIVE = "stop_distance_not_positive"


@dataclass(frozen=True)
class RiskGateDecision:
    approved: bool
    rejection_reasons: tuple[RiskRejectionReason, ...]
    approved_quantity: int  # shares (cash) or lots (options); 0 when rejected
    estimated_margin: float
    estimated_worst_case_loss: float


_REJECTED = RiskGateDecision(
    approved=False, rejection_reasons=(), approved_quantity=0,
    estimated_margin=0.0, estimated_worst_case_loss=0.0,
)


def evaluate_opening_range_breakout_signal(
    signal: OpeningRangeBreakoutSignal,
    risk_budget: RiskBudgetConfig,
    margin_config: MarginEstimateConfig = MarginEstimateConfig(),
) -> RiskGateDecision:
    rejection_reasons: list[RiskRejectionReason] = []
    stop_distance = abs(signal.breakout_close_price - signal.stop_loss_price)
    if stop_distance <= 0.0:
        rejection_reasons.append(RiskRejectionReason.STOP_DISTANCE_NOT_POSITIVE)
        return RiskGateDecision(
            approved=False, rejection_reasons=tuple(rejection_reasons),
            approved_quantity=0, estimated_margin=0.0, estimated_worst_case_loss=0.0,
        )
    share_quantity = size_cash_position_by_stop_distance(
        signal.breakout_close_price, signal.stop_loss_price, risk_budget,
        margin_config.intraday_cash_margin_fraction,
    )
    if share_quantity < 1:
        rejection_reasons.append(RiskRejectionReason.RISK_BUDGET_TOO_SMALL_FOR_ONE_UNIT)
    if rejection_reasons:
        return RiskGateDecision(
            approved=False, rejection_reasons=tuple(rejection_reasons),
            approved_quantity=0, estimated_margin=0.0, estimated_worst_case_loss=0.0,
        )
    return RiskGateDecision(
        approved=True, rejection_reasons=(),
        approved_quantity=share_quantity,
        estimated_margin=estimate_intraday_cash_margin(
            signal.breakout_close_price, share_quantity, margin_config
        ),
        estimated_worst_case_loss=stop_distance * share_quantity,
    )


def evaluate_credit_spread_signal(
    signal: CreditSpreadSignal,
    banned_underlying_symbols: frozenset[str],
    risk_budget: RiskBudgetConfig,
    margin_config: MarginEstimateConfig = MarginEstimateConfig(),
) -> RiskGateDecision:
    rejection_reasons: list[RiskRejectionReason] = []

    if signal.underlying_symbol in banned_underlying_symbols:
        rejection_reasons.append(RiskRejectionReason.UNDERLYING_IN_FO_BAN_LIST)

    risk_profile = assess_option_combination_risk([signal.short_leg, signal.hedge_leg])
    if risk_profile.category is not PositionRiskCategory.DEFINED_RISK:
        rejection_reasons.append(RiskRejectionReason.UNDEFINED_RISK_COMBINATION)

    if rejection_reasons:
        return RiskGateDecision(
            approved=False, rejection_reasons=tuple(rejection_reasons),
            approved_quantity=0, estimated_margin=0.0, estimated_worst_case_loss=0.0,
        )

    signal_lots = signal.short_leg.lots
    worst_case_loss_per_lot = risk_profile.worst_case_structural_loss / signal_lots
    margin_per_lot = estimate_defined_risk_spread_margin(
        worst_case_loss_per_lot, margin_config
    )
    affordable_lots = size_defined_risk_spread_lots(
        worst_case_loss_per_lot, margin_per_lot, risk_budget
    )
    if affordable_lots < 1:
        return RiskGateDecision(
            approved=False,
            rejection_reasons=(RiskRejectionReason.RISK_BUDGET_TOO_SMALL_FOR_ONE_UNIT,),
            approved_quantity=0, estimated_margin=0.0, estimated_worst_case_loss=0.0,
        )
    # The signal's own `lots` is the leg selector's STRUCTURAL template (default 1) — it says which
    # strikes to trade, not how much risk to take. Capping affordability by it made every option
    # order exactly 1 lot, which the fractional size-down levers then floored to 0 (B7). The risk
    # budget is the only thing that may size this position.
    approved_lots = affordable_lots
    return RiskGateDecision(
        approved=True, rejection_reasons=(),
        approved_quantity=approved_lots,
        estimated_margin=margin_per_lot * approved_lots,
        estimated_worst_case_loss=worst_case_loss_per_lot * approved_lots,
    )
