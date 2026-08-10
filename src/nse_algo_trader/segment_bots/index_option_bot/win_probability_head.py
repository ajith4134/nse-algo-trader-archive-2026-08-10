"""INDEX-OPTION learned win-probability head — the bot's trained model (engine-grade ML, Rule P + addendum).

A real trained model, not a scalar: it engineers a feature vector from the vol-regime + IV-surface +
structure state, trains a **LightGBM** classifier under **leakage-free walk-forward (time-ordered) CV**,
**isotonically calibrates** the raw scores (GBDTs are miscalibrated), computes **SHAP** attributions for
auditability, and runs a **river ADWIN** drift monitor on the realised-outcome stream. Carried STATE = the
persisted model + calibrator + a metrics ledger (AUC/Brier over time, trained-at, data window, feature
names) via ``WinProbabilityHeadStore``.

Data-sufficiency honesty (Rule Q/K): the head trains only once enough LABELLED trials have accrued from the
deterministic policy's proposals; until then it is not "earned" and the caller keeps the deterministic
policy's transparent probability. The engine ships COMPLETE; the labelled-trial accrual is the one
permissible open blocker, and n / class-balance / optimism are reported, never hidden.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

_IST = timezone(timedelta(hours=5, minutes=30))
_MIN_LABELLED_TRIALS_TO_TRAIN = 200  # below this the head is not earned (deterministic passthrough)
_MIN_PER_CLASS = 20  # need both wins and losses represented

# the engineered feature vector (names are the SHAP/audit contract — order matters)
FEATURE_NAMES: tuple[str, ...] = (
    "blended_forecast_sigma",
    "realized_vol",
    "variance_risk_premium",
    "regime_stressed_prob",
    "garch_minus_har",
    "atm_iv",
    "iv_rank",
    "risk_reversal_25d",
    "term_structure_slope",
    "structure_net_theta",
    "structure_net_vega",
    "structure_is_defined_risk",
    "selector_conviction",
)


@dataclass(frozen=True)
class LabelledTrial:
    """One accrued training example: the feature vector at entry + the realised binary outcome."""

    features: dict[str, float]
    won: bool
    entry_epoch: float  # for time-ordered (leakage-free) splitting


@dataclass(frozen=True)
class TrainingReport:
    """The honest outcome of a training run — surfaced, never hidden (Rule K/O)."""

    trained: bool
    n_samples: int
    n_wins: int
    n_losses: int
    walk_forward_auc: float | None
    walk_forward_brier: float | None
    base_rate: float | None
    top_features: tuple[tuple[str, float], ...]  # (name, mean|SHAP|) descending
    optimism_note: str
    trained_at_ist: str


def engineer_features(regime, surface, decision) -> dict[str, float]:
    """Build the named feature vector from the three upstream states. Missing values → neutral, not silent."""

    stressed = 0.0
    if getattr(regime, "maturity", "") == "earned" and len(regime.regime_probabilities) >= 2:
        stressed = float(regime.regime_probabilities[-1])
    return {
        "blended_forecast_sigma": float(regime.blended_forecast_sigma),
        "realized_vol": float(regime.realized_vol),
        "variance_risk_premium": float(regime.variance_risk_premium or 0.0),
        "regime_stressed_prob": stressed,
        "garch_minus_har": float(regime.garch_forecast_sigma - regime.har_forecast_sigma),
        "atm_iv": float(surface.nearest_atm_iv),
        "iv_rank": float(surface.iv_rank if surface.iv_rank is not None else 0.5),
        "risk_reversal_25d": float(surface.risk_reversal_25d),
        "term_structure_slope": float(surface.term_structure_slope),
        "structure_net_theta": float(decision.plan.net_theta),
        "structure_net_vega": float(decision.plan.net_vega),
        "structure_is_defined_risk": 1.0 if decision.plan.is_defined_risk else 0.0,
        "selector_conviction": float(decision.conviction),
    }


class WinProbabilityHeadStore:
    """Persists the trained model + calibrator + metrics ledger (carried state)."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def model_path(self) -> Path:
        return self._dir / "index_option_win_prob_head.joblib"

    @property
    def ledger_path(self) -> Path:
        return self._dir / "index_option_win_prob_ledger.json"

    def save_model(self, payload: dict) -> None:
        import joblib

        joblib.dump(payload, self.model_path)

    def load_model(self) -> dict | None:
        # joblib(pickle) is safe here: the payload is ONLY this bot's own model, written by save_model to a
        # private store dir under the process owner — never external/untrusted input (no RCE surface).
        import joblib

        if not self.model_path.exists():
            return None
        try:
            return joblib.load(self.model_path)
        except (OSError, EOFError, ValueError):
            return None

    def append_ledger(self, report: TrainingReport) -> None:
        history = []
        if self.ledger_path.exists():
            try:
                history = json.loads(self.ledger_path.read_text())
            except (json.JSONDecodeError, OSError):
                history = []
        history.append(
            {
                "trained_at": report.trained_at_ist,
                "n_samples": report.n_samples,
                "auc": report.walk_forward_auc,
                "brier": report.walk_forward_brier,
                "base_rate": report.base_rate,
            }
        )
        self.ledger_path.write_text(json.dumps(history[-200:], indent=1))


class IndexOptionWinProbabilityHead:
    """Trains/serves the calibrated win-probability model; monitors drift on realised outcomes."""

    def __init__(self, store: WinProbabilityHeadStore | None = None):
        self._store = store
        self._model: Any = None  # LightGBM classifier
        self._calibrator: Any = None  # isotonic map raw→calibrated
        self._drift: Any = None  # river ADWIN
        self._feature_names: tuple[str, ...] = FEATURE_NAMES
        if store is not None:
            payload = store.load_model()
            if payload is not None:
                self._model = payload.get("model")
                self._calibrator = payload.get("calibrator")
                self._feature_names = tuple(payload.get("feature_names", FEATURE_NAMES))

    @property
    def is_earned(self) -> bool:
        return self._model is not None and self._calibrator is not None

    def _matrix(self, trials: list[LabelledTrial]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        x = np.array([[t.features.get(n, 0.0) for n in FEATURE_NAMES] for t in trials], dtype=float)
        y = np.array([1 if t.won else 0 for t in trials], dtype=int)
        order = np.argsort([t.entry_epoch for t in trials])  # time order for leakage-free CV
        return x[order], y[order], order

    def train(self, trials: list[LabelledTrial], now_ist: datetime | None = None) -> TrainingReport:
        """Walk-forward train + isotonic-calibrate on time-ordered labelled trials. Honest report always."""

        stamp = (now_ist or datetime.now(_IST)).strftime("%Y-%m-%d %H:%M:%S IST")
        n = len(trials)
        n_wins = sum(1 for t in trials if t.won)
        n_losses = n - n_wins
        base_rate = (n_wins / n) if n else None

        if n < _MIN_LABELLED_TRIALS_TO_TRAIN or n_wins < _MIN_PER_CLASS or n_losses < _MIN_PER_CLASS:
            report = TrainingReport(
                False, n, n_wins, n_losses, None, None, base_rate, (),
                f"not earned: need ≥{_MIN_LABELLED_TRIALS_TO_TRAIN} trials + ≥{_MIN_PER_CLASS}/class "
                f"(have {n}, {n_wins}W/{n_losses}L) — deterministic passthrough active (Rule Q/K)",
                stamp,
            )
            if self._store is not None:
                self._store.append_ledger(report)
            return report

        import lightgbm as lgb
        from sklearn.isotonic import IsotonicRegression
        from sklearn.metrics import brier_score_loss, roc_auc_score
        from sklearn.model_selection import TimeSeriesSplit

        x, y, _ = self._matrix(trials)
        # size-adaptive params (more leaves/depth only with more data) — no blind hardcoding
        params: dict[str, Any] = {
            "objective": "binary",
            "n_estimators": 200,
            "num_leaves": 15 if n < 600 else 31,
            "max_depth": 3 if n < 600 else 5,
            "learning_rate": 0.03,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": max(10, n // 50),
            "verbosity": -1,
        }

        # walk-forward evaluation: train on the past, score the future fold; NEVER shuffle across time
        splits = TimeSeriesSplit(n_splits=min(5, max(2, n // 60)))
        oof_prob = np.full(n, np.nan)
        for train_idx, test_idx in splits.split(x):
            fold = lgb.LGBMClassifier(**params)
            fold.fit(x[train_idx], y[train_idx])
            oof_prob[test_idx] = np.asarray(fold.predict_proba(x[test_idx]))[:, 1]
        scored = ~np.isnan(oof_prob)
        wf_auc = float(roc_auc_score(y[scored], oof_prob[scored])) if len(set(y[scored].tolist())) > 1 else None
        wf_brier = float(brier_score_loss(y[scored], oof_prob[scored]))

        # final model on all data + isotonic calibration of its scores (calibrated on the OOF preds)
        model = lgb.LGBMClassifier(**params)
        model.fit(x, y)
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(oof_prob[scored], y[scored])

        top_features = self._shap_importances(model, x)
        self._model, self._calibrator = model, calibrator
        if self._store is not None:
            self._store.save_model(
                {"model": model, "calibrator": calibrator, "feature_names": list(FEATURE_NAMES),
                 "trained_at": stamp, "n_samples": n}
            )
        report = TrainingReport(
            True, n, n_wins, n_losses, wf_auc, wf_brier, base_rate, top_features,
            f"walk-forward AUC {wf_auc} on n={n}; small-sample optimism possible if #time-folds low",
            stamp,
        )
        if self._store is not None:
            self._store.append_ledger(report)
        return report

    def _shap_importances(self, model, x: np.ndarray) -> tuple[tuple[str, float], ...]:
        try:
            import shap

            explainer = shap.TreeExplainer(model)
            values = explainer.shap_values(x)
            arr = values[1] if isinstance(values, list) else values
            mean_abs = np.abs(np.asarray(arr)).mean(axis=0).ravel()
            ranked = sorted(zip(FEATURE_NAMES, mean_abs, strict=False), key=lambda kv: -kv[1])
            return tuple((name, float(v)) for name, v in ranked[:8])
        except Exception:  # noqa: BLE001 — SHAP is auxiliary; its failure must not break training
            gains = getattr(model, "feature_importances_", np.zeros(len(FEATURE_NAMES)))
            ranked = sorted(zip(FEATURE_NAMES, gains, strict=False), key=lambda kv: -kv[1])
            return tuple((name, float(v)) for name, v in ranked[:8])

    def calibrated_win_probability(self, features: dict[str, float]) -> float | None:
        """Calibrated P(win) from the trained model, or None when not earned (caller uses deterministic)."""
        if not self.is_earned:
            return None
        x = np.array([[features.get(n, 0.0) for n in self._feature_names]], dtype=float)
        raw = float(self._model.predict_proba(x)[0, 1])
        calibrated = float(self._calibrator.predict([raw])[0])
        return float(min(max(calibrated, 0.01), 0.99))

    def observe_outcome(self, predicted_prob: float, won: bool) -> bool:
        """Feed a realised outcome to the ADWIN drift monitor; returns True on a detected drift (retrain)."""
        try:
            from river.drift import ADWIN
        except ImportError:
            return False
        if self._drift is None:
            self._drift = ADWIN()
        loss = (1.0 - predicted_prob) if won else predicted_prob  # calibration loss stream
        self._drift.update(loss)
        return bool(getattr(self._drift, "drift_detected", False))
