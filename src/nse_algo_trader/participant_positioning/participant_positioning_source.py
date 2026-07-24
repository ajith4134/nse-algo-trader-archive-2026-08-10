"""The swappable seam for NSE participant-wise positioning data.

NSE publishes a daily end-of-day report of open interest split by market
participant category — Client (retail) / DII / FII / Pro — across index &
stock futures and options. This module defines the *shape* of that data and
the `ParticipantPositioningSource` protocol every provider implements, with
zero network code, so read models and tests can depend on it directly.

Production wires the real `NseParticipantPositioningSource` (which fetches the
archived CSV); tests inject an in-memory fake behind this same protocol
(Rule J DI seam) — the fake lives only under tests/ and never reaches the live
path.

The four participant categories and their meaning as an "opponent ledger"
(who is on the other side) are documented in docs/research/47.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


class ParticipantCategory:
    """The exact `Client Type` labels NSE uses in the participant report.
    TOTAL is the market-clearing checksum row (Long == Short), not a party."""

    CLIENT = "Client"
    DII = "DII"
    FII = "FII"
    PRO = "Pro"
    TOTAL = "TOTAL"

    TRADING_PARTIES = (CLIENT, DII, FII, PRO)


@dataclass(frozen=True)
class ParticipantOpenInterestRow:
    """One participant category's open-interest contract counts for a day —
    the 14 numeric columns of the NSE `fao_participant_oi` report, named so
    each field's meaning is clear without the CSV header."""

    client_type: str
    future_index_long: int
    future_index_short: int
    future_stock_long: int
    future_stock_short: int
    option_index_call_long: int
    option_index_put_long: int
    option_index_call_short: int
    option_index_put_short: int
    option_stock_call_long: int
    option_stock_put_long: int
    option_stock_call_short: int
    option_stock_put_short: int
    total_long_contracts: int
    total_short_contracts: int

    @property
    def future_index_net_long(self) -> int:
        """Long − short in index futures — the cleanest directional read."""
        return self.future_index_long - self.future_index_short

    @property
    def index_options_net_call_bias(self) -> int:
        """Net call-minus-put long exposure in index options; positive = this
        party is leaning bullish via options (long calls / short puts)."""
        return (
            self.option_index_call_long
            + self.option_index_put_short
            - self.option_index_put_long
            - self.option_index_call_short
        )


@dataclass(frozen=True)
class ParticipantPositioningSnapshot:
    """A full participant-wise OI report for one trade date: the four trading
    parties (plus the TOTAL checksum row) keyed by category."""

    report_date: date
    rows_by_category: dict[str, ParticipantOpenInterestRow]

    def row_for(self, category: str) -> ParticipantOpenInterestRow | None:
        return self.rows_by_category.get(category)


class ParticipantPositioningSource(Protocol):
    """Anything that can supply a day's participant positioning — the real NSE
    archive fetcher in production, an in-memory fake in tests. Returns None
    when no report exists for that date (holiday / not yet published).

    `positioning_on` serves the OPEN-INTEREST report (positions held);
    `volume_on` serves the same-schema TRADING-VOLUME report (contracts traded
    that day) used to gauge how actively a party is trading its book."""

    def positioning_on(
        self, trade_date: date
    ) -> ParticipantPositioningSnapshot | None: ...

    def volume_on(
        self, trade_date: date
    ) -> ParticipantPositioningSnapshot | None: ...
