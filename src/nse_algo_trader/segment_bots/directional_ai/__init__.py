"""BULL/BEAR directional AI — two independent directional features per segment bot (crypto §03b).

Per bot: a BULL model (calibrated P(up) → CALL/BUY) and a BEAR model (calibrated P(down) → PUT/SELL-short),
each trained on the FULL un-direction-filtered sample with counterfactual triple-barrier labels, combined by
an arbiter into a LONG/SHORT/FLAT verdict that DECIDES the bot's side (the vol/flow logic then sizes +
structures it). Spec: docs/research/bull_bear_directional_ai_spec_2026-08-03.md.
"""

from nse_algo_trader.segment_bots.directional_ai.bull_bear_directional_engine import (
    BullBearDirectionalEngine,
    BullBearTrainingReport,
    DirectionalModelStore,
)
from nse_algo_trader.segment_bots.directional_ai.directional_arbiter import (
    DirectionalArbiter,
    DirectionalVerdict,
)
from nse_algo_trader.segment_bots.directional_ai.directional_feature_engine import (
    DIRECTIONAL_FEATURE_NAMES,
    DirectionalSample,
    build_directional_training_samples,
    directional_features_now,
)

__all__ = [
    "DIRECTIONAL_FEATURE_NAMES",
    "BullBearDirectionalEngine",
    "BullBearTrainingReport",
    "DirectionalArbiter",
    "DirectionalModelStore",
    "DirectionalSample",
    "DirectionalVerdict",
    "build_directional_training_samples",
    "directional_features_now",
]
