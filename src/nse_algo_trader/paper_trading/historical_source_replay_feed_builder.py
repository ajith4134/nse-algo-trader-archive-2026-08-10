"""Build a replay feed's `bars_by_token` from any `HistoricalBarSource` — the
seam that lets the market-closed replay loop run on a chosen source/fidelity
(§53 slice 4 P4a-wire; research/67).

The default replay path reads 5-minute bars from the SQLite store. This builder
lets it instead pull, per instrument, from an injected `HistoricalBarSource` at a
chosen interval — used to feed **ICICI Breeze 1-second** bars into the exact same
`ReplayUniverseFeed` the loop already consumes, so the fidelity climb reaches
trading decisions. Generic over the source, so it equally builds from the Kite
minute source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from nse_algo_trader.market_data.broker_data_source_protocols import (
    HistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument


def build_replay_bars_by_token_from_source(
    historical_bar_source: HistoricalBarSource,
    instruments: list[Instrument],
    bar_interval: BarInterval,
    from_timestamp: datetime,
    to_timestamp: datetime,
) -> dict[int, list[PriceBar]]:
    """Fetch each instrument's bars from the source and key them by token, the
    exact shape `ReplayUniverseFeed` consumes. Instruments the source returns no
    bars for are omitted (so replay simply skips them), never a hard failure."""
    bars_by_token: dict[int, list[PriceBar]] = {}
    for instrument in instruments:
        bars = historical_bar_source.fetch_historical_bars(
            instrument, bar_interval, from_timestamp, to_timestamp
        )
        if bars:
            bars_by_token[instrument.instrument_token] = bars
    return bars_by_token


@dataclass(frozen=True)
class HighFidelityReplayConfig:
    """The optional injection that switches the market-closed replay from the
    stored 5-minute bars to a higher-fidelity source (Breeze 1-second) for a
    bounded focus set on one session. Bounded because Breeze's 5000-calls/day cap
    makes a full-universe 1-second pull infeasible (research/67)."""

    bar_source: HistoricalBarSource
    focus_instruments: list[Instrument]
    session_date: date
    bar_interval: BarInterval = BarInterval.SECOND_1
