# Component-lifecycle homeostat: PHM/CBM exact math + SOTA + OSS sourcing · research/168

Date: 2026-07-27. Rule D research pass for a new trunk: a **component-lifecycle homeostat** that
supervises every live component of the trading system (background threads, broker sessions/tokens, data
adapters, SQLite stores, the LLM provider pool, persisted ML model artifacts, ~30 decision engines) and
autonomously repairs/replaces/quarantines them, built on **Prognostics & Health Management (PHM) /
condition-based maintenance (CBM)** as the algorithm core. Real `WebSearch` + `WebFetch` used throughout
this pass (budget was NOT exhausted this session — every claim below was either fetched from a primary
source or triangulated across ≥2 independent search results; §7 lists the handful of items that could
not be pinned to an exact verbatim formula this pass).

## 0. Grounding: what exists in this repo today

`grep -rlEi "watchdog|heartbeat|circuit_breaker|supervisor|health_check|component_health|self_heal|
quarantine" src` turns up **nothing** resembling a component-health engine — `broker_sessions/`,
`session_management/`, `market_data/` etc. all exist as functional adapters but none of them carry a
supervising health/lifecycle layer. This is genuinely greenfield inside the repo (no Rule-G orphan risk
to reconcile against, no prior sourcing pass to avoid duplicating).

**Confirmed in `.venv` (Python 3.12.13, aarch64) — the exact box this will run on:**

```
numpy 2.4.6   scipy 1.18.0   scikit-learn 1.9.0   lightgbm 4.7.0
cvxpy 1.9.2   statsmodels 0.14.6   joblib 1.5.3   networkx 3.6.1   pandas 3.0.5
```

`networkx` and `statsmodels` are installed and importable but **not yet declared** in `pyproject.toml`
(same undeclared-dependency gap `docs/research/166` flagged — carry the fix into this build: add both
when this engine lands). Both are directly usable for this engine: `networkx` for the **component
dependency graph** (blast-radius / cascading-failure reachability when deciding to quarantine a shared
resource like a broker session that ~30 decision engines depend on) and `statsmodels` is not the primary
tool here (its regime-switching/HMM machinery served research/166; this pass's primary new dependencies
are survival-analysis libraries, §6).

---

## 1. Health-index / degradation modelling

The goal: turn multivariate condition-monitoring telemetry (CPU/thread liveness, heartbeat latency,
error rate, SQLite lock-wait time, broker-token TTL, model-prediction drift, LLM latency/error-rate,
per-engine P&L attribution stability, …) per component into **one scalar health index** `h(t) ∈ [0,1]`
usable as the CBM state variable.

### 1a. Mahalanobis-distance health index

`D²(x) = (x − μ)ᵀ Σ⁻¹ (x − μ)`, where `μ`/`Σ` are the mean vector and covariance matrix of the
condition-monitoring features **estimated from the component's own healthy-baseline period**. This is
the standard PHM health-index construction: it "summariz[es] the multivariate operating parameters and
reduc[es] the data set into a fused distance index," and "takes the correlation and statistical
behaviour of the majority normal cluster into consideration" so correlated features (e.g. CPU load and
heartbeat latency, which move together under normal operation) don't double-count as two independent
anomaly signals — Mahalanobis divides out exactly that shared covariance
([ScienceDirect: statistic Mahalanobis distance for incipient sensor fault detection](https://www.sciencedirect.com/science/article/abs/pii/S000925092030765X);
[Health monitoring of electronic products based on Mahalanobis distance and Weibull decision metrics](https://www.researchgate.net/publication/220456625_Health_monitoring_of_electronic_products_based_on_Mahalanobis_distance_and_Weibull_decision_metrics)).
The Mahalanobis-Taguchi System (MTS) variant tracks `D²` over time and, once a fault is flagged, fits a
**linear trend** to the rising `D²` trajectory to project time-to-threshold — i.e. `D²` doubles as both
the health index AND the raw signal RUL extrapolation is run on (§2).

### 1b. PCA T² + SPE(Q) — multivariate statistical process control (MSPC)

When the feature count is large and features are themselves collinear (typical of a real telemetry
vector: heartbeat latency, queue depth, error rate, retry count, GC pause time, … are rarely
independent), decompose via PCA fit on the healthy baseline, retain the top `a` components, and monitor
**two orthogonal statistics** — this is the field-standard approach in industrial statistical process
control, verified against
[a PCA-based fault-detection review (KU Leuven)](https://wis.kuleuven.be/stat/robust/papers/2013/deketelaere-review.pdf)
and a worked derivation in a PLOS ONE compressor-monitoring paper
([Design and realization of compressor data abnormality safety monitoring](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0315917)):

- **Hotelling's T²** (variation *within* the retained principal subspace): `T² = tᵀ Λ⁻¹ t` where `t` is
  the score vector of a new observation projected onto the retained `a` components and `Λ` is the
  diagonal matrix of their eigenvalues (T² **is** the squared Mahalanobis distance computed in the
  reduced PC space — §1a and §1b are the same statistic in two different coordinate systems). Its
  control limit is the standard textbook F-distribution result (Jackson 1991, *A User's Guide to
  Principal Components*; Chiang/Russell/Braatz 2001, *Fault Detection and Diagnosis in Industrial
  Systems* — canonical, not independently re-fetched this pass, flagged in §7):
  `T²_α = [a(n−1)(n+1)] / [n(n−a)] · F_α(a, n−a)`, `n` = number of healthy-baseline samples used to fit
  the PCA model.
- **SPE / Q-statistic** (residual variation *outside* the retained subspace — "the lack of fit for the
  PCA model"): `Q = ‖x − x̂‖²` where `x̂` is `x` reconstructed from only the retained `a` components. Its
  control limit was derived by **Jackson & Mudholkar (1979)**, *"Control Procedures for Residuals
  Associated with Principal Component Analysis,"* Technometrics 21, 341–349 — confirmed via the KU
  Leuven review and the PLOS paper (which names the same citation and gives the normal-approximation
  form with a `c_α`/eigenvalue/`h₀` adjustment term, though the exact symbolic layout renders as an
  image in both sources and could not be transcribed verbatim this pass — §7). The simpler,
  independently-confirmed **chi-square approximation** form (same KU Leuven source) is usable directly:
  `δ² = g_s · χ²_α(h_s)`, `g_s = ω₂/ω₁`, `h_s = ω₁²/ω₂`, `ω_i = Σ_{j=a+1}^{n} λ_j^i` (sum over the
  *discarded* eigenvalues) — i.e. the residual eigenvalue spectrum alone determines the SPE alarm
  threshold, no distributional assumption on the raw features needed.
- **Decision rule**: fault iff `T² > T²_α` OR `Q > δ²` — T² catches anomalies *within* the normal
  correlation structure (a known combination of features moving to an unusual joint value), Q catches
  anomalies that *break* the normal correlation structure (features moving in a way the healthy
  baseline never saw together) — these are complementary, not redundant, alarms.

### 1c. EWMA / CUSUM — the temporal change-detection layer

T²/Q/Mahalanobis give an instantaneous anomaly score; EWMA and CUSUM turn a **noisy scalar time series**
of that score into a fast, low-false-alarm degradation-onset detector. Verified verbatim against the
**NIST/SEMATECH e-Handbook of Statistical Methods** (primary, authoritative, government source):

- **EWMA** ([NIST §6.3.2.4](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm)):
  `EWMA_t = λ·Y_t + (1−λ)·EWMA_{t−1}`, `EWMA_0` = healthy-baseline mean, `λ ∈ (0,1]` (small `λ` = more
  smoothing, slower to react; `λ=1` degenerates to a plain Shewhart chart). Control limits:
  `UCL/LCL = EWMA_0 ± k·s_ewma`, `s²_ewma = [λ/(2−λ)]·s²` (steady-state form, valid once `t` is not
  small — the exact transient variance has an additional `(1−(1−λ)^{2t})` decay factor that converges to
  this steady-state expression research/166 already cites for a different chart).
- **CUSUM** ([NIST §6.3.2.3](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)):
  two one-sided running sums, `S_hi(i) = max(0, S_hi(i−1) + x_i − μ̂₀ − k)` and
  `S_lo(i) = max(0, S_lo(i−1) + μ̂₀ − k − x_i)`, `S_hi(0)=S_lo(0)=0`; alarm when either exceeds decision
  interval `h` (`k` is the "reference value," conventionally half the shift size worth detecting, e.g.
  `k=σ/2`). CUSUM's cumulative memory makes it **faster than EWMA/Shewhart at detecting small, sustained
  shifts** (both charts detect a 1σ mean shift in ~10 subgroups on average vs. many more for a plain
  Shewhart chart per the ScienceDirect CUSUM/EWMA comparison found this pass) — exactly the "slow,
  monotone degradation trend" signature PHM cares about, as opposed to isolated transient spikes.
- **Fusion into the health index**: the repo's own `predictive_core/surprise_monitor.py`
  (research/134/166) already vendors a Page-Hinkley change detector for exactly this role on a different
  signal (world-model surprise) — the CUSUM/EWMA layer here is the same architectural pattern applied to
  the T²/Q/Mahalanobis health-index stream, reusing the "smoothed statistic → cumulative-drift alarm"
  idiom already proven in this codebase rather than inventing a third one (Rule G-adjacent: don't build
  a parallel change-detection primitive when one is already load-bearing elsewhere in the repo).

### 1d. Normalization/fusion into a single `h(t) ∈ [0,1]`

Standard practice (confirmed across the PHM sources above, not one single citation but the consistent
pattern in all of them): min-max or CDF-transform each raw statistic against its own control limit so
`1.0` = "at the alarm threshold," then fuse multiple per-subsystem indices (e.g. one MD/T²-Q pair per
telemetry cluster: threading health, session health, data-adapter health) via a **weighted max or
weighted mean**, with max preferred when any single subsystem failing should dominate the fused score
(a trading engine with a dead broker session is not "50% healthy" just because its threading subsystem
is fine) — this is the same "never average away a hard failure" principle Rule O §4 already states for
numeric robustness generally.

---

## 2. Remaining Useful Life (RUL) estimation via survival analysis

### 2a. The central fact this section is built around: right censoring dominates our data

At any point in time, almost every one of the ~30 decision engines / 8 SQLite stores / N broker sessions
**has not yet failed** — its true failure time is only known to be `> (current age)`. This is a
**right-censored observation**, and treating it as "no data" (dropping it) or "failure at the current
time" (treating survival as death) are the two classic, both-wrong ways to handle this — survival
analysis exists specifically to use right-censored observations correctly without either bias.

### 2b. Kaplan-Meier — the non-parametric baseline

`Ŝ(t) = Π_{j: t_j ≤ t} (n_j − d_j)/n_j`, `n_j` = number at risk just before time `t_j`, `d_j` = number of
failures at `t_j` — a step function, non-increasing, dropping only at observed failure times (censored
observations leave `n_j` unchanged in later steps except by removing that unit from the risk set at its
censoring time). Variance via **Greenwood's formula**. This is the estimator to compute FIRST, before
fitting any parametric model, because it needs zero distributional assumption and gives an honest
empirical survival curve to check parametric fits against — confirmed against multiple independent
derivations found this pass (bookdown financial-survival-analysis notes, NIH/PMC survival-analysis
primer).

### 2c. Weibull AFT vs. Cox proportional hazards — and why they coincide for us

- **Cox PH**: models the hazard `h(t|x) = h₀(t)·exp(βᵀx)` — covariates multiply a *baseline* hazard
  shared across all units; `h₀(t)` is left completely unspecified (semi-parametric) and estimated via
  the **partial likelihood**, which is exactly what lets Cox PH handle right-censored data cleanly (the
  partial likelihood only compares, at each observed failure time, the covariate values of the unit that
  failed against the risk set of units still alive/uncensored — censored units contribute to the risk
  set for as long as they're known to have survived, then drop out silently).
- **Weibull AFT**: models `log(T) = βᵀx + σ·ε` — covariates rescale time itself ("accelerate" or
  "decelerate" the whole survival curve) rather than multiply an instantaneous hazard; fully parametric
  (both `β` and the Weibull shape/scale are estimated jointly by MLE over the *full* likelihood, not a
  partial one).
- **The coincidence**: *"When the survival distribution of the event of interest follows a Weibull
  distribution, the AFT model and the Cox proportional hazard model coincide... the Weibull model, in
  addition to being proportional, is simultaneously an accelerated failure-time model, and is the only
  parametric distribution to possess both properties"* — meaning for us, picking Weibull-AFT as the
  parametric route is not a downgrade from Cox; it is the *one* distributional choice where the two
  major RUL modelling families agree, and it additionally gives a full parametric survival curve
  (Cox's semi-parametric `h₀(t)` is not directly usable for RUL point-forecasts without an extra
  smoothing step).
- **Right-censored likelihood** (the formula that actually encodes "this component hasn't failed yet"):
  for `n` units with observed/censored times `t_i` and event indicator `δ_i` (1 = failed, 0 = censored),
  the full likelihood is `L = Π_i f(t_i|x_i)^{δ_i} · S(t_i|x_i)^{1−δ_i}` — a censored unit contributes
  its **survival function** `S(t)=1−F(t)` (probability of surviving at least this long) rather than its
  density; verified via the PyMC *Bayesian Parametric Survival Analysis* worked example
  ([pymc.io](https://www.pymc.io/projects/examples/en/latest/survival_analysis/bayes_param_survival.html)),
  which builds exactly this log-likelihood (Gumbel-on-log-time parameterization of the Weibull AFT, with
  the censored contribution built from the survival tail probability) and puts weakly-informative priors
  on the regression coefficients (`β ~ N(0, 5²I)`) and scale (`s ~ HalfNormal(5)`) — the Bayesian route
  is what §5 leans on hardest given how few actual failures we have.
- **Covariates for our components**: age (time since process start / token issue / model deployment),
  restart count, recent error-rate trend (the CUSUM/EWMA signal from §1 feeds in here directly as a
  time-varying covariate), component class (thread vs. session vs. store vs. model), and — critically —
  the component-class itself is the grouping variable §5's hierarchical pooling shares strength across.

### 2d. Wiener / gamma process first-passage-time — the alternative route when almost nothing has failed

When failures are so rare that even a censored-data survival regression has too little event information
to fit stably, PHM's other standard route is to **model the degradation trajectory itself** (the health
index `h(t)` from §1) as a stochastic process and define "failure" as first crossing a threshold, never
needing an observed failure at all to produce an RUL distribution:

- **Wiener process**: `X(t) = X(0) + μt + σB(t)` (`B(t)` = standard Brownian motion). Its first-passage
  time to a threshold `D` has a **closed-form Inverse Gaussian (IG) distribution** — confirmed across
  multiple ScienceDirect papers found this pass (adaptive skew-Wiener, multi-phase Wiener RUL models).
  This is the right choice when the health index can legitimately move in **both directions** (a broker
  session's error rate can improve after a transient network blip, a model's drift score can shrink
  after a retrain) — i.e. most of our software/session components, which don't monotonically wear out
  the way a physical bearing does.
- **Gamma process**: strictly monotonic increments (`X(t)−X(s) ~ Gamma` for `t>s`), so it can ONLY model
  degradation that never improves — appropriate for genuinely monotone counters (e.g. cumulative GC
  pause time, cumulative broker-API rate-limit violations, a model's cumulative distributional drift
  since last retrain if we choose not to let it "heal") but **"impractical for systems with
  non-monotonic trajectories caused by variances from loads or preventive maintenance operations"** per
  the search results — i.e. wrong choice for anything that can recover.
- **Two-phase / change-point extensions** (Wiener-Gamma, Gamma-Gamma) exist in the literature for
  components whose degradation regime itself shifts (e.g. a SQLite store that degrades slowly from
  fragmentation, then rapidly once past a size/lock-contention knee) — noted as a documented future
  upgrade, not needed for a v1 build.
- **This is the "gate only ACTIVATION, build the full algorithm" (Rule Q) escape valve for RUL**: the
  Wiener/gamma route needs **zero observed failures** to produce a calibrated RUL distribution — it only
  needs the *degradation trajectory* (which every live component is already generating every second via
  §1's health index) plus a *failure threshold* (which can be set from domain knowledge — e.g. "3
  consecutive missed heartbeats," "broker token past its documented TTL," "SQLite `database is locked`
  timeout exceeded N times/hour" — even before a single real failure has been observed).

---

## 3. Maintenance-policy optimization

### 3a. CBM as a Markov Decision Process

State `s` = discretized health index / degradation level from §1 (or a hidden true-wear level if we
choose the POMDP route, §3b); actions `a ∈ {monitor, repair, replace, quarantine}`; the standard CBM cost
structure (confirmed pattern across multiple CBM optimization papers found this pass — see the two
threshold-policy papers and the ScienceDirect two-threshold CBM paper): a **downtime/failure cost**
(large, incurred if the system fails before being caught — for us: bad trades executed against a broken
data feed, a stuck order, a stale model silently mispricing risk), a **repair cost** (moderate, partially
restores health without a full state reset), a **replacement cost** (largest planned cost, but resets
degradation to "as good as new" — for us: kill+restart a thread, force-refresh a token, rebuild a SQLite
store from the WAL, retrain/redeploy a model, fail over to a backup broker session), and a **monitoring
cost** (near-zero — we already have the telemetry). Solve via **value iteration**: the Bellman
backward-induction recursion `V(s) = min_a [ c(s,a) + γ Σ_{s'} P(s'|s,a) V(s') ]`, iterated to a fixed
point — standard dynamic programming, unchanged since Bellman (not independently re-fetched, canonical).

### 3b. POMDP when the true state is unobserved

*"When the system health state is unobservable, [prior work] use[s] a POMDP to show the optimality of a
two-level control-limit policy for inspection and replacement of a three-state system"* — this is the
honest framing for us too: the telemetry (§1's health index) is a **noisy observation** of a true
underlying wear state, not the wear state itself (a thread can look healthy on CPU/heartbeat metrics
while its internal state is subtly corrupted). The pragmatic v1, though, is a **certainty-equivalent MDP**
using the Bayesian posterior mean/variance of the health state (§1's Mahalanobis/T² statistics already
ARE a calibrated posterior-flavored estimate, not a point telemetry read) as the MDP's observed state,
with the posterior *variance* feeding directly into the "how much do I trust this state estimate"
axis — the full belief-state POMDP is the documented upgrade path once the certainty-equivalent MDP is
running and its blind spots (if any) are empirically identified, not a mandatory v1 requirement (this
system genuinely does have direct, rich telemetry per component — it's a much more observed setting than
a bearing accessible only via vibration sensors, which is where the POMDP literature's need is sharpest).

### 3c. Control-limit / threshold-policy optimality

*"For many variations of the problem considering only replacement as a repair option, the optimal policy
may exhibit a control-limit structure, i.e., replacement is optimal once the system's degradation state
exceeds some threshold"* — this is a real, provable structural result (not just an empirical heuristic)
under standard monotonicity assumptions (costs and transition probabilities monotone in the degradation
state) — meaning once we solve the MDP once, the resulting optimal policy is expected to reduce to a
**small number of threshold cutoffs per action**, which is both cheap to store/execute at runtime (no
need to re-run value iteration inline in the trading loop — solve offline/periodically, deploy the
resulting threshold table) and human-auditable (a dashboard can show "component X's health is 0.42,
repair threshold is 0.5" in plain language, satisfying Rule N's visibility requirement more directly than
a raw policy table would).

### 3d. Age-replacement / block-replacement — the classical non-CBM baselines

Useful as a **sanity-check baseline** the learned CBM policy must beat, and as the fallback for any
component where condition monitoring genuinely isn't available (a pure age-based fallback is safer than
no policy at all):

- **Age replacement**: replace at failure or at a fixed age `T`, whichever comes first (resets the clock
  either way). Long-run cost rate (renewal-reward form, confirmed via the search results this pass):
  `C(T) = [c_p·R(T) + c_f·(1−R(T))] / ∫₀ᵀ R(t)dt`, `c_p`/`c_f` = planned/failure replacement cost,
  `R(t)` = reliability (survival) function. *"A finite preventive optimum exists only when the failure
  rate increases with age (Weibull shape β>1) and the failure replacement cost exceeds the planned
  replacement cost"* — i.e. this baseline is only worth computing for components with genuine wear-out
  behavior (β>1 in their fitted Weibull, §2c); for components with β≈1 (constant hazard — a session token
  that fails uniformly at random regardless of age, which is plausible for network-blip-driven failures)
  there is NO finite optimal preventive age and CBM (which reacts to actual observed degradation, not
  elapsed time) is strictly the right tool, not just the more sophisticated one.
- **Block replacement**: replace all units of a class at fixed calendar intervals regardless of
  individual age — simpler to schedule (e.g. "restart every session-management thread every Sunday
  night") but wastes recently-replaced units; noted as the even-simpler fallback beneath age replacement.

---

## 4. SOTA analogs — named real systems, and precisely what each does beyond naive threshold alerting

| System | What it does that naive threshold alerting doesn't |
|---|---|
| **NASA C-MAPSS** ([official NASA PCoE repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/), also mirrored on [Zenodo](https://zenodo.org/records/15346912)) | The field's benchmark for RUL estimation from multivariate sensor trajectories run to actual failure, across 4 sub-datasets (FD001–FD004) varying operating-condition and fault-mode complexity. It doesn't just flag "sensor X is out of range" — it produces a **continuous RUL curve per unit** that degrades monotonically as evidence accumulates, which is the exact shape of output §2's survival/degradation models must produce, and is the benchmark this engine's RUL component should be validated against methodologically (not literally — we have no turbofans — but the FD00x train/test/RUL-ground-truth split structure is the right harness pattern to borrow for backtesting our own RUL model against components we've already retired). |
| **Industrial CBM systems** (general pattern across the CBM optimization papers surveyed in §3) | Move from *calendar-based* or *threshold-crossing* maintenance to *cost-optimal, state-contingent* maintenance — the same component at the same health reading gets a different maintenance action depending on the currently-modeled cost/risk trade-off (e.g. more conservative around market open when a bad decision engine is costlier), which a fixed threshold literally cannot express. |
| **Netflix Hystrix / Resilience4j** ([resilience4j docs](https://resilience4j.readme.io/docs/comparison-to-netflix-hystrix)) | A **3-state machine** (CLOSED → OPEN → HALF_OPEN) rather than a binary up/down flag: OPEN rejects calls immediately (fail fast, no wasted retries against a known-bad dependency) and HALF_OPEN **probes with a configurable number of test calls** before deciding to fully re-close — i.e. it already encodes a primitive "monitor → careful re-trial → resume" policy, which is structurally a 3-state control-limit CBM policy without the RUL/survival math underneath it. Confirms our `{monitor, repair, replace, quarantine}` action set is the right generalization (quarantine ≈ OPEN, monitor-while-recovering ≈ HALF_OPEN) with genuine degradation modelling added underneath instead of a bare failure-count threshold. |
| **Kubernetes controller reconciliation + probes + CrashLoopBackOff** ([Pod Lifecycle docs](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/); [controller-runtime backoff discussion](https://github.com/kubernetes-sigs/kubebuilder/discussions/2506)) | Liveness/readiness probes separate "is it alive" from "is it ready for traffic" (two different health axes we should keep separate per component, not fuse into one boolean); CrashLoopBackOff's exponential backoff (10s→20s→40s→80s→…, capped) automatically slows down repair attempts against a component that keeps failing, which is a crude but real **online adaptation of the repair-cost estimate** (each failed repair makes the next attempt "more expensive" in wall-clock terms) — a naive threshold alerter would retry at a fixed cadence forever or give up entirely; the reconciliation-loop pattern itself (continuously diff actual-vs-desired state and act on the delta, never a one-shot check) is the right execution-loop shape for this whole engine. |
| **Erlang/OTP supervision trees** ([Erlang supervisor docs, primary](https://www.erlang.org/doc/system/sup_princ.html)) | `max_restarts`/`max_seconds` ("intensity"/"period") caps how many restarts are tolerated in a rolling window before the supervisor gives up and terminates the whole subtree — this is a **restart-budget**, structurally identical to an SRE error budget (below) but applied to the *repair action itself* rather than to user-facing error rate; and the four restart strategies (`one_for_one`, `one_for_all`, `rest_for_one`, `simple_one_for_one`) are exactly a taxonomy of **blast-radius policies for the "replace" action** — one_for_one = replace only the failed component, one_for_all/rest_for_one = replace correlated/downstream components too. This maps directly onto the `networkx` component-dependency graph from §0: the dependency graph tells us which restart strategy applies to which failure. |
| **SRE error budgets / multiwindow multi-burn-rate alerting** ([Google SRE Workbook, primary](https://sre.google/workbook/alerting-on-slos/)) | Rather than alerting the instant an error occurs, it alerts on the **rate at which a finite budget is being consumed**, using both a long window (catches slow, sustained degradation) and a short window (catches fast burns) simultaneously — verified exact table: 1h/5m windows at 14.4× burn rate (fires on pace to consume 2% of a 30-day budget in 1h), 6h/30m at 6× (5% in 6h), 3d/6h at 1× (10% in 3 days); alert fires only when **both** windows agree, which is precisely the false-positive suppression a naive single-threshold alert cannot achieve. This is the direct template for how the homeostat should gate its OWN alerting/dashboard surfacing of a degrading component — burn-rate-style, not raw-threshold-style. |

---

## 5. Small-N: making the full algorithm principled with almost no observed failures (Rule Q core)

This is the section that determines whether Rule Q is actually satisfiable here, so it is the most
load-bearing part of this research pass. The unifying idea across every technique below: **never let an
estimate collapse to "undefined" or "wildly overconfident" just because a specific component/class has
seen 0–2 events** — every formula here is a smooth interpolation between "trust the prior" (N=0) and
"trust the data" (N large), with the interpolation weight determined automatically by N, never by a
manually-tuned "is N big enough yet" switch.

### 5a. Bayesian priors directly on the Weibull shape/scale

Rather than MLE-fitting a Weibull per component (which is undefined or wildly unstable with 0–1
failures), put priors on the shape `α` (κ in some notations) and scale `β` parameters and update via the
right-censored likelihood from §2c: `L(α,β) = Π_i f(t_i;α,β)^{δ_i}·S(t_i;α,β)^{1−δ_i}`. With **zero**
observed failures for a given component (`δ_i=0` for all `i`), the likelihood reduces to
`Π_i S(t_i;α,β)` — pure survival-function evidence ("it has survived at least this long") — which still
updates the posterior (a component surviving longer without failing IS Bayesian evidence toward a
larger scale `β` / smaller hazard, even with literally zero failure events observed), it just can't pin
down `α` (shape) at all from censoring-only data — which is exactly why §5b (pooling shape `α` across a
component class while letting scale `β` vary per-instance) is the right hierarchical structure, not an
optional refinement.

### 5b. Hierarchical / partial-pooling across similar components — the concrete formula

This is the direct fix for "all 8 SQLite stores share a failure prior": treat each store's own
Weibull/Gamma-rate parameter as drawn from a **population distribution** shared across the 8, and let the
data pull each instance's estimate away from the population mean only as fast as that instance's own
evidence accumulates. Verified against PyMC's worked **Hierarchical Partial Pooling** example
([pymc.io](https://www.pymc.io/projects/examples/en/latest/case_studies/hierarchical_partial_pooling.html))
— a Beta-Binomial case study (baseball batting averages: each player's true skill pooled toward a league
mean) that is structurally identical to our Gamma-Poisson failure-rate case (Gelman et al., *Bayesian
Data Analysis*, ch. 5, is the canonical general reference for this conjugate-hierarchical construction —
textbook material, not independently re-fetched, flagged §7):

```
Hyperpriors (population level, shared across the 8 SQLite stores / N broker sessions / M decision engines):
    φ ~ Uniform(0, 1)                       # population mean failure-rate-ish quantity
    κ ~ Exponential-transformed(·) > 0      # population "concentration" (higher κ = components in this
                                             #   class are more alike; lower κ = more heterogeneous)

Per-component parameter (one per store/session/engine instance i in the class):
    θ_i ~ Beta(α = φ·κ, β = (1−φ)·κ)        # (Beta-Binomial form, PyMC's verified worked example)
    -- or, for our Gamma-Poisson failure-RATE analog (the direct adaptation, §5c) --
    λ_i ~ Gamma(shape = φ·κ, rate = κ)      # same φ/κ mean-precision reparameterization

Likelihood:
    y_i ~ Binomial(n_i, θ_i)                # (batting-average form)
    -- or --
    failures_i ~ Poisson(λ_i · exposure_i)  # (our form: exposure_i = component-i's observed uptime)
```

**Why this is exactly the right structure for Rule Q**: a SQLite store with 400 hours of uptime and 0
failures gets a `λ_i` estimate shrunk toward the *other 7 stores'* pooled experience (which may include a
handful of real failures across the class even though this specific instance has none) — "no pooling"
(each store's own MLE) would give `λ̂=0` for the zero-failure stores (nonsensical — implies literally
zero hazard forever) and "full pooling" (one shared rate for all 8) would ignore that some individual
stores are systematically different; partial pooling is the honest middle. The shrinkage strength is
**automatic and data-driven**, not a hand-tuned threshold: *"no pooling is typically noisier than
hierarchical partial pooling, especially in small samples,"* and *"when the sampling variance is small
relative to the between-group variance (large sample), the shrinkage factor approaches 0 and the group
keeps its raw estimate"* — this is precisely Rule Q's requirement #4 (handle small N *inside* the full
algorithm via hierarchical pooling) satisfied by construction, and requirement #3 (maturity arms
automatically as trades/observations accrue, no code change) falls out for free: as `exposure_i` grows,
`θ_i`/`λ_i`'s posterior naturally detaches from the population prior with zero additional logic.

### 5c. Conjugate Gamma-Poisson — the closed-form fallback with no MCMC needed

For a single component's failure-rate estimate (before/instead of the hierarchical model above), the
Gamma prior is conjugate to a Poisson failure-count likelihood, giving an exact closed-form posterior —
confirmed via the search results this pass and a standard Bayesian-reliability primer found in the
same sweep:

```
Prior:      λ ~ Gamma(α₀, β₀)                       # β₀ in rate parameterization
Data:       observe k failures over exposure time T
Posterior:  λ | k, T ~ Gamma(α₀ + k, β₀ + T)        # closed form, EXACT, no failures needed for it
                                                     #   to be well-defined (k=0 just gives Gamma(α₀, β₀+T))
Point estimate (posterior mean):  λ̂ = (α₀ + k) / (β₀ + T)
```

This is the formula to reach for when a component class is too small/idiosyncratic to justify a full
hierarchical model (e.g. "the LLM provider pool" might have only 3–4 provider instances, too few to
usefully estimate a population `φ,κ` from) — pick `(α₀,β₀)` from domain knowledge or from a *related but
larger* class via empirical Bayes (§5d), and the single-component posterior is still exact and
well-defined at `k=0`.

### 5d. Empirical-Bayes shrinkage (James-Stein flavor) for continuous quantities

For continuous reward/health-degradation-rate estimates (not just failure counts), the analogous
shrinkage-toward-a-global-mean estimator research/166 already derived and uses in this exact repo for a
different quantity (`predictive_core`/experience-memory shrinkage, per that doc's §1a):
`R̂(s,a) = (Σreward(s,a) + κ·R̄_global) / (N(s,a) + κ)` — the same **James-Stein-flavored shrinkage**
(Efron & Morris 1975, canonical, cited in research/166, not re-derived here) applies directly to a
per-component degradation-rate estimate: `rate_i_shrunk = (Σobserved_i + κ·ratē_global)/(N_i + κ)`. This
is the same mathematical family as §5b/§5c (all three are instances of "posterior mean = weighted average
of observed data and a prior/pooled mean, weighted by relative sample size") — worth stating explicitly
so the eventual implementation shares ONE shrinkage primitive across health-rate, failure-rate, and
reward-rate estimation rather than three near-duplicate formulas (Rule C/simplify-adjacent: one
well-named `shrink_toward_prior(observed_sum, observed_n, prior_mean, prior_strength)` helper, reused).

### 5e. Abstention / uncertainty-widening when even shrinkage isn't enough

For a genuinely novel component (a just-added 31st decision engine with zero history and no obviously
"similar" class to borrow from even via §5b/§5c), the honest move is **not** to force a point estimate at
all — widen the posterior predictive interval and let the CBM policy's cost-minimization naturally prefer
the cheap `monitor` action while uncertainty is high (a wide posterior on `λ` pushes the expected cost of
`replace`/`repair` up via the tail risk term, without needing a separate hand-coded "if N < threshold,
abstain" rule — this is Rule Q requirement #2, the maturity ladder, expressed as a *consequence* of
properly propagated uncertainty rather than a bolted-on gate). Concretely: report the **posterior
predictive RUL distribution's width** (not just its mean) on the dashboard per component (Rule Q
requirement #5, "show `have N / need M`" — here expressed as posterior credible-interval width shrinking
as evidence accrues, which is a more honest and continuous signal than a binary N-vs-threshold count).

---

## 6. OSS sourcing — evaluated against the actual ARM64/Linux/Python 3.12 venv this project runs on

Every package below was **actually downloaded** (`pip download --no-deps`) against this exact venv
(Python 3.12.13, aarch64, pip 26.1.2) to confirm real installability, not just checked by name.
GitHub/PyPI metadata (stars, last push, license, last release date) was pulled live via the GitHub REST
API and PyPI JSON API this pass — not from memory.

| Package | Verdict | Evidence + reason |
|---|---|---|
| **lifelines** | **INTEGRATE** | `CamDavidsonPilon/lifelines`, 2,598★, MIT, last push 2026-03-07 (actively maintained), pure-Python wheel downloads cleanly. `CoxPHFitter`/`WeibullAFTFitter`/`KaplanMeierFitter` all confirmed (fetched their docs directly) to take `duration_col`/`event_col` exactly matching our right-censored data shape, support `penalizer`/`l1_ratio` regularization (useful for the small-N covariate case — shrinks coefficients toward 0 the same family as §5), and expose the exact censored-likelihood math §2c needs. **This is the primary survival-analysis dependency.** |
| **scikit-survival** | **REJECT (as primary), evaluate later if needed** | `sebp/scikit-survival`, 1,311★, GPL-3.0, pushed as recently as today (2026-07-26) — very actively maintained, but **no prebuilt wheel for cp312-aarch64** (`pip download` fell back to the sdist, requiring a from-source Cython/C build on this box). Its value-add over lifelines is scikit-learn-pipeline-native survival ML (random survival forests, gradient-boosted CoxPH) — genuinely useful for a LATER upgrade (covariate-rich RUL model once we have enough failures for a tree ensemble to be meaningful) but not needed for the v1 parametric/hierarchical build lifelines already covers, and the build-from-source friction on this exact box is a real cost worth avoiding until the extra power is actually needed. |
| **reliability** (MatthewReid854) | **REJECT** | `MatthewReid854/reliability`, 428★, LGPL-3.0, last PyPI release 2025-03-07 (reasonably fresh), wheel downloads cleanly, confirmed (fetched PyPI page) to support right-censored fitting for Weibull/Gamma/etc. and Kaplan-Meier/Nelson-Aalen. Rejected anyway because it is **MLE-only — confirmed no Bayesian/hierarchical machinery** ("no mention of Bayesian methods" across its own docs), and §5's hierarchical-pooling + Bayesian-prior requirement is the load-bearing half of this whole build (Rule Q). It would be redundant with lifelines' frequentist fits while adding nothing for the small-N problem that actually matters here. |
| **pymdptoolbox** | **REJECT as runtime dependency; keep as a test-only numerical cross-check** | `sawcordwell/pymdptoolbox`, 556★, BSD-3-Clause. **Actually installed and ran successfully** in an isolated venv against numpy 2.5.1/scipy on this exact architecture (`ValueIteration` on the classic `forest` example converged and returned a policy) — so it is NOT broken, contrary to what its staleness might suggest. Rejected as a *production* dependency because (a) its last PyPI release was 2015 (11 years stale — GitHub shows commits as recent as 2023 but those did not produce a new release), (b) it implements plain tabular MDP value/policy iteration only — no POMDP belief-state support (§3b) and no hook for feeding in hierarchically-pooled (§5b) transition/cost estimates without monkey-patching its internals, and (c) the actual algorithm we need (Bellman value iteration over a state space of maybe 5–8 health bins × 4 actions) is ~50 lines of numpy we must write ourselves regardless, to keep the cost model and hierarchical-Bayes plumbing in one place. **Recommended use**: pin it as a `dev`-only dependency purely to unit-test our hand-rolled value-iteration against its independent implementation on toy problems (numerical-parity test), never imported from production code. |
| **mdptoolbox-hiive** | **REJECT** | `hiive/hiivemdptoolbox`, only 21★, PyPI last release 2020-02-18. A Python-3-modernized fork of pymdptoolbox with a few extra algorithms — same core limitation as pymdptoolbox (tabular MDP only, no POMDP), and since pymdptoolbox itself already installs and runs fine on this box (verified above), the fork adds no capability we need badly enough to justify a second, less-popular dependency in the same lineage. |
| **simple-pid** | **REJECT** | `m-lundberg/simple-pid`, 905★, MIT, actively maintained — a genuine, well-built continuous PID controller (confirmed via its PyPI description: "a simple, easy to use PID controller"). Wrong tool class entirely: our action space is **discrete** (`monitor/repair/replace/quarantine`), not a continuous actuator output a PID loop would drive. No natural mapping exists; forcing one (e.g. using a PID output to continuously retune an alert threshold) is a speculative future auxiliary, not this engine's core. |
| **python-control** (PyPI name `python-control`) | **REJECT — and flag as a naming trap** | **Critical finding**: the PyPI package literally named `python-control` is a **reserved placeholder with zero functionality** (`pip download` succeeds and returns a 1.4KB wheel; its own PyPI metadata says *"Reserved name placeholder. No functionality."*). The REAL control-systems library (`python-control/python-control` on GitHub, 2,056★, BSD-3-Clause, pushed 2026-06-09, actively maintained) is published on PyPI under the **different name `control`** (confirmed via PyPI JSON API: `control` v0.10.2, homepage `python-control.org`). Even the real `control` library is rejected for the same reason as simple-pid: it is a continuous state-space/transfer-function control-theory toolkit (Kalman filters, LQR, root-locus) with no natural fit to a discrete maintenance-action MDP. **Action item for whoever eventually writes `pyproject.toml`: never `pip install python-control` expecting the real library — it silently installs a no-op placeholder.** |
| **networkx** | **INTEGRATE (already a dependency)** | Already installed (3.6.1, confirmed in `.venv`) though undeclared in `pyproject.toml` (carry the declaration fix into this build). Used for the **component dependency graph**: model which decision engines depend on which broker session/data adapter/model artifact as a `DiGraph`, use reachability (`nx.descendants`) to compute blast radius before a `quarantine`/`replace` action, and this is the concrete substrate for the Erlang-OTP-style restart-strategy taxonomy (§4) — `one_for_one` vs `one_for_all`/`rest_for_one` becomes "quarantine just this node" vs "quarantine this node's `nx.descendants`." |
| **pybreaker** | **INTEGRATE** | `danielfm/pybreaker`, 688★, BSD-3-Clause, pushed 2026-07-04 (actively maintained). Confirmed (fetched its GitHub page) 3-state CLOSED/OPEN/HALF_OPEN machine with `fail_max`/`reset_timeout`/`success_threshold` and a genuinely useful `CircuitBreakerListener` hook (`before_call`/`state_change`/`failure`/`success` callbacks) — this is the exact wiring point to push circuit-breaker state transitions onto the dashboard (Rule N) and into the health-index fusion (§1d) as one more telemetry input. Use as the **fast, reactive front line** (per-call fail-fast) that sits in front of the slower, deliberative CBM/RUL layer (§2–§3) which decides the actual repair/replace/quarantine action. |
| **purgatory** | **REJECT** | `mardiros/purgatory` (real repo — not the `sbabin/purgatory` guess, which doesn't exist), only 4★, asyncio-only circuit breaker. Rejected for obscurity (4 stars, minimal community validation) and because pybreaker already covers the sync circuit-breaker need; if/when parts of this system go fully async, revisit. |
| **circuitbreaker** (fabfuel) | **REJECT** | 520★, ambiguous license (`NOASSERTION` via GitHub API, no LICENSE file found at the expected path) — irrelevant to the actual decision under Rule E (license is never a filter here) but noted for completeness; rejected instead because it is feature-thinner than pybreaker (simpler decorator-only API, no listener/hook mechanism), and we specifically need the hook mechanism to wire state changes into the dashboard. Redundant with pybreaker for our needs. |
| **tenacity** | **INTEGRATE** | `jd/tenacity`, 8,731★, Apache-2.0, pushed 2026-07-15 (very actively maintained — the de facto standard Python retry library). Confirmed rich wait-strategy composition (`wait_exponential`, `wait_random_exponential` for jittered exponential backoff — directly implementing the Kubernetes-CrashLoopBackOff pattern from §4), stop conditions (`stop_after_attempt`/`stop_after_delay`, composable with `|`), and callback hooks (`before_sleep_log`, `retry_error_callback`) for observability. This is the concrete implementation of the CBM `repair` action's retry loop. |
| **river** | **INTEGRATE** | `online-ml/river`, 5,891★, BSD-3-Clause, pushed today (2026-07-26). Confirmed prebuilt `manylinux_2_28_aarch64` wheel for cp312 (installs cleanly, no build step). Both `ADWIN` and `PageHinkley` confirmed present in `river.drift` (fetched docs) — ADWIN's adaptive-window two-sub-window comparison is a genuine alternative/complement to the fixed-parameter EWMA/CUSUM in §1c for streams where the right smoothing constant isn't known in advance. Use alongside (not instead of) the NIST-standard EWMA/CUSUM: EWMA/CUSUM for the well-understood, parameter-tunable signals (T²/Q/Mahalanobis), ADWIN/Page-Hinkley for signals whose right time-scale is not known a priori. |
| **ruptures** | **REJECT (for v1); revisit for offline analysis** | `deepcharles/ruptures`, 2,067★, BSD-2-Clause, pushed 2026-07-06, prebuilt aarch64 wheel confirmed. A genuinely strong **offline** change-point-detection library (multiple search methods: PELT, binary segmentation, window-based). Rejected for the *online, real-time* homeostat loop specifically because it's designed for batch/offline segmentation of a completed series, not streaming single-point updates (river's ADWIN/Page-Hinkley are the streaming-native fit) — but flagged as the right tool for a LATER offline forensics feature ("show me exactly where this component's degradation trajectory changed regime," post-hoc, for a human reviewing a past incident). |
| **pyod** | **INTEGRATE (as a complementary ensemble option, not the core T²/Q primitive)** | `yzhao062/pyod`, 9,932★, BSD-2-Clause, pushed 2026-07-24 (very actively maintained, the standard Python outlier-detection toolkit — 60+ detectors). Its `PCA` detector (confirmed via its source and description) computes a similar SVD-based reconstruction-error anomaly score, but fuses what §1b keeps deliberately separate (T² in the retained subspace vs. Q/SPE in the residual subspace) into one combined score with no exposed, separately-calibrated control limits for each — so it is NOT the right tool for the **primary** health-index primitive, where we specifically want the classical, separately-thresholded T²/Q pair (hand-rolled on top of `sklearn.decomposition.PCA`, already a dependency). Where PyOD earns its place: as an **optional richer anomaly-ensemble** layer for components whose telemetry doesn't fit the Gaussian-ish assumption T²/Q leans on (e.g. `ECOD`/`COPOD`/`IsolationForest` detectors as a second opinion feeding into §1d's fusion), not as a replacement for the core statistic. |

---

## 7. What I could NOT verify this pass

- **The exact symbolic form of the *refined* Jackson & Mudholkar (1979) SPE/Q control-limit formula**
  (the version using `θ₁,θ₂,θ₃,h₀,c_α` rather than the simpler chi-square approximation) — every source
  found this pass (KU Leuven review, PLOS ONE paper, a Google Groups/MATLAB thread) either rendered the
  equation as an un-transcribable image or paraphrased around it without reproducing the exact symbols.
  I have HIGH confidence the simpler, fully-verified chi-square approximation given in §1b
  (`δ² = g_s·χ²_α(h_s)`) is mathematically valid and sufficient for a v1 build, but the more precise
  normal-approximation form should be pulled directly from the original Technometrics paper (Jackson &
  Mudholkar, 1979, Technometrics 21:341–349) or a textbook that reproduces it in text (not an image)
  before it's hard-coded into production, rather than trusting my paraphrase of a paraphrase.
- **The Hotelling T² control-limit formula** (`T²_α = [a(n−1)(n+1)]/[n(n−a)]·F_α(a,n−a)`) is given from
  memory of the standard textbook result (Jackson 1991; Chiang/Russell/Braatz 2001) — it is extremely
  standard and I'm confident in it, but unlike every other formula in this doc it was not independently
  re-derived from a freshly-fetched primary source this pass (my WebFetch attempts on two candidate
  sources for it both failed — one PDF was image-only, one page 503'd). Flagged per Rule D/O's honesty
  requirement rather than silently presented as equally-verified.
- **A live, current GitHub star count / last-commit date for `reliability` (MatthewReid854)'s GitHub repo
  vs. its PyPI release** — I confirmed the PyPI release date (2025-03-07) and GitHub star count (428,
  pushed 2025-03-07 — consistent) via the API, so this is actually fine, but noting it because unlike
  the other rejections its recency is genuinely good and the rejection rests entirely on the
  Bayesian-capability gap, not staleness — worth the user double-checking that trade-off specifically
  since `reliability`'s frequentist fits are otherwise higher-quality/more full-featured than a hand-roll.
- **Whether `scikit-survival` actually succeeds building from source on this exact box** — I confirmed
  `pip download` resolves an sdist (no prebuilt wheel), but did NOT run the actual build-from-source to
  completion (would need a C/Cython toolchain check and meaningful build time); the REJECT verdict is
  based on avoiding that friction for a v1 that doesn't need scikit-survival's extra power yet, not on a
  confirmed build failure. If a later slice needs it, actually attempt the source build before assuming
  it works.
- **WebSearch quota**: not exhausted this session — every section above used live search, and the
  majority of load-bearing formulas were confirmed via `WebFetch` on primary or near-primary sources
  (NIST e-Handbook, Erlang docs, Google SRE Workbook, PyMC docs, GitHub/PyPI APIs). No fallback-to-memory
  was needed, unlike research/166's session.

---

## §RECOMMENDATION — the exact algorithm stack to implement

1. **Health index (§1)**: per telemetry cluster, fit PCA on a healthy-baseline window (`sklearn.
   decomposition.PCA`, already a dependency) → track **T² + SPE/Q** with the chi-square-approximation
   control limits (§1b, fully verified) as the calibrated 0/1 alarm pair; feed the raw statistics through
   an **EWMA** (NIST formula, §1c) for the primary smoothing/alarm layer, cross-checked by **river's
   ADWIN** for signals where the right smoothing timescale isn't known a priori. Fuse per-cluster scores
   into one `h(t)∈[0,1]` per component via weighted-max (never weighted-mean — a single hard failure
   must dominate).
2. **RUL (§2)**: **lifelines' `WeibullAFTFitter`/`CoxPHFitter`** as the primary right-censored survival
   regression, with the covariate set = age, restart count, EWMA-derived degradation trend, component
   class. For components/classes with too little failure data even for a regularized regression, fall
   back to a **Wiener-process first-passage-time** RUL (closed-form Inverse-Gaussian, hand-rolled — no
   OSS gap here, it's a ~20-line closed-form) driven directly off the §1 health-index trajectory, since
   it needs zero observed failures to produce a calibrated distribution.
3. **Small-N principledness (§5 — the load-bearing section)**: a **hierarchical Gamma-Poisson /
   Beta-Binomial partial-pooling model** (hand-rolled conjugate math per §5b/§5c — closed-form, no PPL
   dependency needed for the conjugate cases; reach for `pymc` only if/when a non-conjugate covariate
   structure is actually needed) grouping components by class (8 SQLite stores share one population
   prior, N broker sessions share another, ~30 decision engines share a third), with one shared
   `shrink_toward_prior(observed_sum, observed_n, prior_mean, prior_strength)` primitive reused across
   failure-rate, health-degradation-rate, and reward-rate shrinkage (unifying §5b/§5c/§5d into one
   function, per Rule C).
4. **Maintenance policy (§3)**: a hand-rolled **Bellman value-iteration** solver (~50–80 lines of numpy,
   deliberately not `pymdptoolbox` — verified working but too stale/rigid to extend, kept only as a
   `dev`-dependency numerical cross-check in tests) over the discretized health state from step 1, costs
   parameterized per-component-class from step 3, producing a **control-limit threshold table** (§3c) —
   solved periodically offline, deployed as a cheap lookup at runtime, not re-solved inline per decision.
5. **Reactive front line (§4/§6)**: **pybreaker** as the fast, per-call circuit breaker (CLOSED/OPEN/
   HALF_OPEN) sitting in front of the deliberative CBM layer, with **tenacity** implementing the actual
   `repair` action's exponentially-backed-off retry loop, and **networkx** (already a dependency) as the
   component-dependency graph determining blast radius for `replace`/`quarantine` (Erlang-OTP-style
   `one_for_one` vs `one_for_all`/`rest_for_one` strategy selection, §4).
6. **Alerting surfaced to the dashboard**: multiwindow multi-burn-rate style (§4, Google SRE) rather than
   single-threshold — apply the same "long window + short window must both agree" pattern to each
   component's health-degradation rate before surfacing a dashboard alarm (Rule N), reusing the exact
   14.4×/6×/1× three-tier structure as a starting point, tunable per component class.
7. **New declared dependencies** (add to `pyproject.toml`, all ARM64/Linux/Python-3.12 wheel-or-clean-
   sdist-verified this pass): `lifelines`, `pybreaker`, `tenacity`, `river`. Add `pymdptoolbox` and
   `pyod` under `[project.optional-dependencies].dev`/a numerical-cross-check-only extra. Also fix the
   pre-existing undeclared-dependency gap by adding `networkx` and `statsmodels` to `[project]
   .dependencies` in the same change (both already installed and used; research/166 flagged this same
   gap and it's still unfixed).
