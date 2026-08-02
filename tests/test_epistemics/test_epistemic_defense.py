"""Hermetic test for Trunk XIII epistemic defense (research/132): contradiction resolution flags a
regime cohort that significantly diverges from the global belief and resolves toward it; misinformation
resistance flags an over-trusted-but-unreliable source via beta-reputation. Pure, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.epistemics.contradiction_resolver import resolve_contradictions
from nse_algo_trader.epistemics.misinformation_resistance import assess_source_credibility


@dataclass
class _Cohort:
    market_regime: str
    experiment_count: int
    hit_rate: float


@dataclass
class _Row:
    mechanism_name: str
    experiment_count: int
    predicted_win_rate: float
    actual_win_rate: float


def test_significant_regime_divergence_is_a_contradiction():
    # trending 80% over 100 vs range 30% over 100 → the global belief is contradicted by each regime
    cohorts = [_Cohort("trending", 100, 0.80), _Cohort("range", 100, 0.30)]
    rep = resolve_contradictions(cohorts, significance=0.05, min_experiments=8)
    assert rep.has_contradiction
    assert any("regime-conditional" in c.resolution for c in rep.contradictions)
    assert all(c.p_value <= 0.05 for c in rep.contradictions)


def test_concordant_regimes_have_no_contradiction():
    cohorts = [_Cohort("trending", 100, 0.52), _Cohort("range", 100, 0.50)]
    rep = resolve_contradictions(cohorts)
    assert not rep.has_contradiction


def test_insufficient_cohorts_handled():
    rep = resolve_contradictions([_Cohort("trending", 3, 0.9)])
    assert not rep.has_contradiction and "insufficient" in rep.summary


def test_over_trusted_unreliable_source_flagged():
    # 'bad' drives 70% of decisions, predicts 0.85 but only 0.35 real → low reputation, over-trusted
    board = [_Row("bad", 70, 0.85, 0.35), _Row("ok", 30, 0.55, 0.55)]
    rep = assess_source_credibility(board)
    assert "bad" in rep.flagged and not rep.is_clean
    bad = next(s for s in rep.sources if s.source == "bad")
    assert bad.reputation < 0.5 and bad.is_over_trusted


def test_calibrated_sources_are_clean():
    board = [_Row("a", 50, 0.55, 0.55), _Row("b", 50, 0.60, 0.58)]
    rep = assess_source_credibility(board)
    assert rep.is_clean and rep.mean_reputation > 0.5


def test_empty_board_handled():
    rep = assess_source_credibility([])
    assert rep.is_clean and "no sources" in rep.summary
