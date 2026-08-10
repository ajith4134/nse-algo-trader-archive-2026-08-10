"""CASH-INTRADAY segment bot — the third segment-specialist bot (cross-sectional equity).

Owns the full NSE cash universe (~2000 stocks), intraday, cross-sectional: it ranks the whole universe each
cycle on an engineered factor stack, trains a LightGBM ranker to predict forward relative return, and
constructs a cost-aware long/short book (top vs bottom quantile). Distinct shape from the option bots —
no option structures; it proposes cash-equity longs and shorts. SOTA analog: Microsoft Qlib (Alpha158 +
LightGBM + cost-aware backtest).

Spec: docs/research/three_segment_bots_spec_2026-08-03.md (§3 CASH row) + REDESIGN_v1 (L4 cash edge).
"""

from nse_algo_trader.segment_bots.cash_intraday_bot.cash_intraday_bot import CashIntradayBot
from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_alpha_model import (
    CrossSectionalAlphaModel,
    CrossSectionalAlphaStore,
    CrossSectionalTrainingReport,
)
from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_features import (
    CROSS_SECTIONAL_FEATURE_NAMES,
    build_cross_sectional_features,
)

__all__ = [
    "CROSS_SECTIONAL_FEATURE_NAMES",
    "CashIntradayBot",
    "CrossSectionalAlphaModel",
    "CrossSectionalAlphaStore",
    "CrossSectionalTrainingReport",
    "build_cross_sectional_features",
]
