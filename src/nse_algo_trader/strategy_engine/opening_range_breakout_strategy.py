"""Opening-Range Breakout — the v1 directional strategy (PLAN §7).

Classic construction: the high/low of the session's first N minutes is
the opening range; the first bar CLOSING beyond either bound after the
range window triggers the signal in that direction. Stop = opposite
range bound; target = entry ± risk × reward ratio. One signal per
session, no entries after the cutoff time (intraday square-off leaves
room to manage the trade).

All defaults are starting parameters to be tuned by Layer 7
backtesting — nothing here is a claimed edge yet (`docs/research/13`
grades breakout filters B; the §3b validation pipeline judges it later).
"""

from dataclasses import dataclass
from datetime import time, timedelta

from nse_algo_trader.market_data import PriceBar
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    OpeningRangeBreakoutSignal,
    SignalDirection,
)
from nse_algo_trader.universe_registry import Instrument


@dataclass(frozen=True)
class OpeningRangeBreakoutConfig:
    opening_range_minutes: int = 15
    target_risk_reward_ratio: float = 2.0
    latest_entry_time_ist: time = time(14, 30)


def detect_opening_range_breakout(
    single_session_bars: list[PriceBar],
    signal_instrument: Instrument,
    config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
) -> OpeningRangeBreakoutSignal | None:
    """First qualifying breakout in one session's bars, or None.

    `single_session_bars` must be one session, chronological. The
    breakout is judged on bar closes (not wicks), the standard
    false-breakout filter for bar-based ORB.
    """
    if not single_session_bars:
        return None
    session_start = single_session_bars[0].timestamp
    opening_range_end = session_start + timedelta(minutes=config.opening_range_minutes)

    opening_range_bars = [
        bar for bar in single_session_bars if bar.timestamp < opening_range_end
    ]
    if not opening_range_bars:
        return None
    opening_range_high = max(bar.high_price for bar in opening_range_bars)
    opening_range_low = min(bar.low_price for bar in opening_range_bars)

    for bar in single_session_bars:
        if bar.timestamp < opening_range_end:
            continue
        if bar.timestamp.time() > config.latest_entry_time_ist:
            return None
        if bar.close_price > opening_range_high:
            direction = SignalDirection.LONG
            stop_loss_price = opening_range_low
        elif bar.close_price < opening_range_low:
            direction = SignalDirection.SHORT
            stop_loss_price = opening_range_high
        else:
            continue
        entry_price = bar.close_price
        risk_per_unit = abs(entry_price - stop_loss_price)
        target_offset = config.target_risk_reward_ratio * risk_per_unit
        return OpeningRangeBreakoutSignal(
            instrument=signal_instrument,
            direction=direction,
            triggered_at=bar.timestamp,
            breakout_close_price=entry_price,
            opening_range_high=opening_range_high,
            opening_range_low=opening_range_low,
            stop_loss_price=stop_loss_price,
            target_price=(
                entry_price + target_offset
                if direction is SignalDirection.LONG
                else entry_price - target_offset
            ),
        )
    return None
