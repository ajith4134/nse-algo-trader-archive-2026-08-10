"""DirectionalSideBrain — the one place a bot turns its own price history into a LONG/SHORT/NEUTRAL side.

Slice 1 built the BULL/BEAR directional AI (``bull_bear_directional_engine`` + ``directional_arbiter`` +
``directional_feature_engine``) but nothing consumed its verdict — the three segment bots all read a passive
``adapter.trend_side`` that the production adapter hard-returns as ``NEUTRAL``, leaving every directional
(CE/PE, cash long/short) branch dormant. This brain is the consumer: each bot owns one, feeds it the price
series it already pulls, and gets back an arbitrated verdict that wakes those branches.

Lifecycle per underlying (full universe, keyed by symbol):
  * a persisted ``BullBearDirectionalEngine`` is loaded/created lazily and cached in memory;
  * while the engine is not earned, each call attempts a train on freshly-built triple-barrier samples —
    the engine's own ``_MIN_SAMPLES_TO_TRAIN`` / ``_MIN_PER_CLASS`` ladder gates activation (Rule Q: a thin
    series stays ``gathering`` → NEUTRAL, the algorithm is never shrunk to fit the data);
  * once earned, inference is cheap: latest-bar features → directional view → arbiter → verdict.

The meta-labelling depth (conflict → FLAT, weak-edge → FLAT, else stronger side with conviction) lives in
the arbiter; this module is the lifecycle + normalisation glue around it, not a re-implementation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nse_algo_trader.segment_bots.directional_ai.bull_bear_directional_engine import (
    BullBearDirectionalEngine,
    DirectionalModelStore,
)
from nse_algo_trader.segment_bots.directional_ai.directional_arbiter import (
    DirectionalArbiter,
    DirectionalVerdict,
)
from nse_algo_trader.segment_bots.directional_ai.directional_feature_engine import (
    build_directional_training_samples,
    directional_features_now,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide

_GATHERING_VERDICT = DirectionalVerdict(
    side=TradeSide.NEUTRAL,
    conviction=0.0,
    p_up=0.5,
    p_down=0.5,
    margin=0.0,
    is_conflict=False,
    rationale="directional brain gathering history → neutral (bot keeps its existing side)",
)


def _as_bars(prices: pd.Series | pd.DataFrame | None) -> pd.DataFrame | None:
    """Normalise a bot's price data (close-only Series or OHLC DataFrame) into a bars frame with a close col."""
    if prices is None:
        return None
    if isinstance(prices, pd.DataFrame):
        if "close" in prices.columns and len(prices):
            return prices
        return None
    if isinstance(prices, pd.Series):
        if len(prices) == 0:
            return None
        close = prices.astype(float).reset_index(drop=True)
        return pd.DataFrame({"close": close, "high": close, "low": close})
    return None


class DirectionalSideBrain:
    """One per bot. Owns a per-underlying directional engine and serves an arbitrated directional verdict."""

    def __init__(
        self,
        store_dir: Path,
        arbiter: DirectionalArbiter | None = None,
        horizon: int = 12,
        max_new_trains_per_cycle: int = 4,
    ):
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._arbiter = arbiter or DirectionalArbiter()
        self._horizon = horizon
        # Cold-start throttle: training a per-underlying model is expensive (~seconds). Cap NEW trainings per
        # cycle so a full-universe pass never blocks the pod tick — cold-start spreads over cycles, and once a
        # model is earned it persists and only cheap inference runs. Set 0 to disable the cap.
        self._max_new_trains_per_cycle = max_new_trains_per_cycle
        self._new_trains_this_cycle = 0
        self._engines: dict[str, BullBearDirectionalEngine] = {}

    def begin_cycle(self) -> None:
        """Reset the per-cycle training budget — the owning bot calls this at the start of each propose pass."""
        self._new_trains_this_cycle = 0

    def _engine_for(self, underlying: str) -> BullBearDirectionalEngine:
        engine = self._engines.get(underlying)
        if engine is None:
            store = DirectionalModelStore(self._store_dir / _safe_key(underlying))
            engine = BullBearDirectionalEngine(store)
            self._engines[underlying] = engine
        return engine

    def verdict_for(self, underlying: str, prices: pd.Series | pd.DataFrame | None) -> DirectionalVerdict:
        """Train-if-needed then infer → the arbitrated LONG/SHORT/NEUTRAL verdict for this underlying."""
        bars = _as_bars(prices)
        if bars is None:
            return _GATHERING_VERDICT

        engine = self._engine_for(underlying)
        if not engine.is_earned:
            budget_left = (self._max_new_trains_per_cycle <= 0
                           or self._new_trains_this_cycle < self._max_new_trains_per_cycle)
            if not budget_left:
                return _GATHERING_VERDICT  # deferred to a later cycle — cold-start throttle (not a failure)
            samples = build_directional_training_samples(bars, horizon=self._horizon)
            if samples:
                self._new_trains_this_cycle += 1
                engine.train(samples)  # persists on success; stays un-earned below the maturity ladder
            if not engine.is_earned:
                return _GATHERING_VERDICT

        view = engine.directional_view(directional_features_now(bars))
        return self._arbiter.arbitrate(view)

    def side_for(self, underlying: str, prices: pd.Series | pd.DataFrame | None) -> TradeSide:
        """Convenience: just the side, for callers that don't need the full verdict."""
        return self.verdict_for(underlying, prices).side

    def observe_outcome(self, underlying: str, verdict: DirectionalVerdict, went_up: bool) -> bool:
        """Feed a realised direction back to the underlying's engine for drift monitoring. True if drifted."""
        engine = self._engines.get(underlying)
        if engine is None or not engine.is_earned:
            return False
        from nse_algo_trader.segment_bots.directional_ai.bull_bear_directional_engine import DirectionalView

        view = DirectionalView(verdict.p_up, verdict.p_down, "earned")
        return engine.observe_outcome(view, went_up)


def _safe_key(underlying: str) -> str:
    """Filesystem-safe per-underlying store key (symbols can carry '/', ':' etc.)."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(underlying)) or "_"
