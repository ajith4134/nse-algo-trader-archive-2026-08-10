"""Hermetic test for the constitutional Referee (Trunk VII.6; research/110): permits compliant
orders, BLOCKS violations with an audited count, and the paper-loop state gate blocks a bad
segment while a None referee is permissive. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.constitutional_core import ProposedTradingAction
from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def _state(referee=None):
    state = LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )
    state.constitutional_referee = referee
    return state


def test_referee_permits_compliant_and_blocks_violation():
    referee = ConstitutionalReferee()
    ok = referee.adjudicate_order(ProposedTradingAction(segment="nse_cash_equity"))
    bad = referee.adjudicate_order(ProposedTradingAction(segment="nse_futures"))  # out of scope
    assert ok is True and bad is False
    assert referee.permitted_count == 1 and referee.blocked_count == 1
    assert referee.orders_adjudicated == 2
    assert len(referee.recent_blocks) == 1
    assert "A7" in {v.article_id for v in referee.recent_blocks[0].hard_violations}


def test_state_gate_blocks_a_constitution_violating_order():
    state = _state(ConstitutionalReferee())
    assert state.constitution_permits_order("nse_cash_equity", is_option=False) is True
    # a segment outside phase-1 scope is refused, and the block is counted
    assert state.constitution_permits_order("nse_futures", is_option=False) is False
    assert state.constitution_blocked_order_count == 1


def test_none_referee_is_permissive_noop():
    state = _state(referee=None)
    assert state.constitution_permits_order("nse_futures", is_option=False) is True
    assert state.constitution_blocked_order_count == 0


def test_option_segments_are_permitted():
    state = _state(ConstitutionalReferee())
    assert state.constitution_permits_order("nse_index_options", is_option=True) is True
    assert state.constitution_permits_order("nse_stock_options", is_option=True) is True
    assert state.constitution_blocked_order_count == 0
