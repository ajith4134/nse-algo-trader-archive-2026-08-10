"""The Capital-Allocation Optimizer ENGINE — orchestrator (research/163 §3-§6/§8 module 7).

Ties the layers into one decision: RAW experience → scenario matrix + shrunk covariance → pick the
objective mode (Mean-CVaR when scenarios suffice, else auto-fall-back to parametric Mean-Variance;
Risk-Parity / Enhanced-indexing on request) → assemble + solve the CVXPY program under the full
constraint set (per-position/segment caps · gross/net · cardinality via iterative-reweighted-ℓ1 ·
turnover penalty) → round to whole lots → gate on whether it has EARNED the right to act. Emits an
`AllocationResult` whose per-candidate size multiplier the entry sites apply — identity until earned
(Rule P.4). Carried state (turnover w_prev, earned evidence, mode history) via the engine store.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate, AllocationResult
from nse_algo_trader.capital_allocation.allocation_constraint_builder import (
    AllocationConstraintConfig,
    build_budget_and_risk_constraints,
    cardinality_reweight_penalty,
    turnover_penalty,
)
from nse_algo_trader.capital_allocation.allocation_objective_programs import (
    enhanced_indexing_objective,
    mean_cvar_objective,
    mean_variance_objective,
    solve_risk_parity_weights,
)
from nse_algo_trader.capital_allocation.capital_allocation_engine_store import (
    CapitalAllocationEngineStore,
    CapitalAllocationState,
)
from nse_algo_trader.capital_allocation.experience_scenario_matrix_builder import (
    ScenarioMatrix,
    build_scenario_matrix,
    scenario_key,
)
from nse_algo_trader.capital_allocation.ledoit_wolf_covariance_estimator import shrunk_covariance_matrix

MODE_MEAN_CVAR = "mean_cvar"
MODE_MEAN_VARIANCE = "mean_variance"
MODE_RISK_PARITY = "risk_parity"
MODE_ENHANCED_INDEXING = "enhanced_indexing"

_ACTIVE_WEIGHT_THRESHOLD = 1e-4     # a weight below this counts as "not taken" (for active_count/cardinality)
_REWEIGHT_EPSILON = 1e-6            # ε in the reweighted-ℓ1 update γ_i = 1/(w_i + ε)


@dataclass(frozen=True)
class CapitalAllocationConfig:
    """Risk appetite + solver policy (research/163 §10 defaults — all configurable)."""

    cvar_alpha: float = 0.95
    # Mode-specific risk aversion: CVaR is a loss magnitude (~1e-1 scale), variance is vol² (~1e-3 scale),
    # so one λ cannot serve both — separate knobs, calibrated so typical positive edges DO get allocated
    # (research/163 §10 risk-appetite defaults). Raise to be more risk-averse (allocate less / hold cash).
    cvar_risk_aversion: float = 0.35
    variance_risk_aversion: float = 5.0
    scenario_count: int = 512
    preferred_mode: str = "auto"                 # auto | mean_cvar | mean_variance | risk_parity | enhanced_indexing
    cardinality_reweight_iterations: int = 3
    cardinality_penalty_coefficient: float = 1e-3
    min_session_dates_to_earn: int = 10          # real trading days before the engine may ACT
    constraint_config: AllocationConstraintConfig = field(default_factory=AllocationConstraintConfig)

    @property
    def cvar_scenario_floor(self) -> int:
        """S_min ≈ 10/(1−α) — the min scenarios to trust empirical CVaR (research/162 §9 heuristic)."""
        return int(math.ceil(10.0 / max(1.0 - self.cvar_alpha, 1e-6)))


def empirical_cvar(portfolio_scenario_returns: np.ndarray, alpha: float) -> float:
    """CVaR_α as a loss magnitude: mean of the worst (1−α) tail of the loss distribution. Positive =
    expected loss in the tail; NEGATIVE when even the worst tail is still profitable (high μ, low vol)."""
    if portfolio_scenario_returns.size == 0:
        return 0.0
    losses = -np.asarray(portfolio_scenario_returns, dtype=float)
    var_level = float(np.quantile(losses, alpha))
    tail = losses[losses >= var_level]
    return float(tail.mean()) if tail.size else float(var_level)


class CapitalAllocationOptimizer:
    """Solves the per-tick capital allocation across simultaneous candidates + serves the earned gate.

    `experience_source` is the DI seam (Rule J): production passes the real `ExperienceMemory` (anything
    exposing `recent_closed_experiences(limit)`); tests inject a fake. `None` → no history (pure risk
    allocation on candidate-carried scenarios only)."""

    def __init__(self, experience_source=None, config: CapitalAllocationConfig | None = None,
                 store: CapitalAllocationEngineStore | None = None, history_limit: int = 5000):
        self._experience_source = experience_source
        self._config = config or CapitalAllocationConfig()
        self._store = store or CapitalAllocationEngineStore()
        self._history_limit = history_limit
        self._state: CapitalAllocationState = self._store.load()

    @property
    def is_performance_earned(self) -> bool:
        return self._state.is_performance_earned

    # -- data --------------------------------------------------------------------------------------
    def _load_records(self) -> list[dict]:
        source = self._experience_source
        if source is None:
            return []
        try:
            return list(source.recent_closed_experiences(limit=self._history_limit))
        except Exception:
            return []

    def _distinct_session_dates(self, records: list[dict]) -> int:
        return len({str(r.get("session_date")) for r in records if r.get("session_date") is not None})

    # -- mode selection ----------------------------------------------------------------------------
    def _select_mode(self, scenarios: ScenarioMatrix, benchmark_available: bool) -> tuple[str, bool]:
        """Return (mode, fell_back). 'auto' → CVaR when scenarios suffice, else parametric MV fallback."""
        preferred = self._config.preferred_mode
        if preferred == MODE_ENHANCED_INDEXING and not benchmark_available:
            preferred = "auto"     # EI needs a benchmark + factor model (research/163 §3 — queued blocker)
        if preferred in (MODE_MEAN_VARIANCE, MODE_RISK_PARITY, MODE_ENHANCED_INDEXING):
            return preferred, False
        if preferred == MODE_MEAN_CVAR:
            thin = scenarios.min_real_sample_count < self._config.cvar_scenario_floor
            return (MODE_MEAN_VARIANCE, True) if thin else (MODE_MEAN_CVAR, False)
        # auto
        if scenarios.min_real_sample_count >= self._config.cvar_scenario_floor:
            return MODE_MEAN_CVAR, False
        return MODE_MEAN_VARIANCE, True

    # -- the solve ---------------------------------------------------------------------------------
    def allocate(self, candidates: list[AllocationCandidate], account_capital: float,
                 benchmark=None) -> AllocationResult:
        """Solve the allocation for this tick's candidate set. `benchmark` (weights, factor exposures,
        factor cov, specific var) enables the enhanced-indexing mode; None disables it."""
        if not candidates:
            return self._trivial_result([], MODE_MEAN_VARIANCE, "trivial", scenario_count=0, fell_back=False)

        records = self._load_records()
        distinct_dates = self._distinct_session_dates(records)
        scenarios = build_scenario_matrix(candidates, records, scenario_count=self._config.scenario_count)
        covariance = shrunk_covariance_matrix(scenarios.returns_matrix) if scenarios.returns_matrix.size \
            else np.eye(len(candidates)) * 1e-8
        mu = np.array([c.expected_edge_mu for c in candidates], dtype=float)
        w_prev = self._previous_weight_vector(candidates)
        benchmark_available = benchmark is not None
        mode, fell_back = self._select_mode(scenarios, benchmark_available)

        try:
            weights_vec, solver_status, aux = self._solve_mode(
                mode, candidates, mu, scenarios.returns_matrix, covariance, w_prev, benchmark)
        except Exception as solve_error:  # surfaced (Rule O.3), never a silent wrong number
            return self._trivial_result(candidates, mode, f"error:{type(solve_error).__name__}",
                                        scenario_count=scenarios.min_real_sample_count, fell_back=fell_back)

        weights = {c.candidate_id: float(max(weights_vec[i], 0.0)) for i, c in enumerate(candidates)}
        result = self._assemble_result(candidates, weights, mode, solver_status, scenarios,
                                       covariance, w_prev, account_capital, fell_back, distinct_dates)
        self._persist(candidates, weights, mode, distinct_dates, result)
        return result

    def _solve_mode(self, mode, candidates, mu, scenario_returns, covariance, w_prev, benchmark):
        n = len(candidates)
        if mode == MODE_RISK_PARITY:
            erc = solve_risk_parity_weights(covariance)
            erc = np.minimum(erc, self._config.constraint_config.max_position_weight)
            total = erc.sum()
            return (erc / total if total > 0 else np.full(n, 1.0 / n)), "optimal", {}

        weight = cp.Variable(n, name="allocation_weight")
        shared = build_budget_and_risk_constraints(weight, candidates, self._config.constraint_config)

        if mode == MODE_MEAN_CVAR:
            objective_expr, extra, aux = mean_cvar_objective(
                weight, mu, scenario_returns, self._config.cvar_alpha, self._config.cvar_risk_aversion)
        elif mode == MODE_ENHANCED_INDEXING:
            objective_expr, extra, aux = enhanced_indexing_objective(
                weight, mu, benchmark["benchmark_weight"], benchmark["factor_exposure"],
                benchmark["factor_covariance"], benchmark["specific_variance"],
                self._config.variance_risk_aversion)
        else:  # MODE_MEAN_VARIANCE
            objective_expr, extra, aux = mean_variance_objective(
                weight, mu, covariance, self._config.variance_risk_aversion)

        status = self._solve_with_cardinality(weight, objective_expr, shared + extra, w_prev, candidates)
        weights_vec = weight.value if weight.value is not None else np.zeros(n)
        return np.asarray(weights_vec, dtype=float), status, aux

    def _solve_with_cardinality(self, weight, objective_expr, constraints, w_prev, candidates) -> str:
        """Solve, applying iterative-reweighted-ℓ1 for cardinality + a turnover penalty, then (if a hard
        K is set) truncate to the top-K and resolve on that subset for an exact feasible allocation."""
        cfg = self._config
        gamma = cfg.constraint_config.turnover_gamma
        n = len(candidates)
        reweight = np.ones(n)
        k = cfg.constraint_config.cardinality_k
        iterations = cfg.cardinality_reweight_iterations if k else 1
        status = "error"
        for _ in range(max(iterations, 1)):
            penalty = cardinality_reweight_penalty(weight, reweight * cfg.cardinality_penalty_coefficient) if k \
                else cp.Constant(0.0)
            turnover_term = turnover_penalty(weight, w_prev, gamma)
            problem = cp.Problem(cp.Maximize(objective_expr - penalty - turnover_term), constraints)
            status = self._robust_solve(problem)
            if weight.value is None:
                break
            reweight = 1.0 / (np.asarray(weight.value, dtype=float) + _REWEIGHT_EPSILON)

        if k and weight.value is not None:
            weights_vec = np.asarray(weight.value, dtype=float)
            active = int(np.sum(weights_vec > _ACTIVE_WEIGHT_THRESHOLD))
            if active > k:
                keep = set(np.argsort(weights_vec)[-k:].tolist())
                zero_constraints = [weight[j] == 0 for j in range(n) if j not in keep]
                turnover_term = turnover_penalty(weight, w_prev, gamma)
                problem = cp.Problem(cp.Maximize(objective_expr - turnover_term), constraints + zero_constraints)
                status = self._robust_solve(problem)
        return status

    @staticmethod
    def _robust_solve(problem: cp.Problem) -> str:
        """CLARABEL first (best on aarch64), SCS fallback (research/161 §4). Returns the CVXPY status."""
        for solver in (cp.CLARABEL, cp.SCS):
            try:
                problem.solve(solver=solver)
                if problem.status in ("optimal", "optimal_inaccurate"):
                    return problem.status
            except Exception:
                continue
        return problem.status or "error"

    # -- assembly / state --------------------------------------------------------------------------
    def _assemble_result(self, candidates, weights, mode, solver_status, scenarios, covariance,
                         w_prev, account_capital, fell_back, distinct_dates) -> AllocationResult:
        from nse_algo_trader.capital_allocation.integer_lot_allocator import round_weights_to_lots

        n = len(candidates)
        weight_vec = np.array([weights[c.candidate_id] for c in candidates])
        portfolio_returns = scenarios.returns_matrix @ weight_vec if scenarios.returns_matrix.size \
            else np.zeros(0)
        cvar = empirical_cvar(portfolio_returns, self._config.cvar_alpha)
        vol = float(math.sqrt(max(weight_vec @ covariance @ weight_vec, 0.0)))
        turnover = float(np.sum(np.abs(weight_vec - w_prev))) if w_prev.size == n else 0.0
        active_count = int(np.sum(weight_vec > _ACTIVE_WEIGHT_THRESHOLD))

        lot_alloc = round_weights_to_lots(candidates, weights, account_capital)
        is_earned = distinct_dates >= self._config.min_session_dates_to_earn

        # The equal-weight baseline CVaR — the acceptance bar checks optimizer CVaR ≤ this (research/163 §5).
        equal_w = np.full(n, min(1.0 / n, self._config.constraint_config.max_position_weight))
        eq_returns = scenarios.returns_matrix @ equal_w if scenarios.returns_matrix.size else np.zeros(0)
        equal_weight_cvar = empirical_cvar(eq_returns, self._config.cvar_alpha)

        return AllocationResult(
            weights=weights,
            capital=lot_alloc.capital_deployed,
            lots=lot_alloc.lots,
            objective_mode_used=mode,
            solver_status=solver_status,
            portfolio_cvar=cvar,
            portfolio_vol=vol,
            active_count=active_count,
            turnover=turnover,
            scenario_count=scenarios.min_real_sample_count,
            fell_back=fell_back,
            is_earned=is_earned,
            diagnostics={
                "equal_weight_cvar": equal_weight_cvar,
                "cvar_reduction_vs_equal": equal_weight_cvar - cvar,
                "distinct_session_dates": distinct_dates,
                "cvar_scenario_floor": self._config.cvar_scenario_floor,
                "assumed_independent": scenarios.assumed_independent,
                "leftover_capital": lot_alloc.leftover_capital,
                "weight_sum": float(weight_vec.sum()),
                "naive_equal_weight": float(min(1.0 / n, self._config.constraint_config.max_position_weight)),
            },
        )

    def _previous_weight_vector(self, candidates: list[AllocationCandidate]) -> np.ndarray:
        """Build w_prev aligned to the current candidate order, looking each up by its STABLE key."""
        prior = self._state.last_weights_by_key
        return np.array([prior.get(str(scenario_key(c)), 0.0) for c in candidates], dtype=float)

    def _persist(self, candidates, weights, mode, distinct_dates, result: AllocationResult) -> None:
        self._state.last_weights_by_key = {
            str(scenario_key(c)): weights[c.candidate_id] for c in candidates}
        self._state.distinct_session_dates_seen = max(self._state.distinct_session_dates_seen, distinct_dates)
        self._state.is_performance_earned = result.is_earned
        self._state.record_mode(mode)
        self._state.last_evaluation = {
            "cvar": result.portfolio_cvar,
            "cvar_reduction_vs_equal": result.diagnostics.get("cvar_reduction_vs_equal"),
            "solver_status": result.solver_status,
        }
        import contextlib
        with contextlib.suppress(Exception):
            self._store.save(self._state)  # persistence failure must not break the trading decision

    def _trivial_result(self, candidates, mode, status, scenario_count, fell_back) -> AllocationResult:
        return AllocationResult(
            weights={c.candidate_id: 0.0 for c in candidates},
            capital={c.candidate_id: 0.0 for c in candidates},
            lots={c.candidate_id: 0 for c in candidates},
            objective_mode_used=mode, solver_status=status, portfolio_cvar=0.0, portfolio_vol=0.0,
            active_count=0, turnover=0.0, scenario_count=scenario_count, fell_back=fell_back,
            is_earned=self._state.is_performance_earned, diagnostics={},
        )
