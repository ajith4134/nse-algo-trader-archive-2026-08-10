"""research/93 — the Closed-trades panel sources from the DURABLE experience memory (all
sessions, survives restarts), not the process-local ledger. Hermetic."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.memory_reflection.experience_memory import ClosedExperiment
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)

IST = ZoneInfo("Asia/Kolkata")


def _exp(n, token, provenance, pnl, kind="cash_equity", when=None):
    when = when or datetime(2026, 7, 24, 15, 15, tzinfo=IST) - timedelta(minutes=n)
    return ClosedExperiment(
        experiment_id=f"orb:{token}:{when.isoformat()}", occurred_at=when,
        session_date=when.date(), strategy_tag="orb", mechanism_name="breakout",
        regime_context="normal", instrument_token=token, instrument_kind=kind,
        assigned_table="confident_win", direction="long", predicted_outcome="win",
        win_probability=0.6, actual_outcome="win" if pnl > 0 else "loss",
        prediction_was_correct=pnl > 0, brier_contribution=0.1, realized_pnl=pnl,
        realized_return_fraction=0.01, predicted_exit_cause="t", actual_exit_cause="exited_target",
        kill_criteria="k", data_provenance=provenance,
    )


def test_recent_closed_experiences_newest_first(tmp_path: Path):
    mem = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    mem.record_closed_experiment(_exp(3, 101, "live", 100.0))
    mem.record_closed_experiment(_exp(1, 102, "replay_faithful", -50.0))  # newest
    mem.record_closed_experiment(_exp(2, 103, "live", 20.0))
    rows = mem.recent_closed_experiences(limit=10)
    assert [r["instrument_token"] for r in rows] == [102, 103, 101]  # newest first
    assert rows[0]["data_provenance"] == "replay_faithful"
    assert rows[0]["realized_pnl"] == -50.0


def test_service_closed_trades_come_from_persisted_memory(tmp_path: Path):
    mem = SqliteExperienceMemory(db_file_path=tmp_path / "e.sqlite3")
    for i in range(5):
        mem.record_closed_experiment(_exp(i, 738561, "live", 100.0 - i))
    mem.record_closed_experiment(_exp(9, 111, "replay_faithful", -30.0, kind="index_option"))

    service = LivePaperTradingService(object(), 1_000_000.0)
    service._experience_memory = mem  # inject the durable memory (writer-thread owned)
    # a token→symbol map (normally from the universe)
    service._token_symbol_cache = {738561: "RELIANCE", 111: "NIFTY 25000 CE"}

    views = service._recent_closed_trades()
    assert len(views) == 6  # from memory, not the empty in-memory ledger
    symbols = {v.trading_symbol for v in views}
    assert "RELIANCE" in symbols and "NIFTY 25000 CE" in symbols
    replay = next(v for v in views if v.provenance == "replay_faithful")
    assert replay.segment == "index_option" and replay.realized_pnl == -30.0
    # an unknown token falls back to #token, never crashes
    service._token_symbol_cache = {}
    assert all(v.trading_symbol.startswith("#") or v.trading_symbol for v in service._recent_closed_trades())
