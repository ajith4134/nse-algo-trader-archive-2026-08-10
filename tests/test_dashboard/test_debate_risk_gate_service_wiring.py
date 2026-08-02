"""Hermetic test for the service-level wiring of the Layer 11 slice-2c earn-calibration
(research/101): `_record_debate_risk_observations` persists through the injected store, and
`_refresh_debate_risk_calibration` scores it and pushes the earned flag onto the loop state
(the gate's switch). No LLM, no network — the store path is an injected temp file.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def _service(tmp_path):
    service = LivePaperTradingService(object(), 1_000_000.0)
    service._debate_risk_observation_store_path = tmp_path / "obs.sqlite3"
    return service


def test_empty_store_leaves_the_gate_unearned(tmp_path):
    service = _service(tmp_path)
    service._refresh_debate_risk_calibration()
    assert service._latest_debate_risk_calibration.observation_count == 0
    assert service._state.debate_risk_calibration_earned is False  # gate stays inert


def test_separating_observations_earn_the_gate(tmp_path):
    service = _service(tmp_path)
    when = datetime(2026, 7, 25, 15, 15)
    # low-risk mechanism wins 80% (n=50), high-risk wins 30% (n=50) → separation 0.50
    obs = (
        [("lo", 0.2, True, when)] * 40 + [("lo", 0.2, False, when)] * 10
        + [("hi", 0.9, True, when)] * 15 + [("hi", 0.9, False, when)] * 35
    )
    service._record_debate_risk_observations(obs)
    service._refresh_debate_risk_calibration()

    verdict = service._latest_debate_risk_calibration
    assert verdict.observation_count == 100
    assert verdict.earned is True
    assert service._state.debate_risk_calibration_earned is True  # flips the gate on
