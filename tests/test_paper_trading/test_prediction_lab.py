from datetime import date, datetime, timedelta

import pytest

from nse_algo_trader.broker_oms import SimulatedBrokerClient
from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.paper_trading import INDIA_MARKET_TIMEZONE, PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import (
    GradedPrediction,
    PredictedTradeOutcome,
    PredictionLabeledTable,
    PredictionTableScoreboard,
    TradePredictionRecord,
    build_orb_prediction_record,
    grade_prediction,
    run_orb_prediction_lab_session,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    NamedPredictionReason,
)
from nse_algo_trader.risk_management import RiskBudgetConfig
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutSignal,
    SignalDirection,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

INFY = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)


def _signal(direction=SignalDirection.LONG) -> OpeningRangeBreakoutSignal:
    return OpeningRangeBreakoutSignal(
        instrument=INFY, direction=direction,
        triggered_at=datetime(2026, 7, 22, 9, 30, tzinfo=INDIA_MARKET_TIMEZONE),
        breakout_close_price=103.0, opening_range_high=102, opening_range_low=98,
        stop_loss_price=98.0, target_price=113.0,
    )


class TestPredictionRecordInvariants:
    def test_confident_loss_must_predict_loss(self):
        with pytest.raises(ValueError, match="CONFIDENT_LOSS"):
            TradePredictionRecord(
                session_date=date(2026, 7, 22), instrument_token=1, strategy_tag="x",
                direction=SignalDirection.LONG,
                predicted_outcome=PredictedTradeOutcome.WIN,  # contradiction
                win_probability=0.2,
                assigned_table=PredictionLabeledTable.CONFIDENT_LOSS,
                expected_reward_multiple=-1.0, reasons=(),
                mechanism_name="m", predicted_exit_cause="stop",
                kill_criteria="k", calendar_context="normal",
            )

    def test_win_probability_bounds_enforced(self):
        with pytest.raises(ValueError, match="win_probability"):
            TradePredictionRecord(
                session_date=date(2026, 7, 22), instrument_token=1, strategy_tag="x",
                direction=SignalDirection.LONG,
                predicted_outcome=PredictedTradeOutcome.WIN, win_probability=1.5,
                assigned_table=PredictionLabeledTable.UNCERTAIN,
                expected_reward_multiple=2.0, reasons=(),
                mechanism_name="m", predicted_exit_cause="target",
                kill_criteria="k", calendar_context="normal",
            )


class TestAdxConfidencePrediction:
    def test_high_adx_goes_to_confident_win(self):
        record = build_orb_prediction_record(_signal(), 40.0, date(2026, 7, 22), 2.0)
        assert record.assigned_table is PredictionLabeledTable.CONFIDENT_WIN
        assert record.predicted_outcome is PredictedTradeOutcome.WIN
        assert record.win_probability > 0.6
        assert "trend continuation" in record.mechanism_name

    def test_low_adx_goes_to_confident_loss_deliberately(self):
        record = build_orb_prediction_record(_signal(), 8.0, date(2026, 7, 22), 2.0)
        assert record.assigned_table is PredictionLabeledTable.CONFIDENT_LOSS
        assert record.predicted_outcome is PredictedTradeOutcome.LOSS
        assert record.win_probability < 0.4
        assert "false breakout" in record.mechanism_name
        assert record.predicted_exit_cause == "stop"

    def test_mid_adx_goes_to_uncertain(self):
        record = build_orb_prediction_record(_signal(), 22.5, date(2026, 7, 22), 2.0)
        assert record.assigned_table is PredictionLabeledTable.UNCERTAIN
        assert record.win_probability == pytest.approx(0.5, abs=0.02)


class TestGrading:
    def test_confident_win_correct_when_trade_wins(self):
        record = build_orb_prediction_record(_signal(), 40.0, date(2026, 7, 22), 2.0)
        graded = grade_prediction(record, realized_pnl=5000.0)
        assert graded.actual_outcome is PredictedTradeOutcome.WIN
        assert graded.prediction_was_correct

    def test_confident_loss_prediction_wins_when_trade_loses(self):
        # deliberate-loss trade that DOES lose -> its prediction was correct
        record = build_orb_prediction_record(_signal(), 8.0, date(2026, 7, 22), 2.0)
        graded = grade_prediction(record, realized_pnl=-2000.0)
        assert graded.actual_outcome is PredictedTradeOutcome.LOSS
        assert graded.prediction_was_correct

    def test_brier_contribution_rewards_calibration(self):
        record = build_orb_prediction_record(_signal(), 40.0, date(2026, 7, 22), 2.0)
        confident_and_right = grade_prediction(record, 5000.0)
        confident_and_wrong = grade_prediction(record, -5000.0)
        assert confident_and_right.brier_contribution < confident_and_wrong.brier_contribution


class TestScoreboard:
    def _graded(self, table_adx, pnl):
        record = build_orb_prediction_record(_signal(), table_adx, date(2026, 7, 22), 2.0)
        return grade_prediction(record, pnl)

    def test_confident_win_beats_confident_loss_check(self):
        board = PredictionTableScoreboard()
        # win-table trades that win, loss-table trades that lose
        board.add_graded_prediction(self._graded(40.0, 5000.0))
        board.add_graded_prediction(self._graded(38.0, 3000.0))
        board.add_graded_prediction(self._graded(8.0, -2000.0))
        assert board.confident_win_beats_confident_loss() is True
        win = board.score_for_table(PredictionLabeledTable.CONFIDENT_WIN)
        assert win.actual_win_rate == 1.0 and win.prediction_count == 2

    def test_empty_tables_return_none(self):
        board = PredictionTableScoreboard()
        assert board.overall_score() is None
        assert board.confident_win_beats_confident_loss() is None


def _session(ohlc, start_min=15):
    start = datetime(2026, 7, 22, 9, 15, tzinfo=INDIA_MARKET_TIMEZONE)
    return [
        PriceBar(408065, start + timedelta(minutes=5 * i), BarInterval.MINUTE_5,
                 o, h, l, c, 1000)
        for i, (o, h, l, c) in enumerate(ohlc)
    ]


class TestLabSessionWiring:
    def test_no_breakout_files_no_prediction(self):
        board = PredictionTableScoreboard()
        result = run_orb_prediction_lab_session(
            _session([(100, 101, 99, 100)] * 8), INFY, SimulatedBrokerClient(),
            RiskBudgetConfig(1_000_000.0), PaperTradingLedger(1_000_000.0), board,
            regime_adx_value=30.0,
        )
        assert result.graded_prediction is None
        assert board.overall_score() is None

    def test_breakout_session_files_a_graded_prediction_on_the_confident_win_table(self):
        opening = [(100, 101, 98, 100), (100, 102, 99, 101), (101, 102, 99, 100)]
        breakout = opening + [(101, 104, 100, 103.0), (103, 114, 103, 113.5)]
        board = PredictionTableScoreboard()
        result = run_orb_prediction_lab_session(
            _session(breakout), INFY, SimulatedBrokerClient(),
            RiskBudgetConfig(1_000_000.0), PaperTradingLedger(1_000_000.0), board,
            regime_adx_value=40.0,  # trending -> CONFIDENT_WIN
        )
        assert result.graded_prediction is not None
        assert (
            result.graded_prediction.record.assigned_table
            is PredictionLabeledTable.CONFIDENT_WIN
        )
        assert board.overall_score().prediction_count == 1

    def test_batch_replay_driver_warms_adx_and_files_predictions(self):
        opening = [(100, 101, 98, 100), (100, 102, 99, 101), (101, 102, 99, 100)]
        breakout = opening + [(101, 104, 100, 103.0), (103, 114, 103, 113.5)]
        board = PredictionTableScoreboard()
        from nse_algo_trader.paper_trading.prediction_lab import (
            run_orb_prediction_lab_over_replay,
        )

        results = run_orb_prediction_lab_over_replay(
            _session(breakout), INFY, SimulatedBrokerClient(),
            RiskBudgetConfig(1_000_000.0), PaperTradingLedger(1_000_000.0), board,
        )
        assert any(r.graded_prediction is not None for r in results)
