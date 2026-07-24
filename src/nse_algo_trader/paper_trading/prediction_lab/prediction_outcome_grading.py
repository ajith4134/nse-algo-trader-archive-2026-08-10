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
from nse_algo_trader.paper_trading.prediction_lab.proper_scoring_rules import (
    logarithmic_score,
    probability_assigned_to_outcome,
    quadratic_score,
)


@dataclass(frozen=True)
class GradedPrediction:
    record: TradePredictionRecord
    actual_outcome: PredictedTradeOutcome
    realized_pnl: float
    prediction_was_correct: bool  # did reality match the predicted label?
    brier_contribution: float  # (win_prob - actual_win_indicator)^2
    # Proper scoring rules on the probability assigned to what actually happened
    # (research/48). log punishes confident-wrong toward ∞ (Brier saturates);
    # quadratic is a bounded reward-form score (+1 best, −1 worst).
    logarithmic_score: float = 0.0
    quadratic_score: float = 0.0


def grade_prediction(
    record: TradePredictionRecord, realized_pnl: float
) -> GradedPrediction:
    trade_actually_won = realized_pnl > 0.0
    actual_outcome = (
        PredictedTradeOutcome.WIN if trade_actually_won else PredictedTradeOutcome.LOSS
    )
    actual_win_indicator = 1.0 if trade_actually_won else 0.0
    probability_of_outcome = probability_assigned_to_outcome(
        record.win_probability, trade_actually_won
    )
    return GradedPrediction(
        record=record,
        actual_outcome=actual_outcome,
        realized_pnl=realized_pnl,
        prediction_was_correct=(record.predicted_outcome is actual_outcome),
        brier_contribution=(record.win_probability - actual_win_indicator) ** 2,
        logarithmic_score=logarithmic_score(probability_of_outcome),
        quadratic_score=quadratic_score(probability_of_outcome),
    )
