"""Signal data model for Layer 4 — what strategies emit, not orders.

A signal is a fully-specified trading intention (instruments, direction,
protective levels, atomic multi-leg grouping) that Layers 5/6 validate
and execute. Multi-leg signals carry all legs in one object so no
downstream step can ever see half a spread (`docs/PLAN.md` §1.3).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from nse_algo_trader.universe_registry import Instrument


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


class OptionLegAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class CreditSpreadBias(str, Enum):
    BULLISH_SELL_PUT_SPREAD = "bull_put"
    BEARISH_SELL_CALL_SPREAD = "bear_call"


@dataclass(frozen=True)
class OpeningRangeBreakoutSignal:
    """Directional breakout of the session's opening range on one instrument."""

    instrument: Instrument
    direction: SignalDirection
    triggered_at: datetime
    breakout_close_price: float  # entry reference = close of the breakout bar
    opening_range_high: float
    opening_range_low: float
    stop_loss_price: float  # opposite side of the opening range
    target_price: float  # entry ± risk*reward multiple
    strategy_tag: str = "opening_range_breakout_v1"


@dataclass(frozen=True)
class OptionLegIntent:
    instrument: Instrument
    action: OptionLegAction
    lots: int


@dataclass(frozen=True)
class CreditSpreadSignal:
    """Defined-risk premium-selling spread: short leg + further-OTM hedge.

    Both legs live in this one object and must be routed as one atomic
    unit — never as two independent orders.
    """

    underlying_symbol: str
    bias: CreditSpreadBias
    short_leg: OptionLegIntent  # the premium-collecting SELL
    hedge_leg: OptionLegIntent  # the protective further-OTM BUY
    short_leg_estimated_delta: float
    strategy_tag: str = "credit_spread_v1"

    def __post_init__(self) -> None:
        if self.short_leg.action is not OptionLegAction.SELL:
            raise ValueError("credit spread short leg must be a SELL")
        if self.hedge_leg.action is not OptionLegAction.BUY:
            raise ValueError("credit spread hedge leg must be a BUY")
        if self.short_leg.lots != self.hedge_leg.lots:
            raise ValueError(
                "credit spread legs must have equal lots (defined-risk pairing)"
            )
