"""Hermetic test for the Global Workspace integrator (Trunk VIII; research/123): safety-critical
contributions win + ignite + are broadcast to a real subscriber; sub-threshold winners don't ignite;
salience ordering + coalition are correct; empty input is handled. Exercises the vendored blinker bus.
"""

from __future__ import annotations

from nse_algo_trader.sentience.global_workspace import (
    GlobalWorkspace,
    WorkspaceContribution,
    salience_score,
)


def _c(source, kind="info", urgency=0.5, relevance=0.5, confidence=0.5, critical=False):
    return WorkspaceContribution(
        source=source, kind=kind, urgency=urgency, relevance=relevance,
        confidence=confidence, content=f"{source} says something", is_critical=critical,
    )


def test_critical_contribution_scores_max_and_wins():
    crit = _c("constitution", "safety", urgency=0.1, relevance=0.1, confidence=0.1, critical=True)
    assert salience_score(crit) == 1.0  # floored to max despite low factors
    ws = GlobalWorkspace()
    b = ws.run_cycle([_c("momentum", urgency=0.9, relevance=0.9, confidence=0.9), crit])
    assert b.winner_source == "constitution" and b.ignited and b.kind == "safety"


def test_ignited_broadcast_reaches_a_real_subscriber():
    ws = GlobalWorkspace()
    received = []
    ws.subscribe(lambda sender, broadcast=None, **_: received.append(broadcast))
    ws.run_cycle([_c("ethics_law", "safety", critical=True)])
    assert len(received) == 1 and received[0].winner_source == "ethics_law"


def test_sub_threshold_winner_does_not_ignite_or_broadcast():
    ws = GlobalWorkspace(ignition_threshold=0.9)
    received = []
    ws.subscribe(lambda sender, broadcast=None, **_: received.append(broadcast))
    b = ws.run_cycle([_c("weak", urgency=0.2, relevance=0.2, confidence=0.2)])
    assert b is not None and not b.ignited
    assert received == []  # nothing broadcast when nothing ignites
    assert ws.latest_broadcast is b  # current focus still cached


def test_coalition_groups_near_winners():
    ws = GlobalWorkspace(coalition_epsilon=0.1)
    b = ws.run_cycle([
        _c("a", urgency=0.8, relevance=0.8, confidence=0.8),
        _c("b", urgency=0.78, relevance=0.8, confidence=0.8),
        _c("c", urgency=0.1, relevance=0.1, confidence=0.1),
    ])
    assert "a" in b.coalition and "b" in b.coalition and "c" not in b.coalition


def test_empty_contributions_returns_none():
    assert GlobalWorkspace().run_cycle([]) is None


def test_highest_salience_advisory_wins_when_no_critical():
    ws = GlobalWorkspace(ignition_threshold=0.5)
    b = ws.run_cycle([
        _c("low", urgency=0.3, relevance=0.3, confidence=0.3),
        _c("high", urgency=0.9, relevance=0.8, confidence=0.7),
    ])
    assert b.winner_source == "high" and b.ignited
