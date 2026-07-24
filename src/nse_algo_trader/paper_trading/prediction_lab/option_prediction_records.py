"""§9 prediction records for the OPTION paths, so option trades are first-class
falsifiable experiments (not just display labels) — per Rule I, options are not
scoped out of the lab. Mirrors `adx_confidence_prediction` (ORB/cash):

- **Directional long option** (opened on a TRENDING underlying): wins by trend
  continuation — confidence RISES with ADX (same logistic as ORB).
- **Credit spread** (opened on a RANGE-BOUND underlying): wins by premium decay
  in chop — confidence RISES as ADX FALLS (the inverse), because the thesis is
  "no trend to run the short strike over".

Both feed the same `PredictionTableScoreboard` grading + the Layer-10
experience memory, so calibration/reflection cover options too.
"""

from datetime import date

from nse_algo_trader.paper_trading.prediction_lab.adx_confidence_prediction import (
    _ADX_PROBABILITY_CENTER,
    _CONFIDENT_LOSS_PROBABILITY,
    _CONFIDENT_WIN_PROBABILITY,
    _win_probability_from_adx,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    NamedPredictionReason,
    PredictedTradeOutcome,
    PredictionLabeledTable,
    TradePredictionRecord,
)
from nse_algo_trader.strategy_engine import SignalDirection


def _table_outcome_exit(win_probability: float):
    if win_probability >= _CONFIDENT_WIN_PROBABILITY:
        return PredictionLabeledTable.CONFIDENT_WIN, PredictedTradeOutcome.WIN, "target"
    if win_probability <= _CONFIDENT_LOSS_PROBABILITY:
        return PredictionLabeledTable.CONFIDENT_LOSS, PredictedTradeOutcome.LOSS, "stop"
    is_win = win_probability >= 0.5
    return (
        PredictionLabeledTable.UNCERTAIN,
        PredictedTradeOutcome.WIN if is_win else PredictedTradeOutcome.LOSS,
        "target" if is_win else "stop",
    )


def build_directional_option_prediction_record(
    option_instrument,
    breakout_direction_value: str,
    adx_value: float,
    session_date: date,
    target_reward_multiple: float,
) -> TradePredictionRecord:
    win_probability = _win_probability_from_adx(adx_value)
    table, outcome, exit_cause = _table_outcome_exit(win_probability)
    return TradePredictionRecord(
        session_date=session_date,
        instrument_token=option_instrument.instrument_token,
        strategy_tag="directional_option_orb_v1",
        direction=(
            SignalDirection.LONG
            if breakout_direction_value == "long"
            else SignalDirection.SHORT
        ),
        predicted_outcome=outcome,
        win_probability=win_probability,
        assigned_table=table,
        expected_reward_multiple=(
            target_reward_multiple if outcome is PredictedTradeOutcome.WIN else -1.0
        ),
        reasons=(
            NamedPredictionReason("adx", adx_value, adx_value - _ADX_PROBABILITY_CENTER),
        ),
        mechanism_name="long ATM option riding the spot's ORB breakout (ADX-trending)",
        predicted_exit_cause=exit_cause,
        kill_criteria="exit if the spot re-enters its opening range for 2 bars",
        calendar_context="normal",
    )


def build_credit_spread_prediction_record(
    short_leg_instrument,
    bias_value: str,
    adx_value: float,
    session_date: date,
) -> TradePredictionRecord:
    # Range thesis: confidence is HIGH when ADX is LOW (the inverse of trend).
    win_probability = 1.0 - _win_probability_from_adx(adx_value)
    table, outcome, exit_cause = _table_outcome_exit(win_probability)
    return TradePredictionRecord(
        session_date=session_date,
        instrument_token=short_leg_instrument.instrument_token,
        strategy_tag="credit_spread_v1",
        direction=(
            SignalDirection.LONG if bias_value == "bull_put" else SignalDirection.SHORT
        ),
        predicted_outcome=outcome,
        win_probability=win_probability,
        assigned_table=table,
        expected_reward_multiple=(
            1.0 if outcome is PredictedTradeOutcome.WIN else -1.0
        ),
        reasons=(
            NamedPredictionReason("adx", adx_value, _ADX_PROBABILITY_CENTER - adx_value),
        ),
        mechanism_name="defined-risk credit spread capturing premium in a range-bound regime",
        predicted_exit_cause=exit_cause,
        kill_criteria="exit if the short strike is breached (regime turned trending)",
        calendar_context="normal",
    )
