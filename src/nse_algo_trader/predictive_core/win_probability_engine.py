"""The ML win-probability ENGINE (Trunk IX PREDICTIVE-CORE; research/156).

Orchestrates the model lifecycle — train → cross-validated evaluate → persist (carried state) → serve —
and turns the calibrated P(win) into a DECISION-GRADE output: a fractional-Kelly position-size multiplier
applied at the entry sites. The engine ACTS (moves size) only once it has EARNED it — i.e. the trained
model beats the incumbent fixed-formula baseline on held-out (cross-validated) log-loss. That earning is
computed on REAL data NOW (not market-gated); accruing more trading DAYS to strengthen it is the one open
data blocker (research/156 §4). Composes the feature pipeline + model core + model store.
"""

from __future__ import annotations

from nse_algo_trader.predictive_core.win_probability_features import (
    build_inference_frame,
    build_training_frame,
)
from nse_algo_trader.predictive_core.win_probability_model import (
    TrainedWinModel,
    WinModelHyperparameters,
    predict_win_probability,
    train_win_model,
)
from nse_algo_trader.predictive_core.win_probability_model_store import (
    DEFAULT_WIN_MODEL_PATH,
    load_win_model,
    save_win_model,
)

# The edge below which we treat the model as giving no actionable advantage (defer to base sizing).
_MIN_ACTIONABLE_KELLY = 0.0
# The Kelly fraction at/above which the engine grants FULL size; between floor and this it scales up.
_FULL_SIZE_KELLY = 0.25
# Fractional-Kelly safety factor (never bet full Kelly).
_KELLY_FRACTION = 0.5
# Size multiplier floor when the edge is absent/negative (size-down-only — never breaches risk policy).
_SIZE_FLOOR = 0.25


def kelly_fraction(win_probability: float, reward_risk: float) -> float:
    """Kelly-optimal fraction for a bet that wins `reward_risk` units w.p. p and loses 1 w.p. (1-p):
        f* = p − (1−p)/b.  Negative when there is no edge."""
    if reward_risk <= 0:
        return 0.0
    p = min(1.0, max(0.0, win_probability))
    return p - (1.0 - p) / reward_risk


def edge_size_multiplier(win_probability: float, reward_risk: float, is_earned: bool) -> float:
    """Decision-grade output: a position-size multiplier in [floor, 1.0] from the model's edge.

    Identity (1.0) until the engine is performance-EARNED — an unvalidated model never moves a trade.
    Once earned: a fractional-Kelly edge at/above `_FULL_SIZE_KELLY` → full size (1.0); no edge → the
    floor; linear between. Size-DOWN-only, so it never increases risk beyond the risk gate's approval."""
    if not is_earned:
        return 1.0
    f = _KELLY_FRACTION * kelly_fraction(win_probability, reward_risk)
    if f <= _MIN_ACTIONABLE_KELLY:
        return _SIZE_FLOOR
    if f >= _FULL_SIZE_KELLY:
        return 1.0
    return _SIZE_FLOOR + (1.0 - _SIZE_FLOOR) * (f - _MIN_ACTIONABLE_KELLY) / (_FULL_SIZE_KELLY - _MIN_ACTIONABLE_KELLY)


class WinProbabilityEngine:
    """Trains/loads the win-probability model and serves calibrated probabilities + size multipliers."""

    def __init__(self, model_path=DEFAULT_WIN_MODEL_PATH,
                 hyperparams: WinModelHyperparameters = WinModelHyperparameters()):
        self._model_path = model_path
        self._hyperparams = hyperparams
        self._trained: TrainedWinModel | None = None

    # -- lifecycle -----------------------------------------------------------------------------------
    def train_from_records(self, records) -> bool:
        """Build features → train + evaluate → persist. Returns True on a successful fit."""
        X, y, schema = build_training_frame(records)
        if len(y) == 0 or y.nunique() < 2:
            return False  # can't train a classifier without both classes
        time_groups = [r.get("session_date") for r in records
                       if r.get("realized_return_fraction") is not None]
        self._trained = train_win_model(X, y, schema, self._hyperparams, time_groups=time_groups)
        save_win_model(self._trained, self._model_path)
        return True

    def load(self) -> bool:
        self._trained = load_win_model(self._model_path)
        return self._trained is not None

    def load_or_train(self, records) -> bool:
        return self.load() or self.train_from_records(records)

    # -- serving -------------------------------------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        return self._trained is not None

    @property
    def is_performance_earned(self) -> bool:
        """The acting gate: True only when the trained model beat the baseline on held-out CV log-loss."""
        return bool(self._trained and self._trained.evaluation and self._trained.evaluation.beats_baseline)

    @property
    def evaluation(self):
        return self._trained.evaluation if self._trained else None

    def predict_win_probability(self, feature_values: dict) -> float | None:
        """Calibrated P(win) for a candidate (dict of raw feature values), or None when no model."""
        if not self._trained:
            return None
        X_row = build_inference_frame(feature_values, self._trained.schema)
        return predict_win_probability(self._trained, X_row)

    def win_probability_size_multiplier(self, feature_values: dict, reward_risk: float) -> float:
        """The decision-grade size multiplier for a candidate: identity until earned, else edge-scaled."""
        if not self.is_performance_earned:
            return 1.0
        p = self.predict_win_probability(feature_values)
        if p is None:
            return 1.0
        return edge_size_multiplier(p, reward_risk, is_earned=True)


def feature_values_from_prediction_record(prediction_record, direction: str, instrument_kind: str,
                                          now) -> dict:
    """Build the engine's feature dict for a LIVE candidate from its prediction record + context, matching
    the training feature names (the prior win_probability, mechanism, table, tags, direction, kind, time).
    Categorical values not seen at train time route as missing in LightGBM — safe (research/156)."""
    assigned = getattr(prediction_record, "assigned_table", None)
    return {
        "mechanism_name": getattr(prediction_record, "mechanism_name", None),
        "strategy_tag": getattr(prediction_record, "strategy_tag", None),
        "assigned_table": getattr(assigned, "value", assigned),
        "win_probability": getattr(prediction_record, "win_probability", None),
        "direction": direction,
        "instrument_kind": instrument_kind,
        "occurred_at": now.isoformat() if hasattr(now, "isoformat") else now,
        "market_regime": None,
        "regime_context": None,
    }
