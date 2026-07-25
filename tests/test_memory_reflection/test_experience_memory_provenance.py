"""Layer-10 provenance tagging (research/62 slice 3a; research/53 §8.2): every
memory node records whether it came from a live session or from 24/7 replay, so
replayed lessons can be weighted below live and separated in queries.

Includes the migration path (a pre-provenance DB gains the column, old rows →
'live') and a REAL-DATA pass on a COPY of the live memory DB (never the live file
itself — the running old-code service still writes it).
"""

import shutil
import sqlite3
from dataclasses import replace
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


def test_calibration_board_separates_live_from_replay(tmp_path):
    """The slice-3a separability payoff: the same mechanism winning live but
    losing in replay must NOT be pooled into one misleading calibration row."""
    memory = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    for i in range(3):  # live: all wins
        memory.record_closed_experiment(_experiment(f"live-{i}", "live"))
    for i in range(3):  # replay: all losses (same "orb"/"breakout" cohort)
        loss = replace(
            _experiment(f"replay-{i}", "replay_faithful"),
            actual_outcome="loss", prediction_was_correct=False,
        )
        memory.record_closed_experiment(loss)

    live = memory.calibration_board(minimum_experiments=1, data_provenance="live")
    replay = memory.calibration_board(
        minimum_experiments=1, data_provenance="replay_faithful"
    )
    pooled = memory.calibration_board(minimum_experiments=1)

    live_row = next(r for r in live if r.mechanism_name == "breakout")
    replay_row = next(r for r in replay if r.mechanism_name == "breakout")
    pooled_row = next(r for r in pooled if r.mechanism_name == "breakout")
    assert (live_row.experiment_count, live_row.actual_win_rate) == (3, 1.0)
    assert (replay_row.experiment_count, replay_row.actual_win_rate) == (3, 0.0)
    # Pooling (no filter) would hide the replay-only failure behind a 0.5 average.
    assert pooled_row.experiment_count == 6
    assert pooled_row.actual_win_rate == 0.5


def test_real_memory_db_calibration_board_is_provenance_separable_on_a_copy(tmp_path):
    if not _REAL_MEMORY_DB.exists():
        pytest.skip("real experience_memory DB not present (CI / fresh checkout)")
    copy_path = tmp_path / "experience_memory_copy.sqlite3"
    shutil.copy(_REAL_MEMORY_DB, copy_path)
    memory = SqliteExperienceMemory(db_file_path=copy_path)

    # All real experiences are live → the replay-only board is empty, and the
    # live-only board equals the pooled board (nothing to separate out yet).
    pooled_keys = {
        (r.strategy_tag, r.mechanism_name, r.experiment_count)
        for r in memory.calibration_board(minimum_experiments=3)
    }
    live_keys_before = {
        (r.strategy_tag, r.mechanism_name, r.experiment_count)
        for r in memory.calibration_board(minimum_experiments=3, data_provenance="live")
    }
    assert live_keys_before == pooled_keys
    assert memory.calibration_board(minimum_experiments=3, data_provenance="replay_faithful") == []

    # Inject replayed experiences: they surface ONLY in the replay board and
    # leave the real live calibration byte-for-byte unchanged (no leakage).
    for i in range(3):
        memory.record_closed_experiment(
            replace(
                _experiment(f"replay-real-{i}", "replay_faithful"),
                actual_outcome="loss", prediction_was_correct=False,
            )
        )
    replay_after = memory.calibration_board(
        minimum_experiments=3, data_provenance="replay_faithful"
    )
    assert any(r.mechanism_name == "breakout" and r.experiment_count == 3 for r in replay_after)
    live_keys_after = {
        (r.strategy_tag, r.mechanism_name, r.experiment_count)
        for r in memory.calibration_board(minimum_experiments=3, data_provenance="live")
    }
    assert live_keys_after == live_keys_before


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


def test_prequential_forecast_score_punishes_confident_wrong(tmp_path):
    """§53 slice 3b-ii: a calibrated-and-right stream scores a low log-loss; a
    confidently-wrong stream scores a high one."""
    mem = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    for i in range(5):  # p=0.6, all WON (the _experiment default)
        mem.record_closed_experiment(_experiment(f"win-{i}", "live"))
    calibrated = mem.prequential_forecast_score()
    assert calibrated.experiment_count == 5
    assert abs(calibrated.mean_log_loss_bits - 0.737) < 0.01  # -log2(0.6)
    assert abs(calibrated.mean_brier - 0.16) < 1e-9  # (0.6-1)^2

    mem2 = SqliteExperienceMemory(db_file_path=tmp_path / "e2.sqlite3")
    for i in range(5):  # p=0.9 but all LOST -> confidently wrong
        mem2.record_closed_experiment(
            replace(
                _experiment(f"loss-{i}", "live"),
                win_probability=0.9, actual_outcome="loss", prediction_was_correct=False,
            )
        )
    wrong = mem2.prequential_forecast_score()
    assert abs(wrong.mean_log_loss_bits - 3.322) < 0.01  # -log2(0.1)
    assert wrong.mean_log_loss_bits > calibrated.mean_log_loss_bits


def test_prequential_forecast_score_empty_is_none(tmp_path):
    mem = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    score = mem.prequential_forecast_score()
    assert score == mem.prequential_forecast_score()  # deterministic
    assert score.experiment_count == 0
    assert score.mean_log_loss_bits is None and score.mean_brier is None


def test_prequential_forecast_score_separates_live_from_replay(tmp_path):
    mem = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    for i in range(4):  # live wins at 0.6
        mem.record_closed_experiment(_experiment(f"live-{i}", "live"))
    for i in range(4):  # replay: confident 0.9 losses
        mem.record_closed_experiment(
            replace(
                _experiment(f"rep-{i}", "replay_faithful"),
                win_probability=0.9, actual_outcome="loss", prediction_was_correct=False,
            )
        )
    live = mem.prequential_forecast_score(data_provenance="live")
    replay = mem.prequential_forecast_score(data_provenance="replay_faithful")
    assert (live.experiment_count, replay.experiment_count) == (4, 4)
    assert replay.mean_log_loss_bits > live.mean_log_loss_bits  # replay forecasts worse
    assert mem.prequential_forecast_score().experiment_count == 8  # pooled


def test_real_db_prequential_forecast_score_on_a_copy(tmp_path):
    if not _REAL_MEMORY_DB.exists():
        pytest.skip("real experience_memory DB not present")
    copy_path = tmp_path / "copy.sqlite3"
    shutil.copy(_REAL_MEMORY_DB, copy_path)
    mem = SqliteExperienceMemory(db_file_path=copy_path)
    overall = mem.prequential_forecast_score()
    live = mem.prequential_forecast_score(data_provenance="live")
    replay = mem.prequential_forecast_score(data_provenance="replay_faithful")
    assert overall.experiment_count == mem.experiment_count()
    assert live.experiment_count == overall.experiment_count  # all real rows are live
    assert replay.experiment_count == 0 and replay.mean_log_loss_bits is None
    assert overall.mean_log_loss_bits > 0 and 0.0 <= overall.mean_brier <= 1.0
    # Independent Brier recompute from the raw rows matches the scorer.
    rows = sqlite3.connect(str(copy_path)).execute(
        "SELECT win_probability, "
        "CASE WHEN actual_outcome='win' THEN 1.0 ELSE 0.0 END FROM experience_nodes"
    ).fetchall()
    expected_brier = sum((p - won) ** 2 for p, won in rows) / len(rows)
    assert abs(overall.mean_brier - expected_brier) < 1e-9
