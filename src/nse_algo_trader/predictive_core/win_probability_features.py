"""Feature engineering for the ML win-probability engine (Trunk IX PREDICTIVE-CORE; research/156). PURE.

Turns raw `experience_nodes` records into a modelling frame (X, y) plus a `FeatureSchema` that is CARRIED
into inference so training and serving encode categories identically (the train/serve-skew guard that a
scalar diagnostic never needs). Categorical features become pandas `category` dtype (LightGBM's native
categorical handling); numeric features are coerced + imputed; zero-variance columns are dropped so the
model never learns from a constant. Target: win = realized_return_fraction > 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

# Raw experience-node columns used as features, by role.
_CATEGORICAL_COLUMNS = (
    "mechanism_name", "direction", "instrument_kind", "assigned_table", "strategy_tag",
    "market_regime", "regime_context",
)
_NUMERIC_PASSTHROUGH = ("win_probability",)  # the prior (fixed-formula) estimate = a strong baseline feature
_TARGET_COLUMN = "realized_return_fraction"
_TIME_COLUMN = "occurred_at"


@dataclass(frozen=True)
class FeatureSchema:
    """The exact feature contract carried from training into inference (train/serve-skew guard)."""

    feature_names: tuple                    # ordered feature columns the model expects
    categorical_features: tuple             # subset that are categorical
    numeric_features: tuple                 # subset that are numeric
    category_levels: dict = field(default_factory=dict)  # name -> ordered category vocabulary


def _hour_of_day(value) -> float:
    dt = _parse_dt(value)
    return float(dt.hour + dt.minute / 60.0) if dt is not None else float("nan")


def _day_of_week(value) -> float:
    dt = _parse_dt(value)
    return float(dt.weekday()) if dt is not None else float("nan")


def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _engineer_rows(records) -> pd.DataFrame:
    """Raw node dicts → an engineered DataFrame (categoricals + numerics + derived time features)."""
    rows = []
    for r in records:
        row: dict = {}
        for col in _CATEGORICAL_COLUMNS:
            value = r.get(col)
            row[col] = None if value in (None, "") else str(value)
        for col in _NUMERIC_PASSTHROUGH:
            row[col] = pd.to_numeric(r.get(col), errors="coerce")
        row["hour_of_day"] = _hour_of_day(r.get(_TIME_COLUMN))
        row["day_of_week"] = _day_of_week(r.get(_TIME_COLUMN))
        rows.append(row)
    return pd.DataFrame(rows)


def build_training_frame(records):
    """Raw experience records → (X: DataFrame, y: Series[int], schema: FeatureSchema).

    Drops zero-variance columns; encodes categoricals as `category` dtype; imputes numeric NaNs with the
    column median (a fitted value recorded in the schema is overkill here — median is stable + carried
    implicitly by refitting each train). Only records with a defined realized return are usable."""
    usable = [r for r in records if pd.to_numeric(r.get(_TARGET_COLUMN), errors="coerce") == r.get(_TARGET_COLUMN)
              and r.get(_TARGET_COLUMN) is not None]
    frame = _engineer_rows(usable)
    target = pd.Series([1 if float(r[_TARGET_COLUMN]) > 0 else 0 for r in usable], name="win")

    categorical, numeric, levels = [], [], {}
    engineered_categorical = list(_CATEGORICAL_COLUMNS)
    engineered_numeric = list(_NUMERIC_PASSTHROUGH) + ["hour_of_day", "day_of_week"]

    for col in engineered_categorical:
        if col not in frame or frame[col].nunique(dropna=True) < 2:
            continue  # zero-variance / all-missing → drop (never learn from a constant)
        cats = sorted(v for v in frame[col].dropna().unique())
        frame[col] = pd.Categorical(frame[col], categories=cats)
        categorical.append(col)
        levels[col] = tuple(cats)

    for col in engineered_numeric:
        if col not in frame or frame[col].notna().sum() == 0 or frame[col].nunique(dropna=True) < 2:
            continue
        median = frame[col].median()
        frame[col] = frame[col].fillna(median).astype(float)
        numeric.append(col)

    feature_names = tuple(categorical + numeric)
    schema = FeatureSchema(
        feature_names=feature_names, categorical_features=tuple(categorical),
        numeric_features=tuple(numeric), category_levels=levels)
    return frame[list(feature_names)], target, schema


def build_inference_frame(feature_values: dict, schema: FeatureSchema) -> pd.DataFrame:
    """One candidate's raw feature values → a 1-row frame encoded to the SAME schema as training.

    Unseen categorical values become NaN (LightGBM routes them as missing); missing numerics → NaN
    (the trained model's default direction handles them). This is the train/serve contract."""
    engineered = _engineer_rows([feature_values])
    row = {}
    for col in schema.categorical_features:
        row[col] = pd.Categorical(engineered[col], categories=list(schema.category_levels.get(col, ())))
    for col in schema.numeric_features:
        row[col] = pd.to_numeric(engineered[col], errors="coerce").astype(float)
    return pd.DataFrame(row)[list(schema.feature_names)]
