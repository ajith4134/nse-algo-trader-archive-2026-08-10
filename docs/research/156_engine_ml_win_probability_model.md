# research/156 — ENGINE: ML win-probability model (LightGBM) — first Rule-P engine build

**Purpose:** the first feature built under Rule P (engine-grade depth) + the `building-engine-grade-features`
skill — AND a test of whether that rule/skill produce institutional-grade code, benchmarked against a real
SOTA analog (**Qlib's model pipeline**). Trunk IX PREDICTIVE-CORE / I MIND.

## 1. Scope — a real ENGINE (not a scalar)
A trained gradient-boosted classifier that predicts **P(win)** per candidate trade, calibrated, persisted,
and wired to CHANGE position sizing.
- **Algorithm/model:** LightGBM gradient-boosted decision trees (binary classifier) + probability
  CALIBRATION (Platt/sigmoid; isotonic when data permits).
- **Carried STATE:** the trained booster + fitted calibrator + feature schema + training metadata (metrics,
  trained_at, baseline comparison), PERSISTED to a model store (joblib) and reloaded across restarts;
  retrained on a cadence.
- **Raw input pipeline:** `experience_nodes` → a real feature-engineering step (categoricals: mechanism,
  direction, instrument_kind, assigned_table, strategy_tag; numerics: prior win_probability baseline,
  hour-of-day, day-of-week; auto-drop zero-variance columns) → (X, y=win?).
- **Decision-grade output:** calibrated P(win) → an EDGE/Kelly-fraction **size multiplier** applied at the
  entry sites, replacing the fixed formula — a real behaviour change. It ACTS only once it beats the
  fixed-`win_probability` baseline on cross-validated log-loss (a performance gate computed on REAL data
  NOW, not market-gated).
- **SOTA analog (to benchmark against):** Qlib's model pipeline — trained models, walk-forward, calibration,
  evaluation, model persistence. NautilusTrader/Qlib-grade is the bar.

## 1b. Sourcing (Rule I / P.3 — integrate the real library; rejections surfaced for double-check)
Real WebSearch (2026-07-26) on gradient-boosting for tabular classification + calibration:
- **LightGBM 4.7.0 → CHOSEN (integrated).** Native categorical support, sklearn-compatible API,
  lightweight; installed. **Small-data risk flagged by the literature** ("picks LightGBM without tuning
  num_leaves/min_child_samples → silently overfit") → mitigated with small-data-safe hyperparameters
  (low num_leaves, high min_child_samples, shallow max_depth, L1/L2 reg, subsample, early stopping).
- **scikit-learn 1.9.0 → INTEGRATED** for `CalibratedClassifierCV` (Platt/isotonic), `StratifiedKFold`,
  `roc_auc_score`/`brier_score_loss`/`log_loss` — the real calibration + CV + metrics machinery, not
  reimplemented. `joblib` for model persistence.
- **Considered + not chosen (for your double-check — say if you'd prefer one):** XGBoost (noted as a
  strong small-data default — swappable via the same sklearn API if preferred); CatBoost (best for
  high-cardinality categoricals — ours are low-cardinality); FLAML / mljar-supervised AutoML (would
  auto-benchmark all three — heavier, deferred; can add as an outer tuner later).

## 2. Depth-justification (what a DIAGNOSTIC version would OMIT)
A thin version would compute a rolling win-rate scalar and show it on a panel. This engine instead has:
a real **train/validate loop** (walk-forward-by-session-date; stratified-KFold fallback when dates are too
few) with a **generalization claim** (out-of-fold AUC/Brier/log-loss), **class-imbalance handling**
(scale_pos_weight — real data is 19% wins), **probability calibration** (reliability curve), **feature
importances**, **persisted model state**, a **baseline-beat performance gate**, and **decision integration**
that changes sizing. None of that exists in a scalar diagnostic (research/155 gap #5).

## 3. Modules (decomposed engine — `predictive_core/`)
- `win_probability_features.py` — feature engineering: raw nodes → (feature matrix, target, schema);
  zero-variance drop; categorical encoding; a `FeatureSchema` carried into inference so train/serve match.
- `win_probability_model.py` — the model core: LightGBM training (imbalance-weighted, early-stopping),
  probability calibration, cross-validated evaluation (walk-forward/KFold, AUC/Brier/log-loss/calibration
  bins), feature importances. Returns a `TrainedWinModel` + `ModelEvaluation`.
- `win_probability_model_store.py` — persist/load the `TrainedWinModel` + metadata (joblib), atomic write.
- `win_probability_engine.py` — orchestrates train→evaluate→persist; `predict_win_probability(features)`;
  `performance_earned` (beats baseline on CV log-loss); `edge_size_multiplier(win_prob, reward_risk)`
  (Kelly-fraction-based, clamped) — the decision-grade output.
- Decision integration: `live_universe_paper_loop` applies `win_probability_size_multiplier` at the entry
  sites when the engine is performance-earned (else identity); service trains/loads + pushes the engine.

## 4. Data honesty (Rule F/O/K) — the ONE permissible open blocker
Real data today: **340 trades, 19% wins, all on ONE session_date** → true temporal walk-forward is not yet
possible (stratified-KFold fallback is used + flagged), and generalization is weak on this thin, single-day
sample. The ENGINE is complete and institutional-grade; **more trading DAYS to make it strongly predictive
is the single open data-accrual blocker** (accrues over live/replay sessions) — recorded, not hidden. The
performance gate ensures the model only sizes trades once it actually beats the baseline on held-out data.

## 5. Verification
- Hermetic (Rule J): feature pipeline (schema stability, zero-variance drop, encoding), model train/predict
  on a synthetic separable set (AUC≈1), calibration monotonicity, store round-trip, edge-multiplier
  monotonic in win_prob + clamped, performance-gate identity when not earned.
- Real-data (Rule F): train on the real 340 trades → report CV AUC/Brier/log-loss + calibration + feature
  importances + baseline comparison; inspect by eye; confirm the size multiplier changes a real decision.

## 6. Benchmark step (the test's purpose) — RESULT
Built via the `building-engine-grade-features` skill. Benchmarked against Qlib's model pipeline + sklearn.
**Verdict:** the skill WORKED — it forced engine-framing (not a scalar), real-library INTEGRATION
(LightGBM/sklearn/pandas, not reimplemented), the full ML lifecycle (features→model→store→engine),
decision integration (edge→Kelly sizing), and a real-data pass that CAUGHT A REAL BUG (min_child_samples
too large for small folds → size-adaptive regularization). The output is categorically an ENGINE.

**MATCHES institutional STRUCTURE:** trained GBDT (LightGBM = one of Qlib's 24 models), out-of-fold CV
generalization claim, walk-forward/KFold, sklearn probability calibration, carried FeatureSchema
(train/serve-skew guard), joblib persistence, baseline-beat gate, behaviour-changing sizing.

**BELOW institutional DEPTH (honest gaps):** (1) feature depth — 8 features vs Qlib's Alpha158/360
(the biggest gap; thin experience_nodes schema); (2) no hyperparameter tuning/AutoML; (3) no experiment
tracking / model versioning; (4) no SHAP; (5) no drift-aware retraining; (6) data volume — 340 samples /
1 session_date → weak/optimistic generalization (the open blocker).

**Rule/skill improvement:** added an **ML-engine addendum** to `building-engine-grade-features` (feature
depth / feature store · hyperparameter tuning · experiment tracking + versioning · explainability ·
leakage-free time-aware validation · drift-aware retraining · data-sufficiency honesty). Future ML
engines must meet this bar. This closes the build→benchmark→improve loop the user requested.

## 7. Rule K — the deepening backlog (recorded, not hidden)
Feature-store expansion (join raw market/context features) · hyperparameter search (Optuna/FLAML) ·
experiment-tracking ledger · SHAP explanations · drift-detection on retrain · option-site sizing wiring ·
XGBoost/CatBoost/ensemble options. All tracked (BACKLOG + task #10). The one DATA blocker: more trading days.
