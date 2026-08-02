"""Hermetic test for the synthetic stress-scenario generator (Layer 11 slice 6, research/105;
Rule J): grounding carries the real weakness surface (violated assumption + clustering +
negative-edge), the schema is forced, scenarios parse with clamped severity, and pool exhaustion
is a non-generated rehearsal. No network, no real LLM.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.strategy_llm_client import LlmRateLimitError
from nse_algo_trader.llm_strategy.synthetic_stress_rehearsal import (
    STRESS_REHEARSAL_SCHEMA,
    SyntheticStressRehearsal,
    SyntheticStressScenarioGenerator,
)
from tests.test_llm_strategy.llm_strategy_test_doubles import (
    CapturingFakeLlmClient,
    InMemoryExperienceMemoryStub,
    RoleScriptedFakeLlmClient,
)


def _generator(client):
    return SyntheticStressScenarioGenerator(client, InMemoryExperienceMemoryStub())


def test_grounding_carries_the_real_weakness_surface():
    facts = "\n".join(_generator(CapturingFakeLlmClient({})).build_grounding_facts())
    assert "NEGATIVE edge" in facts  # the stub mechanism has a negative mean return
    assert "VIOLATED assumption 'calibration'" in facts
    assert "fails in CLUSTERS" in facts


def test_prompt_carries_facts_and_scenarios_surface():
    canned = {"scenarios": [{
        "scenario_label": "gap-down fake-out",
        "market_condition": "gap-down open that fakes an ORB breakout then reverts",
        "targeted_mechanism": "opening_range_breakout",
        "predicted_failure_mode": "enters long into a reversal and stops out",
        "mitigation": "require a volume-confirmed retest before entry",
        "severity": 0.8,
    }]}
    client = CapturingFakeLlmClient(canned)
    rehearsal = _generator(client).generate()

    assert "fails in CLUSTERS" in client.captured_request.user_prompt
    assert isinstance(rehearsal, SyntheticStressRehearsal) and rehearsal.generated
    assert rehearsal.served_by == "fake-provider:fake-model"
    assert len(rehearsal.scenarios) == 1
    scenario = rehearsal.scenarios[0]
    assert scenario.targeted_mechanism == "opening_range_breakout"
    assert scenario.severity == 0.8
    assert "reverts" in scenario.market_condition


def test_severity_is_clamped_and_bad_items_skipped():
    canned = {"scenarios": [
        {"scenario_label": "s", "market_condition": "c", "targeted_mechanism": "m",
         "predicted_failure_mode": "f", "mitigation": "x", "severity": 3.0},  # → 1.0
        "not-a-dict",  # skipped
    ]}
    rehearsal = _generator(CapturingFakeLlmClient(canned)).generate()
    assert len(rehearsal.scenarios) == 1
    assert rehearsal.scenarios[0].severity == 1.0


def test_schema_is_forced_on_the_request():
    client = CapturingFakeLlmClient({"scenarios": []})
    _generator(client).generate()
    assert client.captured_request.response_json_schema is STRESS_REHEARSAL_SCHEMA
    assert STRESS_REHEARSAL_SCHEMA["required"] == ["scenarios"]


def test_pool_exhaustion_yields_a_non_generated_rehearsal():
    client = RoleScriptedFakeLlmClient(
        output_by_purpose={}, fail_with=LlmRateLimitError("fake", "pool exhausted")
    )
    rehearsal = _generator(client).generate()
    assert rehearsal.generated is False
    assert rehearsal.scenarios == ()
    assert any("fails in CLUSTERS" in f for f in rehearsal.grounding_facts)
