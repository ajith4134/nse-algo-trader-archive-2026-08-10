"""§53 slice 5a — deficit-driven replay session selector + coverage ledger (hermetic)."""

from datetime import date
from pathlib import Path

from nse_algo_trader.paper_trading.deficit_driven_replay_session_selector import (
    select_deficit_replay_session,
)
from nse_algo_trader.paper_trading.replayed_session_regime_ledger import (
    ReplayedSessionRegimeLedger,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime

TREND = MarketRegime.TRENDING
RANGE = MarketRegime.RANGE_BOUND
INDEC = MarketRegime.INDECISIVE


def test_no_candidates_returns_none():
    assert select_deficit_replay_session([], {}) is None


def test_picks_the_least_covered_regime():
    candidates = [
        (date(2026, 7, 20), TREND),
        (date(2026, 7, 21), RANGE),
        (date(2026, 7, 22), INDEC),
    ]
    covered = {"trending": 5, "range_bound": 5, "indecisive": 0}
    # indecisive has zero coverage -> its day wins.
    assert select_deficit_replay_session(candidates, covered) == date(2026, 7, 22)


def test_regime_absent_from_counts_is_zero_coverage():
    candidates = [(date(2026, 7, 20), TREND), (date(2026, 7, 21), RANGE)]
    covered = {"trending": 3}  # range_bound absent -> counts as 0 -> preferred
    assert select_deficit_replay_session(candidates, covered) == date(2026, 7, 21)


def test_tie_breaks_toward_most_recent():
    candidates = [(date(2026, 7, 18), TREND), (date(2026, 7, 22), TREND)]
    # both trending, equal coverage -> most recent (22nd) wins.
    assert select_deficit_replay_session(candidates, {"trending": 1}) == date(2026, 7, 22)


def test_ledger_counts_and_rotation(tmp_path: Path):
    ledger = ReplayedSessionRegimeLedger(tmp_path / "curriculum.sqlite3")
    try:
        assert ledger.covered_regime_counts() == {}
        ledger.record_replayed_session(date(2026, 7, 20), TREND)
        ledger.record_replayed_session(date(2026, 7, 21), TREND)
        ledger.record_replayed_session(date(2026, 7, 22), RANGE)
        assert ledger.covered_regime_counts() == {"trending": 2, "range_bound": 1}
        assert ledger.replayed_session_count() == 3
        # re-recording the same date is idempotent (updates, not double-counts).
        ledger.record_replayed_session(date(2026, 7, 20), INDEC)
        assert ledger.replayed_session_count() == 3
        assert ledger.covered_regime_counts() == {"trending": 1, "range_bound": 1, "indecisive": 1}
    finally:
        ledger.close()


def test_selector_consumes_ledger_counts(tmp_path: Path):
    ledger = ReplayedSessionRegimeLedger(tmp_path / "c.sqlite3")
    try:
        ledger.record_replayed_session(date(2026, 7, 1), TREND)  # trending now covered
        candidates = [(date(2026, 7, 20), TREND), (date(2026, 7, 21), RANGE)]
        chosen = select_deficit_replay_session(candidates, ledger.covered_regime_counts())
        assert chosen == date(2026, 7, 21)  # range_bound (0 covered) beats trending (1)
    finally:
        ledger.close()
