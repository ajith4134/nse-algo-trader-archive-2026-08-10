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

Two combination policies (`SourceCombinationPolicy`, research/84):
  - FAILOVER (default): the behaviour above — first non-empty source wins.
  - GAP_FILL: union across ALL sources — each source fills only the timestamps a
    higher-priority source didn't cover, so a primary with a mid-session gap is
    completed from a secondary (each bar stays wholly from one feed).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from nse_algo_trader.market_data.broker_data_source_protocols import (
    HistoricalBarSource,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.universe_registry import Instrument


class SourceCombinationPolicy(Enum):
    """How the multi-broker source combines its ordered members per instrument."""

    FAILOVER = "failover"  # first source returning non-empty wins; the rest untouched.
    GAP_FILL = "gap_fill"  # union across ALL sources; higher-priority wins per timestamp.


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
        combination_policy: SourceCombinationPolicy = SourceCombinationPolicy.FAILOVER,
    ) -> None:
        if not ordered_sources:
            raise ValueError(
                "MultiBrokerHistoricalBarSource needs at least one source in priority order"
            )
        self._ordered_sources = ordered_sources
        self._on_source_attempt = on_source_attempt
        self._combination_policy = combination_policy

    def fetch_historical_bars(
        self,
        instrument: Instrument,
        bar_interval: BarInterval,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[PriceBar]:
        if self._combination_policy is SourceCombinationPolicy.GAP_FILL:
            return self._fetch_gap_filled(
                instrument, bar_interval, from_datetime, to_datetime
            )
        return self._fetch_failover(
            instrument, bar_interval, from_datetime, to_datetime
        )

    def _fetch_failover(
        self, instrument, bar_interval, from_datetime, to_datetime
    ) -> list[PriceBar]:
        """First source returning non-empty wins; lower-priority sources untouched."""
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

    def _fetch_gap_filled(
        self, instrument, bar_interval, from_datetime, to_datetime
    ) -> list[PriceBar]:
        """Union across ALL sources: each source fills only timestamps not already
        covered by a higher-priority source (so the primary wins every timestamp it
        has, and each returned bar is wholly from one feed — internally consistent).
        The per-source `served` count is the number of NEW timestamps it contributed."""
        bars_by_timestamp: dict[datetime, PriceBar] = {}
        for named_source in self._ordered_sources:
            try:
                bars = named_source.source.fetch_historical_bars(
                    instrument, bar_interval, from_datetime, to_datetime
                )
            except Exception as error:
                self._record_attempt(
                    named_source.name, instrument, "error", 0, repr(error)
                )
                continue
            if not bars:
                self._record_attempt(named_source.name, instrument, "empty", 0, None)
                continue
            contributed = 0
            for bar in bars:
                if bar.timestamp not in bars_by_timestamp:
                    bars_by_timestamp[bar.timestamp] = bar
                    contributed += 1
            self._record_attempt(
                named_source.name, instrument, "served", contributed, None
            )
        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]

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
