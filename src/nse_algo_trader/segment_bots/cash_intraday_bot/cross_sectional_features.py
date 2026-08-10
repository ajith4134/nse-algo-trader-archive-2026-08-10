"""Cross-sectional feature engineering for the CASH bot (Qlib-Alpha-style, Rule P + ML addendum).

Builds a per-stock factor vector from each name's recent intraday bars, then normalises EVERY factor
cross-sectionally across the universe (rank + z-score) — because the alpha is relative: what matters is a
stock's momentum/reversal/volume *versus the rest of the universe this bar*, not its absolute value. This
is the join-in-raw-data-and-engineer-many-features step the ML addendum demands (not a handful of columns).

Input: a dict ``{symbol: DataFrame[open,high,low,close,volume]}`` of recent bars (most recent last).
Output: a DataFrame indexed by symbol with the raw factors + their cross-sectional ranks/z-scores.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# the raw per-stock factors (before cross-sectional normalisation)
_RAW_FACTORS = (
    "ret_1",  # last-bar return
    "ret_5",  # 5-bar momentum
    "ret_15",  # 15-bar momentum
    "reversal_1",  # short-term reversal (−ret_1)
    "realized_vol",  # rolling return volatility
    "volume_ratio",  # current volume vs its own average
    "range_position",  # close within the recent high-low range [0,1]
    "dollar_volume",  # liquidity (close × volume), log
    "gap",  # first-bar gap vs prior close
)

# the model consumes the cross-sectional transforms (rank in [0,1] + z-score), never the raw levels
CROSS_SECTIONAL_FEATURE_NAMES: tuple[str, ...] = tuple(
    f"{factor}_{kind}" for factor in _RAW_FACTORS for kind in ("rank", "z")
)


def _safe_return(prices: np.ndarray, lag: int) -> float:
    if prices.size <= lag or prices[-lag - 1] <= 0:
        return 0.0
    return float(prices[-1] / prices[-lag - 1] - 1.0)


def _raw_factors_for_symbol(bars: pd.DataFrame) -> dict[str, float]:
    if bars is None or len(bars) < 2:
        return dict.fromkeys(_RAW_FACTORS, 0.0)
    close = bars["close"].to_numpy(dtype=float)
    volume = bars["volume"].to_numpy(dtype=float) if "volume" in bars else np.zeros(len(bars))
    high = bars["high"].to_numpy(dtype=float) if "high" in bars else close
    low = bars["low"].to_numpy(dtype=float) if "low" in bars else close
    returns = np.diff(np.log(np.clip(close, 1e-9, None)))
    recent_hi, recent_lo = float(np.max(high[-15:])), float(np.min(low[-15:]))
    avg_vol = float(np.mean(volume[-20:])) if volume[-20:].size else 0.0
    return {
        "ret_1": _safe_return(close, 1),
        "ret_5": _safe_return(close, 5),
        "ret_15": _safe_return(close, 15),
        "reversal_1": -_safe_return(close, 1),
        "realized_vol": float(np.std(returns[-20:])) if returns.size else 0.0,
        "volume_ratio": (float(volume[-1]) / avg_vol) if avg_vol > 0 else 1.0,
        "range_position": ((close[-1] - recent_lo) / (recent_hi - recent_lo)) if recent_hi > recent_lo else 0.5,
        "dollar_volume": float(np.log1p(close[-1] * max(volume[-1], 0.0))),
        "gap": _safe_return(close, len(close) - 1) if close.size >= 2 else 0.0,
    }


def build_cross_sectional_features(universe_bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return a per-symbol feature frame: raw factors + their cross-sectional rank ([0,1]) and z-score."""

    raw = pd.DataFrame(
        {symbol: _raw_factors_for_symbol(bars) for symbol, bars in universe_bars.items()}
    ).T  # index = symbol, columns = raw factors
    if raw.empty:
        return pd.DataFrame(columns=list(CROSS_SECTIONAL_FEATURE_NAMES))

    features = pd.DataFrame(index=raw.index)
    for factor in _RAW_FACTORS:
        col = pd.to_numeric(raw[factor], errors="coerce").fillna(0.0)
        # cross-sectional rank in [0,1] (robust to outliers) + cross-sectional z-score
        features[f"{factor}_rank"] = col.rank(pct=True)
        std = col.std(ddof=0)
        features[f"{factor}_z"] = ((col - col.mean()) / std) if std > 1e-12 else 0.0
    return features[list(CROSS_SECTIONAL_FEATURE_NAMES)].fillna(0.0)
