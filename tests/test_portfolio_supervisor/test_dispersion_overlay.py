"""Tests for the dispersion overlay (§8b) — implied-correlation math + trade selection."""

from __future__ import annotations

import pytest

from nse_algo_trader.portfolio_supervisor.dispersion_overlay import (
    DispersionOverlay,
    ImpliedCorrelationStore,
    implied_correlation,
)


def test_implied_correlation_recovers_known_value():
    # equal weights, equal constituent vols σ_c; with index vol σ_i the closed form gives a known ρ.
    n = 4
    w = [1 / n] * n
    sigma_c = [0.30] * n
    # construct σ_index for a target ρ=0.5: index_var = Σwᵢ²σᵢ² + ρ·Σᵢ≠ⱼ wᵢwⱼσᵢσⱼ
    own = sum((wi**2) * (s**2) for wi, s in zip(w, sigma_c))
    cross = sum(w[i] * w[j] * sigma_c[i] * sigma_c[j] for i in range(n) for j in range(n) if i != j)
    index_var = own + 0.5 * cross
    sigma_index = index_var**0.5
    assert implied_correlation(sigma_index, w, sigma_c) == pytest.approx(0.5, abs=1e-6)


def test_high_correlation_sells_index_buys_constituents():
    overlay = DispersionOverlay()
    # index IV well above the basket → high implied ρ → sell index / buy constituents
    constituents = {f"S{i}": 0.20 for i in range(8)}
    sig = overlay.assess("NIFTY", index_iv=0.30, constituent_ivs=constituents)
    assert sig.action == "sell_index_buy_constituents"
    assert sig.implied_correlation > 0.55 and sig.conviction > 0.0


def test_low_correlation_buys_index_sells_constituents():
    overlay = DispersionOverlay()
    # index IV near the basket (low ρ) → buy index / sell constituents
    constituents = {f"S{i}": 0.30 for i in range(8)}
    sig = overlay.assess("NIFTY", index_iv=0.16, constituent_ivs=constituents)
    assert sig.action == "buy_index_sell_constituents"


def test_abstains_on_too_few_constituents():
    overlay = DispersionOverlay()
    sig = overlay.assess("NIFTY", index_iv=0.30, constituent_ivs={"S0": 0.2, "S1": 0.2})
    assert sig.action == "abstain" and sig.n_constituents == 2


def test_earned_history_gates_non_extreme_signals(tmp_path):
    overlay = DispersionOverlay(ImpliedCorrelationStore(tmp_path))
    constituents = {f"S{i}": 0.20 for i in range(8)}
    # seed 35 sessions of ρ≈0.9 (index_iv 0.191) so a merely-rich ρ≈0.6 reading is not top-percentile
    for _ in range(35):
        overlay.assess("NIFTY", index_iv=0.191, constituent_ivs=constituents)
    modest = overlay.assess("NIFTY", index_iv=0.161, constituent_ivs=constituents)  # ρ≈0.6: rich but below history
    assert modest.correlation_percentile is not None
    assert 0.55 <= modest.implied_correlation < 0.99  # rich vs the absolute threshold, not clamped
    assert modest.action == "abstain"  # gated: not extreme vs its own history


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
