"""Grades a closed paper trade against its PredictionRecord.

A prediction is CORRECT when reality matched what was predicted — which,
crucially, means a CONFIDENT-LOSS trade's prediction WINS when the trade
actually LOSES. Calibration is scored separately via the Brier
contribution on the win-probability, so over/under-confidence is punished
even when the WIN/LOSS label happens to be right.
"""

from dataclasses import dataclass

from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictedTradeOutcome,
    TradePredictionRecord,
)


@dataclass(frozen=True)
class GradedPrediction:
    record: TradePredictionRecord
    actual_outcome: PredictedTradeOutcome
    realized_pnl: float
    prediction_was_correct: bool  # did reality match the predicted label?
    brier_contribution: float  # (win_prob - actual_win_indicator)^2


def grade_prediction(
    record: TradePredictionRecord, realized_pnl: float
) -> GradedPrediction:
    trade_actually_won = realized_pnl > 0.0
    actual_outcome = (
        PredictedTradeOutcome.WIN if trade_actually_won else PredictedTradeOutcome.LOSS
    )
    actual_win_indicator = 1.0 if trade_actually_won else 0.0
    return GradedPrediction(
        record=record,
        actual_outcome=actual_outcome,
        realized_pnl=realized_pnl,
        prediction_was_correct=(record.predicted_outcome is actual_outcome),
        brier_contribution=(record.win_probability - actual_win_indicator) ** 2,
    )
