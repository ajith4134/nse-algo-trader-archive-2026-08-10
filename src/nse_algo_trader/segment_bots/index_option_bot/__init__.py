"""INDEX-OPTION segment bot — the first of the three segment-specialist bots.

Owns the full NSE index-option universe (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50; weeklies +
0DTE). Built engine-by-engine (spec: docs/research/index_option_bot_engine_spec_2026-08-03.md):
volatility-regime engine → IV-surface engine → structure selector → trained head → assembled bot.
"""

from nse_algo_trader.segment_bots.index_option_bot.deterministic_index_option_policy import (
    DeterministicIndexOptionPolicy,
    DeterministicPolicyConfig,
)
from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import (
    BotTrackRecordStore,
    ClosedTrade,
    IndexOptionBot,
    IndexOptionDataAdapter,
)
from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolRankStore,
    ImpliedVolSurfaceEngine,
    ImpliedVolSurfaceState,
    SviSmileFit,
)
from nse_algo_trader.segment_bots.index_option_bot.structure_selector import (
    IndexOptionStructureSelector,
    StructureDecision,
)
from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeEngine,
    VolatilityRegimeState,
    VolatilityRegimeStore,
)
from nse_algo_trader.segment_bots.index_option_bot.win_probability_head import (
    IndexOptionWinProbabilityHead,
    LabelledTrial,
    TrainingReport,
    WinProbabilityHeadStore,
    engineer_features,
)

__all__ = [
    "BotTrackRecordStore",
    "ClosedTrade",
    "IndexOptionBot",
    "IndexOptionDataAdapter",
    "DeterministicIndexOptionPolicy",
    "DeterministicPolicyConfig",
    "IndexOptionWinProbabilityHead",
    "LabelledTrial",
    "TrainingReport",
    "WinProbabilityHeadStore",
    "engineer_features",
    "IndexOptionStructureSelector",
    "StructureDecision",
    "ImpliedVolRankStore",
    "ImpliedVolSurfaceEngine",
    "ImpliedVolSurfaceState",
    "SviSmileFit",
    "VolatilityRegimeEngine",
    "VolatilityRegimeState",
    "VolatilityRegimeStore",
]
