"""Hermetic test for higher-order monitoring + indicator scoreboard (Trunk VIII; research/131): the
metacognition health-state classifier + the faculty scoreboard ranking. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.sentience.global_workspace import WorkspaceBroadcast, WorkspaceContribution
from nse_algo_trader.sentience.indicator_scoreboard import build_indicator_scoreboard
from nse_algo_trader.sentience.workspace_metacognition import (
    HEALTHY,
    OVER_IGNITING,
    STARVED,
    UNDER_IGNITING,
    assess_metacognition,
)


def test_over_igniting_detected():
    m = assess_metacognition([(True, 2)] * 6)
    assert m.health_state == OVER_IGNITING and m.ignition_rate == 1.0


def test_under_igniting_detected():
    m = assess_metacognition([(False, 2)] * 6)
    assert m.health_state == UNDER_IGNITING and m.ignition_rate == 0.0


def test_starved_detected():
    m = assess_metacognition([(False, 0)] * 6)
    assert m.health_state == STARVED


def test_healthy_mix():
    m = assess_metacognition([(True, 2), (False, 2), (True, 3), (False, 2)])
    assert m.health_state == HEALTHY and m.is_healthy


def test_empty_log_is_healthy_placeholder():
    m = assess_metacognition([])
    assert m.cycles_observed == 0 and m.is_healthy


def _c(source, kind="safety", u=0.6, r=0.6, cf=0.6):
    return WorkspaceContribution(source, kind, u, r, cf, "c")


def _b(source):
    return WorkspaceBroadcast(winner_source=source, kind="safety", content="c", salience=0.7, ignited=True)


def test_scoreboard_ranks_and_counts_dominance():
    contribs = [_c("goal_integrity", u=0.9, r=0.9, cf=0.9), _c("interp", "risk", 0.4, 0.5, 0.5)]
    history = [_b("goal_integrity"), _b("goal_integrity"), _b("interp")]
    sb = build_indicator_scoreboard(contribs, history)
    assert sb.leader == "goal_integrity"
    assert sb.scores[0].times_dominant == 2 and sb.scores[1].times_dominant == 1


def test_scoreboard_empty_when_no_contributions():
    sb = build_indicator_scoreboard([], [])
    assert sb.leader is None and not sb.scores
