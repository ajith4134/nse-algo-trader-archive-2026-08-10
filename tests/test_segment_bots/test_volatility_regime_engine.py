"""Tests for the INDEX-OPTION bot's volatility-regime engine — unit + invariant + adversarial + maturity."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.segment_bots.index_option_bot.volatility_regime_engine import (
    VolatilityRegimeEngine,
    VolatilityRegimeStore,
)


def _clustered_price_series(n: int, seed: int, stress: tuple[int, int] | None = None) -> pd.Series:
    """A GARCH-like return series with vol clustering (and an optional stress window) -> price path."""
    rng = np.random.default_rng(seed)
    returns = np.zeros(n)
    vol = 0.01
    for t in range(1, n):
        bump = 0.02 if stress and stress[0] < t < stress[1] else 0.0
        vol = 0.004 + 0.85 * vol + 0.10 * abs(returns[t - 1]) + bump
        returns[t] = rng.normal(0.0, max(vol, 0.003))
    return pd.Series(100.0 * np.exp(np.cumsum(returns)))


def test_fits_and_returns_earned_state(tmp_path):
    store = VolatilityRegimeStore(tmp_path)
    engine = VolatilityRegimeEngine("NIFTY", store)
    state = engine.fit_and_state(_clustered_price_series(600, seed=1), implied_vol=0.16)

    assert state.maturity == "earned"
    assert state.n_observations >= 250
    assert state.garch_forecast_sigma > 0.0
    assert state.har_forecast_sigma > 0.0
    assert state.blended_forecast_sigma > 0.0
    assert state.variance_risk_premium is not None


def test_regime_probabilities_form_a_simplex(tmp_path):
    engine = VolatilityRegimeEngine("BANKNIFTY", VolatilityRegimeStore(tmp_path))
    state = engine.fit_and_state(_clustered_price_series(650, seed=2, stress=(300, 360)))
    total = sum(state.regime_probabilities)
    assert math.isclose(total, 1.0, abs_tol=1e-6)
    assert all(0.0 <= p <= 1.0 for p in state.regime_probabilities)
    assert 0 <= state.regime_index < len(state.regime_probabilities)


def test_blended_forecast_is_between_the_two_forecasts(tmp_path):
    engine = VolatilityRegimeEngine("FINNIFTY", VolatilityRegimeStore(tmp_path))
    state = engine.fit_and_state(_clustered_price_series(500, seed=3))
    lo = min(state.garch_forecast_sigma, state.har_forecast_sigma)
    hi = max(state.garch_forecast_sigma, state.har_forecast_sigma)
    assert lo - 1e-9 <= state.blended_forecast_sigma <= hi + 1e-9


def test_small_sample_gates_to_gathering_not_a_false_calm(tmp_path):
    """Rule Q: below the fit threshold the engine must report 'gathering', never a silent 'calm'."""
    engine = VolatilityRegimeEngine("MIDCPNIFTY", VolatilityRegimeStore(tmp_path))
    state = engine.fit_and_state(_clustered_price_series(80, seed=4), implied_vol=0.15)
    assert state.maturity == "gathering"
    assert state.regime_label == "gathering"
    assert state.blended_forecast_sigma > 0.0  # still produces a usable forecast (EWMA fallback)
    assert not state.is_premium_harvest_regime()  # never signals a harvest while immature


def test_positive_vrp_in_calm_regime_flags_harvest(tmp_path):
    """A low-vol calm series with a high implied vol should read as a premium-harvest regime."""
    rng = np.random.default_rng(9)
    calm = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, 500))))  # steady low vol
    engine = VolatilityRegimeEngine("NIFTY", VolatilityRegimeStore(tmp_path))
    state = engine.fit_and_state(calm, implied_vol=0.40)  # implied far above realized
    assert state.variance_risk_premium is not None and state.variance_risk_premium > 0.0
    assert state.regime_label in ("calm", "elevated")
    assert state.is_premium_harvest_regime()


def test_adversarial_flat_and_degenerate_inputs_do_not_crash(tmp_path):
    engine = VolatilityRegimeEngine("NIFTY", VolatilityRegimeStore(tmp_path))
    # flat prices (zero returns), a one-point series, and NaNs/zeros must not raise
    for series in (pd.Series([100.0] * 400), pd.Series([100.0]), pd.Series([0.0, 100.0, 100.0])):
        state = engine.fit_and_state(series, implied_vol=0.2)
        assert state.blended_forecast_sigma >= 0.0
        assert math.isclose(sum(state.regime_probabilities), 1.0, abs_tol=1e-6)


def test_state_is_persisted_and_reloadable(tmp_path):
    store = VolatilityRegimeStore(tmp_path)
    engine = VolatilityRegimeEngine("NIFTY", store)
    engine.fit_and_state(_clustered_price_series(400, seed=5), implied_vol=0.16)
    latest = store.load_latest("NIFTY")
    assert latest is not None
    assert latest["underlying"] == "NIFTY"
    assert "blended_forecast_sigma" in latest


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
