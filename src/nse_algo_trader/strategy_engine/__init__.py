"""Layer 4 — Strategy / Signal Engine (v1: ORB + credit spreads + ADX gate).

Strategies consume Layer 2 bars and Layer 3 indicators and emit fully
specified signals; nothing in this package places orders.
"""

from nse_algo_trader.strategy_engine.credit_spread_leg_selector import (
    CreditSpreadSelectionConfig,
    select_credit_spread_legs,
)
from nse_algo_trader.strategy_engine.option_moneyness_classifier import (
    OptionMoneyness,
    classify_option_moneyness,
    infer_strike_ladder_step,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
    detect_opening_range_breakout,
)
from nse_algo_trader.strategy_engine.implied_volatility_rank import (
    ImpliedVolatilityRanking,
    rank_implied_volatility,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import (
    AdxRegimeGateConfig,
    MarketRegime,
    V1SessionStrategyChoice,
    choose_v1_session_strategy,
    classify_adx_market_regime,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    CreditSpreadBias,
    CreditSpreadSignal,
    OpeningRangeBreakoutSignal,
    OptionLegAction,
    OptionLegIntent,
    SignalDirection,
)

__all__ = [
    "ImpliedVolatilityRanking",
    "rank_implied_volatility",
    "AdxRegimeGateConfig",
    "CreditSpreadBias",
    "CreditSpreadSelectionConfig",
    "CreditSpreadSignal",
    "MarketRegime",
    "OpeningRangeBreakoutConfig",
    "OpeningRangeBreakoutSignal",
    "OptionLegAction",
    "OptionMoneyness",
    "OptionLegIntent",
    "SignalDirection",
    "V1SessionStrategyChoice",
    "choose_v1_session_strategy",
    "classify_adx_market_regime",
    "classify_option_moneyness",
    "detect_opening_range_breakout",
    "infer_strike_ladder_step",
    "select_credit_spread_legs",
]
