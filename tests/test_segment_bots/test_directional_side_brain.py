"""Tests for DirectionalSideBrain — the lifecycle glue that turns a bot's price history into a side."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.segment_bots.directional_ai.directional_side_brain import DirectionalSideBrain
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide


def _bars(n: int, drift: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    return pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996,
                         "close": close, "volume": rng.integers(1000, 5000, n)})


def test_thin_history_stays_neutral_gathering(tmp_path):
    brain = DirectionalSideBrain(tmp_path)
    v = brain.verdict_for("RELIANCE", _bars(100, 0.0, 1))  # below the maturity ladder
    assert v.side == TradeSide.NEUTRAL and "gathering" in v.rationale


def test_none_or_empty_prices_is_neutral(tmp_path):
    brain = DirectionalSideBrain(tmp_path)
    assert brain.side_for("X", None) == TradeSide.NEUTRAL
    assert brain.side_for("X", pd.Series([], dtype=float)) == TradeSide.NEUTRAL


def test_close_only_series_accepted(tmp_path):
    brain = DirectionalSideBrain(tmp_path)
    v = brain.verdict_for("NIFTY", pd.Series(np.linspace(100, 110, 120)))  # Series → bars, still gathering
    assert v.side == TradeSide.NEUTRAL


def test_earned_brain_returns_a_directional_verdict(tmp_path):
    # a series with real regime structure so the pair earns + the arbiter can take a side
    parts = [_bars(300, 0.005, 3), _bars(300, -0.005, 4), _bars(400, 0.004, 5)]
    close = pd.concat([p["close"] for p in parts]).reset_index(drop=True)
    bars = pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996, "close": close})
    brain = DirectionalSideBrain(tmp_path)
    v = brain.verdict_for("BANKNIFTY", bars)
    assert v.side in (TradeSide.LONG, TradeSide.SHORT, TradeSide.NEUTRAL)
    assert 0.0 <= v.p_up <= 1.0 and 0.0 <= v.p_down <= 1.0
    # once earned it is persisted + cached — a second call must not be gathering
    v2 = brain.verdict_for("BANKNIFTY", bars)
    assert "gathering" not in v2.rationale


def test_engine_is_cached_and_persisted(tmp_path):
    parts = [_bars(300, 0.005, 3), _bars(300, -0.005, 4), _bars(400, 0.004, 5)]
    close = pd.concat([p["close"] for p in parts]).reset_index(drop=True)
    bars = pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996, "close": close})
    DirectionalSideBrain(tmp_path).verdict_for("SBIN", bars)  # trains + persists
    reloaded = DirectionalSideBrain(tmp_path)
    assert reloaded._engine_for("SBIN").is_earned  # loaded straight from disk, no retrain


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_per_cycle_training_budget_throttles_cold_start(tmp_path):
    # deep, structured series so a brain WOULD earn if trained
    import numpy as np, pandas as pd
    parts = [_bars(300, 0.005, 3), _bars(300, -0.005, 4), _bars(400, 0.004, 5)]
    close = pd.concat([p["close"] for p in parts]).reset_index(drop=True)
    bars = pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996, "close": close})
    brain = DirectionalSideBrain(tmp_path, max_new_trains_per_cycle=1)
    brain.begin_cycle()
    a = brain.verdict_for("AAA", bars)   # 1st train allowed → earns
    b = brain.verdict_for("BBB", bars)   # budget spent → deferred to a later cycle (gathering)
    assert "gathering" not in a.rationale
    assert "gathering" in b.rationale
    brain.begin_cycle()                  # new cycle → budget refreshed
    b2 = brain.verdict_for("BBB", bars)
    assert "gathering" not in b2.rationale  # now trains + earns
