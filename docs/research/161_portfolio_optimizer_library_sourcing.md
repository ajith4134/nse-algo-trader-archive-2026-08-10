# 161 — Portfolio / Risk-Allocation Optimizer: OSS Library Sourcing

Status: research complete, empirically verified on target hardware.
Date: 2026-07-26
Scope: `sourcing-oss-parts` sweep for the portfolio/risk-allocation optimizer
engine (Mean-CVaR, Mean-Variance, Risk-Parity, Enhanced-Indexing) that will
size positions across a small set (N≈2–30) of simultaneous trade candidates
at a decision tick, using the project's own paper-trade P&L scenario store.

Target machine: Oracle Linux 9.8, aarch64 (ARM64), Python 3.12.
All installability claims below were **verified by actually installing and
running the code on this machine** (a throwaway venv at
`/tmp/claude-1000/-home-opc/4ce32184-69b4-4131-bb69-cb8473a72823/scratchpad/vtest`),
not inferred from docs alone — this satisfies the project's real-verification
bar (Rule F) for the sourcing decision itself. Full transcripts of every
install/solve command are reproducible from the commands in this file.

---

## 1. Shape of the piece

- **Inputs**: μ (expected edge per candidate, small vector, N≤30), a
  historical/paper-trade **empirical P&L scenario matrix** R (T scenarios ×
  N assets, NOT assumed Gaussian), an optional benchmark return series r_b,
  current weights w0 (for turnover), per-asset/segment caps, gross/net
  limits, a cardinality budget K, and lot/tick sizes per instrument.
- **Behavior**: solve ONE of four objective modes against a SHARED
  constraint set: (1) Mean-CVaR over R (Rockafellar–Uryasev, empirical, not
  parametric), (2) Mean-Variance with Ledoit-Wolf shrinkage Σ, (3)
  Risk-Parity / equal-risk-contribution, (4) Qlib-style benchmark-relative
  enhanced indexing: `max wᵀr − λ(vᵀΣ_b v + var_uᵀd²)` where `d = w − w_b`
  and `v` is a factor-exposure deviation.
- **Outputs**: a weight vector (continuous), optionally rounded to
  integer lots/shares, respecting all constraints.
- **Hard constraints on the search**: must run natively on aarch64 with
  prebuilt wheels wherever possible (no exotic Fortran/BLAS builds), must
  target Python 3.12, must not require a commercial solver (MOSEK/Gurobi/
  CPLEX) for the base engine.

---

## 2. Candidates evaluated

Searched via: GitHub repo pages, PyPI project + JSON API, ReadTheDocs, and
direct source inspection of installed packages (WebSearch quota was
exhausted mid-session — see §6 note — so evidence after that point comes
from WebFetch on GitHub/PyPI/docs URLs and from **actually running the code
on this ARM64 box**, which is stronger evidence than either).

| # | Candidate | Considered for |
|---|---|---|
| 1 | **CVXPY** (+ ECOS, SCS, OSQP, CLARABEL, HiGHS solvers) | modeling substrate |
| 2 | **Riskfolio-Lib** | full objective/constraint zoo |
| 3 | **PyPortfolioOpt** | CVaR + discrete lot rounding |
| 4 | **cvxportfolio** (Stanford/Boyd group) | turnover/tx-cost modeling |
| 5 | **skfolio** | full objective/constraint zoo (alternative) |
| 6 | **pyrb** (jcrichard/pyrb) | risk-parity/risk-budgeting reference |
| 7 | **pyrb** (PyPI, mingi3314) | name collision, checked to rule out |
| 8 | **okama** | portfolio analytics/education |
| 9 | **mvo** (PyPI) | checked, does not exist as a real package |
| 10 | **Qlib** `EnhancedIndexingOptimizer` | reference implementation for objective #4 |

---

## 3. Per-candidate findings

### 3.1 CVXPY — recommendation: DEPEND (mandatory substrate)

- GitHub: [cvxpy/cvxpy](https://github.com/cvxpy/cvxpy) — 6,288★ (2026-07-24
  API check), Apache-2.0, `pushed_at` 2026-07-24 (2 days before this
  writing) — very actively maintained.
- PyPI: [cvxpy 1.9.2](https://pypi.org/project/cvxpy/#files), released
  2026-06-22. Requires Python ≥3.11. Ships aarch64 manylinux wheels for
  **cp311, cp312, cp313, cp314, cp314t**.
- **Verified live on this box**: `pip install cvxpy` inside a Python 3.12
  venv pulled 100% prebuilt aarch64 wheels — no compilation, no C/Fortran
  toolchain needed:
  ```
  Successfully installed ... cvxpy-1.9.2 ... clarabel-0.11.1 osqp-1.1.3
  scs-3.2.11 highspy-1.15.1 qdldl-0.1.9.post1 sparsediffpy-0.3.0 ...
  ```
- `cp.installed_solvers()` returned `['CLARABEL', 'SCS', 'SCIPY', 'HIGHS',
  'OSQP']` out of the box — **no ECOS**, because modern CVXPY (≥1.9) no
  longer pulls ECOS as a default dependency (Clarabel supersedes it for
  SOCP).
- Verified a toy LP solves correctly with `solver=cp.CLARABEL`.
- **Verified a Boolean-variable MILP (cardinality constraint pattern:
  `w <= b`, `sum(b) <= k`) solves correctly via `solver=cp.HIGHS`** — this
  is the critical finding for cardinality support (see §4).
- Solver choice for aarch64: **prefer CLARABEL for SOCP/QP (Mean-Variance,
  enhanced-indexing quad-form), HIGHS for anything with Boolean/integer
  variables (cardinality), SCS as a robust large-scale fallback.** Do NOT
  depend on ECOS (see rejection below).

### 3.2 ECOS solver — REJECTED as a required dependency

- PyPI: [ecos](https://pypi.org/project/ecos/) latest is **2.0.14**
  (released 2024-06-18, GPLv3). Confirmed via the PyPI JSON API
  (`https://pypi.org/pypi/ecos/json`): the `urls` array contains **zero**
  `aarch64`/`arm64` wheel files — only `x86_64`, `win_amd64`, and macOS
  x86_64 wheels for cp37–cp312.
- A source sdist (`ecos-2.0.14.tar.gz`) exists, so `pip install ecos` would
  fall back to a from-source build on ARM64, requiring a C compiler and
  BLAS/LAPACK dev headers — an unnecessary risk/build-time cost given that
  CVXPY 1.9 ships CLARABEL and SCS as ARM64-wheel-native SOCP solvers that
  cover the same problem class.
- Qlib's own reference `EnhancedIndexingOptimizer` (see §3.7) defaults to
  ECOS — **when adapting that code, override the solver to `CLARABEL` (or
  `SCS`) on this box.**
- **Verdict: do not install/require ECOS. Use CLARABEL/SCS instead.**

### 3.3 Riskfolio-Lib — recommendation: DEPEND (primary high-level engine)

- GitHub: [dcajasn/Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib)
  — 4,404★, BSD-3-Clause, `pushed_at` **2026-06-22** (verified via GitHub
  API), 5 open issues (well-triaged), not archived.
- PyPI: [riskfolio-lib 7.3.0](https://pypi.org/project/riskfolio-lib/)
  (2026-05-31). Requires Python ≥3.10, ships aarch64 manylinux wheels for
  all supported CPython versions. Built directly on **CVXPY ≥1.7.2**.
- **Verified live on this box**: `pip install riskfolio-lib` succeeded with
  zero compile steps — pulled a large but fully prebuilt dependency tree
  (numba/llvmlite, scikit-learn, statsmodels, arch, matplotlib, vectorbt,
  astropy — heavier than the other candidates, all pure wheels on aarch64).
- **Verified functionally against a real empirical scenario matrix** (a
  synthetic T=200–250 × N=6–10 returns DataFrame, standing in for the
  project's paper-trade P&L scenario store per Rule J since no live
  scenario store was wired up in this sourcing task):
  - `port.optimization(model='Classic', rm='CVaR', obj='Sharpe', hist=True)`
    — solved correctly. `hist=True` feeds the raw T×N returns matrix
    straight into the Rockafellar–Uryasev CVaR LP — **this is empirical-
    scenario CVaR, not a parametric/covariance shortcut**, confirmed by
    passing a raw returns DataFrame with no covariance step involved.
  - `port.rp_optimization(model='Classic', rm='CVaR', hist=True)` — solved
    a Risk-Parity / equal-risk-contribution allocation using CVaR as the
    risk measure (risk-parity is not restricted to variance).
  - Source inspection of the installed `Portfolio.py` confirms a native
    `card` parameter (cardinality, implemented with CVXPY Boolean
    variables + `cp.sum(e) <= self.card`), a `turnover` parameter
    (`TO_1 <= self.turnover * ...`), and `kindbench`/`benchindex`
    parameters for benchmark tracking-error constraints.
  - **Verified the cardinality path end-to-end**: set `port.card = 4` on a
    10-asset synthetic scenario problem, forced `port.solvers = ['HIGHS']`
    (cardinality needs a MIP-capable solver; the CVaR LP + Boolean
    selection variables is jointly a MILP), and the optimizer returned
    exactly 4 non-zero weights, correctly respecting the empirical-CVaR
    objective under the cardinality constraint.
  - Confirmed `method_cov='ledoit'` in `assets_stats()` — native Ledoit-Wolf
    shrinkage covariance for the Mean-Variance mode.
- **Gap**: Riskfolio-Lib's benchmark constraint (`kindbench`/`benchindex`/
  `turnover`) is a tracking-error/turnover **constraint**, not the exact
  Qlib `max wᵀr − λ(vᵀΣ_b v + var_uᵀd²)` **objective**. No general-purpose
  portfolio library implements that precise Qlib enhanced-indexing form —
  see §3.7. This one objective mode needs bespoke CVXPY code.
- **Gap**: cardinality (Boolean vars) requires a MIP-capable CVXPY backend.
  Riskfolio's own docs just say "a solver that supports MIP" without
  naming one that ships free on ARM64. **HiGHS (bundled with CVXPY 1.9+ via
  `highspy`, has aarch64 wheels) fills this gap for free** — verified
  working above. Do not reach for PySCIPOpt or python-mip (see §3.8/3.9).

### 3.4 PyPortfolioOpt — recommendation: DEPEND (thin, for lot rounding + a 2nd CVaR reference)

- GitHub: moved to org **PyPortfolio/PyPortfolioOpt** — 5,894★, MIT,
  `pushed_at` **2026-07-07**, 105 open issues (larger backlog than
  Riskfolio, but actively triaged).
- PyPI: [PyPortfolioOpt 1.6.0](https://pypi.org/project/PyPortfolioOpt/)
  (2026-02-26). Supports Python 3.10–3.14. Depends on CVXPY ≥1.1.19.
- **Verified live on this box**: installs cleanly on aarch64/py3.12 with no
  new compiled deps beyond what CVXPY already pulled.
- `EfficientCVaR.__init__(self, expected_returns, returns, beta=0.95, ...)`
  — confirmed by direct signature inspection that it takes the **raw
  historical returns matrix** as `returns`, i.e. empirical-scenario CVaR
  (Rockafellar–Uryasev on real observations), matching the project's
  requirement, not a covariance surrogate.
- **Key unique value**: `pypfopt.discrete_allocation.DiscreteAllocation`
  — converts continuous weights into **integer share/lot counts** via a
  greedy algorithm (`greedy_portfolio()`) or an LP-based allocator
  (`lp_portfolio()`). This is exactly the "integer lot/tick rounding"
  requirement and nothing else in the shortlist provides it directly.
- **Role in the recommended architecture**: not the primary objective
  engine (Riskfolio-Lib already covers CVaR/MV/RP more completely) — use
  PyPortfolioOpt narrowly for `DiscreteAllocation` as the final lot-
  rounding stage after Riskfolio/bespoke-CVXPY produces continuous weights.

### 3.5 skfolio — strong alternative, NOT the primary pick (documented, not rejected outright)

- GitHub: [skfolio/skfolio](https://github.com/skfolio/skfolio) — 2,061★,
  BSD-3-Clause, `pushed_at` **2026-07-26** (pushed literally the same day
  as this research — extremely active).
- PyPI: [skfolio 0.20.1](https://pypi.org/project/skfolio/). Depends on
  `cvxpy-base ≥1.5.0`, scikit-learn ≥1.6.0.
- **Verified live on this box**: installs cleanly on aarch64/py3.12,
  pulling its own `cvxpy-base` aarch64 wheel.
- Docs explicitly list: CVaR, Ledoit-Wolf, Risk Parity/Risk Budgeting,
  Benchmark Tracker + Tracking Error Constraints, and **Cardinality and
  Group Cardinality Constraints** as first-class features — on paper this
  covers nearly the same ground as Riskfolio-Lib.
- **Why not primary**: skfolio is built as an sklearn-style
  `fit`/`predict` **Pipeline/Estimator** API (its whole design center is
  cross-validation and ML-style composition of optimizers). The project's
  need is a single decision-tick call with a shared, hand-controlled
  constraint block (caps, cardinality, turnover, lot rounding) switched
  across 4 objective modes and merged with a bespoke Qlib-style term —
  Riskfolio-Lib's `Portfolio` object (`model=`, `rm=`, `obj=` kwargs on one
  object, with `card`/`turnover`/`benchindex` as plain attributes) maps
  onto that "one engine, 4 modes" shape more directly than skfolio's
  estimator-composition style would, without fighting its abstractions.
  skfolio's freshness (pushed today) and cardinality-native pipeline make
  it the natural **second engine to evaluate later** if Riskfolio-Lib's
  bespoke-enhanced-indexing patch proves awkward — recorded here, not
  discarded, per the user's rejection-transparency rule.

### 3.6 cvxportfolio — REJECTED as primary, noted as design reference

- GitHub: [cvxgrp/cvxportfolio](https://github.com/cvxgrp/cvxportfolio) —
  1,242★, **GPLv3**, `pushed_at` 2026-04-27, 30 open issues.
- Built by the Stanford/Boyd convex-optimization group (Boyd, Busseti,
  Diamond et al.), implements the multi-period trading policy framework
  from their paper, with realistic transaction-cost and holding-cost
  models and a causality-enforcing backtester.
- **Reject as primary**: it is architected for **multi-period backtesting
  of a trading policy over a full time series**, not a single-tick,
  simultaneous-candidate capital allocator with an empirical scenario
  matrix as its native input. It does not natively expose CVaR,
  risk-parity, or the Qlib enhanced-indexing form as objective choices.
- **Keep as reference**: its transaction-cost / turnover-penalty modeling
  is the most rigorous of anything surveyed here and is worth reading when
  writing the turnover/tx-cost penalty term for the bespoke engine.
  License is GPLv3 — per project rules, license is not a filtering
  criterion for this personal-use codebase, so this rejection is purely on
  shape-fit, not licensing.

### 3.7 Qlib `EnhancedIndexingOptimizer` — reference implementation, vendor-and-adapt the formula only

- Source:
  [`qlib/contrib/strategy/optimizer/enhanced_indexing.py`](https://github.com/microsoft/qlib/blob/main/qlib/contrib/strategy/optimizer/enhanced_indexing.py)
- Confirmed exact objective: **`d @ r − lamb * (v @ cov_b @ v + var_u @ d**2)`**
  where `d = w − w_bench` (active weight), maximized subject to
  `w ≥ 0, sum(w) = 1`, benchmark-deviation bounds, factor-deviation bounds,
  and an optional turnover cap `‖w − w0‖₁ ≤ delta` (dropped on a retry if
  infeasible).
- Implemented in raw **CVXPY**, defaulting to **ECOS** as the solver — on
  this ARM64 box, ECOS has no wheel (§3.2), so any vendored copy of this
  formula must be re-pointed at `cp.CLARABEL` (SOCP/QP-capable, ARM64
  native) instead.
- **No surveyed library (Riskfolio-Lib, PyPortfolioOpt, skfolio,
  cvxportfolio) implements this exact benchmark-relative quadratic form.**
  Riskfolio-Lib's tracking-error constraint is the closest architectural
  analog (same `d`/benchmark shape) but encodes it as a constraint, not
  this specific maximization objective. **Conclusion: enhanced-indexing
  MUST be hand-written as a bespoke CVXPY objective module**, vendoring
  the qlib formula (MIT-licensed qlib) with a provenance comment, adapted
  to (a) solve on CLARABEL instead of ECOS, and (b) share the same
  constraint-builder (caps/cardinality/turnover/lot-rounding) used for the
  other three objective modes so all four present one unified engine.

### 3.8 pyrb (jcrichard/pyrb) — REJECTED, redundant + stale

- GitHub: [jcrichard/pyrb](https://github.com/jcrichard/pyrb) — 130★, MIT,
  `pushed_at` **2023-07-06** — no commits in ~3 years, effectively
  unmaintained relative to the other candidates (all pushed within the
  last 3 months).
- Implements constrained/unconstrained risk budgeting per Richard &
  Roncalli's "Constrained Risk Budgeting Portfolios" paper — a legitimate,
  well-cited academic reference implementation.
- **Reject**: Riskfolio-Lib's `rp_optimization()` already covers risk
  parity/risk budgeting with 22 risk measures and is actively maintained
  and CVXPY-integrated; pulling in a second, stale, narrower risk-parity
  library for the same capability adds a dependency with no net new
  functionality. Kept only as an academic citation for the risk-budgeting
  math if a future edge case needs it.

### 3.9 "pyrb" on PyPI (mingi3314) — REJECTED, wrong project (name collision)

- PyPI JSON confirms `pyrb` on PyPI is **"Python Rebalancer"**, a CLI tool
  for automating stock rebalancing through a Korean broker (EBest)
  API — unrelated to risk-parity/risk-budgeting optimization. Flagging
  explicitly so this name is not confused with §3.8 in future sourcing
  passes.

### 3.10 okama — REJECTED, wrong shape (analytics, not an institutional optimizer)

- GitHub/PyPI: [okama](https://github.com/mbk-dev/okama), v2.3.0
  (2026-07-14), Python ≥3.11.
- Positioned as an investment-portfolio **analysis and education** library
  (backtesting, Monte Carlo, EOD market data access, macro indicators) with
  basic Mean-Variance optimization and CVaR as a reporting metric.
- **Reject**: no risk-parity, no benchmark-relative/enhanced-indexing
  objective, and CVaR here reads as an analytics/reporting figure rather
  than an optimization objective with cardinality/turnover/lot-rounding
  machinery. Wrong shape for a decision-grade allocator engine.

### 3.11 mvo — REJECTED / unverifiable, does not exist as a substantial package

- `https://pypi.org/pypi/mvo/json` returned **HTTP 404** — there is no
  package named `mvo` on PyPI. Could not find a maintained GitHub project
  under this name matching "mean-variance optimizer" with any real
  activity signal. **Flagging as unverified rather than guessing** — if
  the user has a specific `mvo` repo in mind, it needs to be named
  explicitly for a follow-up check; nothing under this name met the bar
  for consideration here.

### 3.12 PySCIPOpt / python-mip (`mip`) — considered as MIP-solver options for cardinality, REJECTED in favor of HiGHS

- `PySCIPOpt` PyPI JSON (`pypi.org/pypi/PySCIPOpt/json`): latest **6.2.1**,
  **no aarch64/arm64 wheels** — would require compiling the full SCIP
  Optimization Suite from source on ARM64. Rejected: too heavy a build
  dependency for something HiGHS already solves for free.
- `mip` (python-mip) PyPI JSON: latest **1.17.6**, ships only a
  `py3-none-any` wheel bundling native CBC/Gurobi interfaces via CFFI —
  ARM64 behavior for the bundled native CBC binary is unverified from PyPI
  metadata alone (would need an actual install+solve test to confirm, not
  done here since HiGHS already closed the gap). Rejected as unnecessary:
  **HiGHS, bundled automatically with CVXPY ≥1.9 via `highspy` (confirmed
  ARM64 wheel, confirmed working MILP solve on this box, confirmed
  working on a real Riskfolio-Lib cardinality problem)**, already covers
  the cardinality/Boolean-variable requirement with zero extra
  dependencies.

---

## 4. Recommendation

**Primary solver substrate: CVXPY ≥1.9 (aarch64 wheels, Python 3.12,
Apache-2.0), pinned to prefer `CLARABEL` for continuous SOCP/QP problems
(Mean-CVaR LP, Mean-Variance QP, enhanced-indexing QP) and `HIGHS` for any
problem with cardinality/Boolean variables (MILP).**

**Primary high-level engine: Riskfolio-Lib ≥7.3 (BSD-3-Clause, built on
CVXPY, aarch64 wheels).** Use it directly (depend, don't vendor — it is
clean, tested, and actively maintained) for 3 of the 4 objective modes:
- Mean-CVaR: `model='Classic', rm='CVaR', hist=True` — verified to run the
  true empirical-scenario Rockafellar–Uryasev LP on a raw returns matrix.
- Mean-Variance w/ Ledoit-Wolf: `assets_stats(method_cov='ledoit')` +
  `rm='MV'`.
- Risk-Parity: `rp_optimization(rm=<any of 22 measures incl. CVaR>)`.
- Shared constraint machinery to reuse: `card` (cardinality, MIP via
  HiGHS — verified end-to-end), `turnover`, `kindbench`/`benchindex`
  (tracking error).

**Bespoke module required for objective #4 (enhanced-indexing):** no
surveyed library implements Qlib's exact
`max wᵀr − λ(vᵀΣ_b v + var_uᵀd²)` form. Vendor-and-adapt Qlib's
`enhanced_indexing.py` CVXPY formulation directly (MIT-licensed, small,
well-scoped — record provenance comment), re-pointed to `CLARABEL` instead
of its default `ECOS` (which has no ARM64 wheel), and re-wire its
caps/turnover constraint block to share the SAME constraint-builder used
for the Riskfolio-Lib-backed objectives (per-position caps, per-group caps,
gross/net exposure, cardinality-via-HiGHS, turnover penalty) so all four
modes present one unified engine interface rather than two disconnected
code paths.

**Thin dependency for lot/tick rounding: PyPortfolioOpt's
`DiscreteAllocation`** (MIT, aarch64-clean) as the final post-processing
stage converting continuous weights to integer lots/shares — nothing else
surveyed does this job.

**Design reference only (not a runtime dependency): cvxportfolio** for its
transaction-cost/turnover-penalty modeling rigor, when refining the
turnover penalty term.

**Documented but not chosen for v1: skfolio** — equally capable on paper
and the freshest repo of the whole set (pushed the same day as this
research), but its sklearn-Pipeline/Estimator API is a worse structural
fit for a single hand-controlled multi-objective engine than Riskfolio-Lib's
plain `Portfolio` object. Worth a second look if the Riskfolio +
bespoke-enhanced-indexing integration proves awkward in practice.

---

## 5. Exact install lines + ARM64 notes

```bash
# Core substrate (aarch64 wheels confirmed for cp311-cp314 on this box)
python3.12 -m pip install cvxpy          # pulls clarabel, scs, osqp, highspy (all aarch64 wheels)

# Primary high-level engine
python3.12 -m pip install riskfolio-lib  # pulls numba/llvmlite/scikit-learn/statsmodels/vectorbt — heavy but all aarch64 wheels

# Lot/tick rounding stage
python3.12 -m pip install PyPortfolioOpt

# Optional, second engine to evaluate later (not wired into v1)
python3.12 -m pip install skfolio
```

**ARM64 gotchas found:**
1. **Do not `pip install ecos`** on this box unless you accept a from-source
   build (no aarch64 wheel exists as of ecos 2.0.14 / 2024-06-18). Not
   needed — CVXPY 1.9's default solver set (Clarabel/SCS/OSQP/HiGHS)
   already covers SOCP + MIP without it.
2. **Riskfolio-Lib's `card` (cardinality) constraint needs an explicit MIP
   solver.** Its own docs don't name a free one — set
   `port.solvers = ['HIGHS']` explicitly before calling `optimization()`;
   confirmed working on this box.
3. **PySCIPOpt has no ARM64 wheel** (would need building the full SCIP
   suite from source) — avoid it as a MIP backend on this architecture;
   HiGHS covers the same need for free.
4. **Qlib's own `EnhancedIndexingOptimizer` defaults to `solver=ECOS`** —
   when vendoring that code, change the solver argument to `CLARABEL`
   (or `SCS`) or the vendored module will fail to install/solve on this
   box.
5. Python on this box: the system `python3` is 3.9.25; **`python3.12` is
   present at `/usr/bin/python3.12`** but has no `pip` module by default —
   run `python3.12 -m ensurepip --upgrade` (or create a venv) before
   installing any of the above. This is how all installs above were
   actually verified.

**Preferred CVXPY solver defaults on aarch64:**
- Continuous convex (Mean-CVaR LP, Mean-Variance QP, enhanced-indexing QP):
  **CLARABEL** (default-in, ARM64-native, actively maintained Rust solver).
- Any MILP/cardinality/Boolean-variable problem: **HIGHS**.
- Large/ill-conditioned fallback: **SCS**.

---

## 6. Rejections summary (required per project rules — every candidate considered but not chosen)

| Candidate | One-line rejection reason |
|---|---|
| **ECOS** (solver) | No aarch64 wheel (verified via PyPI JSON, latest 2.0.14/2024); would force a from-source build; CVXPY 1.9's Clarabel/SCS/HiGHS already cover the same problem classes natively on ARM64. |
| **cvxportfolio** | Wrong shape — multi-period backtesting/trading-policy framework (GPLv3, Stanford/Boyd), not a single-tick multi-objective allocator; no native CVaR/risk-parity/enhanced-indexing objective choice. Kept as a transaction-cost-modeling reference only. |
| **skfolio** | Feature-complete on paper (CVaR, Ledoit-Wolf, risk parity, cardinality, tracking error — and the most recently pushed repo of the set) but its sklearn-Estimator/Pipeline API is a worse structural fit than Riskfolio-Lib's plain multi-mode `Portfolio` object for one hand-controlled engine; documented as a strong second option, not discarded. |
| **pyrb** (jcrichard) | Legit risk-budgeting reference implementation but stale (`pushed_at` 2023-07-06, no recent activity) and fully redundant with Riskfolio-Lib's actively-maintained `rp_optimization()`. |
| **pyrb** (PyPI, mingi3314) | Name collision — this is "Python Rebalancer," a broker-rebalancing CLI, unrelated to risk-parity optimization. |
| **okama** | Analytics/education-focused library; no risk-parity, no enhanced-indexing objective; CVaR is a reporting metric, not an optimization objective with constraint machinery. |
| **mvo** | No such package exists on PyPI (404 on the JSON API) and no maintained matching GitHub project was found under this name — flagged as unverified rather than guessed at. |
| **PySCIPOpt** | No aarch64 wheel; would require building the full SCIP suite from source. HiGHS (bundled free with CVXPY) already covers the MIP/cardinality need. |
| **python-mip (`mip`)** | Only ships a generic `py3-none-any` wheel with bundled native CBC/Gurobi interfaces of unverified ARM64 behavior; unnecessary since HiGHS already closes the cardinality gap with a confirmed-working ARM64 wheel. |

---

## 7. Sources

- [cvxpy/cvxpy GitHub](https://github.com/cvxpy/cvxpy)
- [cvxpy PyPI](https://pypi.org/project/cvxpy/#files)
- [dcajasn/Riskfolio-Lib GitHub](https://github.com/dcajasn/Riskfolio-Lib)
- [riskfolio-lib PyPI](https://pypi.org/project/riskfolio-lib/)
- [Riskfolio-Lib docs](https://riskfolio-lib.readthedocs.io/en/latest/)
- [PyPortfolio/PyPortfolioOpt GitHub](https://github.com/PyPortfolio/PyPortfolioOpt) (formerly robertmartin8/PyPortfolioOpt)
- [PyPortfolioOpt PyPI](https://pypi.org/project/PyPortfolioOpt/)
- [skfolio/skfolio GitHub](https://github.com/skfolio/skfolio)
- [skfolio PyPI](https://pypi.org/project/skfolio/)
- [cvxgrp/cvxportfolio GitHub](https://github.com/cvxgrp/cvxportfolio)
- [Qlib enhanced_indexing.py](https://github.com/microsoft/qlib/blob/main/qlib/contrib/strategy/optimizer/enhanced_indexing.py)
- [jcrichard/pyrb GitHub](https://github.com/jcrichard/pyrb)
- [pyrb (Python Rebalancer) PyPI JSON](https://pypi.org/pypi/pyrb/json)
- [okama GitHub](https://github.com/mbk-dev/okama) / [okama PyPI JSON](https://pypi.org/pypi/okama/json)
- [mvo PyPI JSON — 404, package does not exist](https://pypi.org/pypi/mvo/json)
- [ecos PyPI JSON](https://pypi.org/pypi/ecos/json)
- [osqp PyPI files](https://pypi.org/project/osqp/#files)
- [scs PyPI files](https://pypi.org/project/scs/#files)
- [clarabel PyPI JSON](https://pypi.org/pypi/clarabel/json)
- [PySCIPOpt PyPI JSON](https://pypi.org/pypi/PySCIPOpt/json)
- [mip (python-mip) PyPI JSON](https://pypi.org/pypi/mip/json)
- GitHub REST API (`api.github.com/repos/...`) — used directly for
  `pushed_at`/stars/license/archived status on all six primary candidates,
  queried live during this research session (2026-07-26).

**Note on method**: the session's WebSearch quota was exhausted early in
this task (200/200 used before this task began). All findings after that
point come from (a) direct `WebFetch` calls to specific GitHub/PyPI/docs
URLs (cited above), (b) the GitHub REST API via `curl`, and (c) **actually
installing and running each candidate library on this ARM64 box** — the
install logs, `cp.installed_solvers()` output, and the cardinality/CVaR
solve results quoted in §3 are real command output from this machine, not
inferred. Where a WebFetch summary and direct source/behavior inspection
disagreed (e.g. one WebFetch pass characterized PyPortfolioOpt's CVaR as
"covariance-based," which direct signature inspection of
`EfficientCVaR.__init__` disproved), the direct-inspection finding is what
is reported here.
