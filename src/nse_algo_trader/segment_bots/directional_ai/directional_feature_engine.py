"""Directional feature + label engine for the BULL/BEAR models (engine-grade, Rule P).

Builds, from a single instrument's bar series, a rich directional feature vector at each point and a
**counterfactual triple-barrier label** (López de Prado, AFML ch. 3): from bar t, place a symmetric
volatility-scaled up-barrier and down-barrier and a vertical (time) barrier; the label is which barrier the
path touches FIRST — up-first → an "up" event, down-first → a "down" event, neither within the horizon → no
directional event. It is COUNTERFACTUAL because it depends only on the price path, never on a fill or exit
the bot controlled (crypto §03b: judging a directional model on realised trade outcomes corrupts the signal).

The SAME labelling yields both targets: ``y_up`` (up-barrier first) trains the BULL model and ``y_down``
(down-barrier first) trains the BEAR model — each on the FULL, un-direction-filtered sample, so both can
calibrate against their negative class (§03b: a bull trained only on up-moves has never seen a down-move).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# the directional feature vector (momentum + trend + volatility + microstructure, per-series temporal)
DIRECTIONAL_FEATURE_NAMES: tuple[str, ...] = (
    "ret_1",
    "ret_5",
    "ret_15",
    "momentum_norm",  # 15-bar return / realized vol (trend strength, signed)
    "realized_vol",
    "vol_ratio",  # short vol / long vol (vol regime)
    "adx_proxy",  # |EMA(up-move) - EMA(down-move)| / range — directional-movement strength
    "directional_index",  # signed +DI - -DI proxy in [-1,1]
    "range_position",  # close within the recent high-low range [0,1]
    "dist_from_ema",  # (close - EMA) / close — displacement from trend
    "up_bar_fraction",  # fraction of recent bars that closed up
    "accel",  # ret_5 minus prior ret_5 (momentum acceleration)
)

_ANNUALIZE = 1.0  # features are per-bar; no annualization needed for the classifier


@dataclass(frozen=True)
class DirectionalSample:
    """One training row: the feature vector at bar t + both counterfactual barrier labels."""

    features: dict[str, float]
    y_up: int  # 1 if the up-barrier was touched first (BULL target)
    y_down: int  # 1 if the down-barrier was touched first (BEAR target)
    as_of_epoch: float  # bar index / timestamp for leakage-free time-ordered CV


def _ema(series: np.ndarray, span: int) -> float:
    if series.size == 0:
        return 0.0
    alpha = 2.0 / (span + 1.0)
    value = float(series[0])
    for x in series[1:]:
        value = alpha * float(x) + (1 - alpha) * value
    return value


def _features_at(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> dict[str, float]:
    """Compute the directional feature vector from the bar window ending at the last element."""
    n = close.size
    if n < 16:
        return dict.fromkeys(DIRECTIONAL_FEATURE_NAMES, 0.0)
    log_ret = np.diff(np.log(np.clip(close, 1e-9, None)))

    def ret(lag: int) -> float:
        return float(close[-1] / close[-lag - 1] - 1.0) if n > lag and close[-lag - 1] > 0 else 0.0

    rv = float(np.std(log_ret[-20:])) if log_ret.size >= 2 else 1e-6
    rv_long = float(np.std(log_ret[-60:])) if log_ret.size >= 20 else rv
    up_moves = np.maximum(np.diff(high[-15:]), 0.0) if n >= 16 else np.zeros(1)
    down_moves = np.maximum(-np.diff(low[-15:]), 0.0) if n >= 16 else np.zeros(1)
    plus_di = float(np.mean(up_moves))
    minus_di = float(np.mean(down_moves))
    di_sum = plus_di + minus_di + 1e-9
    recent_hi, recent_lo = float(np.max(high[-15:])), float(np.min(low[-15:]))
    ema20 = _ema(close[-40:], 20)
    up_bars = float(np.mean((np.diff(close[-15:]) > 0).astype(float))) if n >= 16 else 0.5

    return {
        "ret_1": ret(1),
        "ret_5": ret(5),
        "ret_15": ret(15),
        "momentum_norm": ret(15) / (rv * np.sqrt(15) + 1e-9),
        "realized_vol": rv,
        "vol_ratio": rv / (rv_long + 1e-9),
        "adx_proxy": abs(plus_di - minus_di) / (recent_hi - recent_lo + 1e-9),
        "directional_index": (plus_di - minus_di) / di_sum,
        "range_position": (close[-1] - recent_lo) / (recent_hi - recent_lo) if recent_hi > recent_lo else 0.5,
        "dist_from_ema": (close[-1] - ema20) / close[-1] if close[-1] > 0 else 0.0,
        "up_bar_fraction": up_bars,
        "accel": ret(5) - (float(close[-6] / close[-11] - 1.0) if n > 10 and close[-11] > 0 else 0.0),
    }


def _triple_barrier_label(
    forward_close: np.ndarray, entry: float, sigma: float, barrier_mult: float
) -> tuple[int, int]:
    """Which barrier the forward path touches first. Returns (y_up, y_down); (0,0) = vertical-barrier timeout."""
    up = entry * (1.0 + barrier_mult * sigma)
    down = entry * (1.0 - barrier_mult * sigma)
    for price in forward_close:
        if price >= up:
            return 1, 0
        if price <= down:
            return 0, 1
    return 0, 0  # neither barrier hit within the horizon → no directional event


def build_directional_training_samples(
    bars: pd.DataFrame,
    horizon: int = 12,
    barrier_sigma_mult: float = 1.0,
    min_history: int = 40,
) -> list[DirectionalSample]:
    """Slide over the series → (features at t, counterfactual triple-barrier label over (t, t+horizon])."""
    if bars is None or len(bars) < min_history + horizon + 2:
        return []
    close = bars["close"].to_numpy(dtype=float)
    high = bars["high"].to_numpy(dtype=float) if "high" in bars else close
    low = bars["low"].to_numpy(dtype=float) if "low" in bars else close
    log_ret = np.diff(np.log(np.clip(close, 1e-9, None)))

    samples: list[DirectionalSample] = []
    for t in range(min_history, len(close) - horizon - 1):
        window_sigma = float(np.std(log_ret[max(0, t - 20):t])) or 1e-4
        feats = _features_at(close[: t + 1], high[: t + 1], low[: t + 1])
        y_up, y_down = _triple_barrier_label(
            close[t + 1: t + 1 + horizon], close[t], window_sigma, barrier_sigma_mult
        )
        samples.append(DirectionalSample(feats, y_up, y_down, as_of_epoch=float(t)))
    return samples


def directional_features_now(bars: pd.DataFrame) -> dict[str, float]:
    """Feature vector at the latest bar for live inference (no label)."""
    if bars is None or len(bars) < 16:
        return dict.fromkeys(DIRECTIONAL_FEATURE_NAMES, 0.0)
    close = bars["close"].to_numpy(dtype=float)
    high = bars["high"].to_numpy(dtype=float) if "high" in bars else close
    low = bars["low"].to_numpy(dtype=float) if "low" in bars else close
    return _features_at(close, high, low)
