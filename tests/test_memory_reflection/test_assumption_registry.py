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


class TestRecencyWindowRecovery:
    def test_veto_lifts_when_recent_window_recovers(self, tmp_path):
        from datetime import timedelta
        from nse_algo_trader.memory_reflection import vetoed_mechanisms
        mem = _memory(tmp_path)
        base = datetime(2026, 7, 24, 10, 0, tzinfo=IST)
        # 30 OLD over-confident (predicted 85%, all lose) -> tripped
        for i in range(30):
            e = _exp(i, mechanism="trend", predicted_win_prob=0.85, won=False, ret=-0.01)
            mem.record_closed_experiment(e._replace(occurred_at=base+timedelta(minutes=i))
                                         if hasattr(e, "_replace") else e)
        assert "trend" in vetoed_mechanisms(mem)
        # 40 RECENT calibrated (predicted 85%, ~85% win) fill the recency window
        for i in range(40):
            occ = base + timedelta(hours=3, minutes=i)
            mem.record_closed_experiment(ClosedExperiment(
                f"trend:r{i}", occ, occ.date(), "orb", "trend", "normal",
                2000+i, "cash_equity", "confident_win", "long", "win", 0.85,
                "win" if i % 20 else "loss", i % 20 != 0, 0.1,
                1.0 if i % 20 else -1.0, 0.01, "target",
                "exited_target" if i % 20 else "exited_stop", "kc"))
        # all-time still shows the bad history; the recency-window veto lifts
        assert vetoed_mechanisms(mem) == set()   # recovered
        mem.close()


class TestLogScoreAntibodyTrip:
    def test_confidently_wrong_cohort_trips_via_log_score(self, tmp_path):
        from nse_algo_trader.memory_reflection import vetoed_mechanisms
        mem = _memory(tmp_path)
        # 12 experiments predicting 80% that consistently LOSE -> over-confident,
        # high log-score. Trips the calibration wire (z and/or log-score).
        for i in range(12):
            mem.record_closed_experiment(
                _exp(i, mechanism="overc", predicted_win_prob=0.80, won=False, ret=-0.01)
            )
        assert "overc" in vetoed_mechanisms(mem)
        board = {r.mechanism_name: r for r in mem.calibration_board(minimum_experiments=1)}
        assert board["overc"].mean_log_score > 1.0  # worse than a coin-flip
        mem.close()

    def test_well_calibrated_cohort_has_low_log_score_and_holds(self, tmp_path):
        from nse_algo_trader.memory_reflection import vetoed_mechanisms
        mem = _memory(tmp_path)
        # predict 60%, ~60% actually win -> calibrated -> low log-score, not vetoed
        for i in range(20):
            mem.record_closed_experiment(
                _exp(i, mechanism="cal", predicted_win_prob=0.60,
                     won=(i % 5 < 3), ret=0.01 if i % 5 < 3 else -0.01)
            )
        assert "cal" not in vetoed_mechanisms(mem)
        board = {r.mechanism_name: r for r in mem.calibration_board(minimum_experiments=1)}
        assert board["cal"].mean_log_score < 1.05
        mem.close()
