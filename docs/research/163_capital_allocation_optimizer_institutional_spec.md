# research/163 — Capital-Allocation Optimizer — INSTITUTIONAL SPEC (Rule P engine)

**Date:** 2026-07-26
**Skill:** produced by `idea-to-institutional-spec` (forced MCQ clarify → research → spec → hand off).
**Grounded in:** `research/161` (library sourcing, ARM64-verified) + `research/162` (exact math + SOTA,
primary-source-verified) + `research/155` (the depth-gap this closes: gap #3 "portfolio construction as
constrained optimization").
**Target (depth-upgrade #9):** replace the WILL trunk's rank-only arbitration + fixed/Kelly per-trade
sizing with a real, solved, constrained **capital-allocation optimizer** across simultaneous candidates.
**User's clarify answers:** ALL objective modes · ALL scope levels · ALL four constraint families · full
integration (above win-prob+arbitration, supersedes arbitration sizing, advisory-→-acting via a gate).

---

## 1. Intent & the decision it changes
When multiple entry candidates fire at the same decision tick (N signals across index-opt / stock-opt /
cash), the system today sizes each **independently** (fractional-Kelly × win-prob multiplier) and merely
**ranks** them (Chebyshev MCDM in `will/multi_objective_arbitration.py`). There is no joint allocation:
no objective function over the *set*, no risk budget split, no covariance/tail-risk interaction, no
solver. This engine makes the real portfolio decision — **how to split a bounded risk/capital budget
across the simultaneous candidates so as to maximise risk-adjusted return subject to hard risk
constraints** — by solving a convex program each tick and emitting per-candidate capital weights that set
position sizes. A thin version ("flag if concentration > X%") fails the intent: it is one comparison
operator, not an optimisation (research/155 gap #3).

## 2. I/O contracts (the seams the build + tests bind to)
**Input — the candidate set at a decision tick** (`AllocationCandidate`, frozen dataclass, one per
signal):
- `candidate_id: str`, `segment: str` ∈ {index_option, stock_option, cash}, `underlying: str`,
  `direction: str`, `instrument_kind: str`
- `expected_edge_mu: float` — expected per-unit return = `win_prob × R:R − (1−win_prob)` (reuse
  `predictive_core.win_probability_engine`; identity edge 0 when the win-prob engine is un-earned)
- `per_unit_risk: float` (stop-distance for cash; structural max-loss/lot for defined-risk spreads),
  `entry_price: float`, `lot_or_tick_size: int`, `est_margin_per_unit: float`
- `pnl_scenario_vector: tuple[float, ...] | None` — the candidate's historical per-trade
  `realized_return_fraction` series from `memory_reflection.experience_memory` (the CVaR scenarios);
  `None`/too-thin → the engine falls back (see §4).

**Input — account/portfolio state:** `account_capital`, `w_prev` (last tick's weights, for turnover),
risk-budget config (caps, exposure limits, K_max), the objective-mode selection.

**Output — `AllocationResult`** (frozen): `weights: dict[candidate_id → float]` (fraction of risk
budget, Σ ≤ 1, ≥ 0), `capital: dict[candidate_id → float]`, `lots: dict[candidate_id → int]` (integer,
post-rounding), `objective_mode_used: str`, `solver_status: str`, `portfolio_cvar: float`,
`portfolio_vol: float`, `active_count: int`, `turnover: float`, `scenario_count: int`,
`fell_back: bool`, `is_earned: bool`, `diagnostics: dict`. Units: weights are fractions; CVaR/vol are
positive loss magnitudes (Rule O.5 sign convention); capital in ₹.

## 3. Algorithm / model + named SOTA analog
**SOTA analog:** Qlib `EnhancedIndexingOptimizer` (CVXPY solve-with-fallback pattern) + Riskfolio-Lib's
multi-risk-measure `Portfolio` object. Four objective modes, all convex, all solved via CVXPY:

1. **Mean-CVaR (default)** — Rockafellar–Uryasev (2000) LP over the empirical scenario matrix
   `r_s` (S×N): `max_{w,ζ,u} wᵀμ − λ[ ζ + 1/((1−α)S) Σ_s u_s ]` s.t. `u_s ≥ −wᵀr_s − ζ`, `u_s ≥ 0`,
   + §5 constraints. (research/162 §1; verified identical to Riskfolio-Lib's CVaR block.)
2. **Mean-Variance (fallback + explicit mode)** — Markowitz QP `max_w wᵀμ − λ wᵀΣw`, Σ = **Ledoit-Wolf**
   constant-correlation shrinkage (research/162 §2; verified vs Qlib `ShrinkCovEstimator` + PyPortfolioOpt).
3. **Risk-Parity / ERC** — Spinu log-barrier convex form `min ½wᵀΣw − Σ bᵢ ln(wᵢ)` then renormalise
   (research/162 §3; verified live in Riskfolio-Lib `ExpCone`). The "no-conviction" risk-model regime.
4. **Enhanced-indexing** — Qlib's exact `max_w dᵀr − λ(vᵀΣ_b v + var_uᵀd²)`, d = w − w_bench (vendored
   from Qlib source, ECOS→CLARABEL; research/162 §4). Active only when a benchmark index is supplied.

**Constraints (all four families, §5 of 162):** per-position cap `wᵢ ≤ c_pos`; per-segment cap
`Σ_{i∈seg} wᵢ ≤ c_seg`; gross `Σ|wᵢ| ≤ G` + net `|Σ wᵢ·dirᵢ| ≤ Nmax`; **cardinality** via
iterative-reweighted-ℓ1 + resolve (NOT raw MILP+CVaR — too heavy intraday; Candès-Wakin-Boyd reweight);
**integer lot/tick rounding** via PyPortfolioOpt-style greedy round + resolve-on-residual (never silent
truncation); **turnover/cost** linear penalty `−γ‖w − w_prev‖₁` in the objective.

**Libraries (research/161, ARM64-verified):** CVXPY ≥1.9 (CLARABEL for SOCP/QP, HiGHS for any
integer/Boolean, SCS fallback) + Riskfolio-Lib ≥7.3 (objective/constraint zoo) + PyPortfolioOpt
(`DiscreteAllocation` lot rounding only) + vendored Qlib enhanced-indexing objective.

## 4. Thin-data reality + mode selection (honesty, research/162 §9)
Current paper history ≈ 340 trades in ~1 session-day → empirical CVaR scenarios are thin. Mode selection:
`scenario_count S ≥ S_min = ceil(10/(1−α))` (α=0.95 → S_min=200; flagged an engineering heuristic, not
literature-sourced) → **Mean-CVaR**; else **auto-fall back to Ledoit-Wolf Mean-Variance** and set
`fell_back=True`; auto-promote back to CVaR once real history crosses the floor. This is a real
generalization guard, not a stub.

## 5. Engine-grade ACCEPTANCE CRITERIA (Rule-P checklist → pass/fail for THIS engine)
1. **Real solver** ✅ = a CVXPY program returns `solver_status == "optimal"` for the CVaR LP on real
   scenarios AND for each of MV/ERC/EI modes; NOT a heuristic scalar. Verified by solving on real data.
2. **Carried STATE** ✅ = `w_prev`, earned-status, mode-promotion state, Ledoit-Wolf Σ cache, and solve
   diagnostics persisted via `allocation_engine_store` (joblib/JSON atomic), evolving across ticks.
3. **Raw-input pipeline** ✅ = scenarios built from raw `experience_memory` P&L records (not a
   precomputed weight column); μ from the win-prob engine over raw features.
4. **Decision-grade output that CHANGES behavior** ✅ = per-candidate weights set position sizes at BOTH
   entry sites via the DI seam; the full acting path + the earning/calibration gate are built (advisory
   identity until earned — the ONLY open blocker is live accrual, §6).
5. **Comprehensive tests** ✅ = unit (each mode + each constraint) + property/invariant (Σw≤1, w≥0, caps
   & cardinality & gross/net respected exactly, CVaR ≥ VaR ≥ 0, turnover penalty reduces churn, fallback
   fires when S<S_min, lot-rounded weights stay feasible) + adversarial (N=1; all-μ≤0 → allocate ~0
   / cash; zero-variance; infeasible constraint set → graceful `solver_status` + safe empty allocation,
   never a crash or silent wrong number) + the **Rule-F real-data pass** on the 340-trade history with
   the numbers inspected by eye.
6. **Correct vocabulary** ✅ = "optimizer" is justified — a real solver + carried state.
7. **NUMERIC BAR (concrete pass/fail):** on the real history, the optimizer's chosen allocation must
   (a) solve to optimality, (b) satisfy every constraint exactly (asserted), and (c) yield **empirical
   portfolio CVaR ≤ the equal-weight portfolio's CVaR** on held-out scenarios (the optimizer actually
   reduces tail risk vs naive) — else the build is not done.

## 6. Verification plan (Rule F / J / K)
- **Real-data pass (Rule F):** run the whole engine on `experience_memory`'s real records; confirm the
  scenario builder, mode selection (thin → MV fallback expected), solver optimality, constraint
  satisfaction, and the CVaR-reduction bar — inspect the weights/CVaR/turnover numbers by eye.
- **Hermetic sim (Rule J):** because live CVaR needs many trading days, inject a RICHER synthetic
  scenario matrix (S ≫ S_min) behind the `scenario_source` DI seam to exercise the CVaR mode +
  cardinality + lot rounding end-to-end; the fake lives only under `tests/`, prod uses the real
  experience-memory source.
- **OPEN BLOCKER (Rule K):** the thin 1-day history means the earning gate stays UN-earned (advisory /
  identity) until real trading days accrue — same shape as the win-prob engine. Recorded in BACKLOG + a
  task. The full acting path is built now; only live accrual is deferred.

## 7. Depth justification (what a thin version would OMIT — research/155 gap #3)
A diagnostic version is a `concentration > X%` comparison. This engine instead implements: the objective
function (4 modes), the constraint set (4 families incl. cardinality + integer lots + turnover), the
CVXPY solver, the Ledoit-Wolf covariance matrix, the Rockafellar-Uryasev CVaR LP over real scenarios, the
thin-data fallback, carried state, and the acting integration. Every LOC implements one of those — no
padding. Estimated 8 cohesive modules, hundreds–low-thousands of justified LOC.

## 8. Decomposition (modules the build assembles — Rule C names)
Package `src/nse_algo_trader/capital_allocation/`:
1. `allocation_candidate.py` — input/output contracts (`AllocationCandidate`, `AllocationResult`).
2. `experience_scenario_matrix_builder.py` — data pipeline: experience_memory records → S×N scenario
   matrix per candidate + `scenario_count` + the S_min floor (DI seam `scenario_source`).
3. `ledoit_wolf_covariance_estimator.py` — shrinkage covariance for MV / ERC / EI modes.
4. `allocation_objective_programs.py` — the 4 CVXPY objective builders (CVaR LP / MV QP / ERC log-barrier
   / vendored Qlib enhanced-indexing).
5. `allocation_constraint_builder.py` — per-position/segment caps · gross/net · cardinality
   (reweighted-ℓ1) · turnover penalty.
6. `integer_lot_allocator.py` — PyPortfolioOpt-style greedy lot rounding + resolve-on-residual.
7. `capital_allocation_optimizer.py` — the ENGINE orchestrator: mode selection (CVaR↔MV fallback), solve,
   round, assemble `AllocationResult`, + the performance-earned calibration gate (advisory until earned).
8. `capital_allocation_engine_store.py` — atomic persisted state (w_prev, earned status, mode-promotion,
   diagnostics).

## 9. Integration + dashboard (Rule G / N)
- **Wiring:** add a per-tick **candidate-batch collection point** in `live_universe_paper_loop.py` (the
  current per-signal sizing at :794 & :872 becomes: gather the tick's eligible candidates → one
  `optimizer.allocate(candidates, account_state)` call → apply per-candidate weight to size). Injected
  via a `capital_allocation_fn` DI seam on the loop `state`, defaulting to identity/advisory until earned
  (mirrors `win_probability_size_multiplier_fn`). No orphan — primary consumer is the entry path.
- **Dashboard surface (Rule N):** a "Capital-Allocation Optimizer" panel — objective mode used +
  fallback flag, scenario count vs S_min, per-candidate weight vs naive equal-weight, portfolio CVaR &
  vol, active count (cardinality), turnover, solver status, earned status. Registered in the
  feature-surface manifest.

## 10. Residual choice for the user (Step-5 confirm)
Default `α = 0.95` (CVaR tail), `λ` risk-aversion mid, `K_max` cardinality = min(N, 8), per-position cap
25%, per-segment caps from Rule L, turnover γ small. All configurable; these are the starting values
unless you want different risk appetite. Everything else is settled by the research + your "all" answers.
