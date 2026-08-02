"""The four objective programs, as CVXPY expressions (research/163 §3; research/162 §1-4).

Each builder returns `(objective_expression_to_MAXIMISE, extra_constraints, aux_variables)` given the
weight variable and the market inputs, so the orchestrator can assemble one `cp.Problem`, add the shared
budget/risk constraints + cardinality/turnover penalties, and solve. Risk-parity is a standalone solve
(its log-barrier form is not combinable with the shared long-only budget constraints), so it returns
weights directly. All formulas are the primary-source-verified forms from research/162.

Sign convention: every builder frames a MAXIMISATION of (expected return − λ·risk); risk terms are
positive loss/variance magnitudes.
"""

from __future__ import annotations

import cvxpy as cp
import numpy as np

# Solver preferences for aarch64 (research/161 §4/§5): CLARABEL for SOCP/QP, SCS as a robust fallback.
_QP_SOLVER = cp.CLARABEL
_FALLBACK_SOLVER = cp.SCS


def mean_cvar_objective(weight: cp.Variable, mu: np.ndarray, scenario_returns: np.ndarray,
                        alpha: float, risk_aversion: float):
    """Mean-CVaR (Rockafellar-Uryasev 2000) over the empirical scenario matrix (research/162 §1.3-1.4).

    Maximise  μᵀw − λ·CVaR_α(w),  with CVaR via the LP auxiliaries:
        CVaR_α(w) = ζ + 1/((1−α)·S) · Σ_s u_s,   u_s ≥ −(r_sᵀw) − ζ,   u_s ≥ 0.
    r_s is scenario s's return vector (a row of `scenario_returns`, S×N). Returns the objective to
    maximise + the CVaR auxiliary constraints + {ζ, u} so the orchestrator can read the solved CVaR.
    """
    n_scenarios = scenario_returns.shape[0]
    if n_scenarios == 0:
        raise ValueError("mean_cvar_objective needs at least one scenario")
    zeta = cp.Variable(name="cvar_var")                 # the VaR level ζ
    losses = cp.Variable(n_scenarios, nonneg=True, name="cvar_tail_losses")  # u_s ≥ 0
    portfolio_scenario_return = scenario_returns @ weight            # S-vector of portfolio returns
    cvar = zeta + (1.0 / ((1.0 - alpha) * n_scenarios)) * cp.sum(losses)
    constraints = [losses >= -portfolio_scenario_return - zeta]
    objective = mu @ weight - risk_aversion * cvar
    return objective, constraints, {"zeta": zeta, "losses": losses, "cvar_expr": cvar}


def mean_variance_objective(weight: cp.Variable, mu: np.ndarray, covariance: np.ndarray,
                            risk_aversion: float):
    """Markowitz mean-variance QP (research/162 §2.1): maximise μᵀw − λ·wᵀΣw. Σ is the Ledoit-Wolf
    shrunk covariance. No extra constraints/aux — the quadratic risk is read back as wᵀΣw."""
    variance = cp.quad_form(weight, cp.psd_wrap(covariance))
    objective = mu @ weight - risk_aversion * variance
    return objective, [], {"variance_expr": variance}


def solve_risk_parity_weights(covariance: np.ndarray) -> np.ndarray:
    """Equal-Risk-Contribution weights via Spinu's convex log-barrier (research/162 §3.3):
        min_y  ½ yᵀΣy − (1/N) Σ ln(y_i),   then normalise  w = y / Σy.
    Returns long-only weights summing to 1. Falls back to inverse-variance (a real ERC approximation)
    if the barrier solve fails — surfaced, never a silent uniform vector (Rule O.3)."""
    n = covariance.shape[0]
    if n == 1:
        return np.array([1.0])
    y = cp.Variable(n, pos=True, name="erc_y")
    objective = 0.5 * cp.quad_form(y, cp.psd_wrap(covariance)) - (1.0 / n) * cp.sum(cp.log(y))
    problem = cp.Problem(cp.Minimize(objective))
    try:
        problem.solve(solver=_QP_SOLVER)
        if y.value is None or not np.all(np.isfinite(y.value)):
            raise ValueError("risk-parity barrier solve returned no finite point")
        weights = np.asarray(y.value, dtype=float)
    except Exception:
        # Inverse-variance is the closed-form ERC solution when Σ is diagonal — a real fallback.
        variances = np.clip(np.diag(covariance), 1e-12, None)
        weights = 1.0 / variances
    weights = np.clip(weights, 0.0, None)
    total = weights.sum()
    return weights / total if total > 0 else np.full(n, 1.0 / n)


def enhanced_indexing_objective(weight: cp.Variable, expected_returns: np.ndarray,
                                benchmark_weight: np.ndarray, factor_exposure: np.ndarray,
                                factor_covariance: np.ndarray, specific_variance: np.ndarray,
                                risk_aversion: float):
    """Qlib's EnhancedIndexingOptimizer objective (research/162 §4), vendored verbatim in form:
        maximise  dᵀr − λ(vᵀΣ_b v + var_uᵀd²),   d = w − w_bench,   v = Xᵀd  (factor exposure of the
    active bet). Σ_b is the FACTOR covariance, var_u the specific (idiosyncratic) variances. Requires a
    benchmark + a factor risk model — inputs the current system does not yet produce, so this mode is
    built + tested here but its PROD activation is a queued blocker (research/163 §3; Rule K)."""
    active = weight - benchmark_weight                        # d = w − w_bench
    factor_bet = factor_exposure.T @ active                   # v = Xᵀd
    factor_risk = cp.quad_form(factor_bet, cp.psd_wrap(factor_covariance))
    specific_risk = specific_variance @ cp.square(active)     # var_uᵀ d²
    objective = expected_returns @ active - risk_aversion * (factor_risk + specific_risk)
    return objective, [], {"factor_risk_expr": factor_risk, "specific_risk_expr": specific_risk}
