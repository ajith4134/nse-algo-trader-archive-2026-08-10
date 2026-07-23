"""Risk-budget position sizing — how much of a signal to actually take.

Classic fixed-fractional sizing: risk at most `max_risk_per_trade`
fraction of capital on any single trade, and never let one position's
margin consume more than `max_margin_per_position` fraction of capital.
Sizes are floored to whole shares/lots; a size of zero means the trade
is unaffordable within the risk budget and must be rejected upstream.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskBudgetConfig:
    account_capital: float
    max_risk_per_trade_fraction: float = 0.01  # 1% risk per trade
    max_margin_per_position_fraction: float = 0.25


def size_cash_position_by_stop_distance(
    entry_price: float,
    stop_loss_price: float,
    config: RiskBudgetConfig,
    margin_fraction_of_notional: float = 0.25,
) -> int:
    """Whole-share quantity for a cash trade with a protective stop."""
    per_share_risk = abs(entry_price - stop_loss_price)
    if per_share_risk <= 0.0:
        return 0
    risk_budget = config.account_capital * config.max_risk_per_trade_fraction
    risk_limited_quantity = int(risk_budget / per_share_risk)
    margin_budget = config.account_capital * config.max_margin_per_position_fraction
    margin_limited_quantity = int(
        margin_budget / (entry_price * margin_fraction_of_notional)
    )
    return max(0, min(risk_limited_quantity, margin_limited_quantity))


def size_defined_risk_spread_lots(
    worst_case_structural_loss_per_lot: float,
    estimated_margin_per_lot: float,
    config: RiskBudgetConfig,
) -> int:
    """Whole-lot count for a defined-risk spread (max loss IS the risk)."""
    if worst_case_structural_loss_per_lot <= 0.0 or estimated_margin_per_lot <= 0.0:
        return 0
    risk_budget = config.account_capital * config.max_risk_per_trade_fraction
    risk_limited_lots = int(risk_budget / worst_case_structural_loss_per_lot)
    margin_budget = config.account_capital * config.max_margin_per_position_fraction
    margin_limited_lots = int(margin_budget / estimated_margin_per_lot)
    return max(0, min(risk_limited_lots, margin_limited_lots))
