# IX — Surprise/free-energy monitor + ensemble world-models: OSS prior-art sourcing pass · research/133

Sourcing-oss-parts pass (Rule D) for two `AI_CONCEPT_TREE_STATUS.md` trunk-IX 🔴 branches
("surprise/free-energy monitor", "ensemble world-models"). Both operate purely over data the bot
already computes — the prequential prediction stream (`PrequentialForecastScore` /
`prequential_forecast_score()`, research/65, giving `mean_log_loss_bits` per graded prediction) and
the per-mechanism calibration board (`calibration_board()` → `CalibrationBoardRow.predicted_win_rate`
per `(strategy_tag, mechanism_name)`). No external data source needed for either. Real web/GitHub/PyPI
search run, READMEs/source read before verdicts. No code written this pass (sourcing only). License
recorded as info only (Rule E — personal use, not a filter).

**Environment facts checked first (shape the verdicts below):**
- `scipy==1.18.0` and `numpy==2.5.1` are already installed in `.venv` and scipy is already imported
  in-repo (`scipy.stats.norm` in `sentience/cross_modal_binding.py`, `epistemics/contradiction_resolver.py`)
  — **but neither is listed in `pyproject.toml`'s `dependencies`** (they're pulled in transitively,
  currently undeclared). Worth fixing when either feature is actually built: add explicit
  `scipy>=1.18` (and `numpy` only if a piece below ends up needing it directly).
- `numpy` is NOT imported directly anywhere in `src/` today — everything is pure-Python dataclasses
  over SQLite rows. Any new piece should prefer stdlib (`statistics`, `math`) over pulling numpy into
  the hot path unless a candidate genuinely earns it.
- research/63 already set the house precedent for this exact family of problem: **vendor a small,
  tested slice of `river`'s pattern rather than `pip install river`** (river pulls a Rust extension +
  numpy + Python≥3.11 pin). Both verdicts below follow that same precedent where relevant.

## Summary table

| # | Part | Best real candidate(s) | Verdict |
|---|------|------------------------|---------|
| 1 | Surprise VALUE (−log p) | Already computed — it IS `mean_log_loss_bits` / the per-prediction log-loss the prequential scorer stores | **build** — zero new code needed for the value itself, it exists today |
| 2 | Running level + TREND + spike flag over the surprise stream | `river.drift.PageHinkley` (BSD-3, pure Python, ~100 LOC, self-contained) | **vendor** — lift the class, same pattern as research/63's `river.metrics` vendor |
| 3 | Ensemble combination of per-mechanism forecasts | `sklearn.ensemble.VotingClassifier` / `mlxtend.EnsembleVoteClassifier` | **reject (wrong shape)** — both need fitted `.predict_proba()` sklearn estimators, not a stream of already-computed scalar win-probabilities |
| 4 | Ensemble disagreement (variance across members) | stdlib `statistics.fmean` / `statistics.pvariance` | **build (bespoke)** — 2-line weighted mean + variance, no dependency at all |

## Part 1 — Surprise / free-energy monitor

### 1a. What "surprise" is here
Bayesian surprise of a realized outcome under a forecast p is `−log p(outcome)` — precisely the
per-prediction term the prequential scorer already accumulates into `mean_log_loss_bits`
(`PrequentialForecastScore`, `src/nse_algo_trader/memory_reflection/experience_memory.py:161`).
There is nothing to source for the VALUE — this feature's real job is turning that existing stream
into a **monitor**: running level, trend, and spike/degradation flags.

### 1b. Active-inference libraries considered (and rejected as a dependency)
- **[pymdp / `inferactively-pymdp`](https://github.com/infer-actively/pymdp)** — PyPI:
  `pip install inferactively-pymdp` (or `uv pip install inferactively-pymdp`). MIT license. 723★,
  active (releases through mid-2026), pytest suite, benchmarked against SPM MATLAB. This is genuinely
  the reference Python active-inference/free-energy-principle package — but two disqualifiers:
  1. **Dependency weight**: its `pyproject.toml` now pulls `jax>=0.3.4`, `jaxlib>=0.3.4`,
     `equinox>=0.9`, `mctx>=0.0.5`, `networkx>=3.3`, `matplotlib>=3.1.3`, `seaborn>=0.11.1` on top of
     numpy — a full JAX-based POMDP-solver stack to get one scalar per prediction. Not worth it (Rule
     I is about acquiring what's needed, not over-acquiring).
  2. **Shape mismatch**: its variational-free-energy math (`pymdp/maths.py`:
     `calc_vfe`, `stable_entropy`, `stable_cross_entropy`, `dirichlet_kl_divergence`) is built around
     `Agent.infer_states()`/`infer_policies()` over generative-model tensors (A/B/C matrices), not a
     standalone "surprise of this one outcome" call over an arbitrary probability stream. There is no
     documented supported use of just the surprise/entropy primitives in isolation.
  - **Verdict: reference only.** Worth knowing `stable_cross_entropy`'s log-clipping trick exists if
    numerical edge cases (p→0) ever bite; not worth depending on or vendoring.
- **SPM (Statistical Parametric Mapping)** — the canonical free-energy-principle implementation is
  MATLAB (`spm_MDP_VB` family); no maintained Python port exists beyond pymdp itself (which
  re-implements the same math, not a wrapper of SPM). No separate finding here.

### 1c. KL/entropy primitives — what's actually usable
- **`scipy.special.rel_entr`** — already-installed dependency, elementwise `x·log(x/y)`
  ([docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.rel_entr.html)); this is
  the numerically-correct KL-divergence term (SciPy's own issue tracker flags `scipy.stats.entropy`'s
  base-`e` default and `scipy.special.kl_div`'s extra linear term as the two footguns — `rel_entr`
  summed is the clean one:
  [scipy/scipy#6521](https://github.com/scipy/scipy/issues/6521)). Only relevant if the monitor is
  ever extended to compare two full probability distributions (e.g. a regime-label distribution
  shift). For the binary win-probability case here, surprise is a **one-line** `-math.log2(p if
  outcome else 1-p)` — `rel_entr` isn't even needed for the core value, only cited so it's on record
  as the right tool if the monitor is later generalized past binary outcomes.
- **Verdict: scipy is already a dependency and already sufficient IF the multi-outcome case ever
  arises; the two-outcome case in production today needs no library at all.**

### 1d. Trend / spike detection over the running surprise stream — the real sourcing target
This is the part actually worth an OSS look: turning a running scalar (bits of surprise per
prediction) into "is the world-model DEGRADING" (trending worse) vs. a one-off spike.
- **[`river.drift.PageHinkley`](https://riverml.xyz/dev/api/drift/PageHinkley/)** ([source](https://github.com/online-ml/river/blob/main/river/drift/page_hinkley.py)) —
  BSD-3-Clause, part of `river` (5.9k★, active, PyPI `river` latest 0.25.0 / 2026-05-31). A
  CUSUM-style test over a scalar stream: `update(x)` → `drift_detected: bool`, with
  `mode='up'/'down'/'both'` to watch specifically for the surprise mean trending UP (world-model
  getting worse), `min_instances`, `delta`, `threshold`, `alpha` (forgetting factor) all tunable.
  **Read the actual source**: ~100 LOC, depends only on `river.stats.Mean` (a Welford running-mean,
  itself already vendored into this repo per research/63) and `river.base.DriftDetector` (trivial base
  class) — genuinely standalone-vendorable, exactly the same shape as the research/63 precedent.
  **Verdict: VENDOR** — lift `PageHinkley`, drop the `river.base.DriftDetector` inheritance (replace
  with a plain class matching this repo's dataclass conventions), reuse the already-vendored `Mean`.
- **`river.drift.ADWIN`** — also real and well-documented, but as of the current `river` release its
  Python class is a thin wrapper around `river._river_rust.drift.AdaptiveWindowing` (a compiled Rust
  extension) — **not vendorable** without either building the Rust component separately or taking the
  whole `river` package (which reintroduces the numpy/Python≥3.11/Rust-wheel dependency research/63
  already declined). **Verdict: reject for vendoring** (PageHinkley covers the same job and is pure
  Python).
- **Bayesian online changepoint detection** (`bayesian-changepoint-detection` on PyPI;
  [`bocpdms`](https://github.com/alan-turing-institute/bocpdms), MIT, 34★ — **archived Oct 2025**;
  `bocd`, `chchanges`) — the "proper" Bayesian answer (full run-length posterior + hazard function),
  but meaningfully heavier machinery (needs a chosen hazard rate + a predictive model per hypothesis)
  for a signal that's really "is the mean of a bounded [0, ~a few bits] stream drifting up." **Verdict:
  reject as overkill** — reference only if a future slice wants a full changepoint POSTERIOR instead
  of a boolean drift flag.
- **`ruptures`** — offline/batch changepoint detection (needs the whole series up front). Wrong
  execution model for a live, one-prediction-at-a-time monitor. **Reject.**

### Part 1 recommendation
Build the monitor as: (a) surprise VALUE = the log-loss-bits term the prequential scorer already
computes per graded prediction (no new code), (b) running level = a small trailing window / EWMA over
that stream (stdlib, ~10 lines), (c) trend+spike flag = **vendor `river.drift.PageHinkley`** (BSD-3,
~100 LOC, pure Python, no new runtime dependency once vendored). No case for `pip install
inferactively-pymdp` or `pip install river` — both are real, well-built libraries, just far heavier
than the one primitive each is needed for.

## Part 2 — Ensemble world-models (combine + measure disagreement)

### 2a. What this needs
Per-event, N per-mechanism win-probabilities (already produced by the debate/mechanism layer, read
via `calibration_board()`'s `predicted_win_rate` per mechanism, or the live per-event forecasts before
they're graded) → one blended ensemble probability (weighted mean, weights = e.g. each mechanism's
historical Brier/log-score) + a disagreement/uncertainty number (variance across the N members).

### 2b. scikit-learn / mlxtend ensembling — real, mature, wrong shape
- **[`sklearn.ensemble.VotingClassifier`](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.VotingClassifier.html)**
  (soft voting = probability averaging) and
  **[`sklearn.ensemble.StackingClassifier`](https://scikit-learn.org/stable/modules/ensemble.html)** —
  BSD-3-Clause, the canonical library, extremely mature (scikit-learn itself). Soft-voting is
  literally a weighted average of member `predict_proba()` outputs — the exact math wanted — but the
  API requires each "member" to be a **fitted scikit-learn estimator object** (`.fit(X, y)` /
  `.predict_proba(X)`), not a bag of already-computed scalar probabilities coming from independent
  in-house mechanisms/debate agents. Wrapping each mechanism as a fake zero-degree-of-freedom sklearn
  estimator just to call `VotingClassifier.transform()` (which does expose the per-member array,
  shape `(n_samples, n_classifiers)`, for a manual variance calc) would be more code than the
  bespoke version. **Verdict: reject** — same "wrong execution model" call research/63 made against
  `river.evaluate.progressive_val_score` (real, tested, just coupled to the wrong calling convention).
- **[`mlxtend.classifier.EnsembleVoteClassifier`](https://rasbt.github.io/mlxtend/user_guide/classifier/EnsembleVoteClassifier/)**
  ([repo](https://github.com/rasbt/mlxtend), dual BSD/CC-BY-4.0 license, 5.2k★, mature) — same
  fitted-estimator shape requirement as `VotingClassifier`; its docs show no built-in
  disagreement/variance utility beyond the weighted vote itself. **Verdict: reject**, same reason.

### 2c. Bayesian model averaging / blending libraries — real, wrong input shape
- **[BayesBlend](https://github.com/LedgerInvesting/bayesblend)** (`pip install bayesblend`,
  MIT-family, active 2024–2026, [paper](https://arxiv.org/abs/2405.00158)) — pseudo-BMA, stacking,
  and hierarchical stacking for blending **Bayesian models' pointwise log-likelihood draws**
  (ArviZ/CmdStanPy-shaped `InferenceData`, i.e. full MCMC posterior draws per data point). Built for
  blending e.g. several Stan models' posterior predictive draws, not a handful of point
  win-probabilities from heuristic/LLM-debate mechanisms. **Verdict: reject (wrong shape)** — no
  posterior draws exist here to feed it.
- **`pyBMA`** ([repo](https://github.com/JakeColtman/pyBMA)) — Bayesian model averaging, but scoped
  specifically to Cox proportional-hazards survival models. **Reject — wrong domain entirely.**
- **PyMC + ArviZ `az.compare(..., method="BB-pseudo-BMA")`** — same MCMC-draws requirement as
  BayesBlend, and pulls PyMC (a full probabilistic-programming stack) as a dependency for one weighted
  average. **Reject as overkill.**

### 2d. Proper-scoring / weighting libraries considered for the WEIGHTS
- **[`properscoring`](https://github.com/properscoring/properscoring)** (PyPI `pip install
  properscoring`, Apache-2.0) — CRPS/Brier scoring functions from The Climate Corporation. Checked
  directly on PyPI: **last release 0.1, Nov 2015, `Development Status :: 3 - Alpha`** — no releases
  in a decade, reads as abandoned. Even if alive, it computes scores from arrays it's handed; it
  doesn't do the ensembling/weighting itself. **Verdict: reject** (stale, and this repo's Brier/
  log-score math is already hand-rolled per research/48–49 anyway — no gap to fill).
- **`statsmodels`** — has no dedicated forecast-combination/ensemble-averaging API (checked; its
  ensembling surface is limited to model-selection tooling, nothing matching "combine N pre-computed
  probabilities with weights"). **Not applicable.**

### Part 2 recommendation
This is a genuinely bespoke 2-line computation over data this repo already owns per event: a
**weighted mean** (weight = each mechanism's current Brier or log-score standing, already computed by
`reliability_decomposition()`/`calibration_board()`) and a **weighted/unweighted variance** across the
per-mechanism probabilities for the disagreement number. Python's stdlib `statistics.fmean` (supports
weights via a paired `weights=` in 3.11+... actually stdlib `fmean` doesn't take weights until 3.13 —
note for the build: either hand-roll the weighted sum in 2 lines, since Python is pinned `>=3.11`, or
add the trivial `sum(w*x for w,x in zip(...)) / sum(w)` one-liner) and `statistics.pvariance` (or
`.variance`) cover the disagreement metric with **zero new dependencies** — not scipy, not numpy, not
sklearn. No real library earns its weight here; forcing `scikit-learn` in for a weighted mean+variance
would be the exact over-acquisition Rule I warns against in the other direction (Rule I is "go get what's
missing," not "add a dependency where stdlib already suffices").

## Overall recommendation
1. **Surprise monitor**: the surprise VALUE already exists (prequential log-loss bits) — build the
   level/trend/spike wrapper by vendoring `river.drift.PageHinkley` (BSD-3, ~100 LOC, pure Python, no
   new runtime dependency), the same vendor-not-install pattern research/63 already set.
2. **Ensemble world-models**: no library fits the shape (all real candidates assume either fitted
   sklearn estimators or full MCMC posterior draws) — build the weighted-mean + variance bespoke, pure
   stdlib, over the per-mechanism probabilities this repo already computes.
3. **scipy is a hidden, undeclared dependency today** (installed + imported, absent from
   `pyproject.toml`) — fix that in whichever slice lands first, independent of these two features.

## Sources
- https://github.com/infer-actively/pymdp
- https://pypi.org/project/inferactively-pymdp/
- https://github.com/infer-actively/pymdp/blob/main/pymdp/maths.py
- https://arxiv.org/abs/2201.03904 (pymdp paper)
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.rel_entr.html
- https://github.com/scipy/scipy/issues/6521
- https://riverml.xyz/dev/api/drift/PageHinkley/
- https://github.com/online-ml/river/blob/main/river/drift/page_hinkley.py
- https://riverml.xyz/dev/api/drift/ADWIN/
- https://github.com/online-ml/river/blob/main/river/drift/adwin.py
- https://pypi.org/project/river/
- https://github.com/alan-turing-institute/bocpdms (archived)
- https://pypi.org/project/bayesian-changepoint-detection/
- https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.VotingClassifier.html
- https://scikit-learn.org/stable/modules/ensemble.html (StackingClassifier)
- https://rasbt.github.io/mlxtend/user_guide/classifier/EnsembleVoteClassifier/
- https://github.com/rasbt/mlxtend
- https://github.com/LedgerInvesting/bayesblend
- https://arxiv.org/abs/2405.00158
- https://github.com/JakeColtman/pyBMA
- https://github.com/properscoring/properscoring
- https://pypi.org/project/properscoring/
- docs/research/63_prequential_scorer_oss_sourcing.md (house precedent this pass follows)
