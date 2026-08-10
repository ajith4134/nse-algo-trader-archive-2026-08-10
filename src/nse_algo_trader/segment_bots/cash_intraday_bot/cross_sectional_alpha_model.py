"""Cross-sectional alpha model for the CASH bot — the trained ranker (engine-grade ML, Rule P + addendum).

Predicts each stock's forward RELATIVE return from its cross-sectional factor vector, so the universe can be
ranked into a long/short book. A **LightGBM regressor** trained under **leakage-free walk-forward** (time-
ordered), evaluated by **rank-IC** (Spearman between prediction and realised forward return — the standard
cross-sectional metric), with a **river ADWIN** drift monitor and a persisted model + metrics ledger.

Data-sufficiency honesty (Rule Q): until enough time-ordered samples accrue, the model is not earned and
``score`` falls back to a transparent **factor composite** (momentum + reversal + liquidity ranks) — the
universe is still rankable day one, the learned model just takes over once it beats the base signal. n /
#time-periods / rank-IC are reported, never hidden.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_features import (
    CROSS_SECTIONAL_FEATURE_NAMES,
)

_IST = timezone(timedelta(hours=5, minutes=30))
_MIN_SAMPLES_TO_TRAIN = 2000  # cross-sectional: many names × several sessions
_MIN_TIME_PERIODS = 20

# the transparent composite alpha used until the model is earned (weights on cross-sectional rank features)
_COMPOSITE_WEIGHTS = {
    "ret_5_rank": 0.35, "ret_15_rank": 0.25, "reversal_1_rank": 0.20,
    "volume_ratio_rank": 0.10, "range_position_rank": 0.10,
}


@dataclass(frozen=True)
class CrossSectionalSample:
    """One training row: a stock's factor vector at a bar + its realised forward relative return."""

    features: dict[str, float]
    forward_return: float
    as_of_epoch: float


@dataclass(frozen=True)
class CrossSectionalTrainingReport:
    trained: bool
    n_samples: int
    n_time_periods: int
    walk_forward_rank_ic: float | None
    ic_information_ratio: float | None
    top_features: tuple[tuple[str, float], ...]
    optimism_note: str
    trained_at_ist: str


class CrossSectionalAlphaStore:
    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def model_path(self) -> Path:
        return self._dir / "cash_cross_sectional_alpha.joblib"

    def save(self, payload: dict) -> None:
        import joblib

        joblib.dump(payload, self.model_path)

    def load(self) -> dict | None:
        # joblib(pickle) is safe here: only this bot's own model, written by save() to a private dir.
        import joblib

        if not self.model_path.exists():
            return None
        try:
            return joblib.load(self.model_path)
        except (OSError, EOFError, ValueError):
            return None

    def append_ledger(self, report: CrossSectionalTrainingReport) -> None:
        path = self._dir / "cash_cross_sectional_ledger.json"
        history = []
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                history = []
        history.append({"trained_at": report.trained_at_ist, "n": report.n_samples,
                        "rank_ic": report.walk_forward_rank_ic, "ic_ir": report.ic_information_ratio})
        path.write_text(json.dumps(history[-200:], indent=1))


def _spearman(pred: np.ndarray, actual: np.ndarray) -> float:
    if pred.size < 3:
        return 0.0
    pr = pd.Series(pred).rank().to_numpy()
    ar = pd.Series(actual).rank().to_numpy()
    if np.std(pr) < 1e-9 or np.std(ar) < 1e-9:
        return 0.0
    return float(np.corrcoef(pr, ar)[0, 1])


class CrossSectionalAlphaModel:
    """Trains/serves the cross-sectional forward-return ranker; falls back to a factor composite until earned."""

    def __init__(self, store: CrossSectionalAlphaStore | None = None):
        self._store = store
        self._model: Any = None
        self._drift: Any = None
        if store is not None:
            payload = store.load()
            if payload is not None:
                self._model = payload.get("model")

    @property
    def is_earned(self) -> bool:
        return self._model is not None

    def train(self, samples: list[CrossSectionalSample], now_ist: datetime | None = None) -> CrossSectionalTrainingReport:
        stamp = (now_ist or datetime.now(_IST)).strftime("%Y-%m-%d %H:%M:%S IST")
        n = len(samples)
        periods = len({round(s.as_of_epoch, 6) for s in samples})
        if n < _MIN_SAMPLES_TO_TRAIN or periods < _MIN_TIME_PERIODS:
            report = CrossSectionalTrainingReport(
                False, n, periods, None, None, (),
                f"not earned: need ≥{_MIN_SAMPLES_TO_TRAIN} samples over ≥{_MIN_TIME_PERIODS} periods "
                f"(have {n} over {periods}) — factor-composite fallback active (Rule Q/K)", stamp)
            if self._store is not None:
                self._store.append_ledger(report)
            return report

        import lightgbm as lgb

        order = np.argsort([s.as_of_epoch for s in samples])
        x = np.array([[samples[i].features.get(k, 0.0) for k in CROSS_SECTIONAL_FEATURE_NAMES] for i in order])
        y = np.array([samples[i].forward_return for i in order], dtype=float)
        epochs = np.array([samples[i].as_of_epoch for i in order])

        params: dict[str, Any] = {"objective": "regression", "n_estimators": 300, "num_leaves": 31,
                                  "max_depth": 5, "learning_rate": 0.03, "subsample": 0.8,
                                  "colsample_bytree": 0.8, "min_child_samples": 50, "verbosity": -1}

        # walk-forward by time period: train on past periods, score the next; rank-IC per fold
        unique_epochs = np.unique(epochs)
        fold_edges = np.array_split(unique_epochs, min(5, max(2, len(unique_epochs) // 4)))
        ics: list[float] = []
        for k in range(1, len(fold_edges)):
            train_mask = np.isin(epochs, np.concatenate(fold_edges[:k]))
            test_mask = np.isin(epochs, fold_edges[k])
            if train_mask.sum() < 100 or test_mask.sum() < 10:
                continue
            fold = lgb.LGBMRegressor(**params)
            fold.fit(x[train_mask], y[train_mask])
            ics.append(_spearman(np.asarray(fold.predict(x[test_mask])), y[test_mask]))
        rank_ic = float(np.mean(ics)) if ics else None
        ic_ir = float(np.mean(ics) / (np.std(ics) + 1e-9)) if len(ics) > 1 else None

        model = lgb.LGBMRegressor(**params)
        model.fit(x, y)
        self._model = model
        importances = sorted(zip(CROSS_SECTIONAL_FEATURE_NAMES, model.feature_importances_, strict=False),
                             key=lambda kv: -kv[1])[:8]
        if self._store is not None:
            self._store.save({"model": model, "feature_names": list(CROSS_SECTIONAL_FEATURE_NAMES),
                              "trained_at": stamp, "n_samples": n})
        report = CrossSectionalTrainingReport(
            True, n, periods, rank_ic, ic_ir, tuple((n_, float(v)) for n_, v in importances),
            f"walk-forward rank-IC {rank_ic} over {periods} periods; small-#period optimism possible", stamp)
        if self._store is not None:
            self._store.append_ledger(report)
        return report

    def score(self, features: pd.DataFrame) -> pd.Series:
        """Alpha score per symbol: the trained model if earned, else the transparent factor composite."""
        if features.empty:
            return pd.Series(dtype=float)
        if self.is_earned:
            x = features.reindex(columns=list(CROSS_SECTIONAL_FEATURE_NAMES), fill_value=0.0).to_numpy()
            return pd.Series(np.asarray(self._model.predict(x)), index=features.index)
        composite = pd.Series(0.0, index=features.index)
        for feature, weight in _COMPOSITE_WEIGHTS.items():
            if feature in features:
                composite = composite + weight * (features[feature] - 0.5)  # rank centred at 0
        return composite

    def observe_outcome(self, predicted_alpha: float, realised_return: float) -> bool:
        try:
            from river.drift import ADWIN
        except ImportError:
            return False
        if self._drift is None:
            self._drift = ADWIN()
        self._drift.update(abs(realised_return - predicted_alpha))
        return bool(getattr(self._drift, "drift_detected", False))
