"""B23c — excursion (MFE/MAE) reaches the experience memory, so the brain can ask
"do we exit too early?".

Without these columns the profit trail (B23) could only ever be tuned by guesswork: MFE far above
realised P&L, repeatedly, is the evidence that targets cap runs; MAE near zero on winners is the
evidence that stops are wider than the trades ever needed.

See `docs/research/b23_profit_trail_and_excursion_design_2026-07-27.md`.
"""

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from nse_algo_trader.memory_reflection.experience_memory import ClosedExperiment
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def _experiment(
    experiment_id: str,
    mechanism_name: str,
    realized_pnl: float,
    mfe: float = 0.0,
    mae: float = 0.0,
    on_trail: bool = False,
) -> ClosedExperiment:
    return ClosedExperiment(
        experiment_id=experiment_id,
        occurred_at=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        session_date=date(2026, 7, 27),
        strategy_tag="opening_range_breakout_v1",
        mechanism_name=mechanism_name,
        regime_context="normal",
        instrument_token=1,
        instrument_kind="cash_equity",
        assigned_table="uncertain",
        direction="long",
        predicted_outcome="win",
        win_probability=0.5,
        actual_outcome="win" if realized_pnl > 0 else "loss",
        prediction_was_correct=realized_pnl > 0,
        brier_contribution=0.25,
        realized_pnl=realized_pnl,
        realized_return_fraction=realized_pnl / 100_000.0,
        predicted_exit_cause="target",
        actual_exit_cause="exited_target",
        kill_criteria="none",
        maximum_favourable_profit=mfe,
        maximum_adverse_profit=mae,
        exited_on_profit_trail=on_trail,
    )


@pytest.fixture
def memory(tmp_path: Path) -> SqliteExperienceMemory:
    store = SqliteExperienceMemory(tmp_path / "experience_memory.sqlite3")
    yield store
    store.close()


class TestExcursionPersistence:
    def test_excursion_survives_a_round_trip(self, memory):
        memory.record_closed_experiment(
            _experiment("a", "mech", realized_pnl=500.0, mfe=1800.0, mae=-220.0, on_trail=True)
        )
        rows = memory.exit_efficiency_by_mechanism(minimum_experiments=1)
        assert len(rows) == 1
        assert rows[0]["mean_maximum_favourable_profit"] == 1800.0
        assert rows[0]["mean_maximum_adverse_profit"] == -220.0
        assert rows[0]["trail_exit_count"] == 1

    def test_capture_ratio_exposes_giving_profit_back(self, memory):
        """The whole point: reached Rs 2,000, kept Rs 400 -> we exit too late/too loose."""
        for index in range(4):
            memory.record_closed_experiment(
                _experiment(f"g{index}", "gives-it-back", realized_pnl=400.0, mfe=2000.0)
            )
        row = memory.exit_efficiency_by_mechanism(minimum_experiments=1)[0]
        assert row["capture_ratio"] == pytest.approx(0.20)

    def test_a_mechanism_that_keeps_what_it_earns_scores_near_one(self, memory):
        for index in range(4):
            memory.record_closed_experiment(
                _experiment(f"k{index}", "keeps-it", realized_pnl=950.0, mfe=1000.0)
            )
        row = memory.exit_efficiency_by_mechanism(minimum_experiments=1)[0]
        assert row["capture_ratio"] == pytest.approx(0.95)

    def test_unmeasured_legacy_rows_are_excluded_not_counted_as_zero_mfe(self, memory):
        """Rows written before the excursion watermark must not drag every ratio toward 0."""
        memory.record_closed_experiment(
            _experiment("measured", "mech", realized_pnl=900.0, mfe=1000.0)
        )
        memory.record_closed_experiment(  # legacy: no excursion recorded
            _experiment("legacy", "mech", realized_pnl=50.0)
        )
        row = memory.exit_efficiency_by_mechanism(minimum_experiments=1)[0]
        assert row["total_count"] == 2
        assert row["measured_count"] == 1
        assert row["mean_maximum_favourable_profit"] == 1000.0
        assert row["capture_ratio"] == pytest.approx(0.90)

    def test_capture_ratio_is_none_rather_than_a_divide_by_zero(self, memory):
        memory.record_closed_experiment(
            _experiment("loser", "always-red", realized_pnl=-300.0, mae=-800.0)
        )
        row = memory.exit_efficiency_by_mechanism(minimum_experiments=1)[0]
        assert row["capture_ratio"] is None

    def test_minimum_experiments_gates_thin_cohorts(self, memory):
        memory.record_closed_experiment(
            _experiment("only", "thin", realized_pnl=100.0, mfe=200.0)
        )
        assert memory.exit_efficiency_by_mechanism(minimum_experiments=10) == []

    def test_defaults_keep_older_callers_working(self):
        """`build_closed_experiment` callers that predate excursion must still construct."""
        experiment = _experiment("d", "mech", realized_pnl=1.0)
        assert experiment.maximum_favourable_profit == 0.0
        assert experiment.exited_on_profit_trail is False
        assert replace(experiment, maximum_favourable_profit=5.0).maximum_favourable_profit == 5.0


class TestSchemaMigration:
    def test_an_existing_db_without_the_columns_is_migrated_in_place(self, tmp_path):
        """The real DB on the server predates these columns — opening it must not fail."""
        import sqlite3

        database_path = tmp_path / "legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.execute(
            "CREATE TABLE experience_nodes ("
            "experiment_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL,"
            " recorded_at TEXT NOT NULL, session_date TEXT NOT NULL,"
            " strategy_tag TEXT NOT NULL, mechanism_name TEXT NOT NULL,"
            " regime_context TEXT NOT NULL, instrument_token INTEGER NOT NULL,"
            " instrument_kind TEXT NOT NULL, assigned_table TEXT NOT NULL,"
            " direction TEXT NOT NULL, predicted_outcome TEXT NOT NULL,"
            " win_probability REAL NOT NULL, actual_outcome TEXT NOT NULL,"
            " prediction_was_correct INTEGER NOT NULL, brier_contribution REAL NOT NULL,"
            " realized_pnl REAL NOT NULL, realized_return_fraction REAL NOT NULL,"
            " predicted_exit_cause TEXT NOT NULL, actual_exit_cause TEXT NOT NULL,"
            " kill_criteria TEXT NOT NULL)"
        )
        connection.commit()
        connection.close()

        store = SqliteExperienceMemory(database_path)
        try:
            store.record_closed_experiment(
                _experiment("post", "mech", realized_pnl=10.0, mfe=100.0)
            )
            row = store.exit_efficiency_by_mechanism(minimum_experiments=1)[0]
            assert row["mean_maximum_favourable_profit"] == 100.0
        finally:
            store.close()
