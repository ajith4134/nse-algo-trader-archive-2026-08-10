"""The shared contract every segment bot and the portfolio supervisor bind to.

This is the load-bearing seam of the 3-bot redesign: each bot (CASH / INDEX-OPTION / STOCK-OPTION) is a
``SegmentBot`` that consumes its own inputs and emits ``TradeProposal``s; the supervisor consumes proposals
from all three, nets correlated exposure, allocates capital, and arbitrates. A bot PROPOSES only — it never
places an order (crypto Feature-Catalogue §03b: "proposes only"; selection/veto lives at the arbiter).

Keeping this a tiny, dependency-free protocol module means the three bots stay genuinely independent (they
share the contract, not each other's code) and the supervisor can be built and tested against fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class MarketSegment(str, Enum):
    """The three segments, one owning bot each."""

    CASH_INTRADAY = "cash_intraday"
    INDEX_OPTION = "index_option"
    STOCK_OPTION = "stock_option"


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"  # market-neutral premium/vol structure (delta ~ 0 at entry)


class OptionStructureKind(str, Enum):
    """The option structures a bot may propose (index/stock option bots)."""

    SINGLE_DIRECTIONAL = "single_directional"  # long call / long put
    VERTICAL_CREDIT_SPREAD = "vertical_credit_spread"
    VERTICAL_DEBIT_SPREAD = "vertical_debit_spread"
    SHORT_STRANGLE = "short_strangle"
    IRON_CONDOR = "iron_condor"
    IRON_FLY = "iron_fly"
    CALENDAR = "calendar"
    ZERO_DTE_GAMMA = "zero_dte_gamma"
    NONE = "none"  # cash bot uses no option structure


@dataclass(frozen=True)
class OptionStructurePlan:
    """A fully specified multi-leg option structure a bot proposes (empty for the cash bot)."""

    kind: OptionStructureKind
    underlying: str
    expiry: str  # ISO date of the traded expiry
    legs: tuple[dict, ...] = ()  # each: {right: CE/PE, strike: float, side: buy/sell, lots: int}
    is_defined_risk: bool = True
    net_delta: float = 0.0
    net_vega: float = 0.0
    net_theta: float = 0.0


@dataclass(frozen=True)
class BotCompetency:
    """A bot's earned track record — the supervisor allocates capital on this (maturity ladder, Rule Q)."""

    level: int  # 0..5; 0 = gathering, 5 = fully earned
    closed_trades: int
    rolling_sharpe: float | None
    calibration_error: float | None  # lower is better (reliability of its calibrated_prob)
    is_earned: bool  # has it cleared its activation threshold?


@dataclass(frozen=True)
class TradeProposal:
    """A bot's decision-grade proposal to the supervisor. A proposal is a PROPOSAL — not an order."""

    segment: MarketSegment
    bot_name: str
    underlying: str
    side: TradeSide
    structure: OptionStructurePlan
    size_hint_lots: int
    conviction: float  # [0,1]
    calibrated_prob: float  # [0,1] calibrated P(favourable outcome)
    expected_expectancy: float  # net-of-cost expected edge (fraction), objective (never win-rate)
    loss_tail_estimate: float  # e.g. CVaR of the loss, for the supervisor's tail budget
    signal_expiry_epoch: float  # after this the proposal is abandoned (crypto §03b signal-expiry)
    regime_label: str
    feature_provenance: dict = field(default_factory=dict)  # evidence trail (SHAP/inputs) — Rule O

    def is_expired(self, now_epoch: float) -> bool:
        return now_epoch >= self.signal_expiry_epoch


@runtime_checkable
class SegmentBot(Protocol):
    """The contract each segment-specialist bot implements; the supervisor depends only on this."""

    name: str
    segment: MarketSegment

    def competency(self) -> BotCompetency:
        """The bot's earned track record — drives competency-weighted capital allocation."""
        ...

    def propose(self, now_epoch: float) -> list[TradeProposal]:
        """Produce this cycle's proposals from the bot's own data + brain (proposes only, never orders)."""
        ...

    def learn_from_closed_trades(self) -> None:
        """Advance the bot's own self-learning loop from its realised closed trades."""
        ...
