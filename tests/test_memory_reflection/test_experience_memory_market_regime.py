"""§53 slice 5b — market-regime tag on experiences (hermetic). Records experiences
across ADX market regimes and asserts the memory now returns DIFFERENTIATED per-regime
cohorts (the multi-regime read that was blocked while everything was one 'normal' blob),
plus the session-date backfill that retro-tags pre-existing rows. Real-data unblock =
scripts/verify_experience_market_regime_realdata.py."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.memory_reflection.experience_memory import ClosedExperiment
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def memory(tmp_path: Path) -> SqliteExperienceMemory:
    return SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")


def _experiment(n, *, regime="trending", won=True, session=date(2026, 7, 24)):
    occurred = datetime(session.year, session.month, session.day, 11, n % 50, tzinfo=IST)
    return ClosedExperiment(
        experiment_id=f"orb:{n}:{occurred.isoformat()}",
        occurred_at=occurred, session_date=session,
        strategy_tag="orb", mechanism_name="trend", regime_context="normal",
        instrument_token=1000 + n, instrument_kind="cash_equity",
        assigned_table="confident_win" if won else "confident_loss", direction="long",
        predicted_outcome="win", win_probability=0.7,
        actual_outcome="win" if won else "loss", prediction_was_correct=won,
        brier_contribution=0.1, realized_pnl=100.0 if won else -80.0,
        realized_return_fraction=0.02 if won else -0.016,
        predicted_exit_cause="target", actual_exit_cause="exited_target",
        kill_criteria="k", market_regime=regime,
    )


def test_default_market_regime_is_unknown():
    assert _experiment(1).market_regime == "trending"
    exp = ClosedExperiment.__dataclass_fields__["market_regime"]
    assert exp.default == "unknown"  # back-compat default


def test_count_by_market_regime_shows_variety(memory):
    for i in range(5):
        memory.record_closed_experiment(_experiment(i, regime="trending"))
    for i in range(3):
        memory.record_closed_experiment(_experiment(10 + i, regime="range_bound"))
    for i in range(2):
        memory.record_closed_experiment(_experiment(20 + i, regime="indecisive"))
    assert memory.experiment_count_by_market_regime() == {
        "trending": 5, "range_bound": 3, "indecisive": 2
    }


def test_calibration_by_market_regime_is_differentiated(memory):
    # trending: 4/5 win; range_bound: 1/4 win -> the cohorts must differ.
    for i in range(4):
        memory.record_closed_experiment(_experiment(i, regime="trending", won=True))
    memory.record_closed_experiment(_experiment(4, regime="trending", won=False))
    memory.record_closed_experiment(_experiment(10, regime="range_bound", won=True))
    for i in range(3):
        memory.record_closed_experiment(_experiment(11 + i, regime="range_bound", won=False))

    by_regime = {c.market_regime: c for c in memory.calibration_by_market_regime("orb")}
    assert by_regime["trending"].hit_rate == pytest.approx(0.8)
    assert by_regime["range_bound"].hit_rate == pytest.approx(0.25)
    assert by_regime["trending"].experiment_count == 5
    assert by_regime["range_bound"].mean_return_fraction < 0  # losing cohort


def test_minimum_experiments_filters_small_cohorts(memory):
    for i in range(5):
        memory.record_closed_experiment(_experiment(i, regime="trending"))
    memory.record_closed_experiment(_experiment(99, regime="indecisive"))
    regimes = [c.market_regime for c in memory.calibration_by_market_regime(minimum_experiments=3)]
    assert regimes == ["trending"]  # the single-row indecisive cohort is filtered out


def test_backfill_by_session_date_retro_tags(memory):
    # two sessions recorded as 'unknown', then backfilled by date.
    memory.record_closed_experiment(_experiment(1, regime="unknown", session=date(2026, 7, 1)))
    memory.record_closed_experiment(_experiment(2, regime="unknown", session=date(2026, 7, 1)))
    memory.record_closed_experiment(_experiment(3, regime="unknown", session=date(2026, 7, 3)))
    assert memory.experiment_count_by_market_regime() == {"unknown": 3}

    updated = memory.backfill_market_regime_by_session_date({
        date(2026, 7, 1): "trending", date(2026, 7, 3): "range_bound",
    })
    assert updated == 3
    assert memory.experiment_count_by_market_regime() == {"trending": 2, "range_bound": 1}
