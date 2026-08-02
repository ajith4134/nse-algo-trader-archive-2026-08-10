"""Engine-level tests for the Curiosity engine (research/164 §7/§10; Trunk XII).

Property/invariant + cold-start + boredom + persistence + adversarial + the replay-selector consumer,
all with a hermetic in-memory row source (Rule J)."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nse_algo_trader.intrinsic_motivation.curiosity_engine import CuriosityEngine
from nse_algo_trader.intrinsic_motivation.curiosity_engine_store import CuriosityEngineStore
from nse_algo_trader.intrinsic_motivation.learning_progress_estimator import MIN_WINDOW
from nse_algo_trader.paper_trading.deficit_driven_replay_session_selector import (
    select_curiosity_driven_replay_session,
    select_deficit_replay_session,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime


def _rows(strategy, regime, errors, outcome="loss"):
    return [{"strategy_tag": strategy, "market_regime": regime, "brier_contribution": e,
             "actual_outcome": outcome, "win_probability": 0.5, "occurred_at": f"t{i}"}
            for i, e in enumerate(errors)]


def _engine(rows):
    return CuriosityEngine(experience_row_source=lambda limit=99999: rows,
                           store=CuriosityEngineStore(Path(tempfile.mkdtemp()) / "c.json"))


# -- plan invariants ------------------------------------------------------------------------------

def test_plan_probabilities_sum_to_one():
    rows = _rows("orb", "indecisive", [0.2] * 40) + _rows("spread", "trending", [0.1] * 40)
    plan = _engine(rows).compute_exploration_plan()
    total = sum(cp.select_probability for cp in plan.cell_priorities)
    assert total == pytest.approx(1.0, abs=1e-6)
    assert all(cp.priority >= 0.0 for cp in plan.cell_priorities)
    assert all(0.0 <= cp.select_probability <= 1.0 for cp in plan.cell_priorities)


@settings(max_examples=20, deadline=None)
@given(n=st.integers(min_value=1, max_value=60), err=st.floats(0.0, 1.0))
def test_plan_always_valid(n, err):
    plan = _engine(_rows("orb", "indecisive", [err] * n)).compute_exploration_plan()
    assert plan.cell_priorities  # always at least the observed + unobserved cells
    assert plan.temperature >= 0.1
    assert sum(cp.select_probability for cp in plan.cell_priorities) == pytest.approx(1.0, abs=1e-6)


# -- cold-start behaviour -------------------------------------------------------------------------

def test_cold_start_prioritises_unobserved_regimes():
    # only ever traded in 'indecisive' → the engine should top-rank the UNOBSERVED regimes
    plan = _engine(_rows("orb", "indecisive", [0.2] * 30)).compute_exploration_plan()
    top = plan.top_cell
    assert top.is_unobserved is True
    assert top.market_regime in ("trending", "range_bound")


def test_empty_history_is_graceful():
    plan = _engine([]).compute_exploration_plan()
    assert plan.total_trades_seen == 0
    assert plan.is_mature is False
    # no strategies seen → no cells to enumerate; plan is empty but valid
    assert plan.cell_priorities == ()
    assert plan.most_curious_regime() is None


def test_maturity_flag():
    assert _engine(_rows("orb", "indecisive", [0.2] * (2 * MIN_WINDOW))).compute_exploration_plan().is_mature
    assert not _engine(_rows("orb", "indecisive", [0.2] * 3)).compute_exploration_plan().is_mature


# -- boredom: a mastered, stable cell loses priority to a still-learning one ----------------------

def test_boredom_demotes_mastered_cell_below_learning_cell():
    # cell A: flat low error (mastered, LP≈0 → bored). cell B: error steadily dropping (learning).
    mastered = _rows("mastered", "indecisive", [0.05] * (3 * MIN_WINDOW))
    learning = _rows("learning", "indecisive",
                     [0.6] * MIN_WINDOW + [0.3] * MIN_WINDOW + [0.1] * MIN_WINDOW)
    plan = _engine(mastered + learning).compute_exploration_plan()
    by_strategy = {cp.strategy_tag: cp for cp in plan.cell_priorities
                   if not cp.is_unobserved and cp.market_regime == "indecisive"}
    assert by_strategy["learning"].priority > by_strategy["mastered"].priority


# -- persistence ----------------------------------------------------------------------------------

def test_state_persists_across_instances():
    store_path = Path(tempfile.mkdtemp()) / "shared.json"
    rows = _rows("orb", "indecisive", [0.3] * 40)
    src = lambda limit=99999: rows  # noqa: E731
    CuriosityEngine(experience_row_source=src, store=CuriosityEngineStore(store_path)).compute_exploration_plan()
    reloaded = CuriosityEngine(experience_row_source=src, store=CuriosityEngineStore(store_path))
    assert reloaded._state.total_trades_seen == 40
    assert reloaded._state.cell_states  # per-cell learning state survived


# -- the replay-selector consumer (decision-grade wiring) -----------------------------------------

def test_curiosity_driven_selector_picks_highest_priority_regime():
    candidates = [(date(2026, 7, 20), MarketRegime.TRENDING),
                  (date(2026, 7, 21), MarketRegime.RANGE_BOUND),
                  (date(2026, 7, 22), MarketRegime.INDECISIVE)]
    priorities = {"trending": 0.9, "range_bound": 0.2, "indecisive": 0.05}
    assert select_curiosity_driven_replay_session(candidates, priorities) == date(2026, 7, 20)


def test_curiosity_selector_falls_back_to_deficit_without_priorities():
    candidates = [(date(2026, 7, 20), MarketRegime.TRENDING),
                  (date(2026, 7, 21), MarketRegime.INDECISIVE)]
    assert (select_curiosity_driven_replay_session(candidates, {})
            == select_deficit_replay_session(candidates, {}))


def test_curiosity_selector_empty_candidates():
    assert select_curiosity_driven_replay_session([], {"trending": 1.0}) is None
