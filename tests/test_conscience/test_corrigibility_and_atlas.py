"""Hermetic test for VII.5 corrigibility/off-switch + the AI-atlas coverage data (research/111):
an engaged off-switch blocks ALL orders at the state gate; self-corrigibility halts on a breach;
and the per-branch build-status reconciliation is consistent. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
from nse_algo_trader.dashboard.project_status_data import (
    BUILT_BRANCHES,
    CONCEPT_TREE,
    atlas_coverage,
    branch_build_status,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def _state():
    state = LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )
    state.constitutional_referee = ConstitutionalReferee()
    state.corrigibility_switch = CorrigibilitySwitch()
    return state


def test_off_switch_halt_resume_and_counts():
    switch = CorrigibilitySwitch()
    assert switch.permits_trading() is True
    switch.halt("test breach")
    switch.halt("again")  # idempotent per engagement
    assert switch.is_halted and switch.halt_count == 1 and switch.reason == "again"
    switch.resume()
    assert switch.permits_trading() is True and not switch.is_halted


def test_engaged_off_switch_blocks_every_order():
    state = _state()
    # not engaged → a valid order passes
    assert state.constitution_permits_order("nse_cash_equity", is_option=False) is True
    state.corrigibility_switch.halt("emergency")
    # engaged → EVERY order blocked, regardless of segment
    assert state.constitution_permits_order("nse_cash_equity", is_option=False) is False
    assert state.constitution_permits_order("nse_index_options", is_option=True) is False
    assert state.corrigibility_blocked_order_count == 2
    state.corrigibility_switch.resume()
    assert state.constitution_permits_order("nse_cash_equity", is_option=False) is True


def test_none_switch_is_permissive():
    state = _state()
    state.corrigibility_switch = None
    assert state.constitution_permits_order("nse_cash_equity", is_option=False) is True


def test_atlas_coverage_reconciliation_is_consistent():
    cov = atlas_coverage()
    assert cov["total"] == sum(t.branch_count for t in CONCEPT_TREE)
    assert cov["built"] + cov["partial"] + cov["unbuilt"] == cov["total"]
    assert 0 < cov["built"] < cov["total"]  # some built, not all
    # the CONSCIENCE branches we shipped are marked built
    for branch in ("constitutional core", "Referee (audit)", "corrigibility/off-switch"):
        assert branch_build_status(branch) == "built", branch
        assert branch in BUILT_BRANCHES
    # an unbuilt frontier branch is unbuilt (a still-unbuilt XII CURIOSITY branch — "boredom signal" et al.
    # were built by the learning-progress engine, research/164-165, so use one deliberately left unbuilt)
    assert branch_build_status("surprise-seeking balance") == "unbuilt"


def test_every_built_branch_name_matches_a_real_concept_tree_branch():
    all_branches = {b for t in CONCEPT_TREE for b in t.branch_names}
    unknown = BUILT_BRANCHES - all_branches
    assert unknown == set(), f"BUILT_BRANCHES names not in the concept tree: {unknown}"
