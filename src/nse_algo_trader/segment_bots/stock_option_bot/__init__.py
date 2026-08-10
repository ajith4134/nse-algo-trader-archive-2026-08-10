"""STOCK-OPTION segment bot — the second of the three segment-specialist bots.

Owns the full NSE single-stock option (F&O) universe (~211 underlyings). Distinct from the index bot: it is
single-name and EVENT-driven (earnings vol-crush), with per-name IV-rank premium selling, skew/risk-
reversal, and option-flow (PCR / unusual vol-OI) signals. It REUSES the index bot's IV-surface, vol-regime
and learned-head engines (own instances + own stores → choice-B independence at the model level) and adds
the stock-specific brains here.

Spec: docs/research/three_segment_bots_spec_2026-08-03.md (§3 STOCK-OPT row + §7).
"""

from nse_algo_trader.segment_bots.stock_option_bot.event_calendar_gate import (
    EventCalendarSource,
    EventProximity,
    EventProximityGate,
)
from nse_algo_trader.segment_bots.stock_option_bot.option_flow_signals import (
    OptionFlowEngine,
    OptionFlowState,
    PcrHistoryStore,
)
from nse_algo_trader.segment_bots.stock_option_bot.stock_option_bot import StockOptionBot
from nse_algo_trader.segment_bots.stock_option_bot.stock_option_structure_selector import (
    StockOptionStructureSelector,
)

__all__ = [
    "EventCalendarSource",
    "EventProximity",
    "EventProximityGate",
    "OptionFlowEngine",
    "OptionFlowState",
    "PcrHistoryStore",
    "StockOptionBot",
    "StockOptionStructureSelector",
]
