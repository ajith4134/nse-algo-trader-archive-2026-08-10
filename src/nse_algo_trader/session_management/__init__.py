"""Layer 8 — Session / Square-off Management.

Guarantees the no-overnight non-negotiable: every intraday position is
force-squared-off before the 15:30 IST close, and multi-leg square-off is
ordered so a naked, undefined-risk leg is never left open — not even for
one tick (research/07 §D.4). Consumed by the paper loop now and the live
loop later.
"""

from nse_algo_trader.session_management.intraday_square_off_executor import (
    OpenPositionLeg,
    SquareOffConfig,
    SquareOffLegOutcome,
    SquareOffReport,
    build_square_off_order_intents,
    execute_intraday_square_off,
)
from nse_algo_trader.session_management.intraday_square_off_schedule import (
    IntradaySquareOffSchedule,
)

__all__ = [
    "IntradaySquareOffSchedule",
    "OpenPositionLeg",
    "SquareOffConfig",
    "SquareOffLegOutcome",
    "SquareOffReport",
    "build_square_off_order_intents",
    "execute_intraday_square_off",
]
