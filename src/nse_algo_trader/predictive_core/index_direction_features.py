"""Feature engineering for the A3 trending-index DIRECTION model (B35; docs/research/177). PURE.

Turns raw intraday INDEX bars + the index's ATM-IV context into a supervised modelling frame
(X, y, time_groups) for a LightGBM classifier P(next-horizon move is UP), plus a `DirectionFeatureSchema`
carried unchanged into inference (the train/serve-skew guard). Reuses the repo's real indicators —
Yang-Zhang realized vol, ADX/±DI, IV-rank, BS IV — rather than reimplementing lite versions (Rule I/O).

Why these features (b18 A3): the variance-risk-premium (ATM IV − realized vol) is the documented
index-option edge; ADX/±DI give trend strength + side; IV-rank the premium richness; intraday range
position + minutes-to-close encode the forced square-off horizon. The label is the SIGN of the forward
`horizon`-bar return — no look-ahead: only bars strictly before t enter the features, the label uses
the realized future that (in training data) has already happened, and folds split by SESSION DATE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from nse_algo_trader.indicators import (
    compute_average_directional_index,
    compute_implied_volatility_rank,
    compute_yang_zhang_realized_volatility,
)

#: 5-minute bars → ~75/session × 252 sessions. Used only to put per-bar Yang-Zhang RV on the same
#: (annualised) scale as ATM IV so their difference (VRP) is meaningful; the model is scale-robust
#: regardless, but a comparable VRP is a better feature.
_BARS_PER_YEAR = 75 * 252
#: minimum trailing bars before a row is emitted — ADX needs > its period, YZ needs its own minimum.
_MIN_TRAILING_BARS = 30
#: default forward horizon (bars) the direction is predicted over — ~30 min on 5-min bars, well inside
#: the intraday square-off window.
DEFAULT_FORWARD_HORIZON_BARS = 6

_NUMERIC_FEATURES = (
    "ret_1", "ret_3", "ret_6", "adx", "di_spread", "yz_rv_annual", "atm_iv", "vrp",
    "iv_rank", "range_position", "dist_from_open", "minutes_to_close", "hour_of_day",
)
_CATEGORICAL_FEATURES = ("index_symbol",)


@dataclass(frozen=True)
class DirectionFeatureSchema:
    """The exact feature contract carried from training into inference (train/serve-skew guard)."""

    feature_names: tuple
    categorical_features: tuple
    numeric_features: tuple
    category_levels: dict = field(default_factory=dict)
    forward_horizon_bars: int = DEFAULT_FORWARD_HORIZON_BARS


@dataclass(frozen=True)
class IndexDirectionSession:
    """One index's intraday session: the ordered 5-min bars + the day's ATM IV and the trailing IV
    history (older daily ATM IVs) for IV-rank. `iv_rank_eligible` is False for the four monthly-only
    indices until ~Sept 2026 (b18 hard constraint — a 252-day IV lookback spans the weekly→monthly
    structural break); when False the IV-rank feature abstains (NaN) rather than emit a fake rank."""

    index_symbol: str
    bars: list
    atm_iv: float | None = None
    iv_history: tuple = ()
    iv_rank_eligible: bool = True


def _log_return(later: float, earlier: float) -> float:
    if later is None or earlier is None or later <= 0 or earlier <= 0:
        return float("nan")
    return math.log(later / earlier)


def engineer_direction_features(
    trailing_bars: list, session: IndexDirectionSession, as_of_index: int
) -> dict:
    """Raw trailing bars (strictly up to and including index `as_of_index`) → one feature row.

    Uses ONLY information available at bar `as_of_index` — no look-ahead. Shared by training (called
    per t) and live inference (called once at the current bar), so the encoding is identical."""
    window = trailing_bars[: as_of_index + 1]
    bar = window[-1]
    day_bars = [b for b in window if b.timestamp.date() == bar.timestamp.date()]

    closes = [b.close_price for b in window]
    ret_1 = _log_return(closes[-1], closes[-2]) if len(closes) >= 2 else float("nan")
    ret_3 = _log_return(closes[-1], closes[-4]) if len(closes) >= 4 else float("nan")
    ret_6 = _log_return(closes[-1], closes[-7]) if len(closes) >= 7 else float("nan")

    adx_series = compute_average_directional_index(window)
    adx = adx_series.adx[-1]
    plus_di = adx_series.plus_directional_indicator[-1]
    minus_di = adx_series.minus_directional_indicator[-1]
    di_spread = (
        (plus_di - minus_di) if (plus_di is not None and minus_di is not None) else float("nan")
    )

    yz_rv = compute_yang_zhang_realized_volatility(window)
    yz_rv_annual = yz_rv * math.sqrt(_BARS_PER_YEAR) if yz_rv is not None else float("nan")
    atm_iv = session.atm_iv if session.atm_iv is not None else float("nan")
    vrp = (atm_iv - yz_rv_annual) if (session.atm_iv is not None and yz_rv is not None) else float("nan")

    iv_rank = float("nan")
    if session.iv_rank_eligible and session.atm_iv is not None and len(session.iv_history) >= 2:
        rank = compute_implied_volatility_rank(session.atm_iv, list(session.iv_history))
        iv_rank = rank if rank is not None else float("nan")

    day_high = max((b.high_price for b in day_bars), default=bar.high_price)
    day_low = min((b.low_price for b in day_bars), default=bar.low_price)
    day_open = day_bars[0].open_price if day_bars else bar.open_price
    range_position = (
        (bar.close_price - day_low) / (day_high - day_low) if day_high > day_low else float("nan")
    )
    dist_from_open = (bar.close_price - day_open) / day_open if day_open else float("nan")

    close_dt = bar.timestamp.replace(hour=15, minute=30, second=0, microsecond=0)
    minutes_to_close = max(0.0, (close_dt - bar.timestamp).total_seconds() / 60.0)
    hour_of_day = bar.timestamp.hour + bar.timestamp.minute / 60.0

    return {
        "index_symbol": session.index_symbol,
        "ret_1": ret_1, "ret_3": ret_3, "ret_6": ret_6,
        "adx": adx if adx is not None else float("nan"),
        "di_spread": di_spread,
        "yz_rv_annual": yz_rv_annual, "atm_iv": atm_iv, "vrp": vrp, "iv_rank": iv_rank,
        "range_position": range_position, "dist_from_open": dist_from_open,
        "minutes_to_close": minutes_to_close, "hour_of_day": hour_of_day,
    }


def _forward_direction_label(bars: list, as_of_index: int, horizon: int) -> int | None:
    """1 if the close `horizon` bars ahead is higher than now, 0 if lower, None if flat/out-of-range or
    the forward bar crosses into a new session (no overnight look-ahead — intraday only)."""
    future_index = as_of_index + horizon
    if future_index >= len(bars):
        return None
    now_bar, future_bar = bars[as_of_index], bars[future_index]
    if future_bar.timestamp.date() != now_bar.timestamp.date():
        return None  # would peek across the square-off boundary
    if future_bar.close_price == now_bar.close_price:
        return None
    return 1 if future_bar.close_price > now_bar.close_price else 0


def build_direction_training_frame(
    sessions: list, horizon: int = DEFAULT_FORWARD_HORIZON_BARS
):
    """List[IndexDirectionSession] → (X: DataFrame, y: Series[int], time_groups: list[date],
    schema). One row per (index, bar t) with ≥ `_MIN_TRAILING_BARS` trailing bars and a defined
    forward label. `time_groups` = session date, so the model's walk-forward CV never trains on a
    future session (leakage-free)."""
    rows: list[dict] = []
    labels: list[int] = []
    groups: list = []
    for session in sessions:
        bars = session.bars
        for t in range(_MIN_TRAILING_BARS - 1, len(bars)):
            label = _forward_direction_label(bars, t, horizon)
            if label is None:
                continue
            rows.append(engineer_direction_features(bars, session, t))
            labels.append(label)
            groups.append(bars[t].timestamp.date())

    frame = pd.DataFrame(rows)
    schema = _fit_schema(frame, horizon)
    if not schema.feature_names:
        return frame, pd.Series(labels, name="up", dtype=int), groups, schema
    return frame[list(schema.feature_names)], pd.Series(labels, name="up", dtype=int), groups, schema


def _fit_schema(frame: pd.DataFrame, horizon: int) -> DirectionFeatureSchema:
    """Encode categoricals as `category` dtype, keep informative numerics, drop zero-variance columns
    (never learn from a constant). Numeric NaNs are imputed with the column median."""
    categorical, numeric, levels = [], [], {}
    for col in _CATEGORICAL_FEATURES:
        if col not in frame or frame[col].nunique(dropna=True) < 2:
            continue
        cats = sorted(v for v in frame[col].dropna().unique())
        frame[col] = pd.Categorical(frame[col], categories=cats)
        categorical.append(col)
        levels[col] = tuple(cats)
    for col in _NUMERIC_FEATURES:
        if col not in frame or frame[col].notna().sum() == 0 or frame[col].nunique(dropna=True) < 2:
            continue
        frame[col] = frame[col].fillna(frame[col].median()).astype(float)
        numeric.append(col)
    return DirectionFeatureSchema(
        feature_names=tuple(categorical + numeric),
        categorical_features=tuple(categorical), numeric_features=tuple(numeric),
        category_levels=levels, forward_horizon_bars=horizon,
    )


def build_direction_inference_frame(feature_values: dict, schema: DirectionFeatureSchema) -> pd.DataFrame:
    """One live candidate's raw feature dict → a 1-row frame encoded to the SAME schema as training.
    Unseen categorical values → NaN (LightGBM routes as missing); missing numerics → NaN."""
    row: dict = {}
    for col in schema.categorical_features:
        row[col] = pd.Categorical(
            [feature_values.get(col)], categories=list(schema.category_levels.get(col, ()))
        )
    for col in schema.numeric_features:
        row[col] = pd.to_numeric(pd.Series([feature_values.get(col)]), errors="coerce").astype(float)
    return pd.DataFrame(row)[list(schema.feature_names)]


def _unused_datetime_guard(value: datetime) -> None:  # pragma: no cover - keeps datetime import honest
    _ = value
