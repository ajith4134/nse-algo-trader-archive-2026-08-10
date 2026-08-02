"""Tests for the ML win-probability ENGINE (Trunk IX PREDICTIVE-CORE, research/156).

Covers the feature pipeline (schema/zero-variance/encoding), the model on a synthetic SEPARABLE set
(real train→CV→AUC), the Kelly/edge sizing math + clamping, the performance-earned identity gate, and
the model-store round-trip. Uses small synthetic data so the ML path runs fast + deterministically.
"""

from datetime import datetime, timezone

import numpy as np

from nse_algo_trader.predictive_core.win_probability_engine import (
    WinProbabilityEngine,
    edge_size_multiplier,
    kelly_fraction,
)
from nse_algo_trader.predictive_core.win_probability_features import (
    build_inference_frame,
    build_training_frame,
)
from nse_algo_trader.predictive_core.win_probability_model import train_win_model
from nse_algo_trader.predictive_core.win_probability_model_store import (
    load_win_model,
    save_win_model,
)


def _record(mechanism, win, i):
    return {
        "mechanism_name": mechanism, "direction": "long" if i % 2 else "short",
        "instrument_kind": "CASH_EQUITY", "assigned_table": "confident_win" if win else "confident_loss",
        "strategy_tag": "orb_v1", "market_regime": "trend", "regime_context": "adx_high",
        "win_probability": 0.7 if win else 0.3, "occurred_at": f"2026-07-2{i%9}T10:{i%60:02d}:00",
        "realized_return_fraction": 0.02 if win else -0.02,
    }


# Synthetic SEPARABLE dataset: mechanism 'A' always wins, 'B' always loses → learnable.
SEP_RECORDS = ([_record("A", True, i) for i in range(24)] + [_record("B", False, i) for i in range(24)])


def test_feature_pipeline_schema_and_zero_variance_drop():
    X, y, schema = build_training_frame(SEP_RECORDS)
    assert len(y) == 48 and int(y.sum()) == 24
    # Constant columns (instrument_kind, market_regime, regime_context, strategy_tag) are dropped.
    assert "mechanism_name" in schema.categorical_features
    assert "instrument_kind" not in schema.feature_names       # zero-variance → dropped
    assert "win_probability" in schema.numeric_features


def test_inference_frame_matches_schema():
    _, _, schema = build_training_frame(SEP_RECORDS)
    row = build_inference_frame(
        {"mechanism_name": "A", "direction": "long", "win_probability": 0.7,
         "occurred_at": "2026-07-26T10:00:00"}, schema)
    assert list(row.columns) == list(schema.feature_names) and len(row) == 1


def test_model_learns_separable_signal():
    X, y, schema = build_training_frame(SEP_RECORDS)
    trained = train_win_model(X, y, schema)
    ev = trained.evaluation
    assert ev.auc is not None and ev.auc > 0.9            # a real generalization claim on a learnable set
    assert ev.cv_scheme in ("stratified-kfold", "walk-forward-by-session-date")
    # Calibrated probabilities are valid.
    p_a = float(trained.calibrated_model.predict_proba(
        build_inference_frame({"mechanism_name": "A", "win_probability": 0.7,
                               "occurred_at": "2026-07-26T10:00:00"}, schema))[:, 1][0])
    assert 0.0 <= p_a <= 1.0


def test_kelly_fraction_math():
    assert abs(kelly_fraction(0.6, 2.0) - 0.4) < 1e-9      # 0.6 − 0.4/2 = 0.4
    assert kelly_fraction(0.3, 2.0) < 0                    # no edge
    assert kelly_fraction(0.5, 0.0) == 0.0                 # guard bad reward:risk


def test_edge_multiplier_identity_until_earned_then_monotone_and_clamped():
    assert edge_size_multiplier(0.9, 2.0, is_earned=False) == 1.0   # advisory → identity
    lo = edge_size_multiplier(0.4, 2.0, is_earned=True)
    hi = edge_size_multiplier(0.8, 2.0, is_earned=True)
    assert 0.0 < lo <= hi <= 1.0                                    # monotone + clamped in [floor,1]
    assert edge_size_multiplier(0.05, 2.0, is_earned=True) >= 0.0   # no-edge → floor, never negative


def test_engine_performance_gate_is_identity_until_earned(tmp_path):
    engine = WinProbabilityEngine(model_path=tmp_path / "m.joblib")
    assert engine.train_from_records(SEP_RECORDS)
    # Regardless of earned/not, the multiplier is a valid, safe number in [0,1].
    m = engine.win_probability_size_multiplier(
        {"mechanism_name": "A", "win_probability": 0.7, "occurred_at": "2026-07-26T10:00:00"}, 2.0)
    assert 0.0 <= m <= 1.0
    if not engine.is_performance_earned:
        assert m == 1.0            # not earned → never moves a trade


def test_model_store_roundtrip(tmp_path):
    X, y, schema = build_training_frame(SEP_RECORDS)
    trained = train_win_model(X, y, schema)
    path = save_win_model(trained, tmp_path / "win.joblib")
    reloaded = load_win_model(path)
    assert reloaded is not None and reloaded.n_samples == trained.n_samples
    assert reloaded.evaluation.auc == trained.evaluation.auc
