"""Regime-conditioned terminal-price distribution — the forecast the structure optimizer prices trades against.

Given the volatility-regime engine's forecast σ, the directional verdict (drift), and the tenor to expiry,
this Monte-Carlo-samples the underlying's price AT EXPIRY under a fat-tailed, regime-mixture model:

    S_T = S_0 · exp((μ − ½σ²)·T + σ·√T·Z),   Z ~ Student-t(ν)

* **σ per regime** — a mixture over the regime posterior (calm / elevated / stressed each contribute their
  own vol, weighted by probability) so the distribution widens when the market is fragile, not a single
  lognormal.
* **fat tails** — Student-t with degrees-of-freedom ν set from the regime (calm → high ν ≈ Gaussian;
  stressed → low ν → heavy tails), scaled to unit variance so σ stays the intended vol.
* **drift μ** — from the arbiter's directional conviction (0 when NEUTRAL), so a trending name's terminal
  distribution shifts with the trend.

The optimizer prices every candidate structure's P&L across these terminal samples to get E[P&L], CVaR, and
P(profit) — the trade the distribution says pays best.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_SAMPLES = 20_000
_CALM_DOF = 12.0        # near-Gaussian tails in a calm regime
_STRESSED_DOF = 3.0     # heavy tails when stressed
_MAX_ANNUAL_DRIFT = 0.25  # a full-conviction directional read maps to at most this annualized drift


@dataclass(frozen=True)
class TerminalDistribution:
    """Monte-Carlo terminal prices for one underlying at one expiry (+ the tenor that produced them)."""

    spot: float
    tenor_years: float
    samples: np.ndarray  # shape (N,), simulated S_T

    def probability_above(self, level: float) -> float:
        return float(np.mean(self.samples >= level))


class TerminalDistributionModel:
    """Builds a regime-mixture, fat-tailed terminal-price distribution from the forecast σ + drift."""

    def __init__(self, n_samples: int = _SAMPLES, seed: int = 12345):
        self._n = n_samples
        self._rng = np.random.default_rng(seed)

    def simulate(
        self,
        spot: float,
        tenor_years: float,
        regime_forecast_sigma: float,
        regime_probabilities: tuple[float, ...] | None = None,
        regime_sigmas: tuple[float, ...] | None = None,
        directional_conviction: float = 0.0,
        directional_sign: int = 0,
    ) -> TerminalDistribution:
        """Simulate S_T. ``regime_probabilities``/``regime_sigmas`` (optional) give the mixture; else a single σ."""
        spot = float(spot)
        tenor = max(float(tenor_years), 1.0 / 365.0)  # never zero-tenor (same-day expiry → intraday floor)
        n = self._n

        sigma = self._mixture_sigma(regime_forecast_sigma, regime_probabilities, regime_sigmas, n)
        dof = self._degrees_of_freedom(regime_probabilities)
        z = self._unit_variance_student_t(dof, n)

        mu = _MAX_ANNUAL_DRIFT * float(min(max(directional_conviction, 0.0), 1.0)) * int(np.sign(directional_sign))
        drift = (mu - 0.5 * sigma**2) * tenor
        diffusion = sigma * np.sqrt(tenor) * z
        s_t = spot * np.exp(drift + diffusion)
        return TerminalDistribution(spot=spot, tenor_years=tenor, samples=s_t)

    def _mixture_sigma(self, forecast_sigma, probs, sigmas, n) -> np.ndarray:
        """Per-sample σ drawn from the regime posterior mixture; falls back to the single forecast σ."""
        base = max(float(forecast_sigma or 0.0), 1e-4)
        if probs and sigmas and len(probs) == len(sigmas) and abs(sum(probs) - 1.0) < 0.2 and len(probs) >= 2:
            p = np.asarray(probs, dtype=float)
            p = p / p.sum()
            regime_idx = self._rng.choice(len(p), size=n, p=p)
            regime_sig = np.asarray([max(float(s), 1e-4) for s in sigmas], dtype=float)
            return regime_sig[regime_idx]
        return np.full(n, base, dtype=float)

    @staticmethod
    def _degrees_of_freedom(probs) -> float:
        """Heavier tails as the stressed-regime probability rises (calm→~Gaussian, stressed→fat)."""
        if not probs or len(probs) < 2:
            return _CALM_DOF
        stressed_p = float(probs[-1])  # highest-variance regime is last
        return _STRESSED_DOF + (1.0 - stressed_p) * (_CALM_DOF - _STRESSED_DOF)

    def _unit_variance_student_t(self, dof: float, n: int) -> np.ndarray:
        """Student-t samples rescaled to unit variance so the intended σ is preserved."""
        raw = self._rng.standard_t(dof, size=n)
        var = dof / (dof - 2.0) if dof > 2.0 else 1.0
        return raw / np.sqrt(var)
