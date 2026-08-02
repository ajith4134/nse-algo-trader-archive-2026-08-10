"""Hermetic test for the instrumental-convergence limiter (Trunk VII; research/117): permits under
the sprawl cap, blocks at the cap (resource acquisition), and blocks while halted (off-switch
dominance) even under the cap; the state gate enforces + counts. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
from nse_algo_trader.conscience.instrumental_convergence_limiter import (
    ConvergenceLimits,
    assess_convergence,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def test_permits_under_cap():
    v = assess_convergence(open_exposure_count=10, is_halted=False, limits=ConvergenceLimits(400))
    assert v.permit and v.breached == ""


def test_blocks_at_cap_resource_acquisition():
    v = assess_convergence(open_exposure_count=400, is_halted=False, limits=ConvergenceLimits(400))
    assert not v.permit and v.breached == "resource_acquisition"


def test_off_switch_dominance_blocks_even_under_cap():
    v = assess_convergence(open_exposure_count=1, is_halted=True, limits=ConvergenceLimits(400))
    assert not v.permit and v.breached == "off_switch_dominance"


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )


def test_state_gate_permits_normally_and_blocks_when_halted():
    state = _state()
    assert state.convergence_limiter_permits_order() is True  # empty book, not halted
    state.corrigibility_switch = CorrigibilitySwitch()
    state.corrigibility_switch.halt("test")
    assert state.convergence_limiter_permits_order() is False  # off-switch dominance
    assert state.convergence_limiter_blocked_order_count == 1
