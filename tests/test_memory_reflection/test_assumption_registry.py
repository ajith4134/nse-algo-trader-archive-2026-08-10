"""Layer 10 slice 2 — assumption tripwires fire only with significant evidence."""

import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.memory_reflection import (
    AssumptionConfig,
    AssumptionStatus,
    ClosedExperiment,
    SqliteExperienceMemory,
    evaluate_trading_assumptions,
    learn_mechanism_recalibrations,
    vetoed_mechanisms,
)

IST = ZoneInfo("Asia/Kolkata")
_REAL_MEMORY_DB = Path("~/.nse_algo_trader/experience_memory.sqlite3").expanduser()


def _exp(n, *, mechanism, predicted_win_prob, won, ret, data_provenance="live"):
    occurred = datetime(2026, 7, 24, 11, n % 55, n % 60, tzinfo=IST)
    return ClosedExperiment(
        experiment_id=f"{mechanism}:{data_provenance}:{n}", occurred_at=occurred,
        session_date=date(2026, 7, 24), strategy_tag="orb",
        mechanism_name=mechanism, regime_context="normal",
        instrument_token=1000 + n, instrument_kind="cash_equity",
        assigned_table="confident_win", direction="long",
        predicted_outcome="win", win_probability=predicted_win_prob,
        actual_outcome="win" if won else "loss", prediction_was_correct=won,
        brier_contribution=0.2, realized_pnl=1.0 if won else -1.0,
        realized_return_fraction=ret, predicted_exit_cause="target",
        actual_exit_cause="exited_target" if won else "exited_stop",
        kill_criteria="kc", data_provenance=data_provenance,
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


class TestOutcomeSequenceDependence:
    def test_streaky_sequence_clusters(self, tmp_path):
        mem = _memory(tmp_path)
        # a streaky sequence: 6 wins then 6 losses -> after a win you usually win,
        # after a loss you usually lose -> big post-win vs post-loss gap
        for i in range(12):
            mem.record_closed_experiment(
                _exp(i, mechanism="streak", predicted_win_prob=0.5,
                     won=(i < 6), ret=0.01 if i < 6 else -0.01)
            )
        dep = {d.mechanism_name: d for d in mem.outcome_sequence_dependence(minimum_experiments=6)}
        assert dep["streak"].clusters is True
        assert dep["streak"].post_win_win_rate > dep["streak"].post_loss_win_rate
        mem.close()

    def test_alternating_sequence_does_not_cluster_positively(self, tmp_path):
        mem = _memory(tmp_path)
        # alternating W,L,W,L... -> after a win you lose, after a loss you win
        # -> strong NEGATIVE dependence (also clusters, opposite sign)
        for i in range(12):
            mem.record_closed_experiment(
                _exp(i, mechanism="alt", predicted_win_prob=0.5,
                     won=(i % 2 == 0), ret=0.01 if i % 2 == 0 else -0.01)
            )
        dep = {d.mechanism_name: d for d in mem.outcome_sequence_dependence(minimum_experiments=6)}
        # post-win win-rate ~0, post-loss ~1 -> gap strongly negative
        assert dep["alt"].dependence_gap < -0.15
        mem.close()

    def test_clustering_note_reaches_the_calibration_verdict(self, tmp_path):
        from nse_algo_trader.memory_reflection import evaluate_trading_assumptions
        mem = _memory(tmp_path)
        for i in range(12):
            mem.record_closed_experiment(
                _exp(i, mechanism="streak2", predicted_win_prob=0.5,
                     won=(i < 6), ret=0.01 if i < 6 else -0.01)
            )
        details = " ".join(
            v.detail for v in evaluate_trading_assumptions(mem)
            if v.assumption_name == "calibration"
        )
        assert "errors cluster" in details
        mem.close()


class TestProvenanceWeightedDecisions:
    """§53 slice 3b-i: replay evidence is weighted BELOW live in the veto +
    recalibration, so a replay-only lesson can inform but never override live."""

    def test_replay_only_overconfident_mechanism_is_not_vetoed(self, tmp_path):
        mem = _memory(tmp_path)
        # 18 REPLAY losses at predicted 0.85 → effective n = 18*0.25 = 4.5 < 12,
        # so it never reaches the veto threshold on replay evidence alone.
        for i in range(18):
            mem.record_closed_experiment(
                _exp(i, mechanism="trend", predicted_win_prob=0.85, won=False,
                     ret=-0.01, data_provenance="replay_faithful")
            )
        assert "trend" not in vetoed_mechanisms(mem)
        mem.close()

    def test_identical_evidence_as_live_is_vetoed(self, tmp_path):
        mem = _memory(tmp_path)
        # The SAME 18 losses, but LIVE (weight 1.0) → vetoed. Proves it is the
        # provenance weighting, not the sample size, that spared the replay case.
        for i in range(18):
            mem.record_closed_experiment(
                _exp(i, mechanism="trend", predicted_win_prob=0.85, won=False,
                     ret=-0.01, data_provenance="live")
            )
        assert "trend" in vetoed_mechanisms(mem)
        mem.close()

    def test_replay_cannot_drag_a_live_good_mechanism_into_a_veto(self, tmp_path):
        mem = _memory(tmp_path)
        # 40 LIVE experiences, well-calibrated-to-good (26/40 = 65% vs predicted 60%).
        for i in range(40):
            mem.record_closed_experiment(
                _exp(i, mechanism="orb_break", predicted_win_prob=0.6, won=(i < 26),
                     ret=0.01 if i < 26 else -0.01, data_provenance="live")
            )
        # 20 REPLAY losses on the same mechanism.
        for i in range(20):
            mem.record_closed_experiment(
                _exp(100 + i, mechanism="orb_break", predicted_win_prob=0.6, won=False,
                     ret=-0.01, data_provenance="replay_faithful")
            )
        # Pooled (no discount) the replay losses drag it under → vetoed.
        assert "orb_break" in vetoed_mechanisms(
            mem, AssumptionConfig(replay_evidence_weight=1.0)
        )
        # Discounted (default 0.25) live dominates → the good mechanism is spared.
        assert "orb_break" not in vetoed_mechanisms(mem)
        mem.close()

    def test_real_db_weighting_is_a_noop_when_all_experiences_are_live(self, tmp_path):
        if not _REAL_MEMORY_DB.exists():
            pytest.skip("real experience_memory DB not present")
        copy_path = tmp_path / "copy.sqlite3"
        shutil.copy(_REAL_MEMORY_DB, copy_path)
        mem = SqliteExperienceMemory(db_file_path=copy_path)
        # Every real experience is live → discounting replay changes nothing:
        # the veto set and recalibration offsets are identical with/without it.
        discounted = AssumptionConfig()  # replay weight 0.25
        pooled = AssumptionConfig(replay_evidence_weight=1.0)
        assert vetoed_mechanisms(mem, discounted) == vetoed_mechanisms(mem, pooled)
        assert learn_mechanism_recalibrations(mem, discounted) == learn_mechanism_recalibrations(mem, pooled)
        mem.close()
