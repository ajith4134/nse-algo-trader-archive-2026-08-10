"""Tests for the Option Opportunity Scorer — per-engine scoring, argmax, cross-sectional RV + rank."""

from __future__ import annotations

import pytest

from nse_algo_trader.option_alpha.option_opportunity_scorer import (
    OpportunityFeatures,
    OpportunityScoreLedger,
    OptionOpportunityScorer,
    ProfitEngine,
)


def _f(u, *, richness=0.5, vrp=0.05, stressed=0.0, range_bound=True, trend=0.0,
       skew=0.0, term=0.0, expiry=False, pre_event=False):
    return OpportunityFeatures(u, richness, vrp, stressed, range_bound, trend, skew, term, expiry, pre_event)


def _scorer(tmp_path):
    return OptionOpportunityScorer(OpportunityScoreLedger(tmp_path))


def test_scores_in_unit_interval(tmp_path):
    out = _scorer(tmp_path).rank_universe([_f("A"), _f("B", richness=0.9), _f("C", trend=0.8)], "2026-08-04")
    for o in out.values():
        for v in o.scores.as_dict().values():
            assert 0.0 <= v <= 1.0


def test_rich_calm_name_picks_theta(tmp_path):
    out = _scorer(tmp_path).rank_universe(
        [_f("RICH", richness=0.95, vrp=0.1, range_bound=True), _f("X"), _f("Y")], "2026-08-04")
    assert out["RICH"].best_engine is ProfitEngine.THETA
    assert out["RICH"].scores.theta > out["RICH"].scores.vega


def test_strong_trend_picks_delta(tmp_path):
    out = _scorer(tmp_path).rank_universe(
        [_f("TREND", trend=0.9, range_bound=False, richness=0.5), _f("X"), _f("Y")], "2026-08-04")
    assert out["TREND"].best_engine is ProfitEngine.DELTA


def test_cheap_calm_name_picks_vega(tmp_path):
    out = _scorer(tmp_path).rank_universe(
        [_f("CHEAP", richness=0.05, vrp=-0.02, range_bound=True), _f("X", richness=0.5), _f("Y", richness=0.5)],
        "2026-08-04")
    assert out["CHEAP"].best_engine is ProfitEngine.VEGA


def test_expiry_day_enables_gamma(tmp_path):
    out = _scorer(tmp_path).rank_universe(
        [_f("EXP", expiry=True, richness=0.1, trend=0.0), _f("X"), _f("Y")], "2026-08-04")
    assert out["EXP"].scores.gamma > 0.0


def test_relvalue_is_cross_sectional_not_absolute(tmp_path):
    # every name has the SAME skew → none is relatively dislocated → RV ~0.5, never dominates on normal skew
    out = _scorer(tmp_path).rank_universe(
        [_f(u, richness=0.9, vrp=0.1, skew=0.04, term=0.03) for u in ("A", "B", "C", "D")], "2026-08-04")
    for o in out.values():
        assert o.best_engine is ProfitEngine.THETA  # rich premium wins; equal skew gives no RV edge


def test_only_the_extreme_skew_name_gets_high_rv(tmp_path):
    feats = [_f("FLAT1", richness=0.4, skew=0.01), _f("FLAT2", richness=0.4, skew=0.01),
             _f("FLAT3", richness=0.4, skew=0.01), _f("EXTREME", richness=0.4, skew=0.20)]
    out = _scorer(tmp_path).rank_universe(feats, "2026-08-04")
    assert out["EXTREME"].scores.relvalue > out["FLAT1"].scores.relvalue


def test_no_edge_abstains(tmp_path):
    # mid richness, negative VRP (can't sell), NOT stressed (no tail bid), no trend, no skew → no engine has
    # a real edge → abstain. (Stress is NOT no-edge — it is a long-vol/tail edge, tested separately.)
    # rich richness (kills the buy-vol bid) BUT negative VRP (can't sell premium), calm, no trend/skew → the
    # one genuine no-edge corner → abstain.
    out = _scorer(tmp_path).rank_universe(
        [_f("DEAD", richness=0.9, vrp=-0.01, stressed=0.0, trend=0.0, skew=0.0, term=0.0, range_bound=True)],
        "2026-08-04")
    assert out["DEAD"].best_engine is None or out["DEAD"].best_score < 0.25


def test_stressed_regime_picks_long_vega(tmp_path):
    # a fragile/stressed surface → the edge is BUYING convexity (own the tail), not selling premium
    out = _scorer(tmp_path).rank_universe(
        [_f("STRESS", richness=0.6, stressed=0.9, trend=0.0, range_bound=False), _f("X"), _f("Y")], "2026-08-04")
    assert out["STRESS"].best_engine is ProfitEngine.VEGA


def test_ledger_persists_rows(tmp_path):
    _scorer(tmp_path).rank_universe([_f("A"), _f("B")], "2026-08-04")
    path = tmp_path / "opportunity_scores.jsonl"
    assert path.exists() and len(path.read_text().splitlines()) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
