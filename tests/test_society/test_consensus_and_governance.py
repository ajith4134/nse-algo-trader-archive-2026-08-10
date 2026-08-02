"""Hermetic test for Trunk VI society (research/136): consensus aggregates weighted desk opinions +
resolves conflict/deadlock; governance classifies desks trusted vs quarantined by reputation. Pure.
"""

from __future__ import annotations

from nse_algo_trader.society.consensus_resolution import AgentOpinion, resolve_consensus
from nse_algo_trader.society.multi_agent_governance import govern_agents


def test_agreeing_desks_reach_consensus():
    ops = [AgentOpinion("momentum", 0.60, 1.0), AgentOpinion("meanrev", 0.62, 1.0)]
    v = resolve_consensus(ops)
    assert v.is_consensus and abs(v.consensus_probability - 0.61) < 1e-9 and v.conflict < 0.2


def test_split_desks_deadlock_defers_to_highest_weight():
    ops = [AgentOpinion("strong", 0.85, 3.0), AgentOpinion("weak", 0.15, 1.0)]
    v = resolve_consensus(ops)
    assert not v.is_consensus and v.decisive_agent == "strong"
    assert "DEADLOCK" in v.summary and v.consensus_probability > 0.5  # tilted toward the heavier desk


def test_weighted_mean_is_track_record_weighted():
    ops = [AgentOpinion("a", 0.90, 3.0), AgentOpinion("b", 0.50, 1.0)]
    v = resolve_consensus(ops)
    assert abs(v.consensus_probability - (0.90 * 3 + 0.50 * 1) / 4) < 1e-9


def test_no_weighted_desks_handled():
    v = resolve_consensus([AgentOpinion("x", 0.5, 0.0)])
    assert v.participant_count == 0 and not v.is_consensus


def test_governance_trusts_and_quarantines_by_reputation():
    gr = govern_agents({"proven": 0.8, "ok": 0.5, "poor": 0.1})
    assert "proven" in gr.trusted and "ok" in gr.trusted
    assert "poor" in gr.quarantined and "poor" not in gr.trusted
    assert gr.standings[0].agent == "proven"  # reputation-desc


def test_governance_empty_handled():
    gr = govern_agents({})
    assert not gr.standings and "no desks" in gr.summary


def test_governance_mid_reputation_neither_trusted_nor_quarantined():
    gr = govern_agents({"mid": 0.35}, trust_threshold=0.5, quarantine_threshold=0.25)
    assert "mid" not in gr.trusted and "mid" not in gr.quarantined
