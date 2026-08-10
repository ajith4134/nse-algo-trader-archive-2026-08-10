"""Intraday mean-reversion signal family — the inverse of ORB (PLAN §7, L4).

The harvested truth this project trusts: NSE intraday cash tends to
MEAN-REVERT inside a range, while naive momentum bleeds. This engine is
the counterpart to `opening_range_breakout_strategy` — where ORB fires on
a trending tape (high ADX) breaking a range, this one fires on a
*range-bound* tape (low ADX) when price has stretched far from an
intraday mean, and fades the stretch back toward the mean.

Construction (VWAP-band / z-score reversion, the classical mean-reversion
signal):

  * Intraday mean  — either the session-anchored VWAP (reused from the
    Layer-3 indicator stack) or a rolling SMA of close. Both are causal
    (cumulative / trailing-window), so there is no look-ahead.
  * Dispersion     — a trailing-window standard deviation of the residual
    (close - mean), i.e. the width of the VWAP band. Computed from the
    REAL session bars, never a hard-coded level.
  * Stretch        — z = residual / dispersion. A LONG-reversion fires
    when z <= -entry_sigma (price stretched BELOW the mean -> oversold ->
    buy low, target back up at the mean); a SHORT-reversion when
    z >= +entry_sigma (stretched ABOVE -> overbought -> sell high, target
    back down at the mean). Stop sits a further `stop_sigma` on the WRONG
    side (further FROM the mean), so a continued stretch is cut.

Self-calibrating, not magic: `entry_sigma` / `stop_sigma` are config with
documented defaults, but the mean and dispersion are derived per-bar from
the instrument's own intraday tape. A PERCENTILE threshold mode is offered
as the fully non-parametric alternative — the entry stretch is the
empirical N-th percentile of the session's own residual distribution, so
it adapts to each instrument's dispersion shape without assuming a
Gaussian sigma.

Regime gate: mean-reversion needs a non-trending tape. The signal ONLY
fires when the supplied `regime_adx` is at/below the range-bound threshold
(mirrors `session_strategy_regime_gate`'s 20.0 default). A trending
(high-ADX) or unknown (None) regime abstains entirely — the exact inverse
of ORB's "trending only" precondition.

Intraday, cash-directional conventions: quantity is shares (sizing is a
later layer's job); entry reference = the stretched bar's close; one
signal per session (the first qualifying stretch). Nothing here is a
claimed edge yet — the §3b validation pipeline judges it later.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import numpy as np

from nse_algo_trader.indicators.session_anchored_vwap import (
    compute_session_anchored_vwap,
)
from nse_algo_trader.market_data import PriceBar
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.universe_registry import Instrument


class MeanReversionMeanBasis(str, Enum):
    """Which intraday mean the stretch is measured against."""

    SESSION_VWAP = "session_vwap"  # cumulative volume-weighted average price
    ROLLING_SMA = "rolling_sma"  # trailing simple moving average of close


class MeanReversionThresholdMode(str, Enum):
    """How the entry stretch is judged."""

    SIGMA = "sigma"  # z-score vs `entry_sigma` standard deviations
    PERCENTILE = "percentile"  # empirical percentile of session residuals


@dataclass(frozen=True)
class IntradayMeanReversionConfig:
    """Starting parameters for the intraday mean-reversion family.

    Every level the signal actually trades against (mean, dispersion,
    stretch) is computed from the live session bars; the fields here only
    set *how many* sigmas / *which* percentile counts as a tradable
    stretch, plus the regime and warm-up guards.
    """

    mean_basis: MeanReversionMeanBasis = MeanReversionMeanBasis.SESSION_VWAP
    threshold_mode: MeanReversionThresholdMode = MeanReversionThresholdMode.SIGMA

    dispersion_lookback_bars: int = 20  # trailing window for mean(SMA)+std
    entry_sigma: float = 2.0  # stretch (in std) that arms a reversion
    stop_sigma: float = 1.0  # extra std beyond entry -> protective stop
    target_reversion_fraction: float = 1.0  # 1.0 = target the full mean

    # PERCENTILE mode: fire when the residual is at/beyond the N-th (long)
    # or (100-N)-th (short) percentile of the session's own residuals.
    entry_percentile: float = 5.0

    # Regime gate: only fade in a NON-trending tape (inverse of ORB).
    range_bound_adx_threshold: float = 20.0

    # Degenerate-session guard: dispersion must exceed this fraction of the
    # mean price to be a tradable band (0.0 -> guard only exact-zero std,
    # which is enough to make flat sessions emit nothing / never div0).
    min_dispersion_fraction_of_price: float = 0.0

    def __post_init__(self) -> None:
        if self.dispersion_lookback_bars < 2:
            raise ValueError("dispersion_lookback_bars must be >= 2 for a std")
        if self.entry_sigma <= 0.0:
            raise ValueError("entry_sigma must be > 0")
        if self.stop_sigma <= 0.0:
            raise ValueError("stop_sigma must be > 0")
        if not 0.0 < self.target_reversion_fraction <= 1.0:
            raise ValueError("target_reversion_fraction must be in (0, 1]")
        if not 0.0 < self.entry_percentile < 50.0:
            raise ValueError("entry_percentile must be in (0, 50)")
        if self.min_dispersion_fraction_of_price < 0.0:
            raise ValueError("min_dispersion_fraction_of_price must be >= 0")


@dataclass(frozen=True)
class MeanReversionSignal:
    """A fade-the-stretch reversion on one cash instrument.

    Sibling of `OpeningRangeBreakoutSignal` (same critical fields:
    instrument, direction, triggered_at, an entry reference price,
    stop_loss_price, target_price, strategy_tag) plus the reversion-
    specific context (the mean it fades toward, the dispersion, and the
    ADX that confirmed the range-bound regime). Frozen; sign conventions
    are enforced in __post_init__.
    """

    instrument: Instrument
    direction: SignalDirection
    triggered_at: datetime
    entry_reference_price: float  # close of the stretched bar
    intraday_mean_price: float  # VWAP / SMA the fade targets
    dispersion_at_entry: float  # trailing-window residual std (band width)
    stretch_in_sigma: float  # signed z-score at the trigger bar
    stop_loss_price: float  # a further stop_sigma FROM the mean
    target_price: float  # toward the mean (fraction of the way back)
    regime_adx_at_entry: float  # confirmed <= range-bound threshold
    strategy_tag: str = "intraday_mean_reversion_v1"

    def __post_init__(self) -> None:
        # A LONG fades a drop: buy below the mean, stop below entry,
        # target above entry (toward the mean). A SHORT mirrors it.
        if self.direction is SignalDirection.LONG:
            if not (self.stop_loss_price < self.entry_reference_price < self.target_price):
                raise ValueError(
                    "LONG reversion requires stop < entry < target (fade a drop)"
                )
        elif not (self.target_price < self.entry_reference_price < self.stop_loss_price):
            raise ValueError(
                "SHORT reversion requires target < entry < stop (fade a spike)"
            )


def _rolling_simple_moving_average(
    session_bars: list[PriceBar], lookback_bars: int
) -> list[float | None]:
    """Causal trailing SMA of close; None until `lookback_bars` bars seen."""
    closes = [bar.close_price for bar in session_bars]
    sma_series: list[float | None] = [None] * len(closes)
    for bar_index in range(lookback_bars - 1, len(closes)):
        window = closes[bar_index - lookback_bars + 1 : bar_index + 1]
        sma_series[bar_index] = sum(window) / lookback_bars
    return sma_series


def _intraday_mean_series(
    session_bars: list[PriceBar], config: IntradayMeanReversionConfig
) -> list[float | None]:
    if config.mean_basis is MeanReversionMeanBasis.SESSION_VWAP:
        return compute_session_anchored_vwap(session_bars)
    return _rolling_simple_moving_average(session_bars, config.dispersion_lookback_bars)


def detect_intraday_mean_reversion(
    session_bars: list[PriceBar],
    instrument: Instrument,
    config: IntradayMeanReversionConfig = IntradayMeanReversionConfig(),
    regime_adx: float | None = None,
) -> MeanReversionSignal | None:
    """First qualifying mean-reversion stretch in one session, or None.

    `session_bars` must be one session, chronological. `regime_adx` is the
    session's ADX from the Layer-3 indicator (the caller computes it); the
    signal abstains unless it confirms a range-bound tape. No look-ahead:
    the mean, dispersion and stretch at bar i use only bars up to i.
    """
    # Regime gate FIRST — a trending or unknown tape never fades (inverse
    # of ORB, which requires a trending tape).
    if regime_adx is None or regime_adx > config.range_bound_adx_threshold:
        return None
    if not session_bars:
        return None

    mean_series = _intraday_mean_series(session_bars, config)
    lookback = config.dispersion_lookback_bars

    for bar_index in range(lookback - 1, len(session_bars)):
        current_mean = mean_series[bar_index]
        if current_mean is None:
            continue

        # Trailing-window residuals (close - mean); the band's std.
        window_residuals: list[float] = []
        window_incomplete = False
        for prior_index in range(bar_index - lookback + 1, bar_index + 1):
            prior_mean = mean_series[prior_index]
            if prior_mean is None:
                window_incomplete = True
                break
            window_residuals.append(
                session_bars[prior_index].close_price - prior_mean
            )
        if window_incomplete or len(window_residuals) < 2:
            continue

        dispersion = float(np.std(window_residuals, ddof=1))
        dispersion_floor = config.min_dispersion_fraction_of_price * abs(current_mean)
        if dispersion <= dispersion_floor or dispersion <= 0.0:
            # Flat / degenerate session -> no tradable band, never div0.
            continue

        entry_price = session_bars[bar_index].close_price
        residual = entry_price - current_mean
        stretch_in_sigma = residual / dispersion

        direction = _qualifying_direction(
            residual=residual,
            stretch_in_sigma=stretch_in_sigma,
            window_residuals=window_residuals,
            config=config,
        )
        if direction is None:
            continue

        direction_sign = 1.0 if direction is SignalDirection.LONG else -1.0
        target_price = entry_price + config.target_reversion_fraction * (
            current_mean - entry_price
        )
        stop_loss_price = entry_price - direction_sign * config.stop_sigma * dispersion

        return MeanReversionSignal(
            instrument=instrument,
            direction=direction,
            triggered_at=session_bars[bar_index].timestamp,
            entry_reference_price=entry_price,
            intraday_mean_price=current_mean,
            dispersion_at_entry=dispersion,
            stretch_in_sigma=stretch_in_sigma,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            regime_adx_at_entry=regime_adx,
        )
    return None


def _qualifying_direction(
    residual: float,
    stretch_in_sigma: float,
    window_residuals: list[float],
    config: IntradayMeanReversionConfig,
) -> SignalDirection | None:
    """LONG if stretched oversold, SHORT if overbought, else None.

    SIGMA mode compares the z-score to `entry_sigma`; PERCENTILE mode
    compares the raw residual to the empirical tails of the session's own
    residual distribution, so the trigger self-calibrates to the
    instrument's intraday dispersion shape rather than assuming a Gaussian.
    """
    if config.threshold_mode is MeanReversionThresholdMode.SIGMA:
        if stretch_in_sigma <= -config.entry_sigma:
            return SignalDirection.LONG
        if stretch_in_sigma >= config.entry_sigma:
            return SignalDirection.SHORT
        return None

    lower_tail = float(np.percentile(window_residuals, config.entry_percentile))
    upper_tail = float(
        np.percentile(window_residuals, 100.0 - config.entry_percentile)
    )
    if residual < 0.0 and residual <= lower_tail:
        return SignalDirection.LONG
    if residual > 0.0 and residual >= upper_tail:
        return SignalDirection.SHORT
    return None
