"""v1 confidence model: turn a breakout signal + ADX into a PredictionRecord.

The deliberate-loss table needs a real failure mechanism, not a coin flip
(PLAN §9). ADX supplies it: an Opening-Range Breakout in a TRENDING
regime (high ADX) is predicted to WIN via trend-continuation; a breakout
in a RANGE-BOUND regime (low ADX) is predicted to LOSE via the classic
false-breakout-into-chop mechanism — so the CONFIDENT-LOSS table is
opened on purpose, targeting that named mechanism. Mid-ADX breakouts land
in UNCERTAIN. Win-probability is a logistic of ADX around the regime
threshold; it is deliberately un-calibrated at first — the scoreboard
measures how wrong it is (Brier) so later layers can recalibrate.
"""

import math
from datetime import date

from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    NamedPredictionReason,
    PredictedTradeOutcome,
    PredictionLabeledTable,
    TradePredictionRecord,
)
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutSignal,
    SignalDirection,
)

# ADX logistic: centered between the 20/25 regime bands, moderate slope.
_ADX_PROBABILITY_CENTER = 22.5
_ADX_PROBABILITY_SLOPE = 0.18
_CONFIDENT_WIN_PROBABILITY = 0.60
_CONFIDENT_LOSS_PROBABILITY = 0.40


def _win_probability_from_adx(adx_value: float) -> float:
    return 1.0 / (
        1.0 + math.exp(-_ADX_PROBABILITY_SLOPE * (adx_value - _ADX_PROBABILITY_CENTER))
    )


def build_orb_prediction_record(
    signal: OpeningRangeBreakoutSignal,
    adx_value: float,
    session_date: date,
    target_reward_multiple: float,
    calendar_context: str = "normal",
) -> TradePredictionRecord:
    win_probability = _win_probability_from_adx(adx_value)

    if win_probability >= _CONFIDENT_WIN_PROBABILITY:
        assigned_table = PredictionLabeledTable.CONFIDENT_WIN
        predicted_outcome = PredictedTradeOutcome.WIN
        mechanism_name = "post-breakout trend continuation (ADX trending)"
        predicted_exit_cause = "target"
        expected_reward_multiple = target_reward_multiple
    elif win_probability <= _CONFIDENT_LOSS_PROBABILITY:
        assigned_table = PredictionLabeledTable.CONFIDENT_LOSS
        predicted_outcome = PredictedTradeOutcome.LOSS
        mechanism_name = "false breakout into range-bound chop (ADX below trend band)"
        predicted_exit_cause = "stop"
        expected_reward_multiple = -1.0
    else:
        assigned_table = PredictionLabeledTable.UNCERTAIN
        predicted_outcome = (
            PredictedTradeOutcome.WIN
            if win_probability >= 0.5
            else PredictedTradeOutcome.LOSS
        )
        mechanism_name = "indeterminate regime — outcome informative either way"
        predicted_exit_cause = "target" if win_probability >= 0.5 else "stop"
        expected_reward_multiple = (
            target_reward_multiple if win_probability >= 0.5 else -1.0
        )

    reasons = (
        NamedPredictionReason(
            "adx", adx_value, adx_value - _ADX_PROBABILITY_CENTER
        ),
        NamedPredictionReason(
            "breakout_direction",
            1.0 if signal.direction is SignalDirection.LONG else -1.0,
            0.0,
        ),
    )
    return TradePredictionRecord(
        session_date=session_date,
        instrument_token=signal.instrument.instrument_token,
        strategy_tag=signal.strategy_tag,
        direction=signal.direction,
        predicted_outcome=predicted_outcome,
        win_probability=win_probability,
        assigned_table=assigned_table,
        expected_reward_multiple=expected_reward_multiple,
        reasons=reasons,
        mechanism_name=mechanism_name,
        predicted_exit_cause=predicted_exit_cause,
        kill_criteria="exit if price re-enters the opening range for 2 consecutive bars",
        calendar_context=calendar_context,
    )
