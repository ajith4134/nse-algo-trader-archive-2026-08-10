"""Mechanism recalibration — bias-correct win_probability + re-derive table."""
import pytest
from datetime import date

from nse_algo_trader.paper_trading.prediction_lab.adx_confidence_prediction import (
    build_orb_prediction_record,
)
from nse_algo_trader.paper_trading.prediction_lab.mechanism_recalibration import (
    recalibrate_prediction_record, recalibrated_win_probability,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictionLabeledTable,
)
from nse_algo_trader.strategy_engine import OpeningRangeBreakoutSignal, SignalDirection
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)


def _signal():
    inst = Instrument(instrument_token=1, trading_symbol="X",
                      exchange_segment=ExchangeSegment.NSE_CASH,
                      kind=InstrumentKind.CASH_EQUITY, lot_size=1, tick_size=0.05)
    return OpeningRangeBreakoutSignal(
        instrument=inst, direction=SignalDirection.LONG,
        triggered_at=None, breakout_close_price=100.0,
        opening_range_high=100.0, opening_range_low=98.0,
        stop_loss_price=98.0, target_price=104.0,
        strategy_tag="opening_range_breakout_v1")


def _confident_win_record():
    # high ADX -> confident win, high win_probability
    return build_orb_prediction_record(_signal(), adx_value=40.0,
                                        session_date=date(2026, 7, 24),
                                        target_reward_multiple=2.0)


def test_empty_offsets_is_identity():
    rec = _confident_win_record()
    assert recalibrate_prediction_record(rec, {}) is rec


def test_negative_offset_demotes_confident_win():
    rec = _confident_win_record()
    assert rec.assigned_table == PredictionLabeledTable.CONFIDENT_WIN
    # learned bias: this mechanism actually loses -> big negative offset
    offset = {rec.mechanism_name: -0.75}
    out = recalibrate_prediction_record(rec, offset)
    assert out.win_probability < rec.win_probability
    assert out.assigned_table != PredictionLabeledTable.CONFIDENT_WIN  # demoted
    assert out.mechanism_name == rec.mechanism_name  # identity preserved


def test_recalibrated_probability_clamped():
    assert recalibrated_win_probability(0.84, -0.75) == pytest.approx(0.09)
    assert recalibrated_win_probability(0.05, -0.5) == 0.01   # clamp low
    assert recalibrated_win_probability(0.95, 0.5) == 0.99    # clamp high
