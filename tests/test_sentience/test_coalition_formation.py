"""Hermetic test for coalition formation (Trunk VIII; research/127): co-active same-kind signals
corroborate and their combined salience is amplified above the lone winner; amplification is capped
and clamped; a corroborated coalition can ignite when a lone member wouldn't. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.sentience.coalition_formation import form_coalition
from nse_algo_trader.sentience.global_workspace import GlobalWorkspace, WorkspaceContribution


def _c(source, kind, urgency=0.6, relevance=0.6, confidence=0.6):
    return WorkspaceContribution(
        source=source, kind=kind, urgency=urgency, relevance=relevance,
        confidence=confidence, content="c",
    )


def test_lone_winner_combined_equals_base():
    co = form_coalition([(_c("a", "safety"), 0.6)])
    assert co.members == ("a",) and not co.is_corroborated
    assert co.combined_salience == co.base_salience == 0.6


def test_same_kind_coalition_amplifies():
    co = form_coalition([(_c("a", "safety"), 0.60), (_c("b", "safety"), 0.58),
                         (_c("c", "safety"), 0.57)])
    assert co.corroborating_count == 3 and co.is_corroborated
    assert co.combined_salience > co.base_salience  # amplified
    assert abs(co.combined_salience - (0.60 + 0.05 * 2)) < 1e-9


def test_amplification_capped_and_clamped():
    scored = [(_c(f"s{i}", "safety"), 0.95) for i in range(10)]
    co = form_coalition(scored, cap=0.20)
    assert co.combined_salience <= 1.0  # clamped
    assert co.combined_salience - co.base_salience <= 0.20 + 1e-9  # capped


def test_different_kind_near_signal_does_not_corroborate():
    co = form_coalition([(_c("a", "safety"), 0.60), (_c("b", "risk"), 0.59)])
    assert co.corroborating_count == 1 and not co.is_corroborated
    assert co.combined_salience == co.base_salience


def test_corroborated_coalition_ignites_when_lone_would_not():
    ws = GlobalWorkspace(ignition_threshold=0.62)
    # each contribution alone scores 0.60 (< 0.62) but two same-kind corroborate to 0.65 → ignite
    b = ws.run_cycle([_c("a", "safety"), _c("b", "safety")])
    assert b.ignited and b.salience > 0.62
    # a single one does not ignite
    b1 = ws.run_cycle([_c("a", "safety")])
    assert not b1.ignited
