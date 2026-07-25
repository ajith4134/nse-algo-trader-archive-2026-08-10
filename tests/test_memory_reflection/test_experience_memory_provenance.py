"""Layer-10 provenance tagging (research/62 slice 3a; research/53 §8.2): every
memory node records whether it came from a live session or from 24/7 replay, so
replayed lessons can be weighted below live and separated in queries.

Includes the migration path (a pre-provenance DB gains the column, old rows →
'live') and a REAL-DATA pass on a COPY of the live memory DB (never the live file
itself — the running old-code service still writes it).
"""

import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.memory_reflection import ClosedExperiment, SqliteExperienceMemory

IST = ZoneInfo("Asia/Kolkata")
_REAL_MEMORY_DB = Path("~/.nse_algo_trader/experience_memory.sqlite3").expanduser()


def _experiment(experiment_id: str, data_provenance: str) -> ClosedExperiment:
    return ClosedExperiment(
        experiment_id=experiment_id,
        occurred_at=datetime(2026, 7, 24, 11, 0, tzinfo=IST),
        session_date=date(2026, 7, 24), strategy_tag="orb",
        mechanism_name="breakout", regime_context="normal",
        instrument_token=101, instrument_kind="cash_equity",
        assigned_table="confident_win", direction="long",
        predicted_outcome="win", win_probability=0.6, actual_outcome="win",
        prediction_was_correct=True, brier_contribution=0.16, realized_pnl=1.0,
        realized_return_fraction=0.01, predicted_exit_cause="target",
        actual_exit_cause="exited_target", kill_criteria="kc",
        data_provenance=data_provenance,
    )


def test_live_and_replay_experiences_are_counted_separately(tmp_path):
    memory = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    memory.record_closed_experiment(_experiment("live-1", "live"))
    memory.record_closed_experiment(_experiment("replay-1", "replay_faithful"))
    memory.record_closed_experiment(_experiment("replay-2", "replay_faithful"))
    assert memory.experiment_count_by_provenance() == {"live": 1, "replay_faithful": 2}
    assert memory.experiment_count() == 3


def test_default_provenance_is_live_for_back_compat(tmp_path):
    memory = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    # Constructing without data_provenance (older callers) → live.
    experiment = ClosedExperiment(
        experiment_id="x", occurred_at=datetime(2026, 7, 24, 11, 0, tzinfo=IST),
        session_date=date(2026, 7, 24), strategy_tag="orb", mechanism_name="m",
        regime_context="normal", instrument_token=1, instrument_kind="cash_equity",
        assigned_table="uncertain", direction="long", predicted_outcome="win",
        win_probability=0.5, actual_outcome="win", prediction_was_correct=True,
        brier_contribution=0.25, realized_pnl=0.0, realized_return_fraction=0.0,
        predicted_exit_cause="target", actual_exit_cause="exited_target",
        kill_criteria="kc",
    )
    memory.record_closed_experiment(experiment)
    assert memory.experiment_count_by_provenance() == {"live": 1}


def test_migration_adds_column_and_defaults_old_rows_to_live(tmp_path):
    db_path = tmp_path / "old.sqlite3"
    # Build a pre-provenance table (21 cols, no data_provenance) with one row.
    connection = sqlite3.connect(str(db_path))
    connection.execute(
        "CREATE TABLE experience_nodes (experiment_id TEXT PRIMARY KEY, "
        "occurred_at TEXT, recorded_at TEXT, session_date TEXT, strategy_tag TEXT, "
        "mechanism_name TEXT, regime_context TEXT, instrument_token INTEGER, "
        "instrument_kind TEXT, assigned_table TEXT, direction TEXT, "
        "predicted_outcome TEXT, win_probability REAL, actual_outcome TEXT, "
        "prediction_was_correct INTEGER, brier_contribution REAL, realized_pnl REAL, "
        "realized_return_fraction REAL, predicted_exit_cause TEXT, "
        "actual_exit_cause TEXT, kill_criteria TEXT)"
    )
    connection.execute(
        "INSERT INTO experience_nodes VALUES "
        "('old-1','t','t','2026-07-01','orb','m','normal',1,'cash_equity',"
        "'uncertain','long','win',0.5,'win',1,0.25,0.0,0.0,'target','exited_target','kc')"
    )
    connection.commit()
    connection.close()

    memory = SqliteExperienceMemory(db_file_path=db_path)  # triggers migration
    assert memory.experiment_count_by_provenance() == {"live": 1}


def test_real_memory_db_migrates_and_reads_all_live_on_a_copy(tmp_path):
    if not _REAL_MEMORY_DB.exists():
        pytest.skip("real experience_memory DB not present (CI / fresh checkout)")
    # Copy — NEVER migrate the live DB while the running service writes it.
    copy_path = tmp_path / "experience_memory_copy.sqlite3"
    shutil.copy(_REAL_MEMORY_DB, copy_path)
    memory = SqliteExperienceMemory(db_file_path=copy_path)
    by_provenance = memory.experiment_count_by_provenance()
    # Every pre-existing real experience was a live one → all 'live' post-migration.
    assert sum(by_provenance.values()) == memory.experiment_count()
    assert memory.experiment_count() > 100  # the real accumulated history
    assert set(by_provenance) == {"live"}
