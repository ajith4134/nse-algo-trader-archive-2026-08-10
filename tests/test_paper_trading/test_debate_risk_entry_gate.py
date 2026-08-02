"""Hermetic test for the Layer 11 slice-2c entry-GATE consumer on the paper-loop state
(research/101): the debate risk_score sizes-down / defers entries ONLY once calibration is
earned, and is identity (safe) otherwise. Pure state logic — no LLM, no network.
"""

from __future__ import annotations

from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
    )


def test_gate_is_identity_when_signal_has_not_earned_calibration():
    state = _state()
    state.debate_risk_score_by_mechanism = {"m": 0.95}  # very risky…
    # …but not earned → no effect, and nothing counted
    assert state.debate_risk_size_multiplier("m") == 1.0
    assert state.debate_risk_size_multiplier("absent") == 1.0
    assert state.debate_risk_deferred_count == 0
    assert state.debate_risk_sized_down_count == 0


def test_gate_defers_and_sizes_down_by_risk_band_once_earned():
    state = _state()
    state.debate_risk_calibration_earned = True
    state.debate_risk_score_by_mechanism = {"hi": 0.80, "mid": 0.60, "lo": 0.20}

    assert state.debate_risk_size_multiplier("hi") == 0.0   # ≥ 0.75 → full defer
    assert state.debate_risk_size_multiplier("mid") == 0.5  # ≥ 0.55 → size-down
    assert state.debate_risk_size_multiplier("lo") == 1.0   # below → unchanged
    assert state.debate_risk_size_multiplier("absent") == 1.0  # no thesis → unchanged

    assert state.debate_risk_deferred_count == 1
    assert state.debate_risk_sized_down_count == 1
