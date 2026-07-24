"""Layer 10 slice 2 — assumption tripwires fire only with significant evidence."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.memory_reflection import (
    AssumptionConfig,
    AssumptionStatus,
    ClosedExperiment,
    SqliteExperienceMemory,
    evaluate_trading_assumptions,
)

IST = ZoneInfo("Asia/Kolkata")


def _exp(n, *, mechanism, predicted_win_prob, won, ret):
    occurred = datetime(2026, 7, 24, 11, n % 55, n % 60, tzinfo=IST)
    return ClosedExperiment(
        experiment_id=f"{mechanism}:{n}", occurred_at=occurred,
        session_date=date(2026, 7, 24), strategy_tag="orb",
        mechanism_name=mechanism, regime_context="normal",
        instrument_token=1000 + n, instrument_kind="cash_equity",
        assigned_table="confident_win", direction="long",
        predicted_outcome="win", win_probability=predicted_win_prob,
        actual_outcome="win" if won else "loss", prediction_was_correct=won,
        brier_contribution=0.2, realized_pnl=1.0 if won else -1.0,
        realized_return_fraction=ret, predicted_exit_cause="target",
        actual_exit_cause="exited_target" if won else "exited_stop",
        kill_criteria="kc",
    )


def _memory(tmp_path):
    return SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")


class TestCalibrationTripwire:
    def test_overconfident_mechanism_trips_calibration(self, tmp_path):
        mem = _memory(tmp_path)
        # predicted 85% but 0/18 won -> hugely over-confident
        for i in range(18):
            mem.record_closed_experiment(_exp(i, mechanism="trend",
                                              predicted_win_prob=0.85, won=False, ret=-0.01))
        verdicts = evaluate_trading_assumptions(mem)
        cal = [v for v in verdicts if v.assumption_name == "calibration"][0]
        assert cal.status is AssumptionStatus.VIOLATED
        assert cal.sample_count == 18
        mem.close()

    def test_well_calibrated_mechanism_holds(self, tmp_path):
        mem = _memory(tmp_path)
        # predicted 60%, ~60% actually win -> calibrated
        for i in range(20):
            mem.record_closed_experiment(_exp(i, mechanism="ok",
                                              predicted_win_prob=0.6, won=(i % 5 < 3), ret=0.01))
        verdicts = evaluate_trading_assumptions(mem)
        cal = [v for v in verdicts if v.assumption_name == "calibration"][0]
        assert cal.status is AssumptionStatus.HOLDING
        mem.close()

    def test_small_sample_is_insufficient_not_tripped(self, tmp_path):
        mem = _memory(tmp_path)
        for i in range(4):  # below minimum_samples
            mem.record_closed_experiment(_exp(i, mechanism="thin",
                                              predicted_win_prob=0.9, won=False, ret=-0.01))
        verdicts = evaluate_trading_assumptions(mem)
        statuses = {v.status for v in verdicts}
        assert AssumptionStatus.INSUFFICIENT_DATA in statuses
        assert AssumptionStatus.VIOLATED not in statuses  # never trip on noise
        mem.close()


class TestEdgeTripwire:
    def test_negative_edge_trips(self, tmp_path):
        mem = _memory(tmp_path)
        for i in range(15):
            mem.record_closed_experiment(_exp(i, mechanism="bleed",
                                              predicted_win_prob=0.5, won=(i % 2 == 0), ret=-0.05))
        verdicts = evaluate_trading_assumptions(mem)
        edge = [v for v in verdicts if v.assumption_name == "edge"][0]
        assert edge.status is AssumptionStatus.VIOLATED
        mem.close()


class TestAntibodyVeto:
    def test_vetoed_mechanisms_lists_the_tripped_thesis(self, tmp_path):
        from nse_algo_trader.memory_reflection import vetoed_mechanisms
        mem = _memory(tmp_path)
        for i in range(18):  # over-confident -> tripped
            mem.record_closed_experiment(_exp(i, mechanism="badthesis",
                                              predicted_win_prob=0.85, won=False, ret=-0.01))
        for i in range(20):  # calibrated -> not vetoed
            mem.record_closed_experiment(_exp(100 + i, mechanism="goodthesis",
                                              predicted_win_prob=0.6, won=(i % 5 < 3), ret=0.01))
        vetoed = vetoed_mechanisms(mem)
        assert "badthesis" in vetoed
        assert "goodthesis" not in vetoed
        mem.close()
