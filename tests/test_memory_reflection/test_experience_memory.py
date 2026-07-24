"""Layer 10 slice 1 — the experience-memory substrate (research/43).

Pins the three query patterns (calibration-by-regime, prior-outcomes,
reflection diff) on the SQLite backend. Real-data (live §9 stream)
verification is the Rule-F sign-off, recorded in the flowchart note.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.memory_reflection import (
    ClosedExperiment,
    SqliteExperienceMemory,
    build_closed_experiment,
)

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def memory(tmp_path):
    store = SqliteExperienceMemory(
        db_file_path=tmp_path / "exp.sqlite3",
        now_provider=lambda: datetime(2026, 7, 24, 16, 0, tzinfo=IST),
    )
    yield store
    store.close()


def _experiment(n, *, strategy="orb", mechanism="trend", regime="normal",
                kind="cash_equity", won=True, occurred=None, brier=0.1):
    occurred = occurred or datetime(2026, 7, 24, 11, n % 50, tzinfo=IST)
    return ClosedExperiment(
        experiment_id=f"{strategy}:{n}:{occurred.isoformat()}",
        occurred_at=occurred, session_date=occurred.date(),
        strategy_tag=strategy, mechanism_name=mechanism, regime_context=regime,
        instrument_token=1000 + n, instrument_kind=kind,
        assigned_table="confident_win" if won else "confident_loss",
        direction="long",
        predicted_outcome="win", win_probability=0.7,
        actual_outcome="win" if won else "loss",
        prediction_was_correct=won, brier_contribution=brier,
        realized_pnl=100.0 if won else -80.0,
        realized_return_fraction=0.02 if won else -0.016,
        predicted_exit_cause="target", actual_exit_cause="exited_target",
        kill_criteria="re-enter range 2 bars",
    )


class TestRecordAndCalibration:
    def test_calibration_by_regime_aggregates_correctly(self, memory):
        for i in range(7):
            memory.record_closed_experiment(_experiment(i, regime="trending", won=True))
        for i in range(3):
            memory.record_closed_experiment(
                _experiment(100 + i, regime="trending", won=False))
        cal = memory.calibration_for("orb", "trending")
        assert cal.experiment_count == 10
        assert cal.hit_rate == pytest.approx(0.7)  # 7 of 10 correct
        assert cal.mean_return_fraction is not None

    def test_calibration_empty_cohort_is_none_not_zero(self, memory):
        cal = memory.calibration_for("orb", "never-seen")
        assert cal.experiment_count == 0
        assert cal.hit_rate is None

    def test_record_is_idempotent_on_experiment_id(self, memory):
        exp = _experiment(1)
        memory.record_closed_experiment(exp)
        memory.record_closed_experiment(exp)  # same id
        assert memory.experiment_count() == 1


class TestPriorOutcomes:
    def test_prior_outcomes_filters_all_four_keys(self, memory):
        for i in range(5):
            memory.record_closed_experiment(
                _experiment(i, strategy="orb", mechanism="trend",
                            regime="normal", kind="cash_equity", won=True))
        # a different mechanism must NOT leak in
        memory.record_closed_experiment(
            _experiment(9, strategy="orb", mechanism="chop",
                        regime="normal", kind="cash_equity", won=False))
        prior = memory.prior_outcomes_for("orb", "trend", "normal", "cash_equity")
        assert prior.experiment_count == 5
        assert prior.win_rate == pytest.approx(1.0)


class TestReflectionDiff:
    def test_diff_compares_recent_vs_baseline_window(self, memory):
        boundary = datetime(2026, 7, 24, 12, 0, tzinfo=IST)
        # baseline (before noon): mostly wins
        for i in range(6):
            memory.record_closed_experiment(_experiment(
                i, mechanism="trend", won=True,
                occurred=datetime(2026, 7, 24, 10, i, tzinfo=IST)))
        # recent (after noon): mostly losses -> hit rate dropped
        for i in range(6):
            memory.record_closed_experiment(_experiment(
                50 + i, mechanism="trend", won=(i == 0),
                occurred=datetime(2026, 7, 24, 13, i, tzinfo=IST)))
        rows = memory.reflection_diff(boundary)
        row = [r for r in rows if r.mechanism_name == "trend"][0]
        assert row.recent_count == 6 and row.baseline_count == 6
        assert row.baseline_hit_rate == pytest.approx(1.0)
        assert row.recent_hit_rate == pytest.approx(1 / 6)
        assert row.hit_rate_delta < 0  # calibration got worse -> flagged


class TestBuildFromGraded:
    def test_build_closed_experiment_maps_fields(self):
        # minimal stand-ins matching the real §9 shapes
        from types import SimpleNamespace
        record = SimpleNamespace(
            strategy_tag="orb", instrument_token=42, session_date=date(2026, 7, 24),
            mechanism_name="trend", calendar_context="normal",
            assigned_table=SimpleNamespace(value="confident_win"),
            direction=SimpleNamespace(value="long"),
            predicted_outcome=SimpleNamespace(value="win"), win_probability=0.66,
            predicted_exit_cause="target", kill_criteria="kc",
        )
        graded = SimpleNamespace(
            record=record, actual_outcome=SimpleNamespace(value="win"),
            prediction_was_correct=True, brier_contribution=0.11,
        )
        closed = SimpleNamespace(
            entry_price=100.0, quantity=10, realized_pnl=50.0,
            outcome=SimpleNamespace(value="exited_target"),
            closed_at=datetime(2026, 7, 24, 12, 0, tzinfo=IST),
        )
        exp = build_closed_experiment(graded, closed, "cash_equity")
        assert exp.strategy_tag == "orb"
        assert exp.realized_return_fraction == pytest.approx(50.0 / (100.0 * 10))
        assert exp.actual_exit_cause == "exited_target"
        assert exp.instrument_kind == "cash_equity"


class TestCalibrationBoard:
    def test_board_surfaces_the_miscalibrated_mechanism_first(self, memory):
        # "trend" predicted-win but mostly loses (overconfident) — the gap
        # (predicted - actual) should rank it above a well-calibrated cohort.
        for i in range(10):
            memory.record_closed_experiment(_experiment(
                i, mechanism="trend", won=(i < 1)))   # predicted win .7, actual .1
        for i in range(10):
            memory.record_closed_experiment(_experiment(
                50 + i, mechanism="chop", won=(i < 7)))  # actual .7 ~ matches
        board = memory.calibration_board(minimum_experiments=3)
        assert board[0].mechanism_name == "trend"     # biggest predicted-actual gap
        assert board[0].experiment_count == 10
        assert board[0].actual_win_rate < board[0].predicted_win_rate
