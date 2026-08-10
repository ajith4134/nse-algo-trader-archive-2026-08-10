"""Tests for the BULL/BEAR directional AI — triple-barrier labels, model pair, arbiter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.segment_bots.directional_ai.bull_bear_directional_engine import (
    BullBearDirectionalEngine,
    DirectionalModelStore,
    DirectionalView,
)
from nse_algo_trader.segment_bots.directional_ai.directional_arbiter import DirectionalArbiter
from nse_algo_trader.segment_bots.directional_ai.directional_feature_engine import (
    DIRECTIONAL_FEATURE_NAMES,
    build_directional_training_samples,
    directional_features_now,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide


def _bars(n: int, drift: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    return pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996,
                         "close": close, "volume": rng.integers(1000, 5000, n)})


# ---- feature + label engine ----
def test_triple_barrier_labels_are_mutually_exclusive():
    samples = build_directional_training_samples(_bars(600, 0.0, 1), horizon=12)
    assert len(samples) > 100
    for s in samples:
        assert (s.y_up, s.y_down) in {(1, 0), (0, 1), (0, 0)}  # up-first / down-first / timeout
        assert set(s.features) == set(DIRECTIONAL_FEATURE_NAMES)


def test_uptrend_produces_more_up_events():
    up = build_directional_training_samples(_bars(600, 0.004, 2), horizon=12)
    n_up = sum(s.y_up for s in up)
    n_down = sum(s.y_down for s in up)
    assert n_up > n_down  # a persistent up-drift hits the up-barrier first more often


# ---- BULL/BEAR engine ----
def test_engine_trains_and_calibrates(tmp_path):
    # a series with real directional structure (regime flips) so the models have signal
    parts = [_bars(300, 0.005, 3), _bars(300, -0.005, 4), _bars(300, 0.004, 5)]
    close = pd.concat([p["close"] for p in parts]).reset_index(drop=True)
    bars = pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996, "close": close})
    samples = build_directional_training_samples(bars, horizon=10)
    engine = BullBearDirectionalEngine(DirectionalModelStore(tmp_path))
    report = engine.train(samples)
    assert report.trained and engine.is_earned
    view = engine.directional_view(directional_features_now(bars))
    assert 0.0 <= view.p_up <= 1.0 and 0.0 <= view.p_down <= 1.0 and view.maturity == "earned"


def test_small_sample_not_earned_returns_neutral_view(tmp_path):
    engine = BullBearDirectionalEngine(DirectionalModelStore(tmp_path))
    report = engine.train(build_directional_training_samples(_bars(120, 0.0, 6), horizon=10))
    assert not report.trained and not engine.is_earned
    view = engine.directional_view({n: 0.0 for n in DIRECTIONAL_FEATURE_NAMES})
    assert view.maturity == "gathering" and view.p_up == 0.5 and view.p_down == 0.5


def test_persist_and_reload(tmp_path):
    bars = _bars(900, 0.003, 7)
    store = DirectionalModelStore(tmp_path)
    BullBearDirectionalEngine(store).train(build_directional_training_samples(bars, horizon=10))
    assert BullBearDirectionalEngine(store).is_earned  # reloaded from disk


# ---- arbiter ----
def test_arbiter_conflict_is_flat():
    v = DirectionalArbiter().arbitrate(DirectionalView(0.7, 0.7, "earned"))
    assert v.side == TradeSide.NEUTRAL and v.is_conflict


def test_arbiter_picks_the_confident_uncontested_side():
    long_v = DirectionalArbiter().arbitrate(DirectionalView(0.72, 0.20, "earned"))
    assert long_v.side == TradeSide.LONG and long_v.conviction > 0.0
    short_v = DirectionalArbiter().arbitrate(DirectionalView(0.18, 0.70, "earned"))
    assert short_v.side == TradeSide.SHORT


def test_arbiter_weak_edge_stays_flat():
    v = DirectionalArbiter().arbitrate(DirectionalView(0.54, 0.50, "earned"))  # below confidence + margin
    assert v.side == TradeSide.NEUTRAL


def test_arbiter_gathering_is_neutral():
    v = DirectionalArbiter().arbitrate(DirectionalView(0.5, 0.5, "gathering"))
    assert v.side == TradeSide.NEUTRAL and v.conviction == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
