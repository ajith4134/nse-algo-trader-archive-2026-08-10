# IX — surprise/free-energy monitor + ensemble world-models  ·  research/134

**Trunk IX PREDICTIVE-CORE / ACTIVE INFERENCE (the currency).** Design doc (Rule D). Sourcing:
research/133 (real pass, agent a63da04a, 48 tool-uses) — verdicts applied below.

## Sourcing findings (research/133)
- **Surprise/free-energy:** the surprise VALUE is exactly the per-prediction log-loss-bits the
  prequential scorer already computes (−log₂ p). `inferactively-pymdp` (the real FEP library, 723★)
  REJECTED as a dep (pulls jax/equinox/mctx for one scalar). `scipy.special.rel_entr` available but
  the binary case is `−log₂(p)` (stdlib). **The real win: VENDOR `river.drift.PageHinkley`** (BSD,
  ~100 LOC pure-Python) for spike/trend detection — but `river` is NOT installed and is a heavy lib
  for one detector, so **vendor a COMPACT Page-Hinkley** (the classic change-detection test) with
  attribution — the lightweight-piece pattern (like Stouffer/Spearman/VPIN).
- **Ensemble world-models:** NO fitting library at any weight class — sklearn needs fitted estimators
  w/ `.predict_proba`, BayesBlend/pyBMA need MCMC draws, `properscoring` abandoned (2015). **BUILD
  bespoke** — weighted mean + variance over the calibration board's per-mechanism win-probabilities,
  stdlib `statistics`. Also: **scipy declared in pyproject** (used directly, was undeclared).

## The ideas
- **Surprise / free-energy monitor** — active inference: the agent minimises SURPRISE (−log p of
  outcomes = free energy). Monitor the per-mechanism Bayesian surprise (cross-entropy between the
  predicted and realised win-rate) + flag the anomalously-surprising mechanism via Page-Hinkley — a
  world-model that is being surprised is failing; this is the early-warning.
- **Ensemble world-models** — combine the per-mechanism forecasts into ONE ensemble prediction +
  measure DISAGREEMENT (variance across members = epistemic/model uncertainty). High disagreement =
  the world-models don't agree = act with less confidence.

## Component parts (`predictive_core/` — new package for Trunk IX)
- `predictive_core/surprise_monitor.py` — a compact vendored `PageHinkley` (attribution: Page 1954 /
  river's BSD implementation) + `SurpriseReport`(mean_surprise_bits, most_surprising, spike_detected,
  summary) + `monitor_surprise(board)` (per-mechanism cross-entropy in bits → aggregate + spike).
- `predictive_core/ensemble_world_model.py` — `EnsembleForecast`(ensemble_prediction, disagreement,
  member_count, high_disagreement, summary) + `build_ensemble_forecast(board)` (n-weighted mean +
  weighted variance of `predicted_win_rate`).

## Wiring (Rule G/N)
Daily `_maybe_run_predictive_core` over the real calibration board; caches both. Surfaces
`surprise_monitor` + `ensemble_world_model`. READ-ONLY diagnostics (the acting — surprise gating,
ensemble-confidence sizing — is a queued consumer, Rule K).

## Verification
- Hermetic (Rule J): a mechanism whose outcomes sharply contradict its confident prediction → high
  surprise + Page-Hinkley spike; concordant board → low surprise, no spike. Ensemble: agreeing
  mechanisms → low disagreement; a split board → high disagreement; weighted mean is correct.
- Real-data (Rule F): over the real §10 memory, report the real aggregate surprise + most-surprising
  mechanism, and the real ensemble prediction + disagreement.

## Atlas impact
surprise/free-energy monitor + ensemble world-models 🔴→🟢. IX 2🟢→4🟢 (5🔴 left). Overall built
56→58/197 (29.4%). NEW feature package `predictive_core`.
