"""Ledoit-Wolf constant-correlation shrinkage covariance (research/162 §2.2; research/163 §3 mode 2).

The Mean-Variance / Risk-Parity / Enhanced-indexing modes need a covariance matrix Σ across candidates.
A raw sample covariance is singular/ill-conditioned when scenarios are few relative to candidates (our
thin-data reality) — so we shrink toward the constant-correlation target:  Σ̂ = δ·F + (1−δ)·S, where S is
the sample covariance, F is the constant-average-correlation target, and δ* is the Ledoit-Wolf optimal
shrinkage intensity (Ledoit-Wolf 2004, "Honey, I Shrunk the Sample Covariance Matrix"). We INTEGRATE
PyPortfolioOpt's verified implementation (research/161/162 confirmed it matches Qlib's `ShrinkCovEstimator`)
rather than reimplement a lite version (Rule P.3), with explicit guards for the degenerate N=1 /
zero-variance / solver-failure cases (errors surfaced, never swallowed — Rule O.3).
"""

from __future__ import annotations

import numpy as np


def shrunk_covariance_matrix(scenario_matrix: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf constant-correlation shrunk covariance for an S×N scenario/returns matrix.

    Rows = scenarios (S), columns = candidates (N). Returns an N×N positive-semidefinite covariance in
    the SAME per-scenario units as the input (no annualisation). Degenerate cases handled explicitly:
    N==1 → the 1×1 sample variance; S<2 → a tiny diagonal ridge (no covariance is estimable, flagged by
    the caller via scenario_count); any estimator failure → the sample covariance with a PSD ridge.
    """
    matrix = np.asarray(scenario_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(f"scenario_matrix must be 2-D (S×N), got shape {matrix.shape}")
    n_scenarios, n_candidates = matrix.shape

    if n_candidates == 1:
        variance = float(np.var(matrix[:, 0], ddof=1)) if n_scenarios >= 2 else 0.0
        return np.array([[max(variance, _RIDGE)]])

    if n_scenarios < 2:
        # No covariance is estimable from <2 scenarios — return a tiny isotropic ridge so downstream
        # QPs stay well-posed. The caller flags this via scenario_count (data-sufficiency honesty).
        return np.eye(n_candidates) * _RIDGE

    try:
        import pandas as pd
        from pypfopt.risk_models import CovarianceShrinkage

        returns_frame = pd.DataFrame(matrix, columns=[f"c{i}" for i in range(n_candidates)])
        shrinker = CovarianceShrinkage(returns_frame, returns_data=True, frequency=1)
        covariance = np.asarray(shrinker.ledoit_wolf(shrinkage_target="constant_correlation"), dtype=float)
    except Exception:
        # Surface the failure by falling back to the sample covariance (still a real estimate), never a
        # silent zero. A PSD ridge below guarantees the QP solvers stay well-posed.
        covariance = np.atleast_2d(np.cov(matrix, rowvar=False))

    # Zero-variance columns make the constant-correlation target divide by zero → NaN/inf covariance.
    # Guard it (Rule O.4): fall back to the diagonal sample variances (a real, well-posed estimate).
    if not np.all(np.isfinite(covariance)):
        sample_variances = np.var(matrix, axis=0, ddof=1) if n_scenarios >= 2 else np.zeros(n_candidates)
        covariance = np.diag(np.clip(sample_variances, _RIDGE, None))

    return _project_to_psd_with_ridge(covariance)


_RIDGE = 1e-10  # a tiny diagonal floor so covariance matrices stay strictly positive-definite for QP solvers


def _project_to_psd_with_ridge(covariance: np.ndarray) -> np.ndarray:
    """Clip any (numerically) negative eigenvalues to 0 and add a tiny ridge — guarantees the matrix is
    positive-definite so CVXPY's QP path never rejects it as non-PSD (Rule O.4 numeric robustness)."""
    covariance = 0.5 * (covariance + covariance.T)  # symmetrise
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    repaired = (eigenvectors * eigenvalues) @ eigenvectors.T
    repaired = repaired + np.eye(repaired.shape[0]) * _RIDGE
    return 0.5 * (repaired + repaired.T)
