"""Tests for the self-learning engine re-weighting — Bayesian-shrinkage weights + scorer tilt."""

from __future__ import annotations

import pytest

from nse_algo_trader.option_alpha.engine_performance_learner import (
    EnginePerformanceLearner,
    EnginePerformanceStore,
)
from nse_algo_trader.option_alpha.option_opportunity_scorer import (
    OpportunityFeatures,
    OptionOpportunityScorer,
    ProfitEngine,
)


def test_thin_history_stays_neutral(tmp_path):
    store = EnginePerformanceStore(tmp_path)
    store.record("theta", True, 100.0)  # a single win → must NOT swing the weight far from 1.0
    w = EnginePerformanceLearner(store).engine_weights()
    assert 0.95 <= w["theta"] <= 1.15  # shrinkage keeps a 1-trade engine near neutral


def test_proven_winner_upweighted_loser_downweighted(tmp_path):
    store = EnginePerformanceStore(tmp_path)
    for _ in range(40):
        store.record("theta", True, 50.0)   # theta always wins
        store.record("vega", False, -50.0)  # vega always loses
    w = EnginePerformanceLearner(store).engine_weights()
    assert w["theta"] > 1.2 and w["vega"] < 0.8  # tilt toward the winner, away from the loser
    assert w["vega"] >= 0.25  # never zeroed → still explores


def test_weight_floor(tmp_path):
    store = EnginePerformanceStore(tmp_path)
    for _ in range(100):
        store.record("gamma", False, -10.0)  # relentless loser
    assert EnginePerformanceLearner(store).engine_weights()["gamma"] >= 0.25


def test_scorer_applies_engine_weights(tmp_path):
    sc = OptionOpportunityScorer()
    # a rich name where Θ (0.5) normally beats ν; a strong DELTA weight flips selection to Δ
    feats = [OpportunityFeatures("A", richness=0.9, vrp=0.1, stressed_prob=0.0, is_range_bound=True,
                                 trend_conviction=0.4, abs_skew=0.0, abs_term_slope=0.0, is_expiry_day=False,
                                 pre_event=False)]
    base = sc.rank_universe(feats)["A"].best_engine
    tilted = sc.rank_universe(feats, engine_weights={"delta": 3.0})["A"].best_engine
    assert base is ProfitEngine.THETA and tilted is ProfitEngine.DELTA  # learned tilt changes the choice


def test_store_persists(tmp_path):
    s = EnginePerformanceStore(tmp_path)
    s.record("theta", True, 10.0)
    s.record("theta", False, -5.0)
    assert len(EnginePerformanceStore(tmp_path).load()) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
