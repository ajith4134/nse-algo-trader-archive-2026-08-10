# 172 · Component-Lifecycle Homeostat — institutional spec (Trunk X AUTOPOIESIS)

**Date:** 2026-07-27 · **Status:** SPEC (contract for the build) · **Trunk:** X · SELF-PRODUCTION
**Research base:** `168` (PHM/RUL math + SOTA) · `169` (operational-closure formalism) · `170`
(supervision/actuation engineering) · `171` (sourcing standard used for this pass)
**Package:** `src/nse_algo_trader/autopoiesis/`
**User decisions (MCQ, 2026-07-27):** full-organism membership · **all three** algorithm layers
(PHM prognostics + control-theoretic homeostat + supervision tree/breakers) · autonomous budgeted
conscience-checked authority · all three acting levers (vitality gate · quarantine · cadence throttle).

---

## 1 · Intent & the decision it changes

The organism currently cannot perceive or repair itself. Verified facts from the substrate audit:

- **37** `_maybe_run_*` cadence methods each double-swallow exceptions (`except Exception: pass`) — a
  permanently dead engine is indistinguishable from a healthy one.
- `is_alive()` is used at **3 of 6** thread sites purely as a re-entrancy guard — **no liveness monitor,
  no restart**. Process-level `systemd Restart=always` is blind to which internal subsystem died.
- **`win_probability_engine.load_or_train()` = `load() or train_from_records()`** — once the `.joblib`
  exists it is reused **forever**; the 6-hour cadence re-invokes it and it short-circuits to `load()`.
  The model that sizes real trades **can never retrain**. Nothing maintains it → a genuine closure
  violation, not a hypothetical one.
- **Angel One's session has no expiry check at all** (Kite and Breeze have `is_still_valid`; Angel One
  has no store class with one).
- On-disk right now: `market_data.sqlite3` last written **2026-07-24** (3 days stale), Kite and Breeze
  tokens both **expired**.

**The decision it changes.** Organism health becomes a first-class input to trading. A degraded
component that feeds a signal path *tightens or vetoes* entries at all 4 entry sites; a component judged
non-self/failing is *quarantined* so downstream engines fall back to a healthy sibling; and the setpoint
keeper *throttles the organism's own workload* (cadences, universe breadth, LLM call rate) to hold
resource setpoints. A thin version — a dashboard health panel — would fail the intent precisely because
it changes nothing: the system would still trade full-size on a stale model and a dead feed.

## 2 · I/O contracts

**Inputs** (raw pipeline, point-in-time correct, all real):

| Source | Signal | Access |
|---|---|---|
| Threads of `LivePaperTradingService` | liveness, last-heartbeat age, re-entrancy state | `threading.enumerate()` + heartbeat stamps |
| `_maybe_run_*` cadences (37) | last-success time, consecutive-failure count, error rate | orchestrator-recorded |
| SQLite stores (8) | file mtime age, byte size, `PRAGMA integrity_check`, WAL size | `pathlib.stat` + `sqlite3` |
| JSON/joblib artifacts (6) | mtime age vs declared max staleness, load success | `pathlib.stat` |
| Broker sessions (Kite/Breeze/Angel One) | token validity, seconds-to-expiry | existing `is_still_valid` + a NEW Angel One check |
| Data adapters | `SourceAttempt` outcome served/empty/error | existing observer callback |
| LLM provider pool | per-provider cooldown, exhaustion events | existing `on_attempt` observer |
| Process/host | CPU%, RSS, open fds, disk free, thread count | `psutil` |

**Outputs** (typed, frozen dataclasses):

- `ComponentHealthAssessment` — `component_id`, `health_index ∈ [0,1]` (1 = healthy), `t_squared`,
  `spe_q`, `ewma_level`, `degradation_state ∈ {HEALTHY, DEGRADED, FAILING, FAILED}`, `sample_count`.
- `RemainingUsefulLifeEstimate` — `median_hours`, `p10_hours`, `p90_hours`, `estimator ∈
  {WEIBULL_AFT, WIENER_FIRST_PASSAGE, PRIOR_ONLY}`, `is_earned`, `observed_failure_count`.
- `MaintenanceAction` — `action ∈ {MONITOR, REPAIR, REPLACE, QUARANTINE}`, `component_id`,
  `expected_cost`, `blast_radius` (component ids), `restart_strategy ∈ {ONE_FOR_ONE, ONE_FOR_ALL,
  REST_FOR_ONE}`.
- `OperationalClosureReport` — `violations` (non-exogenous source SCCs), `organizations` (non-trivial
  SCCs), `critical_articulation_points`, `is_closed`.
- `OrganismVitalityVerdict` — `vitality_index ∈ [0,1]`, `size_multiplier ∈ [0,1]`, `permits_order: bool`,
  `binding_component_id`, `reason`, `maturity` (per-component `have N / need M`).

**Sign/unit conventions:** health index 1.0 = perfectly healthy (so multipliers compose directly);
all durations in hours, UTC-explicit; the size multiplier is **clamped `[0,1]` structurally** — the
homeostat can only tighten or veto, never up-size.

## 3 · Algorithm + named SOTA analogs

Top-level architecture = **IBM MAPE-K** (Monitor → Analyze → Plan → Execute over shared Knowledge),
level-triggered like a **Kubernetes controller** (reconcile observed vs desired every cycle) rather than
edge-triggered — which is exactly the failure mode of the current `except: pass` swallow.

| Layer | Algorithm | SOTA analog |
|---|---|---|
| Health index | PCA on healthy baseline → Hotelling **T²** + **SPE/Q** with χ²-approx control limits; **EWMA** smoothing; `river` ADWIN cross-check. Fusion by **weighted-max** (one hard failure must dominate, never averaged away) | NASA C-MAPSS / industrial condition-based monitoring |
| RUL | **lifelines `WeibullAFTFitter`** right-censored regression (covariates: age, restart count, EWMA degradation trend, class) → **Wiener-process first-passage** closed-form Inverse-Gaussian when a class has too few failures (needs **zero** observed failures) | PHM prognostics |
| Small-N | **Hierarchical Gamma-Poisson / Beta-Binomial partial pooling** — 8 SQLite stores share one population prior, sessions another, ~30 engines a third; one reused `shrink_toward_prior()` primitive | Empirical-Bayes hierarchical reliability |
| Policy | **Bellman value iteration** over discretized degradation states, actions {monitor, repair, replace, quarantine}, per-class costs → **control-limit threshold table**, solved on cadence, looked up at runtime | Condition-based-maintenance MDP |
| Closure | **Chemical Organization Theory** — `closed` ∧ `self-maintaining` = *organization*; computed as SCC/condensation over a **curated `G_maintains` overlay** (`u → v` = "u is maintained by v"), violation = non-exogenous source SCC; criticality via articulation points + reverse-PageRank | Dittrich & Speroni di Fenizio (2007); Montévil–Mossio closure-of-constraints |
| Reactive front line | **pybreaker** CLOSED→OPEN→HALF_OPEN per component; **tenacity** for repair retries with **decorrelated-jitter** backoff; retry budget (Envoy-style 20%) to prevent repair storms | resilience4j / Hystrix; AWS backoff-and-jitter |
| Supervision | **Erlang/OTP** child specs (`permanent`/`transient`/`temporary`), restart strategies (`one_for_one`/`one_for_all`/`rest_for_one`) chosen by blast radius from the dependency graph, and the **MaxR-restarts-in-MaxT** intensity limiter | OTP supervision trees; k8s CrashLoopBackOff (10s→20s→…→300s cap) |
| Setpoints | Essential variables held in a **viability set** (Ashby ultrastability / Aubin viability kernel), not a single-variable PID — jointly constrained, so the throttle acts on whichever variable is nearest its boundary | Ashby's homeostat |
| Alerting | **Multiwindow multi-burn-rate** (long + short window must agree) before surfacing an alarm | Google SRE burn-rate alerting |

## 4 · Rule-Q maturity ladder (full function now, activation as data accrues)

Every component below is **built to full depth immediately**; only *arming* is data-gated, and each arms
itself automatically with no code change:

| Component | Needs | Behavior while immature | Arms at |
|---|---|---|---|
| PCA T²/SPE health index | ≥30 telemetry samples/component | EWMA + declared-threshold path (full code present, PCA abstains) | 30 samples |
| Weibull AFT RUL | ≥2 observed failures **in the class** | Wiener first-passage FPT (needs 0 failures) — not a stub, a different valid estimator | 2 class failures |
| Hierarchical prior | nothing | **Works from N=0 by construction** — that is its purpose | immediately |
| MDP control-limit policy | costs from priors | solved from prior costs, re-solved as real costs accrue | immediately, refines |
| Closure audit | curated `G_maintains` | full audit — structural, needs no history | immediately |
| Supervision + breakers | nothing | fully armed — reactive layer needs no training | immediately |
| Vitality gate | nothing | **acts immediately, tighten-only** (a degraded organism trading smaller is safe by construction) | immediately |
| Quarantine | nothing | acts immediately, with fallback-sibling requirement | immediately |

`have N / need M` is surfaced per component on the dashboard.

## 5 · Engine-grade acceptance criteria (pass/fail — the build is graded on these)

1. **Real algorithm/model/solver** — PCA+T²/SPE, lifelines AFT survival regression, Wiener FPT
   closed-form, conjugate hierarchical shrinkage, Bellman value iteration, networkx SCC/condensation,
   pybreaker state machine. ✅/❌ each.
2. **Carried state + store** — append-only SQLite: telemetry history, failure events **with censoring
   flags**, repair-action ledger, breaker states. Survives restart (the current safety organs do NOT —
   `incident_post_mortem` names this gap).
3. **Raw-input pipeline** — every input in §2 read from the REAL organism, not simulated.
4. **Decision-grade output that changes behavior** — vitality multiplier + hard veto wired at **all 4
   entry sites**; quarantine acting on the data path; cadence throttle acting on the service loop.
5. **Numeric bars:**
   - Health index separates the **genuinely stale real components** (3-day-old `market_data.sqlite3`,
     expired Kite/Breeze tokens) from healthy ones — verified by eye.
   - Weibull AFT converges under **≥80% right-censoring** and rank-orders by degradation covariates.
     *(Pre-verified during sourcing: ρ=1.857, concordance 1.0, RUL 71.6h→970.8h on 2/10 failures.)*
   - Closure audit finds the **win-probability model** as a real violation (nothing retrains it).
   - MDP policy is a **monotone control-limit**: repair threshold ≥ monitor threshold.
   - Restart-intensity limiter trips after MaxR restarts in MaxT.
   - Breaker traverses CLOSED→OPEN→HALF_OPEN→CLOSED under induced failures.
   - Repair budget exhaustion blocks further repair actions.
   - Vitality multiplier **never exceeds 1.0** (property test).
6. **Tests** — unit + property/invariant (hypothesis) + adversarial (corrupt telemetry, NaN health,
   empty graph, all-censored survival data, repair storm) + the Rule-F real-data pass.
7. **Vocabulary** — "engine" is earned: real solvers + carried state. Sub-parts that only observe are
   named `monitor`/`collector`, not `engine`.

## 6 · Verification plan (Rule F, with Rule-J fallback)

- **Real-data pass (primary, available NOW — market closed does not block it):** the organism itself is
  real and currently degraded. Run the collector against the live filesystem/process: 8 real SQLite
  stores, 6 real artifacts, 3 real broker sessions, real `psutil` process metrics, the real 37-cadence
  registry. Health/RUL/closure outputs inspected by eye.
- **Survival model:** fit on the real repair/failure ledger once accrued; until then the Wiener FPT path
  runs off real health trajectories. Already verified to converge under 80% censoring.
- **Rule-J hermetic sim** (for actuation paths that must not be triggered in prod): a fake component
  behind the `SupervisedComponent` DI seam, living only under `tests/`, to drive restart-intensity
  trips, breaker transitions and repair-budget exhaustion deterministically.
- **⛔ OPEN BLOCKER (Rule K, live-accrual):** true failure-rate posteriors need real failures over real
  trading days. The hierarchical prior makes day-1 estimates principled, and the acting path is fully
  built and armed — only posterior sharpness accrues. Same shape as the win-prob/capital-allocation
  engines.

## 7 · Depth justification — what a thin version would omit

A ~150-line "health monitor" would ship: threshold alerts on a few metrics, a dashboard panel, and
nothing else. It would omit: the censored-survival RUL (so no prognostics — only post-mortem alarms),
the hierarchical prior (so every estimate would be a raw ratio over ~0 failures, wildly unstable),
the MDP policy (so no principled repair-vs-replace-vs-quarantine choice — just "alert the human"),
operational-closure auditing (so the unmaintained win-prob model stays invisible), the supervision tree
with intensity limiting (so a crash-looping thread restarts forever), circuit breakers and retry budgets
(so repair storms), and the entry-site lever (so behavior never changes). Size here is a symptom of
those eight real functions, not padding.

## 8 · Decomposition — `src/nse_algo_trader/autopoiesis/`

| Module | Role |
|---|---|
| `component_registry.py` | membership set (self vs non-self), component classes, EXOGENOUS tags, the curated `G_maintains` overlay |
| `component_telemetry_collector.py` | raw-input pipeline over the real organism (§2 inputs) |
| `component_health_index.py` | PCA T² + SPE/Q + EWMA → `h(t) ∈ [0,1]`, weighted-max fusion |
| `component_failure_hazard_model.py` | lifelines Weibull-AFT RUL + Wiener first-passage fallback |
| `hierarchical_failure_rate_prior.py` | conjugate Gamma-Poisson / Beta-Binomial partial pooling; `shrink_toward_prior()` |
| `maintenance_policy_solver.py` | Bellman value iteration → control-limit threshold table |
| `operational_closure_auditor.py` | networkx SCC/condensation, violations, articulation-point criticality |
| `component_supervision_tree.py` | OTP child specs, restart strategies, MaxR/MaxT intensity limiter, pybreaker breakers |
| `component_repair_executor.py` | the actuator: tenacity decorrelated-jitter retries, repair budget, referee/off-switch pre-check, forensic incident record |
| `homeostatic_setpoint_keeper.py` | viability-set setpoints → cadence/breadth/LLM-rate throttle |
| `autopoiesis_orchestrator.py` | the MAPE-K cycle binding all of the above |
| `autopoiesis_state_store.py` | append-only SQLite: telemetry, censored failure events, repair ledger, breaker states |
| `organism_vitality_gate.py` | the entry-site lever: multiplier + hard veto |

## 9 · Wiring (Rule G) + dashboard (Rule N)

- **Entry sites (4):** `live_universe_paper_loop._open_watched_breakout` ·
  `_seed_cash_instrument_from_orb` · `option_credit_spread_live_path.try_open_option_position_for_underlying`
  · `_try_open_directional_option`. Add `state.organism_vitality_multiplier(component_path)` to the
  multiplier chain (clamped ≤1.0, never raises) and `state.homeostat_permits_order()` to the hard-gate
  stack beside `power_budget_permits_order`.
- **Service cadence:** `_maybe_run_autopoiesis_homeostat(now)` — collect + analyze every cycle
  (cheap), re-solve the MDP policy and re-fit survival hourly.
- **Quarantine:** acts on the data path via the existing `SourceAttempt` observer seam.
- **Throttle:** modulates `scan_interval_seconds` / universe breadth / LLM rate.
- **Dashboard surface:** `component_lifecycle_homeostat` added to `FEATURE_SURFACE_MANIFEST`; metrics =
  organism vitality, per-class health counts, closure violations, RUL of the nearest-to-failure
  component, repairs today vs budget, and each maturity ladder's `have N / need M`.

## 10 · Sourcing — decisions with evidence tiers (Rule O.1a, new standard)

| Part | Decision | Tier | Evidence |
|---|---|---|---|
| Survival/RUL | **lifelines** | **Tier-2** | Installed + ran on our regime: 2/10 failures, 80% censored → converged, ρ=1.857, concordance 1.0, RUL rank-ordered 71.6h→970.8h. `WeibullAFTFitter(penalizer, l1_ratio)` confirmed by signature. |
| Survival alt | scikit-survival **not chosen** | **Tier-2** | Probed + signature-checked: scikit-learn-style Cox/RSF/boosting, **no parametric AFT** with priors; also resolves to an **sdist** on cp312 (source build). Mechanically stronger (OSSF 5.9 vs 3.1) but wrong fit. GPL-3.0 irrelevant (Rule E). |
| Reliability lib | `reliability` **rejected** | **Tier-1** | 507d since push, 0 releases/12mo, OSSF 3.4 — unmaintained past threshold. |
| MDP solver | hand-rolled value iteration; `pymdptoolbox` **dev-only** | **Tier-2** | research/168 installed and ran it — works on numpy 2.5.1/aarch64, but sdist-only, 1148d stale, OSSF 2.0. Kept as a numerical cross-check in tests, not a runtime dep. |
| Breaker | **pybreaker** | **Tier-2** | Test-suite grep: HALF_OPEN state genuinely tested. Caveat surfaced: OSSF `Maintained 0/10` despite a 22-day-old push — sustained activity is weak; vendoring is the fallback if it stalls. |
| Retry | **tenacity** | Tier-1 | OSSF 6.4, pushed 11d, actively released. |
| Retry alt | `stamina` **rejected** | **Tier-2** | Read its source/architecture: it *wraps* tenacity rather than competing — a second retry-flavored dep for no new capability. (It scored **highest** mechanically — a deliberate reminder that the score is not fitness.) |
| Retry alt | `backoff` **rejected** | **Tier-1** | **Repository ARCHIVED upstream**; 815d since push. |
| Breaker alts | `circuitbreaker` / `aiobreaker` / `purgatory` **rejected** | Tier-1 | 482d / 1667d / 376d stale; 520 / 29 / 4 stars; no capability pybreaker lacks. |
| Graph | **networkx** | **Tier-2** | Signature-probed: `strongly_connected_components`, `condensation`, `articulation_points`, `pagerank` all present with the needed shapes. OSSF 7.2. |
| Graph alts | `igraph` / `graph-tool` **rejected** | Tier-2 | research/169: unjustified at hundreds-of-nodes scale; graph-tool needs a heavy non-pip toolchain. |
| Drift | **river** | Tier-1 | ADWIN/Page-Hinkley; OSSF 4.6, pushed today; already the idiom used by `surprise_monitor`. |
| Telemetry | **psutil** | Tier-1 | OSSF 5.3, `Maintained 10/10`, aarch64 wheel. |
| Scheduler | **APScheduler** | Tier-1 | OSSF 5.0, pushed 14d — replaces the hand-listed cadence pattern. |
| Anomaly | `pyod` **deferred** | Tier-2 | research/169: batch-oriented; `river` covers the streaming need. Logged, not built. |
| Immune (AIS) | negative selection / DCA **rejected** | Tier-2 | research/169 read the literature + criticisms (scaling, "hole problem"); the engineering equivalent (registry + provenance + drift) is strictly better. |

**New declared dependencies:** `lifelines`, `pybreaker`, `tenacity`, `river`, `psutil`, `APScheduler`;
plus fixing the **pre-existing undeclared** `networkx` and `statsmodels` (flagged in research/166, still
unfixed). `pymdptoolbox` + `pyod` under dev extras.
