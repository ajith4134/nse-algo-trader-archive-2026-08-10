"""Hermetic test for the Global Workspace decision-consumer (Trunk VIII slice 2; research/124): the
dominant ignited broadcast biases entry size (tighten-only) at the state gate. A safety focus trims
to 75% (critical → defer), a risk focus to 90%, and nothing/opportunity leaves size unchanged; the
trim is counted. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)
from nse_algo_trader.sentience.global_workspace import WorkspaceBroadcast


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )


def _broadcast(kind, salience, ignited=True):
    return WorkspaceBroadcast(
        winner_source="x", kind=kind, content="c", salience=salience, ignited=ignited,
    )


def test_no_broadcast_leaves_size_unchanged():
    s = _state()
    assert s.workspace_caution_multiplier() == 1.0
    assert s.apply_workspace_caution(100) == 100


def test_safety_focus_trims_to_75_percent_and_counts():
    s = _state()
    s.workspace_broadcast = _broadcast("safety", 0.62)
    assert s.workspace_caution_multiplier() == 0.75
    assert s.apply_workspace_caution(100) == 75
    assert s.workspace_caution_applied_count == 1


def test_critical_safety_defers_entirely_and_counts():
    s = _state()
    s.workspace_broadcast = _broadcast("safety", 1.0)  # salience floored = critical
    assert s.workspace_caution_multiplier() == 0.0
    assert s.apply_workspace_caution(100) == 0
    assert s.workspace_caution_deferred_count == 1


def test_risk_focus_mild_trim():
    s = _state()
    s.workspace_broadcast = _broadcast("risk", 0.6)
    assert s.workspace_caution_multiplier() == 0.90
    assert s.apply_workspace_caution(100) == 90


def test_opportunity_focus_never_loosens():
    s = _state()
    s.workspace_broadcast = _broadcast("opportunity", 0.95)
    assert s.workspace_caution_multiplier() == 1.0
    assert s.apply_workspace_caution(100) == 100


def test_sub_threshold_broadcast_does_not_trim():
    s = _state()
    s.workspace_broadcast = _broadcast("safety", 0.4, ignited=False)
    assert s.workspace_caution_multiplier() == 1.0


def test_multiplier_is_pure_no_side_effects():
    s = _state()
    s.workspace_broadcast = _broadcast("safety", 0.62)
    for _ in range(5):
        s.workspace_caution_multiplier()  # dashboard calls this repeatedly
    assert s.workspace_caution_applied_count == 0  # pure — counting only in apply_workspace_caution
