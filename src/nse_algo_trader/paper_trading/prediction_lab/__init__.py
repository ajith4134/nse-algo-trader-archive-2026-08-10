"""The prediction-labeled trade-tables lab (PLAN §9) — Layer 7's core AI.

Every paper trade declares an immutable prediction (WIN / deliberate-LOSS
/ UNCERTAIN) before it opens; reality grades it; a scoreboard measures
calibration. This is where the EPISTEMICS trunk first ignites.
"""

from nse_algo_trader.paper_trading.prediction_lab.adx_confidence_prediction import (
    build_orb_prediction_record,
)
from nse_algo_trader.paper_trading.prediction_lab.opening_range_breakout_prediction_lab import (
    LabSessionResult,
    run_orb_prediction_lab_over_replay,
    run_orb_prediction_lab_session,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_outcome_grading import (
    GradedPrediction,
    grade_prediction,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    NamedPredictionReason,
    PredictedTradeOutcome,
    PredictionLabeledTable,
    TradePredictionRecord,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
    TableScore,
)

__all__ = [
    "GradedPrediction",
    "LabSessionResult",
    "NamedPredictionReason",
    "PredictedTradeOutcome",
    "PredictionLabeledTable",
    "PredictionTableScoreboard",
    "TableScore",
    "TradePredictionRecord",
    "build_orb_prediction_record",
    "grade_prediction",
    "run_orb_prediction_lab_over_replay",
    "run_orb_prediction_lab_session",
]
