"""Act on the memory's calibration diagnosis: recalibrate a prediction's
win-probability (and re-derive its table) from a memory-learned per-mechanism
bias offset. Layer 10 → §9 feedback (research/51).

The base ADX model is deliberately un-calibrated; once the experience memory has
measured a mechanism's calibration gap, an additive bias offset
(actual − predicted win-rate) shifts future predictions onto their real base
rate while preserving the mechanism's relative discrimination (resolution). A
mechanism with no discriminating edge is not recalibrated — it is vetoed
elsewhere (learn_mechanism_recalibrations returns that set separately).

`assign_table_and_outcome` is the single source of truth for the
confident-win/loss/uncertain band logic, shared with the base ADX builder so the
two can never diverge.
"""

from dataclasses import replace

from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictedTradeOutcome,
    PredictionLabeledTable,
    TradePredictionRecord,
)

CONFIDENT_WIN_PROBABILITY = 0.60
CONFIDENT_LOSS_PROBABILITY = 0.40
_MIN_PROBABILITY = 0.01
_MAX_PROBABILITY = 0.99


def assign_table_and_outcome(
    win_probability: float, target_reward_multiple: float
) -> tuple[PredictionLabeledTable, PredictedTradeOutcome, str, float]:
    """The confident-win / confident-loss / uncertain band logic → (table,
    predicted_outcome, predicted_exit_cause, expected_reward_multiple).
    Shared by the base ADX builder and by recalibration so a recalibrated
    probability lands in the same bands the model itself uses."""
    if win_probability >= CONFIDENT_WIN_PROBABILITY:
        return (
            PredictionLabeledTable.CONFIDENT_WIN,
            PredictedTradeOutcome.WIN,
            "target",
            target_reward_multiple,
        )
    if win_probability <= CONFIDENT_LOSS_PROBABILITY:
        return (
            PredictionLabeledTable.CONFIDENT_LOSS,
            PredictedTradeOutcome.LOSS,
            "stop",
            -1.0,
        )
    predicted_win = win_probability >= 0.5
    return (
        PredictionLabeledTable.UNCERTAIN,
        PredictedTradeOutcome.WIN if predicted_win else PredictedTradeOutcome.LOSS,
        "target" if predicted_win else "stop",
        target_reward_multiple if predicted_win else -1.0,
    )


def recalibrated_win_probability(raw_win_probability: float, offset: float) -> float:
    """Additive bias correction, clamped away from 0/1."""
    return min(
        _MAX_PROBABILITY, max(_MIN_PROBABILITY, raw_win_probability + offset)
    )


def recalibrate_prediction_record(
    record: TradePredictionRecord, offset_by_mechanism: dict[str, float]
) -> TradePredictionRecord:
    """Return the record with its win-probability bias-corrected by its
    mechanism's learned offset and its table/outcome re-derived. Identity when
    the mechanism has no offset (cold start) — so this is safe to call on every
    prediction unconditionally."""
    offset = offset_by_mechanism.get(record.mechanism_name)
    if not offset:  # None or 0.0 -> no change
        return record
    new_probability = recalibrated_win_probability(record.win_probability, offset)
    target_reward_multiple = abs(record.expected_reward_multiple) or 1.0
    table, predicted_outcome, exit_cause, expected_reward = assign_table_and_outcome(
        new_probability, target_reward_multiple
    )
    return replace(
        record,
        win_probability=new_probability,
        assigned_table=table,
        predicted_outcome=predicted_outcome,
        predicted_exit_cause=exit_cause,
        expected_reward_multiple=expected_reward,
    )
