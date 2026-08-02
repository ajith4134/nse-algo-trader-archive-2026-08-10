"""RANDOM-CONTROL arm of the skill-vs-luck lab (Layer 7.5 slice 1; research/95).

A strategy's positive P&L is meaningless without a control: is the edge SKILL or LUCK? This runs
the SAME ORB entry TRIGGER (when to enter) but takes a RANDOM DIRECTION (which way), with a
symmetric stop/target at the same risk distance, over the same real session bars — isolating
DIRECTIONAL skill. If the real strategy does not beat this random-direction baseline, its "edge"
is noise. The random direction is a SEEDED coin-flip (seed derived from the session date by the
caller) so the control is fully reproducible. PURE (no I/O); reuses `detect_opening_range_breakout`
for the trigger and `simulate_orb_exit_price` for the exit (Rule I), exactly like the real arm.
"""

from __future__ import annotations

import random

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.paper_trading.replay_session_orb_backtester import (
    simulate_orb_exit_price,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
    detect_opening_range_breakout,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.universe_registry import Instrument


def backtest_random_control_session_return(
    single_session_bars: list[PriceBar],
    signal_instrument: Instrument,
    config: OpeningRangeBreakoutConfig,
    seed: int,
) -> float | None:
    """Signed realized return of a RANDOM-DIRECTION trade taken at the ORB trigger on this
    session, or None if the session produced no signal. Same entry moment and risk distance as
    the real ORB arm, but the direction is a seeded coin-flip and stop/target are symmetric — so
    only directional skill differs. Long return = (exit-entry)/entry; short = (entry-exit)/entry."""
    signal = detect_opening_range_breakout(single_session_bars, signal_instrument, config)
    if signal is None:
        return None
    entry = signal.breakout_close_price
    risk_per_unit = abs(entry - signal.stop_loss_price)
    if entry <= 0 or risk_per_unit <= 0:
        return None

    direction = (
        SignalDirection.LONG
        if random.Random(seed).random() < 0.5
        else SignalDirection.SHORT
    )
    reward = config.target_risk_reward_ratio * risk_per_unit
    if direction is SignalDirection.LONG:
        stop_loss_price, target_price = entry - risk_per_unit, entry + reward
    else:
        stop_loss_price, target_price = entry + risk_per_unit, entry - reward

    after_trigger = [
        bar for bar in single_session_bars if bar.timestamp > signal.triggered_at
    ]
    exit_price = simulate_orb_exit_price(
        after_trigger, direction, stop_loss_price, target_price, entry
    )
    if direction is SignalDirection.LONG:
        return (exit_price - entry) / entry
    return (entry - exit_price) / entry
