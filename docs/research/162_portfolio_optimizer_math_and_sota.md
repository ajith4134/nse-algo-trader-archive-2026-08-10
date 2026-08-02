# Portfolio / Risk-Allocation Optimizer — Exact Math + SOTA Code Structure

Research date: 2026-07-26. Scope: nail down the exact convex-programming formulations
(coded for CVXPY) that define "institutional-grade" for a portfolio/risk-allocation
optimizer engine, cross-checked against the actual source code of three production
libraries (Qlib, cvxportfolio, Riskfolio-Lib), not just textbook summaries.

**Verification method**: primary papers were downloaded and read directly (PDF, not
abstract/snippet) from the authors' own hosting (Ledoit's site, Uryasev's university
page, Roncalli's site, Stanford). Qlib, cvxportfolio, and Riskfolio-Lib were `git
clone`d and their actual `.py` source read — not blog summaries of them. Every
formula below is tagged with a source grade:
- **[A-primary, verified]** — read the actual paper PDF or the actual library source in this session.
- **[B-secondary]** — well-established in the literature / secondary corroboration, but the
  specific primary PDF could not be fetched in this session (flagged explicitly, not silently assumed).

---

## 0. Bottom line / recommended default

**Recommended default engine: Mean-CVaR (Rockafellar–Uryasev LP) with a hard
scenario-count floor, falling back to parametric Mean-Variance (Ledoit-Wolf shrunk Σ)
when the empirical scenario set is too thin to trust.** Layer on: ERC/risk-parity as
an alternative *risk-model* (not return-model) for the "no-conviction" regime,
Qlib-style benchmark-relative tracking-error objective if/when a benchmark index
exists, cardinality via iterative-reweighted-ℓ1 + resolve (not raw MILP+CVaR, which
is too heavy to run intraday), and integer lot rounding as greedy post-processing
with a resolve-on-residual step, never silent truncation. Turnover/transaction cost
enters as a linear ‖w − w_prev‖₁ penalty (cvxportfolio's model additionally adds a
convex market-impact term, `b·σ·|z|^1.5/√V`, which is the honest SOTA form once
volume data exists).

---

## 1. Mean-CVaR (Rockafellar–Uryasev, 2000)

**Primary source** [A-primary, verified]: R.T. Rockafellar & S. Uryasev, "Optimization
of Conditional Value-at-Risk," *Journal of Risk*, Vol. 2, No. 3 (Spring 2000), pp.
21–41. PDF read directly from
https://uryasev.ams.stonybrook.edu/wp-content/uploads/2011/11/CVaR1_JOR.pdf (Uryasev's
own university page — this is the author's canonical hosted copy of the published
journal article).

### 1.1 Definitions (paper's own notation, §2)

Let `f(x, y)` be the **loss** for decision vector `x` (portfolio weights) under random
vector `y` (asset returns), `Ψ(x, α) = P(f(x,y) ≤ α)` the loss CDF. For confidence
level `β ∈ (0,1)`:

- β-VaR: `α_β(x) = min{α : Ψ(x,α) ≥ β}`  (eq. 2)
- β-CVaR: `φ_β(x) = (1−β)⁻¹ ∫_{f(x,y)≥α_β(x)} f(x,y) p(y) dy`  (eq. 3)

### 1.2 The key auxiliary function (Theorem 1, the heart of the paper)

Define, for `(x, α) ∈ X × ℝ`:

```
F_β(x, α) = α + (1−β)⁻¹ · E_y[ (f(x,y) − α)⁺ ]                         (eq. 4)
```
where `[t]⁺ = max(t, 0)`.

**Theorem 1** [A-primary, verified — read directly, p.24-25 of the PDF]: `F_β(x,·)` is
convex and continuously differentiable in α, and:

```
φ_β(x) = min_α  F_β(x, α)                                              (eq. 5)
```

i.e. **CVaR at a fixed x can be computed by an unconstrained scalar convex
minimization over α — no need to compute VaR first.**

**Theorem 2** [A-primary, verified, p.25-26]: minimizing β-CVaR over `x ∈ X` is
*equivalent* to jointly minimizing `F_β(x,α)` over `(x,α) ∈ X × ℝ`:

```
min_{x∈X} φ_β(x)  =  min_{(x,α)∈X×ℝ} F_β(x,α)                          (eq. 10)
```

and if `f(x,y)` is convex in `x` and `X` is a convex set, the joint minimization is an
instance of **convex programming.**

### 1.3 Scenario (LP) reformulation — exactly what the task asked for

The paper approximates the expectation in `F_β` by sampling `y_1, …, y_q` (empirical
scenarios), giving [A-primary, verified, eq. 9 & p.27-28]:

```
F̃_β(x, α) = α + 1/(q(1−β)) · Σ_{k=1}^{q} [f(x, y_k) − α]⁺              (eq. 9)
```

For the portfolio case the paper sets `x_j ≥ 0, Σx_j = 1` (eq. 11) and loss
`f(x,y) = −xᵀy` (eq. 12, 23), i.e. loss is *negative return*. Substituting:

```
F̃_β(x, α) = α + 1/(q(1−β)) Σ_k [ −xᵀy_k − α ]⁺
```

**This is literally the `ζ + 1/((1−α)S) Σ_s (−wᵀr_s − ζ)⁺` form in the task** —
`α ↔ ζ`, `β ↔ α(confidence)`, `q ↔ S`, `y_k ↔ r_s`.

The paper shows [A-primary, verified, p.27-28] this reduces to an **LP** by
introducing one auxiliary real variable `u_k` per scenario:

```
minimize        α + 1/(q(1−β)) Σ_{k=1}^{q} u_k
subject to      u_k ≥ 0                           for k = 1..q
                xᵀy_k + α + u_k ≥ 0                for k = 1..q     (i.e. u_k ≥ −xᵀy_k − α)
                x ∈ X  (e.g. x ≥ 0, Σx_j = 1, μ(x) ≤ −R for a target-return constraint)
```

### 1.4 Full `max_w wᵀμ − λ·CVaR_α(w)` program, CVXPY form

Variables: `w ∈ ℝᴺ` (portfolio weights), `ζ ∈ ℝ` (the VaR/threshold auxiliary, the
paper's `α`), `u ∈ ℝ_+ˢ` (one slack per scenario, the paper's `u_k`).

```python
import cvxpy as cp
import numpy as np

S, N = r.shape           # r: S scenarios x N assets, empirical/bootstrapped returns
mu   = r.mean(axis=0)    # expected return vector (or a separate alpha forecast)
alpha_conf = 0.95         # confidence level (task's "α"; paper's "β")
lam  = 1.0                # risk-aversion, task's λ

w   = cp.Variable(N)
zeta = cp.Variable()               # VaR threshold  (paper's α / Rockafellar-Uryasev ζ)
u   = cp.Variable(S, nonneg=True)  # per-scenario shortfall slack (paper's u_k)

cvar = zeta + cp.sum(u) / ((1 - alpha_conf) * S)     # exact LP CVaR, eq. 9 above

constraints = [
    u >= -(r @ w) - zeta,        # u_k >= (-w^T r_s - zeta), i.e. u_k >= [.]+ via u>=0 below
    u >= 0,
    cp.sum(w) == 1,
    w >= 0,                      # long-only; drop for long/short
]

objective = cp.Maximize(mu @ w - lam * cvar)
prob = cp.Problem(objective, constraints)
prob.solve(solver=cp.ECOS)       # or cp.CLARABEL / cp.SCS
```

**Exact variable/constraint list** (as requested):
- Variables: `w ∈ ℝᴺ` (weights), `ζ ∈ ℝ` (VaR aux, unconstrained), `u ∈ ℝ_+ˢ` (S
  shortfall slacks).
- Constraints: `u_s ≥ −wᵀr_s − ζ` for each scenario `s` (S constraints), `u_s ≥ 0` (S
  constraints, redundant with `u ≥ 0` bound on the Variable), `Σw_j = 1`, `w ≥ 0` (or
  box bounds), optionally `wᵀμ ≥ R_target` (Rockafellar-Uryasev's eq. 15 style gain
  constraint).
- Total scenario-dependent constraints: `2S`. This is why CVaR is an **LP** in `w, ζ,
  u` jointly (given empirical scenarios) — no quadratic form appears anywhere,
  confirmed by Theorem 2 (§1.2 above): convex `f` + convex `X` ⇒ joint convex program.

**Note on solvers used in practice**: Riskfolio-Lib's actual CVXPY implementation
[A-primary, verified — read directly from `riskfolio/src/Portfolio.py` source, cloned
from github.com/dcajasn/Riskfolio-Lib] confirms this exact structure verbatim in
production code (variable names differ but the math is identical):
```python
# Riskfolio-Lib Portfolio.py, rp_optimization() and optimization(), CVaR block:
VaR_1 = cp.Variable((1, 1))                 # this is the paper's "alpha" / task's "zeta"
Z1 = cp.Variable((T, 1))                    # this is the paper's "u_k", one per scenario (T rows)
# ... constraints: Z1 >= 0 ,  Z1 >= -returns @ w - VaR_1  (verified in source)
CVaR_L = VaR_1 + 1 / (alpha * T) * cp.sum(Z1)
```
This is a direct, independent (different author, different codebase) re-implementation
of exactly the Rockafellar–Uryasev LP — strong triangulation.

---

## 2. Mean-Variance (Markowitz) + Ledoit-Wolf shrinkage

### 2.1 Markowitz QP

Standard, uncontested (Markowitz 1952, *Portfolio Selection*, Journal of Finance —
foundational, not re-verified by PDF here since it's undisputed textbook material
[B-secondary, universally cited, e.g. by Rockafellar-Uryasev themselves as problem
(P3), which we did verify directly reading their paper, p.28]):

```
max_w   wᵀμ − λ·wᵀΣw
s.t.    Σw_j = 1,  w ≥ 0  (long-only; drop for long/short)
```

CVXPY:
```python
w = cp.Variable(N)
Sigma = cp.psd_wrap(Sigma_hat)     # shrunk covariance, see 2.2
objective = cp.Maximize(mu @ w - lam * cp.quad_form(w, Sigma))
constraints = [cp.sum(w) == 1, w >= 0]
prob = cp.Problem(objective, constraints)
prob.solve(solver=cp.ECOS)
```
This is a QP (convex quadratic objective, linear constraints) — CVXPY dispatches it
to ECOS/OSQP/CLARABEL as an SOCP-representable QP.

### 2.2 Ledoit-Wolf shrinkage — exact formulas

**Primary source** [A-primary, verified — full PDF read]: O. Ledoit & M. Wolf, "Honey,
I Shrunk the Sample Covariance Matrix," *Journal of Portfolio Management*, 30(4),
2004, pp. 110-119 (DOI: 10.3905/jpm.2004.110). PDF (working-paper version, Nov 2003,
identical formulas to the published JPM article per Qlib's own citation cross-check
below) read directly from https://ledoit.net/honey.pdf, hosted on the author's own
site.

**The shrinkage estimator** (paper's eq. 2):
```
Σ̂_shrink = δ* · F + (1 − δ*) · S
```
where `S` = sample covariance matrix, `F` = the shrinkage **target**, `δ*` = shrinkage
**intensity** (a scalar in [0,1]).

**Shrinkage target — constant-correlation model** (this paper's specific contribution,
§3.2, formalized in Appendix A, eq. 3) [A-primary, verified]:

Let `s_ij` = sample covariance entries, `r_ij = s_ij/√(s_ii·s_jj)` sample pairwise
correlations, and `r̄ = 2/((N−1)N) · Σ_{i<j} r_ij` the average sample correlation
across all pairs. The constant-correlation shrinkage target `F` has entries:

```
f_ii = s_ii                      (keep the sample variance on the diagonal)
f_ij = r̄ · √(s_ii · s_jj)        (off-diagonal: same variance, but every pair
                                   forced to share the single average correlation r̄)
```

**Shrinkage intensity — the optimal δ*** (Appendix B, eq. 4-5) [A-primary, verified]:
minimizes the expected quadratic (Frobenius-norm) loss `R(δ) = E‖δF + (1−δ)S − Σ‖²`.
Writing `π̂` = sum of asymptotic variances of the sample-covariance entries, `ρ̂` = sum
of asymptotic covariances between the shrinkage-target entries and the
sample-covariance entries, `γ̂ = Σᵢⱼ(f_ij − s_ij)²` (misspecification of the target),
`κ̂ = (π̂ − ρ̂)/γ̂`, and `T` = number of return observations:

```
δ̂* = max{ 0, min{ κ̂/T, 1 } }                                          (eq. 5)
```
(clipped to `[0,1]` because finite-sample noise can occasionally push the raw ratio
outside that range).

**Cross-check via Qlib's own source** [A-primary, verified — read directly from
`qlib/model/riskmodel/shrink.py`, cloned from github.com/microsoft/qlib, commit
`79633dd9506ea689e5400dea0197717b5b3d74b7`]: Qlib's `ShrinkCovEstimator` implements
*exactly* this constant-correlation target and cites the same two Ledoit-Wolf papers
by DOI in its own docstring:
```python
class ShrinkCovEstimator(RiskModel):
    """
    ...
    S_hat = (1 - alpha) * S + alpha * F
    References:
        [2] Ledoit, O., & Wolf, M. (2004). Honey, I shrunk the sample covariance matrix.
            Journal of Portfolio Management, 30(4), 1-22. https://doi.org/10.3905/jpm.2004.110
    """
    def _get_shrink_target_const_corr(self, X, S):
        n = len(S); var = np.diag(S); sqrt_var = np.sqrt(var)
        covar = np.outer(sqrt_var, sqrt_var)
        r_bar = (np.sum(S / covar) - n) / (n * (n - 1))
        F = r_bar * covar
        np.fill_diagonal(F, var)
        return F

    def _get_shrink_param_lw_const_corr(self, X, S, F):
        t, n = X.shape
        # ... implements the exact pi-hat, rho-hat, gamma-hat, kappa-hat above
        alpha = max(0, min(1, kappa / t))
        return alpha
```
Note Qlib names the intensity `alpha` where Ledoit-Wolf's paper calls it `δ` (the
paper explicitly notes it switched symbols from its own earlier 2003 paper's `α` to
avoid clashing with expected-excess-return `α` — see paper's footnote 3, p.11). Two
independent codebases (Qlib, and any CVXPY implementation following the paper
directly) computing the *identical* closed-form is strong triangulation that this is
the correct, faithfully-transcribed formula.

CVXPY-ready Python (paper's formulas, standalone):
```python
def ledoit_wolf_const_corr_shrinkage(returns: np.ndarray) -> np.ndarray:
    """returns: T x N matrix of asset returns (not demeaned assumed handled inside)."""
    T, N = returns.shape
    X = returns - returns.mean(axis=0, keepdims=True)
    S = (X.T @ X) / T                                  # sample covariance (biased, T denom)
    var = np.diag(S)
    sqrt_var = np.sqrt(var)
    corr_denom = np.outer(sqrt_var, sqrt_var)
    r_bar = (np.sum(S / corr_denom) - N) / (N * (N - 1))
    F = r_bar * corr_denom
    np.fill_diagonal(F, var)
    # pi-hat: sum of asymptotic variances of sample covariance entries
    y = X ** 2
    phi_mat = (y.T @ y) / T - S ** 2
    pi_hat = np.sum(phi_mat)
    # rho-hat: sum of asymptotic covariances between F entries and S entries
    theta_mat = ((X ** 3).T @ X) / T - var[:, None] * S
    np.fill_diagonal(theta_mat, 0)
    rho_hat = np.sum(np.diag(phi_mat)) + r_bar * np.sum(
        np.outer(1 / sqrt_var, sqrt_var) * theta_mat
    )
    gamma_hat = np.sum((F - S) ** 2)
    kappa_hat = (pi_hat - rho_hat) / gamma_hat
    delta_star = max(0.0, min(kappa_hat / T, 1.0))
    return delta_star * F + (1 - delta_star) * S
```

---

## 3. Risk-Parity / Equal-Risk-Contribution (ERC)

**Primary source** [A-primary, verified — full PDF read]: S. Maillard, T. Roncalli, J.
Teiletche, "On the Properties of Equally-Weighted Risk Contributions Portfolios,"
*Journal of Portfolio Management*, 36(4), 2010, pp. 60-70. Working-paper version
(May 2009) read directly from http://www.thierry-roncalli.com/download/erc.pdf,
hosted on co-author Roncalli's own site.

### 3.1 Risk contribution — exact definitions (paper §2.1)

Let `σ(x) = √(xᵀΣx)`. The **marginal risk contribution** of asset i (paper eq., §2.1):
```
∂σ(x)/∂x_i = (x_i σ_i² + Σ_{j≠i} x_j σ_ij) / σ(x)   =   (Σx)_i / σ(x)
```
The **total risk contribution** of asset i: `σ_i(x) = x_i · ∂σ(x)/∂x_i`, and Euler's
theorem (σ is homogeneous of degree 1) gives the exact decomposition:
```
σ(x) = Σ_{i=1}^{N} σ_i(x)
```
**Task's `RC_i = w_i(Σw)_i / (wᵀΣw)`** is the *normalized* (fraction-of-total, using
variance instead of vol in the denominator) version of this same quantity — both are
standard; the paper's own version normalizes by `σ(x)` not `σ(x)²`, but `RC_i(paper) =
σ_i(x)/σ(x)` and `RC_i(task, variance form) = σ_i(x)²-analog` are the same equalization
condition up to a monotone rescaling, so the ERC condition below is identical either
way.

### 3.2 ERC condition (paper eq. 1-2)

```
x* = { x ∈ [0,1]^N : Σx_i = 1,  x_i · ∂_{x_i}σ(x) = x_j · ∂_{x_j}σ(x)  ∀ i,j }
```
i.e. find weights such that every asset's *total* risk contribution is equal
(`σ_i(x) = σ(x)/N` for all i).

**Closed forms only exist in special cases** [A-primary, verified, §3.1-3.2]:
- 2-asset case: `x* = ( σ₁⁻¹/(σ₁⁻¹+σ₂⁻¹), σ₂⁻¹/(σ₁⁻¹+σ₂⁻¹) )` — inverse-vol weighting,
  independent of correlation.
- Equal-correlation case (N>2): `x_i = σ_i⁻¹ / Σⱼσⱼ⁻¹` (paper's eq. 3) — inverse-vol
  weighting again.
- General case: **no closed form** — `x_i = β_i⁻¹/Σβⱼ⁻¹` (eq. 5) is *endogenous*
  (β_i depends on x itself), so a numerical solve is required.

### 3.3 Convex reformulation — the paper's own log-barrier form, and Spinu's generalization

The Maillard-Roncalli-Teiletche paper itself already proposes (§3.3, eq. 7-8)
[A-primary, verified] the log-barrier convex program:

```
y* = argmin_y  √(yᵀΣy)
s.t.           Σᵢ ln(y_i) ≥ c,   y ≥ 0
```
with `c` an arbitrary constant (any `c` works; only the shape of the optimum matters),
then **renormalize** `x_i* = y_i*/Σⱼyⱼ*` to get the ERC portfolio. The paper notes this
is a convex program (a convex quadratic-form objective with a concave-constraint
lower bound) and its solution is **unique** whenever Σ is positive-definite
[A-primary, verified, p.8: "the formulation in (7) has the advantage that it allows
to show that the ERC solution is unique... it is defining the minimization program of
a quadratic function... with a lower bound (itself a convex function)"].

**Spinu (2013)** [B-secondary — the specific SSRN PDF for F. Spinu, "An Algorithm for
Computing Risk Parity Weights" (SSRN 2297383) returned 403/404 in this session and
could not be independently re-verified by direct PDF read; the formulation below is
the version universally cited in the subsequent literature (e.g. Roncalli's 2013 book
*Introduction to Risk Parity and Budgeting*, and is corroborated by production code —
see below) reformulates this as an *unconstrained* unconstrained convex QP with a log
barrier baked into the objective, which is the form the task asked for:
```
min_w   ½ wᵀΣw − Σᵢ bᵢ ln(w_i)
s.t.    w > 0
```
where `b_i` are target risk-budget weights (`b_i = 1/N` for equal-risk ERC). This is
the same "quadratic + log-barrier" convex object as the paper's eq. 7 above, just
moved from a constrained to an unconstrained (barrier) form — mathematically
equivalent up to the multiplier on the barrier term.

**Cross-check via Riskfolio-Lib's actual production code** [A-primary, verified —
read directly from `riskfolio/src/Portfolio.py`, `rp_optimization()`, cloned from
github.com/dcajasn/Riskfolio-Lib]: the library's real risk-parity solver uses
*exactly* this log-barrier-then-renormalize pattern, via CVXPY's exponential cone
(needed because `cp.log` on a vector inside a linear inequality requires the
`ExpCone` representation for some solvers):
```python
# Riskfolio-Lib Portfolio.py, rp_optimization():
w  = cp.Variable((N, 1))
k  = cp.Variable((1, 1))              # normalization variable (paper's implicit "sum y")
log_w = cp.Variable((N, 1))
rb = ...                              # risk-budget vector b_i (1/N for ERC)
constraints += [
    rb.T @ log_w >= 1,
    cp.ExpCone(log_w * 1000, np.ones((N, 1)) * 1000, w * 1000),   # w >= exp(log_w), i.e. log_w = log(w)
]
# objective minimizes risk (e.g. sqrt(w^T Sigma w) for MV) subject to the above
# then x* = w* / sum(w*)
```
This is an independent, different-author re-implementation of the identical
"quadratic-risk + log-barrier, then renormalize" idea traced from the 2010 paper
through to Spinu's generalization — strong triangulation even though Spinu's own PDF
was unreachable this session.

CVXPY, standalone (recommended engine form, DCP-clean without needing ExpCone
directly — CVXPY's `cp.log` handles the conversion internally):
```python
w = cp.Variable(N, pos=True)
b = np.ones(N) / N        # equal risk budget; generalize to arbitrary budgets for risk-budgeting
objective = cp.Minimize(0.5 * cp.quad_form(w, Sigma))
constraints = [b @ cp.log(w) >= 1]     # log-barrier diversification floor (Spinu / MRT eq. 7)
prob = cp.Problem(objective, constraints)
prob.solve(solver=cp.ECOS)
x = w.value / w.value.sum()            # renormalize to get final ERC weights
```

---

## 4. Qlib `EnhancedIndexingOptimizer` — exact objective (read from source)

**Source** [A-primary, verified — full file read]:
`qlib/contrib/strategy/optimizer/enhanced_indexing.py`, cloned from
github.com/microsoft/qlib, commit `79633dd9506ea689e5400dea0197717b5b3d74b7`
(2026-07-23). Reproduced verbatim (class docstring + `__call__`):

```python
class EnhancedIndexingOptimizer(BaseOptimizer):
    """
    Notations:
        w0: current holding weights      wb: benchmark weight
        r: expected return                F: factor exposure
        cov_b: factor covariance          var_u: residual variance (diagonal)
        lamb: risk aversion parameter     delta: total turnover limit
        b_dev: benchmark deviation limit  f_dev: factor deviation limit
    Also denote:
        d = w - wb: benchmark deviation   v = d @ F: factor deviation

    The optimization problem for enhanced indexing:
        max_w  d @ r - lamb * (v @ cov_b @ v + var_u @ d**2)
        s.t.   w >= 0
               sum(w) == 1
               sum(|w - w0|) <= delta
               d >= -b_dev
               d <= b_dev
               v >= -f_dev
               v <= f_dev
    """
```
This matches the task's requested form **exactly**: `max_w dᵀr − λ(vᵀΣ_b v +
var_uᵀd²)` where `d = w − w_bench` and `v = d @ F` (factor exposure of the deviation
— confirmed, not `w`'s own factor exposure, but the *deviation's* factor exposure,
which is the correct Barra-style active-risk decomposition: total tracking-error
variance = factor-risk term `vᵀΣ_b v` + idiosyncratic-risk term `var_uᵀd²`).

Actual CVXPY code (verbatim from source, lightly trimmed):
```python
w = cp.Variable(len(r), nonneg=True)
d = w - wb                                    # benchmark exposure
v = d @ F                                     # factor exposure of the deviation
ret  = d @ r                                  # excess return
risk = cp.quad_form(v, cov_b) + var_u @ (d**2)  # tracking-error variance
obj  = cp.Maximize(ret - lamb * risk)

cons = [cp.sum(w) == 1, w >= lb, w <= ub]     # lb/ub incorporate b_dev bounds + forced-hold/sell masks
if f_dev is not None:
    cons += [v >= -f_dev, v <= f_dev]
if delta is not None and w0 is not None:
    cons += [cp.norm(w - w0, 1) <= delta]     # total turnover constraint (note: constraint, not penalty)

prob = cp.Problem(obj, cons)
prob.solve(solver=cp.ECOS, warm_start=True)
```
Notable production-hardening details in the real source (not in the docstring math,
but load-bearing for "institutional-grade"):
- **Two-trial fallback**: if the problem is infeasible with the turnover constraint,
  Qlib automatically retries *without* the turnover constraint (logs a warning)
  rather than crashing — a real engine needs this same degrade-gracefully pattern.
- **Warm-starting**: `w.value = wb` before solving, and `warm_start=True` passed to
  ECOS — meaningful for intraday re-optimization cadence.
- **Epsilon-then-renormalize**: after solving, weights below `epsilon` (default
  5e-5) are zeroed and the remainder renormalized to sum to 1 — this *is* the
  "solve-then-truncate-then-renormalize" cardinality heuristic mentioned in the task,
  seen here in Microsoft's own production code, confirming it's the accepted
  practical pattern rather than an ad hoc shortcut.
- Return scaling: `r` is rescaled to have the same order of magnitude as the
  volatility (`r = r/r.std() * sqrt(mean(diag(F@cov_b@F.T) + var_u))`) before
  optimizing — otherwise `lamb` has no stable, transferable meaning across
  rebalances. This is a detail every λ-weighted objective in this document needs.

Separately, Qlib's plain `PortfolioOptimizer` (`qlib/contrib/strategy/optimizer/optimizer.py`,
same repo, same commit) [A-primary, verified] implements GMV / MVO / **risk-parity**
/ inverse-vol via `scipy.optimize.minimize` (SLSQP) rather than CVXPY, using the
literal squared-residual risk-parity objective:
```
min_w  Σᵢ [ w_i − (wᵀSw)/((Sw)_i · N) ]²
```
— i.e. an unconstrained-form penalty on deviation from equal *fractional* risk
contribution, an alternative to the log-barrier form in §3.3 (SLSQP, not CVXPY,
because the squared-residual form isn't a DCP-convex expression in general — this
is why Spinu's convex log-barrier reformulation is preferred when a convex solver is
required).

---

## 5. Cardinality constraint (max K nonzero weights)

### 5.1 Exact MILP form
Standard, textbook OR formulation [B-secondary — well-established across the
optimization-in-finance literature (e.g., Bienstock 1996, "Computational study of a
family of mixed-integer quadratic programming problems," *Math. Programming* 74;
Bertsimas & Shioda 2009, "Algorithm for cardinality-constrained quadratic
optimization," *Comp. Optimization & Applications* 43; Chang, Meade, Beasley,
Sharaiha 2000, "Heuristics for cardinality constrained portfolio optimisation,"
*Computers & OR* 27 — consensus formulation across all of these; specific PDFs not
independently re-fetched in this session, flagged rather than silently presented as
directly verified]:

```
Variables:  w ∈ ℝᴺ (weights), z ∈ {0,1}ᴺ (asset-selected indicator)
Objective:  max_w  wᵀμ − λ·CVaR_α(w)   (or any convex objective from §1-4)
Constraints:
    w_i ≤ M · z_i           for all i     (big-M: w_i can only be nonzero if z_i=1)
    w_i ≥ ε · z_i            for all i     (optional: enforce a minimum position size, avoids "MILP finds a 1e-9 weight")
    Σ z_i ≤ K                             (at most K names)
    Σ w_i = 1,  w ≥ 0
```
`M` should be as tight as possible (e.g. the single-name concentration cap already in
force, not an arbitrary large constant) — a loose big-M badly weakens the LP
relaxation bound and blows up solve time, which is the single most common practical
mistake in cardinality-constrained portfolio MILPs.

### 5.2 Why MILP+CVaR is heavy, and the practical relaxations
CVaR already introduces `S` extra continuous variables + `2S` constraints (§1.3); add
`N` binaries for cardinality and the combined mixed-integer LP/QP has a
worst-case-exponential branch-and-bound tree that does not scale to intraday
re-optimization cadence over a large universe. Three standard alternatives, in
increasing order of fidelity to true cardinality:

1. **Solve-then-truncate-then-resolve** (what Qlib actually does in production — see
   §4 "epsilon-then-renormalize" — and the most common practical approach): solve the
   continuous relaxation, zero out weights below a floor (or keep only the top-K by
   |weight|), then **re-solve** the same convex program restricted to the surviving
   names (so the remaining capital is optimally reallocated among the K survivors,
   not just renormalized pro-rata). Cheap (2 convex solves, no MILP), but not
   provably optimal for the cardinality-constrained problem.
2. **Iterative reweighted-ℓ1** [A-primary, verified — full PDF read]: E. Candès, M.
   Wakin, S. Boyd, "Enhancing Sparsity by Reweighted ℓ1 Minimization," *J. Fourier
   Anal. Appl.* 14 (2008), 877-905, DOI 10.1007/s00041-008-9045-x, PDF read directly
   from https://web.stanford.edu/~boyd/papers/pdf/rwl1.pdf (Boyd's own Stanford
   page). The algorithm (paper §2.2, eq. 6-7):
   ```
   1. w_i^(0) = 1 for all i (iteration 0 weights)
   2. Solve the weighted-ℓ1 problem:  x^(ℓ) = argmin Σᵢ w_i^(ℓ)|x_i|  s.t. (constraints)
   3. Update weights:  w_i^(ℓ+1) = 1 / (|x_i^(ℓ)| + ε)      — small weights get
      driven to zero next round; already-large weights are barely penalized
   4. Repeat for a small fixed number of iterations (paper uses ℓ_max = 2 in its
      main sparse-recovery example) or until convergence.
   ```
   Applied to portfolio cardinality: replace the plain turnover/ℓ1 penalty (§7) with
   this reweighted version and it converges towards a sparser (lower effective
   cardinality) solution than a single unweighted ℓ1 shrinkage would, while every
   iteration stays a plain convex program (no MILP solver needed).
3. **Raw MILP** (CVXPY + a MIP-capable backend — ECOS_BB, CBC, GLPK_MI, or a
   commercial solver like Gurobi/MOSEK via CVXPY's interface) for the exact §5.1
   formulation — reserved for end-of-day / overnight rebalances where solve time is
   not intraday-critical, never for the hot path.

CVXPY sketch for approach 3 (only when a MIP solver is available and off the hot
path):
```python
w = cp.Variable(N, nonneg=True)
z = cp.Variable(N, boolean=True)
M = 0.20  # e.g. single-name cap already enforced elsewhere; keep M as tight as possible
constraints = [
    w <= M * z,
    cp.sum(z) <= K,
    cp.sum(w) == 1,
]
# objective: any convex objective from sections 1-4 (e.g. Mean-CVaR)
prob = cp.Problem(cp.Maximize(mu @ w - lam * cvar_expr), constraints)
prob.solve(solver=cp.GLPK_MI)   # or cp.CBC / cp.MOSEK if licensed
```

---

## 6. Integer lot/tick rounding

### 6.1 The two approaches — confirmed by a real, actively-maintained OSS implementation

**Source** [A-primary, verified — full method bodies read]:
`robertmartin8/PyPortfolioOpt`, `pypfopt/discrete_allocation.py`, `DiscreteAllocation`
class (cloned from github.com/robertmartin8/PyPortfolioOpt). This library ships
*both* of the approaches the task named, as two named, swappable methods on the same
class — direct, load-bearing confirmation that these are the two accepted
practical patterns, not a hypothetical dichotomy:

- **`greedy_portfolio()`** — post-optimization rounding, exactly the algorithm
  described below, read verbatim from source:
  1. First round: for every ticker (processed in descending weight order), buy
     `n_shares = floor(weight · total_value / price)` — always rounds **down**,
     guaranteeing the running cost never exceeds available funds.
  2. Second round (the actual "greedy-fill" loop): while `available_funds > 0`,
     recompute the *current realized* weights from shares bought so far, compute the
     `deficit = ideal_weights − current_weights` vector, and buy **one more share**
     of the asset with the largest positive deficit (largest under-allocation
     relative to target) — repeat until no affordable asset still has positive
     deficit. If the highest-deficit asset can't be afforded with remaining cash, it
     falls through to the next-highest-deficit asset (bounded to 10 tries) before
     giving up and returning the leftover cash.
  3. Long/short books are handled by splitting into a long sub-portfolio and a short
     sub-portfolio, each independently greedy-allocated, then recombined.
- **`lp_portfolio()`** — the MILP-with-integer-lot-variables approach, implemented
  with CVXPY directly (integer variables + a solver that supports MIP, defaulting to
  `ECOS_BB` when available) — confirming this is a real, off-the-shelf, drop-in
  alternative when solve-time budget allows, not a purely theoretical option.

This is a stronger confirmation of §6.1/6.2 than the general OR literature alone: a
maintained, widely-used (see §12 sourcing evaluation) library ships the exact same
two-approach split the task asked about, as literal method names on one class.

- **Post-optimization rounding** (industry-standard default; used by essentially
  every practical implementation, including cvxportfolio's simulator layer and
  PyPortfolioOpt's `greedy_portfolio()` above): solve the continuous convex program
  for weights `w*`, convert to share counts `n_i = w_i* · V / p_i` (V = portfolio
  value, p_i = price), round each `n_i` to the nearest tradeable lot size (1 share
  for most equities; `L` for NSE F&O lot-size contracts), then **greedily fill the
  residual cash** left over from rounding by nudging the position(s) with the
  largest deficit between ideal and realized weight up by one more lot until the
  residual cash is smaller than one lot's value at every remaining price.
- **MILP with integer lot variables**: replace `w_i` directly with an integer
  variable `n_i ∈ ℤ` (or `n_i = L·k_i, k_i ∈ ℤ` for lot-size `L`) inside the
  optimization, i.e. `w_i = n_i·p_i/V` substituted into the *original* convex
  objective — this turns even the plain Markowitz QP into a MIQP. Provably optimal
  given integer constraints, but pays the same combinatorial cost as §5's MILP, and
  additionally couples cardinality-like nonconvexity into every name (not just a
  binary "in/out"), making it markedly heavier than the cardinality MILP alone.
  PyPortfolioOpt's `lp_portfolio()` is the confirmed reference implementation of this
  path.

### 6.2 Standard practical approach and its pitfalls
Given intraday latency constraints, **post-optimization greedy-fill rounding is the
standard practical approach** — this is what the task explicitly names, and it is
consistent with what Qlib does implicitly at the "epsilon-then-renormalize" step
(§4) and what a lot-aware execution layer must additionally do on top of Qlib's raw
continuous output (Qlib itself does not model lot sizes at all — it operates purely
in continuous weight space, `w = cp.Variable(len(r), nonneg=True)`, confirmed by
direct source read in §4).

**Pitfalls, most severe first:**
1. **Small portfolios / high-price names**: if `V` is small relative to a stock's lot
   value (common for NSE F&O contracts with large lot sizes, or simply high-priced
   stocks), naive rounding can force a position to either 0 or a lot size that is a
   large fraction of the whole book — the rounding error is *not* negligible relative
   to the optimized weight, and greedy-fill needs a "skip this name if 1 lot already
   exceeds its target weight by more than X%" guard rather than blindly buying a lot.
2. **Risk-budget drift compounding across rebalances**: repeated round-then-drift
   without re-solving against the *actual current* (post-rounding) holdings as `w0`
   in the next turnover constraint causes systematic risk-budget drift over many
   rebalances — the next optimization must always use the *realized* (rounded)
   holdings as its `w0`, never the previous period's unrounded target.
3. **Greedy-fill is not the same as re-optimizing**: greedily bumping the
   "best" name by a lot to consume residual cash is a heuristic, not a re-solve — it
   can leave the realized portfolio measurably off the efficient frontier
   relative to what a full integer re-solve would find, especially when residual
   cash is a large fraction of one lot's value for many names simultaneously (small
   books, expensive stocks). A cheap partial fix: after greedy-fill, do a *local*
   re-solve of the continuous problem restricted to ± 1 lot around each rounded
   position (a small, fast QP) rather than a full MILP.
4. **Directional rounding bias**: always rounding down (floor) systematically
   underinvests and leaves growing cash drag across many rebalances; always rounding
   to nearest avoids this but can occasionally round a position *up through* a
   cardinality or concentration cap — the rounding step must re-check every
   hard constraint (single-name cap, cardinality K, leverage) after rounding, not
   just before.

---

## 7. Transaction-cost / turnover penalty

### 7.1 Standard linear form (task's requested form)
```
objective += − γ · ‖w − w_prev‖₁         (γ = cost coefficient, e.g. half the
                                            round-trip bid-ask spread + brokerage bps)
```
CVXPY:
```python
turnover_cost = gamma * cp.norm(w - w_prev, 1)
objective = cp.Maximize(mu @ w - lam * risk_expr - turnover_cost)
```
This is exactly linear (an ℓ1 norm), so it stays inside whatever cone program the
risk term already requires (LP for CVaR, QP for Markowitz, log-barrier convex for
ERC) — it never changes the *problem class*, only adds `2N` extra linear terms via
CVXPY's automatic epigraph reformulation of `‖·‖₁`.

### 7.2 SOTA richer form (cvxportfolio) — confirmed by source read
**Source** [A-primary, verified — full class read]: `cvxportfolio/costs.py`,
`TransactionCost` class, cloned from github.com/cvxgrp/cvxportfolio. Per-asset cost,
verbatim from the docstring (labeled "equation 2.2" of the project's own paper,
*cvxportfolio: A Python Package and a Book*):
```
cost(x) = a·|x| + b·σ·|x|^(3/2)/√V + c·x
```
where `x` = dollar amount traded, `a` = linear cost coefficient (e.g. half the
bid-ask spread + flat brokerage), `b` = market-impact coefficient (order 1), `σ` =
recent return volatility of the asset, `V` = (estimated) traded volume over the
period, `c` = a directional bias term (e.g. negative of the open-to-VWAP return if
executing at VWAP). The `|x|^1.5/√V` term is the classic square-root market-impact
law — this is the piece the plain `‖w−w_prev‖₁` penalty in the task's §7 and in most
academic Mean-CVaR/Markowitz papers omits, and it is what separates a
"textbook-adequate" turnover penalty from a SOTA one once real volume data is
available. CVXPY-compatible (confirmed convex — `cp.abs(z)**1.5` is DCP-convex since
the exponent is ≥1):
```python
z = w - w_prev          # dollar trade amounts (or weight-space, scaled by portfolio value)
cost = a * cp.abs(z) @ ones + b * (cp.abs(z) ** 1.5) @ (sigma / np.sqrt(volume_hat))
```
**Recommendation for this project**: start with the plain linear ℓ1 penalty (§7.1) —
it requires no volume data and is always DCP-safe — and add the market-impact term
only once a reliable intraday volume forecast exists (the same gating logic Qlib and
cvxportfolio both apply: volume-dependent cost terms are optional add-ons layered on
top of the linear term, never a replacement for it).

---

## 8. SOTA code-structure comparison

| | **Qlib `EnhancedIndexingOptimizer`** | **cvxportfolio** | **Riskfolio-Lib** |
|---|---|---|---|
| Repo (cloned, commit verified) | github.com/microsoft/qlib, `qlib/contrib/strategy/optimizer/` + `qlib/model/riskmodel/` | github.com/cvxgrp/cvxportfolio, `cvxportfolio/` | github.com/dcajasn/Riskfolio-Lib, `riskfolio/src/Portfolio.py` |
| Solver backend | CVXPY + ECOS (hardcoded, with try/except fallback) | CVXPY, solver-agnostic (user-selectable) | CVXPY, multiple solvers depending on cone type (LP/QP/SOCP/SDP/exp/power) |
| Objective shape | Single fixed formula: benchmark-relative `dᵀr − λ(vᵀΣ_b v + var_uᵀd²)` — one optimizer class, few knobs | Fully compositional: `Objective = Return − Risk − Σ Costs`, each term is a swappable class (`ReturnsForecast`, `FullCovariance`/`FactorModelCovariance`, `TransactionCost`, `HoldingCost`) combined via operator overloading | Also compositional but via a **risk-measure zoo**: one `Portfolio` object, `rm=` parameter selects among 20+ convex risk measures (MV, MAD, CVaR, CDaR, EVaR, Tail-Gini, Worst-Case, etc.) inside one shared `optimization()`/`rp_optimization()` method — breadth of risk models, not breadth of cost/return models |
| Multi-period? | No — single-period only | **Yes** — `SinglePeriodOptimization` and `MultiPeriodOptimization` policies, the latter explicitly accounts for how today's trade affects tomorrow's constraints/costs (its key differentiator) | No — single-period only |
| Risk-model layer | Separate module (`qlib/model/riskmodel/`) with `ShrinkCovEstimator` (Ledoit-Wolf / OAS / 3 shrink targets) supplied as a BYO covariance to the optimizer — clean separation of estimation vs optimization | `DiagonalCovariance`, `FullCovariance`, `FactorModelCovariance` as swappable risk-model estimator classes, same compositional pattern as costs | `ParamsEstimation.py` module supplies covariance/mu estimators (incl. shrinkage, Black-Litterman, factor models) separately from `Portfolio.py`'s optimization logic |
| Cardinality / integer support | None built in (continuous weights only; epsilon-truncate-renormalize as the only sparsification) | `MaxWeights`/`MinWeights`/`LeverageLimit` constraints exist but no native cardinality/MILP | Native: "Integer constraints enable mutually exclusive asset selections" + explicit cardinality-limit and turnover-restriction constraint API (per its docs) |
| Turnover / cost | `sum(|w-w0|) <= delta` — a hard **constraint**, not a penalty | `TransactionCost` (a|x|+b·σ|x|^1.5/√V+c·x, §7.2) as an objective **penalty**, composable with any other cost | Turnover constraints in its constraint API, alongside tracking-error and leverage bounds |
| Production-hardening details found in source | Two-trial solve (drop turnover constraint on infeasibility), warm-start, return-rescaling before optimizing, epsilon-truncate-then-renormalize | Extensive `Estimator`/`CvxpyExpressionEstimator` abstraction so cost/risk/return terms can pull live or forecast data per-period; explicit "paper section X.Y" doc cross-references for every formula | Bundled `AuxFunctions.py`/`ConstraintsFunctions.py` helpers translate human constraint specs (e.g. "asset A weight ≤ 10%") into the correct CVXPY constraint automatically |

**Design takeaway for this project**: cvxportfolio's compositional
Return/Risk/Cost-as-swappable-objects pattern is the right one to imitate for
extensibility (new cost/risk terms bolt on without touching the solver-wiring code);
Riskfolio-Lib's single risk-measure-zoo `Portfolio` class is the right one to imitate
for breadth (CVaR, MV, ERC all live behind one call signature, `rm=` selects the
measure); Qlib's two-trial-solve-with-fallback and warm-start pattern is the right
one to imitate for production robustness on the hot path.

---

## 9. Data reality: thin empirical scenario sets

**Context supplied by the task** (not independently re-derived in this research
session — treated as given, not re-verified against a live trade log here): the
project's current paper-trade history is concentrated in roughly one session-day
(~340 trades). That is nowhere near enough for an *honest* empirical CVaR at, say,
`α=0.95` — the 95th-percentile tail of 340 same-day, likely-correlated intraday
observations is a handful of data points, and the LP in §1.3 will happily return a
confident-looking but statistically meaningless number from `S` this small (the
Rockafellar-Uryasev LP itself, and every empirical-CVaR implementation cross-checked
in §1, silently accepts any `S` — nothing in the math or in Riskfolio-Lib's/Qlib's
source enforces a minimum scenario count; that check has to be added by the caller).

**How to handle this honestly, without overclaiming:**

1. **Scenario-count floor + honest degrade path.** Set an explicit minimum `S_min`
   (a reasonable floor for a 95%+ CVaR is on the order of `S_min ≈ 10/(1−α)` scenarios
   so the tail set (`(1−α)·S` worst observations) itself contains a handful of points
   — e.g. at α=0.95 that's `S_min ≈ 200`, at α=0.99 `S_min ≈ 1000`. Below `S_min`,
   **do not report a CVaR number as if it were reliable** — fall back to the
   parametric Mean-Variance program (§2) with a Ledoit-Wolf-shrunk covariance, which
   degrades gracefully because shrinkage is specifically designed to be robust when
   `T` (here, the scenario/observation count) is small relative to `N` (see §2.2,
   Ledoit-Wolf's own motivation: "the sample covariance matrix... contains a lot of
   estimation error when the number of data points is of comparable or even smaller
   order than the number of individual stocks" — precisely this project's regime with
   ~340 observations against a large universe).
2. **Bootstrap/block-bootstrap resampling to manufacture more scenarios from the same
   history** — standard technique, but must be block/moving-block bootstrap (resample
   contiguous chunks of the trading day, not i.i.d. individual trades) to preserve the
   intraday autocorrelation structure; naive i.i.d. resampling of 340 correlated
   intraday observations understates true tail risk because it destroys the
   volatility-clustering / momentum structure that drives real tail events. This
   manufactures *more scenario rows* but does **not** manufacture new information —
   it is a variance-reduction device for the CVaR *estimator* given the data that
   exists, not a substitute for having more independent trading days. This must be
   labeled in any dashboard/output as "bootstrap-resampled, N_effective ≈ (actual
   distinct days), not N_raw_scenarios" so nobody downstream mistakes resampled-row
   count for independent-observation count.
3. **Scenario-count honesty in the output.** Whatever the engine reports (CVaR
   number, or "fell back to parametric MV because S < S_min"), the *raw* scenario
   count (independent trading days, not resampled rows) and the confidence level used
   must be surfaced alongside the number — silently computing CVaR on 340 correlated
   observations and presenting it with the same confidence as a CVaR computed on 5
   years of daily data would be exactly the kind of overclaiming this research is
   asked to avoid.
4. **As more real trading days accumulate, promote automatically**: the engine should
   re-check `S` (in independent-day units) against `S_min` on every rebalance and
   switch from parametric-MV back to empirical Mean-CVaR the moment the real history
   crosses the floor — never require a manual code change to "turn on" CVaR once
   enough real data exists. This is a straightforward `if S_days >= S_min: use CVaR
   else: use shrunk-MV` branch at the top of the engine's solve routine, with the
   branch decision itself logged for the same overclaiming-avoidance reason as point 3.

No paper claims a specific minimum-S threshold for CVaR reliability as a hard rule —
the `S_min ≈ 10/(1−α)` heuristic above is a reasonable engineering rule of thumb
derived from "the tail set must contain a handful of points," not itself a
peer-reviewed result, and should be flagged as such (**[B-secondary, engineering
heuristic, not a literature-verified threshold**) rather than presented as if
Rockafellar-Uryasev or anyone else specified it.

---

## 10. OSS sourcing evaluation (Rule I / `sourcing-oss-parts` gate)

**Method actually used this session**: `WebSearch` was unavailable (session budget
exhausted before this task started — see §11), so the marketplace-discovery half of
a normal sourcing pass (broad PyPI/GitHub keyword search for competing
implementations) could not be run. In its place, direct verification was substituted:
every candidate repo named in the task, plus one additional candidate found via
domain knowledge (PyPortfolioOpt, because it is the most commonly cited
general-purpose Python portfolio-optimization library and the task's own §6 "integer
lot/tick rounding" ask is exactly its `discrete_allocation` module's purpose), was
`git clone`d and its actual source read, and its live GitHub metadata (stars, open
issues, last push, license, archived status) was pulled via `api.github.com` to
assess maintenance health — this is real due diligence, not a from-memory
recommendation, but it is narrower than a full keyword sweep would have been. That
gap is logged in `docs/BACKLOG.md` (see below) rather than silently left implicit.

| Repo | Stars | Open issues | Last push (as of 2026-07-26) | License | Archived? | Verdict |
|---|---|---|---|---|---|---|
| `microsoft/qlib` | 46,689 | 467 | 2026-07-23 | MIT | No | **Reference/vendor-pattern, not a dependency.** Actively maintained, huge community. Its `EnhancedIndexingOptimizer` + `ShrinkCovEstimator` are exactly the objective shapes needed (§4, §2.2) — recommend **adapting the pattern (BYO-risk-model optimizer class, two-trial solve-with-fallback, warm-start, epsilon-truncate-renormalize)** rather than depending on all of Qlib (which pulls in a much larger data-pipeline/backtesting framework this project doesn't need — Qlib is a whole research platform, not a standalone optimizer library; pulling it in as a dependency for one optimizer class would be a poor fit for an intraday execution codebase). |
| `cvxgrp/cvxportfolio` | 1,242 | 30 | 2026-04-27 | GPL-3.0 | No | **Reference/vendor-pattern, not a direct dependency** (license is not the reason — Rule E — the reason is architectural fit: its multi-period `MarketSimulator`/`Policy` abstraction is built for daily-rebalance long-horizon simulation, a different cadence than this project's intraday loop). Recommend **adapting its compositional Return/Risk/Cost-as-swappable-objects pattern** (§8) and its exact `TransactionCost` market-impact formula (§7.2) as a small, hand-written module once volume forecasts exist — vendoring the whole package would bring in its simulator/backtester machinery this project already has its own version of. |
| `dcajasn/Riskfolio-Lib` | 4,404 | 5 | 2026-06-22 | BSD-3-Clause | No | **Strong vendor candidate.** Low open-issue count relative to stars (healthy maintenance signal), BSD-3 (permissive, though per Rule E license was not a factor in ranking), and its `Portfolio` class already implements essentially every risk measure this document needs (CVaR §1, MV §2, ERC via log-barrier/ExpCone §3, cardinality constraints) behind one coherent API, directly on top of CVXPY (a library this project would add as a dependency regardless). **Recommendation: add as a real dependency** (`pip install Riskfolio-Lib`) and call its `Portfolio.optimization()`/`rp_optimization()` directly for the risk-measure zoo, rather than hand-rolling every risk measure — reserve custom CVXPY code (this document's §1-§3 snippets) for the project-specific pieces Riskfolio-Lib doesn't cover out of the box (the Qlib-style benchmark-tracking objective of §4, and any project-specific scenario-generation/bootstrap logic from §9). |
| `robertmartin8/PyPortfolioOpt` | *(GitHub API returned a redirect for this repo during the metadata pull in this session — the repo's numeric ID has moved/renamed at some point; stars/issues/push-date could not be captured this pass, flagged as an open item below rather than fabricated)* | — | — | — | — | **Vendor candidate for §6 (discrete/lot allocation) specifically.** Its `DiscreteAllocation.greedy_portfolio()`/`lp_portfolio()` (source read directly, quoted in §6.1) are exactly the two approaches this document independently derived from first principles — confirms the design rather than replacing it. Recommend **adapting (not vendoring wholesale)** the greedy-fill deficit-maximization loop, since this project's lot-size semantics (NSE F&O contract lot sizes, not "1 share") need a small modification to the library's implicit lot-size-of-1 assumption. |

**Rejected without full evaluation** (named for completeness, not chased down this
session due to the WebSearch gap — logged, not silently dropped): `scipy.optimize`
(already a project dependency per `pyproject.toml:21`, viable for the risk-parity
SLSQP path Qlib itself uses as an alternative to the CVXPY log-barrier form, §4 end)
was confirmed present; a broader PyPI search for other CVaR-specific or
cardinality-specific niche packages (e.g. anything purpose-built for MILP+CVaR) was
not run and is the explicit backlog item below.

## 11. Sources (full list, with grades)

| # | Source | Grade | How verified |
|---|---|---|---|
| 1 | R.T. Rockafellar & S. Uryasev, "Optimization of conditional value-at-risk," *Journal of Risk* 2(3), 2000, pp. 21-41 | A-primary | Full PDF read from https://uryasev.ams.stonybrook.edu/wp-content/uploads/2011/11/CVaR1_JOR.pdf |
| 2 | O. Ledoit & M. Wolf, "Honey, I Shrunk the Sample Covariance Matrix," *J. Portfolio Management* 30(4), 2004, DOI 10.3905/jpm.2004.110 | A-primary | Full PDF (working-paper version) read from https://ledoit.net/honey.pdf |
| 3 | S. Maillard, T. Roncalli, J. Teiletche, "On the Properties of Equally-Weighted Risk Contributions Portfolios," *J. Portfolio Management* 36(4), 2010 | A-primary | Full PDF read from http://www.thierry-roncalli.com/download/erc.pdf |
| 4 | F. Spinu, "An Algorithm for Computing Risk Parity Weights," SSRN 2297383, 2013 | B-secondary | PDF unreachable this session (SSRN 403, mirrors 404); formulation corroborated via Riskfolio-Lib production source + Maillard-Roncalli-Teiletche's own eq. 7 precursor |
| 5 | Microsoft Qlib, `qlib/contrib/strategy/optimizer/enhanced_indexing.py` + `optimizer.py` + `qlib/model/riskmodel/shrink.py` | A-primary | `git clone`d github.com/microsoft/qlib, commit `79633dd9506ea689e5400dea0197717b5b3d74b7`, full files read |
| 6 | cvxgrp/cvxportfolio, `cvxportfolio/costs.py` (`TransactionCost` class) | A-primary | `git clone`d github.com/cvxgrp/cvxportfolio, full class read |
| 7 | dcajasn/Riskfolio-Lib, `riskfolio/src/Portfolio.py` (`optimization()`, `rp_optimization()`) | A-primary | `git clone`d github.com/dcajasn/Riskfolio-Lib, relevant sections read |
| 8 | E. Candès, M. Wakin, S. Boyd, "Enhancing Sparsity by Reweighted ℓ1 Minimization," *J. Fourier Anal. Appl.* 14, 2008, DOI 10.1007/s00041-008-9045-x | A-primary | Full PDF read from https://web.stanford.edu/~boyd/papers/pdf/rwl1.pdf |
| 9 | Cardinality-constrained MILP (big-M) formulation: Bienstock 1996 (*Math. Programming* 74); Bertsimas & Shioda 2009 (*Comp. Opt. & Applications* 43); Chang/Meade/Beasley/Sharaiha 2000 (*Computers & OR* 27) | B-secondary | Cited by name/venue from established domain knowledge; specific PDFs not re-fetched this session (all three fetch attempts for adjacent Stanford/Roncalli URLs succeeded but these three specific papers were not re-probed — flagged rather than silently presented as independently re-verified) |
| 10 | Markowitz, "Portfolio Selection," *J. Finance* 7(1), 1952 | B-secondary | Foundational/undisputed; not re-fetched (cited indirectly via Rockafellar-Uryasev's own reference to it as problem P3, which *was* directly read) |
| 11 | cvxportfolio documentation site, riskfolio-lib.readthedocs.io | B-secondary | Fetched via WebFetch tool (rendered summary, not raw HTML/source) — architecture description corroborated against and superseded by direct source reads (rows 6-7) where they overlap |
| 12 | `robertmartin8/PyPortfolioOpt`, `pypfopt/discrete_allocation.py` (`DiscreteAllocation.greedy_portfolio()`, `.lp_portfolio()`) + `pypfopt/risk_models.py` (`CovarianceShrinkage`, delegates to `sklearn.covariance.ledoit_wolf`/`.oas`) | A-primary | `git clone`d github.com/robertmartin8/PyPortfolioOpt, both modules read directly (§6.1, §10) |

## 12. Explicit gaps / what was not independently verified

- Spinu (2013)'s own PDF could not be fetched (SSRN blocked, mirror 404s) — the
  log-barrier unconstrained form attributed to it in §3.3 is corroborated by two
  independent things (the Maillard-Roncalli-Teiletche paper's own eq. 7, which *was*
  read directly, and Riskfolio-Lib's production ExpCone implementation, which *was*
  read directly) but is not a first-hand read of Spinu's specific paper text.
- The three cardinality-MILP OR references (Bienstock, Bertsimas-Shioda,
  Chang-Meade-Beasley-Sharaiha) are cited by well-established name/venue from
  training-time domain knowledge, not re-fetched and read in this session — the big-M
  MILP formulation itself is standard enough (and internally consistent/simple enough
  to derive from first principles) that this is a low-risk citation gap, but it is
  flagged rather than hidden.
- The `S_min ≈ 10/(1−α)` scenario-count-floor heuristic in §9 is this document's own
  engineering judgment, not a number pulled from any paper — flagged explicitly in
  §9, not presented as literature-sourced.
- The task's stated "~340 trades over ~1 session-day" data point was taken as given
  context from the task prompt and was not independently re-confirmed against a live
  trade log or database in this research session (no portfolio-optimizer code or
  paper-trade log currently exists in the repo to check against — this is greenfield
  research ahead of a build, confirmed by a repo search that found no existing
  portfolio/risk-allocation optimizer module).
- Web search (the `WebSearch` tool) was unavailable for this entire session (budget
  exhausted before this task began) — every source above was obtained via direct
  `WebFetch`/`curl` to a specific guessed-and-verified URL or via `git clone` of the
  actual source repository, not via a search engine. This means the source list is
  necessarily narrower than a fully unconstrained search would have produced (e.g. no
  opportunity to discover additional competing shrinkage-target papers, alternative
  ERC algorithms, or newer 2024-2026 cardinality-relaxation techniques via search);
  what's here is verified-deep on the specific formulas requested, not
  breadth-swept across the whole possible literature.
- **Sourcing-gate specific blocker** (also logged in `docs/BACKLOG.md`): the §10 OSS
  evaluation covered only the repos named in the task plus one adjacent candidate
  found from domain knowledge (PyPortfolioOpt). A proper `sourcing-oss-parts` keyword
  sweep (PyPI search for "CVaR portfolio optimization", "cardinality constrained
  portfolio python", "risk parity cvxpy", GitHub topic search, etc.) was not run
  because `WebSearch` was unavailable all session — this is a real gap in breadth of
  alternatives considered, not just a citation-depth gap, and is tracked as an open
  backlog item rather than silently treated as a complete sourcing pass.
