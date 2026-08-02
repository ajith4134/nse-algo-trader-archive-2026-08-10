"""Hermetic test for the memory-grounded analyst (Rule J): assert the prompt is built from
the REAL memory read-model facts and the parsed reflection surfaces. No network, no real LLM.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.memory_grounded_strategy_analyst import (
    MemoryGroundedStrategyAnalyst,
    StrategicReflection,
)
from tests.test_llm_strategy.llm_strategy_test_doubles import (
    CapturingFakeLlmClient,
    InMemoryExperienceMemoryStub,
)


def _analyst_with(canned):
    memory = InMemoryExperienceMemoryStub()
    client = CapturingFakeLlmClient(canned_output=canned)
    return MemoryGroundedStrategyAnalyst(client, memory), client, memory


def test_grounding_facts_contain_real_memory_numbers():
    analyst, _, _ = _analyst_with({})
    facts = analyst.build_grounding_facts()
    joined = "\n".join(facts)
    # The worst-calibrated mechanism name + its predicted-vs-actual gap must be present.
    assert "opening_range_breakout" in joined
    assert "predicted win-rate 62% vs actual 41%" in joined
    assert "over-confidence gap +21pp" in joined
    # Regime spread and totals from the real read-model.
    assert "Total graded experiences in memory: 200." in joined
    assert "trending=90" in joined


def test_prompt_carries_the_facts_and_reflection_surfaces():
    canned = {
        "findings": ["ORB is over-confident: predicts 62% but wins 41%."],
        "hypotheses": ["Stops are too tight in trending regimes."],
        "distrust_mechanisms": ["opening_range_breakout"],
    }
    analyst, client, _ = _analyst_with(canned)
    reflection = analyst.reflect()

    # The LLM actually received the grounded facts in its prompt.
    assert client.captured_request is not None
    assert "opening_range_breakout" in client.captured_request.user_prompt
    assert "predicted win-rate 62% vs actual 41%" in client.captured_request.user_prompt

    # The parsed structured reflection surfaces.
    assert isinstance(reflection, StrategicReflection)
    assert reflection.generated is True
    assert reflection.served_by == "fake-provider:fake-model"
    assert reflection.findings == (
        "ORB is over-confident: predicts 62% but wins 41%.",
    )
    assert reflection.distrust_mechanisms == ("opening_range_breakout",)
    # Grounding facts are retained for transparency on the surface.
    assert any("opening_range_breakout" in f for f in reflection.grounding_facts)


def test_reflection_schema_is_forced_on_the_request():
    analyst, client, _ = _analyst_with({"findings": [], "hypotheses": [],
                                        "distrust_mechanisms": []})
    analyst.reflect()
    schema = client.captured_request.response_json_schema
    assert schema["required"] == ["findings", "hypotheses", "distrust_mechanisms"]
    assert schema["additionalProperties"] is False
