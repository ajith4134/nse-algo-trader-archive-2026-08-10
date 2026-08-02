"""Hermetic test for the Layer 7.5 slice-4 lab summaries (research/108): profit-provenance
decomposition vs the control arms, and the trade-independent world-model scoreboard. Pure, no I/O.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.memory_reflection.experience_memory import (
    MarketRegimeCalibration,
    PrequentialForecastScore,
)
from nse_algo_trader.paper_trading.control_arm_comparison import (
    ControlArmComparison,
    ControlArmStats,
)
from nse_algo_trader.paper_trading.profit_provenance import decompose_profit_provenance
from nse_algo_trader.paper_trading.shadow_rejected_arm import (
    ArmPerformance,
    ShadowRejectedAnalysis,
)
from nse_algo_trader.paper_trading.world_model_scoreboard import score_world_model


def _comparison(real_total, random_total):
    real = ControlArmStats("real", 15, 0.7, 0.01, real_total, 0.9)
    rnd = ControlArmStats("random", 15, 0.5, 0.0, random_total, 0.1)
    return ControlArmComparison(real=real, random_control=rnd, has_edge=True, verdict="v")


def _shadow(rejection_adds_skill, rejected_mean):
    taken = ArmPerformance("taken", 3, 200, 0.5, 0.0)
    rejected = ArmPerformance("shadow-rejected", 2, 100, 0.3, rejected_mean)
    return ShadowRejectedAnalysis(taken, rejected, rejection_adds_skill, "detail")


# ----- profit provenance -----


def test_provenance_splits_luck_and_directional_skill():
    prov = decompose_profit_provenance(
        _comparison(real_total=0.12, random_total=0.02), _shadow(True, -0.03)
    )
    assert prov.total_real_return == 0.12
    assert prov.luck_baseline == 0.02
    assert round(prov.directional_skill, 4) == 0.10  # 0.12 - 0.02
    assert prov.gate_avoided_loss_per_trade == 0.03  # refused a -3% mechanism → saved +3%
    assert prov.dominant_source == "directional skill"


def test_provenance_flags_luck_dominant_when_skill_is_small():
    prov = decompose_profit_provenance(
        _comparison(real_total=0.09, random_total=0.08), _shadow(None, 0.0)
    )
    assert prov.dominant_source == "luck baseline"  # skill 0.01 < luck 0.08
    assert prov.gate_avoided_loss_per_trade is None


# ----- world-model scoreboard -----


class _MemoryStub:
    def __init__(self, log_loss, regime_hit_rates):
        self._log_loss = log_loss
        self._regimes = regime_hit_rates

    def prequential_forecast_score(self, data_provenance=None):
        return PrequentialForecastScore(
            experiment_count=200, mean_log_loss_bits=self._log_loss, mean_brier=0.24
        )

    def calibration_by_market_regime(self, strategy_tag=None, minimum_experiments=1):
        return [
            MarketRegimeCalibration(r, 50, hr, 0.25, 0.0)
            for r, hr in self._regimes.items()
        ]


def test_world_model_informative_when_forecast_beats_coinflip_and_regimes_resolve():
    wm = score_world_model(_MemoryStub(0.85, {"trending": 0.6, "range": 0.4}))
    assert wm.forecast_log_loss_bits == 0.85
    assert wm.regime_resolution == pytest.approx(0.2)  # 0.6 - 0.4 spread
    assert wm.world_model_informative is True
    assert "INFORMATIVE" in wm.verdict


def test_world_model_not_informative_when_forecast_is_coinflip():
    wm = score_world_model(_MemoryStub(1.1, {"trending": 0.6, "range": 0.4}))
    assert wm.world_model_informative is False  # 1.1 bits ≥ coin flip
    assert "NOT yet informative" in wm.verdict


def test_world_model_regime_noise_is_not_informative():
    wm = score_world_model(_MemoryStub(0.8, {"trending": 0.50, "range": 0.51}))
    assert wm.regime_resolution < 0.05
    assert wm.world_model_informative is False  # forecast good but regime label is noise
