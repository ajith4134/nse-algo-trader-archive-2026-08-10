"""A resilient `HistoricalBarSource` that fails over across several broker adapters
(task #20; research/84; PLAN §8a.12).

Individually each broker adapter (Kite, Breeze, Fyers, Upstox, Angel One, Groww) is a
single point of failure — a broker can be rate-limited, mid-outage, missing a symbol
in its instrument master, or un-entitled. This source holds an ORDERED list of them
and, per instrument, tries each in priority order until one returns bars:

  - a source that RAISES (outage / rate-limit / its resolver `KeyError` because the
    symbol isn't in that broker's master) → failover to the next,
  - a source that returns EMPTY → failover to the next (an empty from the primary must
    not mask data a secondary has),
  - the first source returning NON-EMPTY bars wins,
  - all sources exhausted → `[]` (the replay builder then simply omits the instrument;
    never a hard crash).

Because it implements the `HistoricalBarSource` protocol itself, it drops into every
existing consumer (`build_replay_bars_by_token_from_source`,
`HighFidelityReplayConfig.bar_source`) with no change. The priority ORDER is injected
by the composition root (that is where Rule L / user preference is applied) — this
class hard-codes no broker.

Slice-2 gap-fill AGGREGATION (fill a primary's missing timestamps from lower-priority
sources) is a separate queued slice (research/84; BACKLOG). This slice is failover.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from nse_algo_trader.market_data.broker_data_source_protocols import (
    HistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument


@dataclass(frozen=True)
class NamedHistoricalBarSource:
    """One broker adapter paired with a human-readable name for observability."""

    name: str
    source: HistoricalBarSource


@dataclass(frozen=True)
class SourceAttempt:
    """The outcome of trying one source for one instrument (fed to the observer)."""

    source_name: str
    instrument_trading_symbol: str
    outcome: str  # "served" | "empty" | "error"
    bar_count: int
    error_repr: str | None


class MultiBrokerHistoricalBarSource:
    """Ordered failover across broker historical sources. Implements
    `HistoricalBarSource`, so it is itself injectable anywhere one is consumed."""

    def __init__(
        self,
        ordered_sources: list[NamedHistoricalBarSource],
        on_source_attempt: Callable[[SourceAttempt], None] | None = None,
    ) -> None:
        if not ordered_sources:
            raise ValueError(
                "MultiBrokerHistoricalBarSource needs at least one source in priority order"
            )
        self._ordered_sources = ordered_sources
        self._on_source_attempt = on_source_attempt

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        for named_source in self._ordered_sources:
            try:
                bars = named_source.source.fetch_historical_bars(
                    instrument, bar_interval, from_datetime, to_datetime
                )
            except Exception as error:  # broker outage / rate-limit / resolver KeyError
                self._record_attempt(
                    named_source.name, instrument, "error", 0, repr(error)
                )
                continue
            if bars:
                self._record_attempt(
                    named_source.name, instrument, "served", len(bars), None
                )
                return bars
            self._record_attempt(named_source.name, instrument, "empty", 0, None)
        return []

    def _record_attempt(
        self,
        source_name: str,
        instrument: Instrument,
        outcome: str,
        bar_count: int,
        error_repr: str | None,
    ) -> None:
        if self._on_source_attempt is None:
            return
        self._on_source_attempt(
            SourceAttempt(
                source_name=source_name,
                instrument_trading_symbol=instrument.trading_symbol,
                outcome=outcome,
                bar_count=bar_count,
                error_repr=error_repr,
            )
        )

    def source_names_in_priority_order(self) -> list[str]:
        return [named.name for named in self._ordered_sources]
