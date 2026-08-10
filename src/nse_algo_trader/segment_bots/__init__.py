"""Segment-specialist AI bots + portfolio supervisor (redesign 2026-08-03).

Three fully independent segment bots — CASH intraday, INDEX-OPTION, STOCK-OPTION — each owning its own
data, models, risk sizing, execution policy and self-learning loop, coordinated by one portfolio supervisor
that allocates capital and nets/arbitrates conflicting exposure. Every bot binds to the shared contract in
``segment_bot_protocol`` and PROPOSES trades; only the supervisor + execution seam place orders.

Spec: docs/research/three_segment_bots_spec_2026-08-03.md (+ index_option_bot_engine_spec_2026-08-03.md).
"""

from nse_algo_trader.segment_bots.segment_bot_protocol import (
    BotCompetency,
    MarketSegment,
    OptionStructureKind,
    OptionStructurePlan,
    SegmentBot,
    TradeProposal,
    TradeSide,
)

__all__ = [
    "BotCompetency",
    "MarketSegment",
    "OptionStructureKind",
    "OptionStructurePlan",
    "SegmentBot",
    "TradeProposal",
    "TradeSide",
]
