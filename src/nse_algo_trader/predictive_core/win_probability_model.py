"""The ML win-probability model core (Trunk IX PREDICTIVE-CORE; research/156).

A real trained model, not a formula: a LightGBM gradient-boosted classifier (small-data-safe
hyperparameters + class-imbalance weighting) wrapped in scikit-learn probability CALIBRATION, with a
cross-validated evaluation that produces a GENERALIZATION claim (out-of-fold AUC / Brier / log-loss),
a reliability (calibration) curve, feature importances, and an honest comparison against the incumbent
fixed-formula baseline. Integrates LightGBM + scikit-learn (research/156 §Sourcing) — the real
libraries, not a reimplemented subset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import UTC, datetime

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from nse_algo_trader.predictive_core.win_probability_features import FeatureSchema


@dataclass(frozen=True)
class WinModelHyperparameters:
    """Small-data-safe LightGBM settings — the literature (research/156 §Sourcing) warns GBMs silently
    overfit small data without tuning num_leaves / min_child_samples, so these are deliberately shallow +
    regularised."""

    num_leaves: int = 8
    max_depth: int = 3
    learning_rate: float = 0.05
    n_estimators: int = 200
    min_child_samples: int = 20
    reg_alpha: float = 1.0
    reg_lambda: float = 1.0
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    calibration_method: str = "sigmoid"   # Platt — robust on small data (isotonic needs more)


@dataclass(frozen=True)
class CalibrationBin:
    mean_predicted: float
    observed_rate: float
    count: int


@dataclass(frozen=True)
class ModelEvaluation:
    n_samples: int
    positive_rate: float
    cv_scheme: str
    n_splits: int
    auc: float | None
    brier: float
    log_loss: float
    baseline_brier: float | None
    baseline_log_loss: float | None
    beats_baseline: bool
    calibration_bins: tuple = field(default_factory=tuple)
    feature_importances: tuple = field(default_factory=tuple)  # (feature, gain) desc
    summary: str = ""


@dataclass(frozen=True)
class TrainedWinModel:
    calibrated_model: Any             # fitted CalibratedClassifierCV (sklearn duck-typed)
    schema: FeatureSchema
    trained_at: datetime
    n_samples: int
    positive_rate: float
    evaluation: ModelEvaluation | None = None


def _build_lgbm(hyperparams: WinModelHyperparameters, scale_pos_weight: float, n_reference: int):
    """Construct the LightGBM classifier, ADAPTING regularization to dataset size so it can still split
    on small data (a fixed min_child_samples tuned for large data forbids all splits on tiny folds →
    a constant, useless model). min_child_samples scales with n; num_leaves is capped for tiny sets."""
    import lightgbm as lgb

    min_child = max(3, min(hyperparams.min_child_samples, max(1, n_reference // 12)))
    num_leaves = hyperparams.num_leaves if n_reference >= 60 else max(2, min(hyperparams.num_leaves, 4))
    return lgb.LGBMClassifier(
        objective="binary", num_leaves=num_leaves, max_depth=hyperparams.max_depth,
        learning_rate=hyperparams.learning_rate, n_estimators=hyperparams.n_estimators,
        min_child_samples=min_child, reg_alpha=hyperparams.reg_alpha,
        reg_lambda=hyperparams.reg_lambda, subsample=hyperparams.subsample,
        colsample_bytree=hyperparams.colsample_bytree, scale_pos_weight=scale_pos_weight,
        verbose=-1, n_jobs=1, deterministic=True, random_state=13, subsample_freq=1)


def _scale_pos_weight(y) -> float:
    positives = int(np.sum(y))
    negatives = len(y) - positives
    return (negatives / positives) if positives > 0 else 1.0


def _choose_splits(n_samples: int, positives: int) -> int:
    """Pick a CV fold count that keeps ≥ a few positives per fold on small, imbalanced data."""
    if positives < 6 or n_samples < 20:
        return 0  # too few to cross-validate honestly
    return max(2, min(5, positives // 4, n_samples // 10))


def _calibration_bins(y_true, y_prob, n_bins: int = 5) -> tuple:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for lo, hi in zip(bins[:-1], bins[1:], strict=True):
        mask = (y_prob >= lo) & (y_prob < hi if hi < 1.0 else y_prob <= hi)
        if mask.sum() == 0:
            continue
        out.append(CalibrationBin(
            mean_predicted=float(y_prob[mask].mean()), observed_rate=float(np.mean(y_true[mask])),
            count=int(mask.sum())))
    return tuple(out)


def evaluate_win_model(X, y, schema: FeatureSchema, prior_win_probability,
                       hyperparams: WinModelHyperparameters = WinModelHyperparameters(),
                       time_groups=None) -> ModelEvaluation:
    """Cross-validated evaluation → an honest generalization claim + baseline comparison.

    Walk-forward by `time_groups` (session dates) when ≥3 distinct groups exist; otherwise stratified
    K-fold (recorded as `cv_scheme`). Produces OUT-OF-FOLD predictions only, so metrics are held-out."""
    y_arr = np.asarray(y, dtype=int)
    n, positives = len(y_arr), int(np.sum(y_arr))
    positive_rate = positives / n if n else 0.0

    n_splits = _choose_splits(n, positives)
    if n_splits == 0:
        return ModelEvaluation(
            n_samples=n, positive_rate=positive_rate, cv_scheme="none", n_splits=0, auc=None,
            brier=float("nan"), log_loss=float("nan"), baseline_brier=None, baseline_log_loss=None,
            beats_baseline=False, summary="too few samples/positives for an honest CV verdict")

    distinct_groups = len(set(time_groups)) if time_groups is not None else 0
    oof = np.full(n, np.nan)
    if distinct_groups >= 3:
        cv_scheme = "walk-forward-by-session-date"
        groups_sorted = sorted(set(time_groups))
        group_arr = np.asarray(time_groups)
        splits = []
        for i in range(1, len(groups_sorted)):
            train_mask = np.isin(group_arr, groups_sorted[:i])
            test_mask = np.isin(group_arr, [groups_sorted[i]])
            if train_mask.sum() and test_mask.sum():
                splits.append((np.where(train_mask)[0], np.where(test_mask)[0]))
        n_splits = len(splits)
    else:
        cv_scheme = "stratified-kfold"
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=13)
        splits = list(skf.split(X, y_arr))

    for train_idx, test_idx in splits:
        if len(set(y_arr[train_idx])) < 2:
            continue  # a fold with one class can't train a classifier
        model = _build_lgbm(hyperparams, _scale_pos_weight(y_arr[train_idx]), len(train_idx))
        model.fit(X.iloc[train_idx], y_arr[train_idx])
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]

    scored = ~np.isnan(oof)
    y_s, p_s = y_arr[scored], oof[scored]
    if len(set(y_s)) < 2:
        return ModelEvaluation(
            n_samples=n, positive_rate=positive_rate, cv_scheme=cv_scheme, n_splits=n_splits, auc=None,
            brier=float(brier_score_loss(y_s, p_s)) if len(y_s) else float("nan"),
            log_loss=float("nan"), baseline_brier=None, baseline_log_loss=None, beats_baseline=False,
            summary="held-out folds were single-class — no AUC; accrue more diverse trades")

    auc = float(roc_auc_score(y_s, p_s))
    brier = float(brier_score_loss(y_s, p_s))
    ll = float(log_loss(y_s, np.clip(p_s, 1e-6, 1 - 1e-6)))

    baseline_brier = baseline_ll = None
    beats_baseline = False
    if prior_win_probability is not None:
        base = np.clip(np.asarray(prior_win_probability, dtype=float)[scored], 1e-6, 1 - 1e-6)
        if np.isfinite(base).all():
            baseline_brier = float(brier_score_loss(y_s, base))
            baseline_ll = float(log_loss(y_s, base))
            beats_baseline = ll < baseline_ll   # lower log-loss = better probabilistic forecast

    importances = _full_fit_importances(X, y_arr, hyperparams, schema)
    summary = (f"{cv_scheme} ({n_splits} folds), n={n} ({positive_rate:.0%} win): AUC {auc:.3f}, "
               f"Brier {brier:.3f}, logloss {ll:.3f}"
               + (f" vs baseline logloss {baseline_ll:.3f} → "
                  f"{'BEATS' if beats_baseline else 'below'} baseline" if baseline_ll is not None else ""))
    return ModelEvaluation(
        n_samples=n, positive_rate=positive_rate, cv_scheme=cv_scheme, n_splits=n_splits, auc=auc,
        brier=brier, log_loss=ll, baseline_brier=baseline_brier, baseline_log_loss=baseline_ll,
        beats_baseline=beats_baseline, calibration_bins=_calibration_bins(y_s, p_s),
        feature_importances=importances, summary=summary)


def _full_fit_importances(X, y_arr, hyperparams, schema: FeatureSchema) -> tuple:
    if len(set(y_arr)) < 2:
        return ()
    model = _build_lgbm(hyperparams, _scale_pos_weight(y_arr), len(y_arr))
    model.fit(X, y_arr)
    gains = model.booster_.feature_importance(importance_type="gain")
    pairs = sorted(zip(schema.feature_names, (float(g) for g in gains), strict=True), key=lambda kv: kv[1], reverse=True)
    return tuple(pairs)


def train_win_model(X, y, schema: FeatureSchema,
                    hyperparams: WinModelHyperparameters = WinModelHyperparameters(),
                    time_groups=None) -> TrainedWinModel:
    """Fit the FINAL calibrated model on all data (after evaluating). Carried state = the fitted model."""
    y_arr = np.asarray(y, dtype=int)
    evaluation = evaluate_win_model(X, y, schema, X.get("win_probability"), hyperparams, time_groups)

    base = _build_lgbm(hyperparams, _scale_pos_weight(y_arr), len(y_arr))
    positives = int(np.sum(y_arr))
    calib_folds = max(2, min(3, positives // 5)) if positives >= 4 else 2
    calibrated = CalibratedClassifierCV(base, method=hyperparams.calibration_method, cv=calib_folds)
    calibrated.fit(X, y_arr)

    return TrainedWinModel(
        calibrated_model=calibrated, schema=schema, trained_at=datetime.now(UTC),
        n_samples=len(y_arr), positive_rate=positives / len(y_arr) if len(y_arr) else 0.0,
        evaluation=evaluation)


def predict_win_probability(trained: TrainedWinModel, X_row) -> float:
    """The calibrated P(win) for one candidate frame (built via build_inference_frame → same schema)."""
    return float(trained.calibrated_model.predict_proba(X_row)[:, 1][0])
