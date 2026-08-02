"""Hermetic test for the prediction-market council (Layer 11 slice 5, research/104; Rule J):
each role forecasts independently from the real grounding, probabilities clamp, the aggregate is
the track-record-weighted mean (equal → simple mean), the pure weighting tilts toward accurate
roles, and pool exhaustion is a non-generated forecast. No network, no real LLM.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.llm_strategy.prediction_council import (
    COUNCIL_FORECAST_SCHEMA,
    CouncilForecast,
    PredictionCouncil,
    track_record_weights,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import LlmRateLimitError
from tests.test_llm_strategy.llm_strategy_test_doubles import (
    InMemoryExperienceMemoryStub,
    RoleScriptedFakeLlmClient,
)

_ROLES = ["momentum", "mean_reversion", "regime_realist", "risk_officer"]


def _forecast(probability):
    return {"probability": probability, "rationale": "r"}


def _council(output_by_purpose=None, default_output=None, fail_with=None, store=None):
    client = RoleScriptedFakeLlmClient(
        output_by_purpose=output_by_purpose or {},
        default_output=default_output or _forecast(0.5),
        fail_with=fail_with,
    )
    return PredictionCouncil(client, InMemoryExperienceMemoryStub(), store), client


# ----- pure track-record weighting -----


def test_weights_are_equal_when_no_role_has_a_record():
    weights = track_record_weights({}, _ROLES)
    assert weights == pytest.approx({r: 0.25 for r in _ROLES})


def test_weights_tilt_toward_the_lower_log_loss_role():
    # momentum sharp (0.3 bits), risk poor (2.0 bits); others unproven (baseline 1.0)
    weights = track_record_weights(
        {"momentum": 0.3, "risk_officer": 2.0}, _ROLES
    )
    assert weights["momentum"] > weights["regime_realist"] > weights["risk_officer"]
    assert sum(weights.values()) == pytest.approx(1.0)


# ----- the council -----


def test_each_role_forecasts_independently_from_the_grounding():
    council, client = _council()
    council.forecast("prop", "Will X win its next trade?")
    assert [r.purpose for r in client.captured_requests] == [
        f"prediction_council_{role}" for role in _ROLES
    ]
    for request in client.captured_requests:
        assert "opening_range_breakout" in request.user_prompt  # real grounding fact
        assert "Will X win its next trade?" in request.user_prompt


def test_aggregate_equals_simple_mean_when_weights_are_equal():
    council, _ = _council(output_by_purpose={
        "prediction_council_momentum": _forecast(0.8),
        "prediction_council_mean_reversion": _forecast(0.2),
        "prediction_council_regime_realist": _forecast(0.6),
        "prediction_council_risk_officer": _forecast(0.4),
    })
    forecast = council.forecast("prop", "q")
    assert isinstance(forecast, CouncilForecast) and forecast.generated
    assert len(forecast.member_forecasts) == 4
    assert forecast.simple_mean_probability == pytest.approx(0.5)
    assert forecast.weighted_probability == pytest.approx(0.5)  # equal weights → == mean
    assert forecast.is_reputation_tilted is False


def test_probability_is_clamped_to_unit_interval():
    council, _ = _council(default_output=_forecast(1.7))
    forecast = council.forecast("prop", "q")
    assert all(m.probability == 1.0 for m in forecast.member_forecasts)


def test_pool_exhaustion_yields_a_non_generated_forecast():
    council, _ = _council(fail_with=LlmRateLimitError("fake", "pool exhausted"))
    forecast = council.forecast("prop", "q")
    assert forecast.generated is False
    assert "momentum" in forecast.note  # first role that hit the exhausted pool
    assert any("opening_range_breakout" in f for f in forecast.grounding_facts)


def test_forecast_schema_is_forced():
    council, client = _council()
    council.forecast("prop", "q")
    for request in client.captured_requests:
        assert request.response_json_schema is COUNCIL_FORECAST_SCHEMA
    assert COUNCIL_FORECAST_SCHEMA["required"] == ["probability", "rationale"]
