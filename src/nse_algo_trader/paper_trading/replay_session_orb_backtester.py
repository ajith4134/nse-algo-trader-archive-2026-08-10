"""Deterministic per-session backtest of the ORB strategy on one session's REAL bars —
the measurement atom of the champion-challenger tournament (§53 slice 5c-i; research/87).

Reuses `strategy_engine.detect_opening_range_breakout` for the signal (Rule I), then
simulates the trade's outcome on the same session's bars: after the trigger bar, a LONG
wins if a later bar's high reaches the target and loses if its low reaches the stop (stop
checked first within a bar = conservative); a SHORT is mirrored; if neither is hit by the
session's end, the position exits at the last close. Returns the SIGNED realized return
fraction, or None when the session produced no ORB signal (no trade). PURE (no I/O).
"""

from __future__ import annotations

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
    detect_opening_range_breakout,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.universe_registry import Instrument


def backtest_orb_session_return(
    single_session_bars: list[PriceBar],
    signal_instrument: Instrument,
    config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
) -> float | None:
    """Signed realized return fraction of the ORB trade on this session, or None if the
    session produced no signal. Long return = (exit-entry)/entry; short = (entry-exit)/entry."""
    signal = detect_opening_range_breakout(single_session_bars, signal_instrument, config)
    if signal is None:
        return None
    entry = signal.breakout_close_price
    if entry <= 0:
        return None
    after_trigger = [
        bar for bar in single_session_bars if bar.timestamp > signal.triggered_at
    ]
    exit_price = _simulate_exit_price(
        after_trigger, signal.direction, signal.stop_loss_price, signal.target_price, entry
    )
    if signal.direction is SignalDirection.LONG:
        return (exit_price - entry) / entry
    return (entry - exit_price) / entry


def _simulate_exit_price(
    bars_after_trigger: list[PriceBar],
    direction: SignalDirection,
    stop_loss_price: float,
    target_price: float,
    entry_price: float,
) -> float:
    """The fill price the trade exits at: the stop or target if touched (stop first within
    a bar), else the last close. No bars after the trigger → exit at entry (flat)."""
    last_close = entry_price
    for bar in bars_after_trigger:
        last_close = bar.close_price
        if direction is SignalDirection.LONG:
            if bar.low_price <= stop_loss_price:  # stop checked first (conservative)
                return stop_loss_price
            if bar.high_price >= target_price:
                return target_price
        else:  # SHORT
            if bar.high_price >= stop_loss_price:
                return stop_loss_price
            if bar.low_price <= target_price:
                return target_price
    return last_close
