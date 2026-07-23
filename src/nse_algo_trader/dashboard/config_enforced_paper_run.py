"""Enforces the dashboard's TradingControlConfig in the paper loop.

Turns the dashboard knobs into real engine behavior: the account capital
and risk fraction feed position sizing, disabled segments/strategies stop
trading, and the min/max capital-per-trade limits gate order size. This is
what makes toggling a segment off on the phone actually stop those trades.
"""

from nse_algo_trader.broker_oms import SimulatedBrokerClient
from nse_algo_trader.dashboard.trading_control_config import (
    SelectableStrategy,
    TradableSegment,
    TradingControlConfig,
)
from nse_algo_trader.market_data import PriceBar
from nse_algo_trader.paper_trading import (
    PaperTradingLedger,
    make_slippage_fill_adjuster,
)
from nse_algo_trader.paper_trading.prediction_lab import (
    PredictionTableScoreboard,
    run_orb_prediction_lab_over_replay,
)
from nse_algo_trader.risk_management import RiskBudgetConfig
from nse_algo_trader.universe_registry import Instrument

# Cash intraday uses ~25% peak margin; used to translate a max-capital-per-
# trade (notional) cap into the risk layer's margin-fraction-of-capital cap.
_CASH_INTRADAY_MARGIN_FRACTION_OF_NOTIONAL = 0.25


def map_control_config_to_risk_budget(
    config: TradingControlConfig,
) -> RiskBudgetConfig:
    """Account capital, per-trade risk %, and the max-capital-per-trade cap
    become the risk layer's sizing budget. Max notional per position is
    capped at `max_capital_per_trade` by expressing it as a
    margin-fraction-of-capital limit."""
    max_margin_fraction = min(
        1.0,
        (config.max_capital_per_trade * _CASH_INTRADAY_MARGIN_FRACTION_OF_NOTIONAL)
        / config.account_virtual_capital,
    )
    return RiskBudgetConfig(
        account_capital=config.account_virtual_capital,
        max_risk_per_trade_fraction=config.max_risk_per_trade_fraction,
        max_margin_per_position_fraction=max_margin_fraction,
    )


def is_orb_cash_trading_enabled(config: TradingControlConfig) -> bool:
    return config.is_segment_enabled(
        TradableSegment.NSE_CASH_EQUITY
    ) and config.is_strategy_enabled(SelectableStrategy.OPENING_RANGE_BREAKOUT)


def clamp_quantity_to_capital_limits(
    entry_price: float, sized_quantity: int, config: TradingControlConfig
) -> int:
    """Apply the min/max capital-per-trade limits to a sized cash quantity.
    Clamps down to the max notional; returns 0 (skip the trade) if even the
    clamped notional is below the min-capital-per-trade floor."""
    if entry_price <= 0 or sized_quantity <= 0:
        return 0
    max_affordable_quantity = int(config.max_capital_per_trade / entry_price)
    clamped_quantity = min(sized_quantity, max_affordable_quantity)
    deployed_notional = entry_price * clamped_quantity
    if deployed_notional < config.min_capital_per_trade:
        return 0
    return clamped_quantity


def run_config_enforced_orb_paper_lab(
    control_config: TradingControlConfig,
    chronological_bars: list[PriceBar],
    instrument: Instrument,
    ledger: PaperTradingLedger,
    scoreboard: PredictionTableScoreboard,
) -> None:
    """Runs the ORB paper lab only if the config enables cash ORB trading,
    using the config-derived risk budget. When disabled, trades nothing —
    the ledger and scoreboard stay empty (the honest 'segment/strategy off'
    outcome)."""
    if not is_orb_cash_trading_enabled(control_config):
        return
    run_orb_prediction_lab_over_replay(
        chronological_bars,
        instrument,
        SimulatedBrokerClient(fill_price_adjuster=make_slippage_fill_adjuster()),
        map_control_config_to_risk_budget(control_config),
        ledger,
        scoreboard,
    )
