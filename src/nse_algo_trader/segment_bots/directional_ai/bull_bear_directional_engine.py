"""BULL/BEAR directional engine — the two calibrated directional models per bot (engine-grade ML, Rule P).

Two independent trained models over the SAME feature vector:

* **BULL** — LightGBM classifier of ``y_up`` (up-barrier-first) → calibrated **P(up)**.
* **BEAR** — LightGBM classifier of ``y_down`` (down-barrier-first) → calibrated **P(down)**.

Each is trained on the FULL, un-direction-filtered sample (so it sees its negative class and can calibrate),
under leakage-free **walk-forward** (time-ordered CV), **isotonically calibrated** (tree scores are
miscalibrated), with **SHAP** attributions and a **river ADWIN** drift monitor on its realised outcomes.
Carried state = both persisted models + calibrators + a metrics ledger, per bot.

Rule Q maturity ladder: below a minimum labelled-sample count the pair is not earned and ``directional_view``
returns ``maturity="gathering"`` with neutral 0.5/0.5 probabilities — the bot then keeps its existing
(rule/rank) side, never a spurious directional bet on an untrained model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from nse_algo_trader.segment_bots.directional_ai.directional_feature_engine import (
    DIRECTIONAL_FEATURE_NAMES,
    DirectionalSample,
)

_IST = timezone(timedelta(hours=5, minutes=30))
_MIN_SAMPLES_TO_TRAIN = 400
_MIN_PER_CLASS = 30
_MIN_TIME_FOLDS = 3


@dataclass(frozen=True)
class DirectionalView:
    """Live directional read for one instrument."""

    p_up: float
    p_down: float
    maturity: str  # "gathering" | "earned"

    @property
    def net_directional(self) -> float:
        return self.p_up - self.p_down  # >0 bullish, <0 bearish


@dataclass(frozen=True)
class BullBearTrainingReport:
    """Honest outcome of a training run (surfaced, never hidden — Rule K/O)."""

    trained: bool
    n_samples: int
    n_up: int
    n_down: int
    bull_walk_forward_auc: float | None
    bear_walk_forward_auc: float | None
    bull_top_features: tuple[tuple[str, float], ...]
    bear_top_features: tuple[tuple[str, float], ...]
    optimism_note: str
    trained_at_ist: str


class DirectionalModelStore:
    """Persists the BULL + BEAR models/calibrators + a metrics ledger (carried state), per bot."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def model_path(self) -> Path:
        return self._dir / "bull_bear_models.joblib"

    def save(self, payload: dict) -> None:
        import joblib

        joblib.dump(payload, self.model_path)

    def load(self) -> dict | None:
        # joblib(pickle) is safe here: only this bot's own models, written by save() to a private dir.
        import joblib

        if not self.model_path.exists():
            return None
        try:
            return joblib.load(self.model_path)
        except (OSError, EOFError, ValueError):
            return None

    def append_ledger(self, report: BullBearTrainingReport) -> None:
        path = self._dir / "bull_bear_ledger.json"
        history = []
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                history = []
        history.append({"trained_at": report.trained_at_ist, "n": report.n_samples,
                        "bull_auc": report.bull_walk_forward_auc, "bear_auc": report.bear_walk_forward_auc})
        path.write_text(json.dumps(history[-200:], indent=1))


class BullBearDirectionalEngine:
    """Trains + serves the BULL (P↑) and BEAR (P↓) models for one bot, with drift monitoring."""

    def __init__(self, store: DirectionalModelStore | None = None):
        self._store = store
        self._bull_model: Any = None
        self._bull_cal: Any = None
        self._bear_model: Any = None
        self._bear_cal: Any = None
        self._bull_drift: Any = None
        self._bear_drift: Any = None
        if store is not None:
            payload = store.load()
            if payload is not None:
                self._bull_model = payload.get("bull_model")
                self._bull_cal = payload.get("bull_cal")
                self._bear_model = payload.get("bear_model")
                self._bear_cal = payload.get("bear_cal")

    @property
    def is_earned(self) -> bool:
        return all(m is not None for m in (self._bull_model, self._bull_cal, self._bear_model, self._bear_cal))

    def _matrix(self, samples: list[DirectionalSample]):
        order = np.argsort([s.as_of_epoch for s in samples])
        x = np.array([[samples[i].features.get(k, 0.0) for k in DIRECTIONAL_FEATURE_NAMES] for i in order])
        y_up = np.array([samples[i].y_up for i in order], dtype=int)
        y_down = np.array([samples[i].y_down for i in order], dtype=int)
        return x, y_up, y_down

    def _train_one(self, x, y, params):
        """Walk-forward train + isotonic calibrate one directional model. Returns (model, calibrator, auc, shap)."""
        import lightgbm as lgb
        from sklearn.isotonic import IsotonicRegression
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import TimeSeriesSplit

        n = len(y)
        oof = np.full(n, np.nan)
        splits = TimeSeriesSplit(n_splits=min(5, max(_MIN_TIME_FOLDS, n // 100)))
        for tr, te in splits.split(x):
            if y[tr].sum() == 0 or y[tr].sum() == len(tr):
                continue
            fold = lgb.LGBMClassifier(**params)
            fold.fit(x[tr], y[tr])
            oof[te] = np.asarray(fold.predict_proba(x[te]))[:, 1]
        scored = ~np.isnan(oof)
        auc = (float(roc_auc_score(y[scored], oof[scored]))
               if scored.sum() > 0 and len(set(y[scored].tolist())) > 1 else None)
        model = lgb.LGBMClassifier(**params)
        model.fit(x, y)
        calibrator = IsotonicRegression(out_of_bounds="clip")
        if scored.sum() > 0 and len(set(y[scored].tolist())) > 1:
            calibrator.fit(oof[scored], y[scored])
        else:
            calibrator.fit(np.array([0.0, 1.0]), np.array([0.0, 1.0]))
        return model, calibrator, auc, self._shap(model, x)

    def _shap(self, model, x) -> tuple[tuple[str, float], ...]:
        try:
            import shap

            values = shap.TreeExplainer(model).shap_values(x)
            arr = values[1] if isinstance(values, list) else values
            mean_abs = np.abs(np.asarray(arr)).mean(axis=0).ravel()
            ranked = sorted(zip(DIRECTIONAL_FEATURE_NAMES, mean_abs, strict=False), key=lambda kv: -kv[1])
            return tuple((n, float(v)) for n, v in ranked[:6])
        except Exception:  # noqa: BLE001 — SHAP is auxiliary; its failure must not break training
            gains = getattr(model, "feature_importances_", np.zeros(len(DIRECTIONAL_FEATURE_NAMES)))
            ranked = sorted(zip(DIRECTIONAL_FEATURE_NAMES, gains, strict=False), key=lambda kv: -kv[1])
            return tuple((n, float(v)) for n, v in ranked[:6])

    def train(self, samples: list[DirectionalSample], now_ist: datetime | None = None) -> BullBearTrainingReport:
        stamp = (now_ist or datetime.now(_IST)).strftime("%Y-%m-%d %H:%M:%S IST")
        n = len(samples)
        n_up = sum(s.y_up for s in samples)
        n_down = sum(s.y_down for s in samples)
        if n < _MIN_SAMPLES_TO_TRAIN or n_up < _MIN_PER_CLASS or n_down < _MIN_PER_CLASS:
            report = BullBearTrainingReport(
                False, n, n_up, n_down, None, None, (), (),
                f"not earned: need ≥{_MIN_SAMPLES_TO_TRAIN} samples + ≥{_MIN_PER_CLASS} up & down events "
                f"(have {n}: {n_up}↑/{n_down}↓) — bot keeps its existing side (Rule Q/K)", stamp)
            if self._store is not None:
                self._store.append_ledger(report)
            return report

        x, y_up, y_down = self._matrix(samples)
        params: dict[str, Any] = {"objective": "binary", "n_estimators": 250, "num_leaves": 31,
                                  "max_depth": 4, "learning_rate": 0.03, "subsample": 0.8,
                                  "colsample_bytree": 0.8, "min_child_samples": 30, "verbosity": -1}
        self._bull_model, self._bull_cal, bull_auc, bull_shap = self._train_one(x, y_up, params)
        self._bear_model, self._bear_cal, bear_auc, bear_shap = self._train_one(x, y_down, params)
        if self._store is not None:
            self._store.save({"bull_model": self._bull_model, "bull_cal": self._bull_cal,
                              "bear_model": self._bear_model, "bear_cal": self._bear_cal,
                              "feature_names": list(DIRECTIONAL_FEATURE_NAMES), "trained_at": stamp})
        report = BullBearTrainingReport(
            True, n, n_up, n_down, bull_auc, bear_auc, bull_shap, bear_shap,
            f"walk-forward AUC bull={bull_auc} bear={bear_auc} on n={n}; small-fold optimism possible", stamp)
        if self._store is not None:
            self._store.append_ledger(report)
        return report

    def directional_view(self, features: dict[str, float]) -> DirectionalView:
        """Calibrated (P(up), P(down)) for the latest features; neutral 0.5/0.5 until earned (Rule Q)."""
        if not self.is_earned:
            return DirectionalView(0.5, 0.5, "gathering")
        x = np.array([[features.get(k, 0.0) for k in DIRECTIONAL_FEATURE_NAMES]])
        p_up = float(self._bull_cal.predict([float(self._bull_model.predict_proba(x)[0, 1])])[0])
        p_down = float(self._bear_cal.predict([float(self._bear_model.predict_proba(x)[0, 1])])[0])
        return DirectionalView(min(max(p_up, 0.0), 1.0), min(max(p_down, 0.0), 1.0), "earned")

    def observe_outcome(self, view: DirectionalView, went_up: bool) -> bool:
        """Feed a realised directional outcome to the ADWIN drift monitors; True on detected drift."""
        try:
            from river.drift import ADWIN
        except ImportError:
            return False
        if self._bull_drift is None:
            self._bull_drift, self._bear_drift = ADWIN(), ADWIN()
        self._bull_drift.update((1.0 - view.p_up) if went_up else view.p_up)
        self._bear_drift.update(view.p_down if went_up else (1.0 - view.p_down))
        return bool(getattr(self._bull_drift, "drift_detected", False)
                    or getattr(self._bear_drift, "drift_detected", False))
