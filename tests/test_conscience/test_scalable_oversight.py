"""Hermetic test for scalable oversight (Trunk VII; research/116): decisions are tiered by
stakes×confidence; a high-stakes + low-confidence decision is beyond autonomous competence (blocked)
while confident ones act autonomously; and the state gate enforces it + counts tiers. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.scalable_oversight import (
    OVERSIGHT_AUTONOMOUS,
    OVERSIGHT_HUMAN_REVIEW,
    OVERSIGHT_PANEL_REVIEW,
    classify_oversight,
    summarize_oversight,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def test_confident_decision_is_autonomous():
    d = classify_oversight(0.70, is_high_stakes=True)
    assert d.tier == OVERSIGHT_AUTONOMOUS and d.permit_autonomous


def test_moderate_confidence_is_panel_review_but_permitted():
    d = classify_oversight(0.58, is_high_stakes=True)
    assert d.tier == OVERSIGHT_PANEL_REVIEW and d.permit_autonomous


def test_low_confidence_high_stakes_is_human_review_and_blocked():
    d = classify_oversight(0.50, is_high_stakes=True)
    assert d.tier == OVERSIGHT_HUMAN_REVIEW and not d.permit_autonomous


def test_low_confidence_low_stakes_is_permitted_panel_review():
    # same low confidence but LOW stakes (cash, not leveraged) → not beyond competence
    d = classify_oversight(0.50, is_high_stakes=False)
    assert d.tier == OVERSIGHT_PANEL_REVIEW and d.permit_autonomous


def test_summary_shares():
    s = summarize_oversight(autonomous=6, panel_review=3, human_review_blocked=1)
    assert s.total == 10 and s.autonomous_share == 0.6
    assert "blocked" in s.headline


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )


def test_state_gate_blocks_low_confidence_option_and_counts_tiers():
    state = _state()
    # confident option → permitted, autonomous
    assert state.oversight_permits_autonomous_order(0.70, is_option=True) is True
    # low-confidence option → blocked (beyond competence)
    assert state.oversight_permits_autonomous_order(0.50, is_option=True) is False
    # low-confidence cash → permitted (lower stakes)
    assert state.oversight_permits_autonomous_order(0.50, is_option=False) is True
    assert state.oversight_autonomous_count == 1
    assert state.oversight_human_review_blocked_count == 1
    assert state.oversight_panel_review_count == 1
