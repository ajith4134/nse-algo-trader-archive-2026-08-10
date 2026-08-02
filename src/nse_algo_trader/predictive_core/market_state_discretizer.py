"""Market-state discretizer (research/166/167 §2; Trunk IX). Raw bars → (state, action, reward) transitions.

The generative world-model needs a small DISCRETE market state. We derive it self-containedly from a
rolling window of real price bars: a TREND bucket (down / flat / up — the sign+strength of the windowed
return, volatility-normalised) × a VOLATILITY bucket (low / mid / high — the windowed realised vol vs its
own terciles) → |S| = 9 states (a trend×vol proxy for the project's regime×vol axis). For each bar we also
compute the forward h-bar return, which is the REWARD of each hypothetical action:
enter_long = +forward return, enter_short = −forward return, hold = 0. State transitions s_t → s_{t+1} are
market evolution (action-independent — a small retail order does not move the market, an honest modelling
choice, research/167 §3). PURE: bars in → transitions/rewards out.
"""

from __future__ import annotations

from dataclasses import dataclass

# The discrete axes (self-describing).
TREND_BUCKETS = ("down", "flat", "up")
VOLATILITY_BUCKETS = ("low", "mid", "high")
ACTIONS = ("enter_long", "enter_short", "hold")

_TREND_Z_THRESHOLD = 0.5     # |windowed return / windowed vol| below this = "flat"


@dataclass(frozen=True)
class MarketState:
    """One discrete market state: a (trend × volatility) bucket. 9 states total."""

    trend_bucket: str
    volatility_bucket: str

    @property
    def index(self) -> int:
        """Stable 0..8 index (trend-major) for the transition/reward tensors."""
        return TREND_BUCKETS.index(self.trend_bucket) * len(VOLATILITY_BUCKETS) \
            + VOLATILITY_BUCKETS.index(self.volatility_bucket)

    @staticmethod
    def from_index(index: int) -> MarketState:
        return MarketState(TREND_BUCKETS[index // len(VOLATILITY_BUCKETS)],
                           VOLATILITY_BUCKETS[index % len(VOLATILITY_BUCKETS)])

    @property
    def label(self) -> str:
        return f"{self.trend_bucket}/{self.volatility_bucket}"


STATE_COUNT = len(TREND_BUCKETS) * len(VOLATILITY_BUCKETS)   # 9
ACTION_COUNT = len(ACTIONS)                                   # 3


@dataclass(frozen=True)
class StateTransitionObservation:
    """One observed step: state s at t, next state s' at t+1, and the per-action rewards realised from t."""

    state_index: int
    next_state_index: int
    action_rewards: dict[str, float]   # {"enter_long": r, "enter_short": -r, "hold": 0.0}


def _bar_returns(closes: list[float]) -> list[float]:
    """Simple per-bar returns; 0.0 where the prior close is non-positive (Rule O.4 guard)."""
    out = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        out.append((closes[i] - prev) / prev if prev > 0 else 0.0)
    return out


def _stddev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


def compute_volatility_terciles(closes: list[float], window: int) -> tuple[float, float]:
    """Data-driven low/high volatility cut points (33rd/66th percentiles of the windowed realised vol)."""
    returns = _bar_returns(closes)
    vols = [_stddev(returns[max(0, i - window):i]) for i in range(window, len(returns) + 1)]
    vols = sorted(v for v in vols if v > 0)
    if len(vols) < 3:
        return (0.0, float("inf"))
    return (vols[len(vols) // 3], vols[2 * len(vols) // 3])


def classify_state(windowed_return: float, windowed_vol: float,
                   vol_low_cut: float, vol_high_cut: float) -> MarketState:
    """Map a window's (return, vol) to the discrete (trend × volatility) state."""
    z = (windowed_return / windowed_vol) if windowed_vol > 0 else 0.0
    trend = "up" if z > _TREND_Z_THRESHOLD else ("down" if z < -_TREND_Z_THRESHOLD else "flat")
    vol_bucket = "low" if windowed_vol <= vol_low_cut else ("high" if windowed_vol > vol_high_cut else "mid")
    return MarketState(trend, vol_bucket)


def discretize_bar_closes(closes: list[float], window: int = 20, horizon: int = 5,
                          vol_cuts: tuple[float, float] | None = None) -> list[StateTransitionObservation]:
    """Real close-price series → the sequence of (state, next_state, per-action reward) observations.

    `window` = rolling window for the trend/vol features; `horizon` = forward bars over which the entry
    reward (forward return) is realised. `vol_cuts` may be supplied (e.g. a stable cross-symbol calibration);
    otherwise they are computed from this series (data-driven terciles). Needs ≥ window+horizon+2 closes.
    """
    if len(closes) < window + horizon + 2:
        return []
    if vol_cuts is None:
        vol_cuts = compute_volatility_terciles(closes, window)
    vol_low_cut, vol_high_cut = vol_cuts
    returns = _bar_returns(closes)

    observations: list[StateTransitionObservation] = []
    # index t indexes into `closes`; features use the window ending at t; reward looks forward `horizon`.
    for t in range(window, len(closes) - horizon - 1):
        window_returns = returns[t - window:t]
        windowed_return = (closes[t] - closes[t - window]) / closes[t - window] if closes[t - window] > 0 else 0.0
        windowed_vol = _stddev(window_returns)
        state = classify_state(windowed_return, windowed_vol, vol_low_cut, vol_high_cut)

        next_window_returns = returns[t + 1 - window:t + 1]
        next_windowed_return = (closes[t + 1] - closes[t + 1 - window]) / closes[t + 1 - window] \
            if closes[t + 1 - window] > 0 else 0.0
        next_state = classify_state(next_windowed_return, _stddev(next_window_returns), vol_low_cut, vol_high_cut)

        forward_return = (closes[t + horizon] - closes[t]) / closes[t] if closes[t] > 0 else 0.0
        observations.append(StateTransitionObservation(
            state_index=state.index, next_state_index=next_state.index,
            action_rewards={"enter_long": forward_return, "enter_short": -forward_return, "hold": 0.0}))
    return observations
