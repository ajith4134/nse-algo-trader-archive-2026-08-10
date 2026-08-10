"""Tests for the INDEX-OPTION learned win-probability head (LightGBM + isotonic + walk-forward + Rule Q)."""

from __future__ import annotations

import numpy as np
import pytest

from nse_algo_trader.segment_bots.index_option_bot.win_probability_head import (
    FEATURE_NAMES,
    IndexOptionWinProbabilityHead,
    LabelledTrial,
    WinProbabilityHeadStore,
)


def _signal_trials(n: int, seed: int) -> list[LabelledTrial]:
    """Labelled trials where the outcome truly depends on a few features, so a real model can learn."""
    rng = np.random.default_rng(seed)
    trials = []
    for i in range(n):
        f = {name: float(rng.normal()) for name in FEATURE_NAMES}
        logit = (
            1.2 * f["iv_rank"]
            + 1.0 * f["variance_risk_premium"]
            + 0.8 * f["structure_net_theta"]
            - 0.5 * f["regime_stressed_prob"]
        )
        won = rng.random() < 1.0 / (1.0 + np.exp(-logit))
        trials.append(LabelledTrial(features=f, won=bool(won), entry_epoch=float(i)))
    return trials


def test_trains_earns_and_beats_base_rate(tmp_path):
    head = IndexOptionWinProbabilityHead(WinProbabilityHeadStore(tmp_path))
    report = head.train(_signal_trials(500, seed=1))
    assert report.trained and head.is_earned
    assert report.walk_forward_auc is not None and report.walk_forward_auc > 0.6  # learns real signal
    assert report.n_wins >= 20 and report.n_losses >= 20


def test_shap_surfaces_the_true_signal_features(tmp_path):
    head = IndexOptionWinProbabilityHead(WinProbabilityHeadStore(tmp_path))
    report = head.train(_signal_trials(500, seed=2))
    top = {name for name, _ in report.top_features[:4]}
    # the features the synthetic label actually depends on should dominate the SHAP ranking
    assert {"iv_rank", "variance_risk_premium"} & top


def test_calibrated_probability_ranks_edge_and_is_bounded(tmp_path):
    head = IndexOptionWinProbabilityHead(WinProbabilityHeadStore(tmp_path))
    head.train(_signal_trials(500, seed=3))
    high = {n: 0.0 for n in FEATURE_NAMES}
    high.update({"iv_rank": 2.0, "variance_risk_premium": 2.0, "structure_net_theta": 1.0})
    low = {n: 0.0 for n in FEATURE_NAMES}
    low.update({"iv_rank": -2.0, "variance_risk_premium": -2.0, "regime_stressed_prob": 2.0})
    p_hi, p_lo = head.calibrated_win_probability(high), head.calibrated_win_probability(low)
    assert 0.0 <= p_lo < p_hi <= 1.0


def test_persists_and_reloads_earned_model(tmp_path):
    store = WinProbabilityHeadStore(tmp_path)
    IndexOptionWinProbabilityHead(store).train(_signal_trials(400, seed=4))
    reloaded = IndexOptionWinProbabilityHead(store)
    assert reloaded.is_earned
    assert reloaded.calibrated_win_probability({n: 0.0 for n in FEATURE_NAMES}) is not None


def test_small_sample_is_not_earned_and_passthrough(tmp_path):
    """Rule Q: below the trial threshold the head does not train; the caller falls back to deterministic."""
    head = IndexOptionWinProbabilityHead(WinProbabilityHeadStore(tmp_path))
    report = head.train(_signal_trials(40, seed=5))
    assert not report.trained and not head.is_earned
    assert head.calibrated_win_probability({n: 0.0 for n in FEATURE_NAMES}) is None  # passthrough
    assert "not earned" in report.optimism_note


def test_class_imbalance_blocks_training(tmp_path):
    head = IndexOptionWinProbabilityHead(WinProbabilityHeadStore(tmp_path))
    all_wins = [LabelledTrial({n: 0.0 for n in FEATURE_NAMES}, won=True, entry_epoch=float(i)) for i in range(300)]
    report = head.train(all_wins)
    assert not report.trained  # no losses → cannot learn a boundary


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
