"""Hermetic test for the causal-cluster analyst (Layer 11 slice 3, research/102; Rule J):
the prompt is built from the REAL multi-hop cluster facts (over-confidence + cross-regime +
temporal clustering + violated assumptions), the schema is forced, the parsed hypotheses
surface, and pool exhaustion is a non-generated analysis. No network, no real LLM.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.causal_cluster_analyst import (
    CAUSAL_ANALYSIS_SCHEMA,
    CausalClusterAnalysis,
    CausalClusterAnalyst,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import LlmRateLimitError
from tests.test_llm_strategy.llm_strategy_test_doubles import (
    CapturingFakeLlmClient,
    InMemoryExperienceMemoryStub,
    RoleScriptedFakeLlmClient,
)


def _analyst(client):
    return CausalClusterAnalyst(client, InMemoryExperienceMemoryStub())


def test_grounding_facts_contain_the_real_cluster_numbers():
    facts = "\n".join(_analyst(CapturingFakeLlmClient({})).build_grounding_facts())
    # over-confident calibration board row
    assert "predicted 62% vs actual 41%" in facts
    # cross-regime cohort
    assert "Regime 'trending'" in facts
    # temporal multi-hop clustering (non-iid)
    assert "CLUSTERS in time" in facts and "dependence gap +27%" in facts
    # a violated statistical assumption (the 'what' the causal 'why' explains)
    assert "VIOLATED assumption 'calibration'" in facts


def test_prompt_carries_facts_and_hypotheses_surface():
    canned = {"hypotheses": [{
        "cluster_label": "post-loss ORB failures",
        "implicated_mechanisms": ["opening_range_breakout"],
        "suspected_common_cause": "stops too tight after a losing streak in trends",
        "falsifiable_prediction": "widening stops post-loss lifts post-loss win-rate",
        "confidence": 0.7,
    }]}
    client = CapturingFakeLlmClient(canned)
    analysis = _analyst(client).analyze()

    assert "CLUSTERS in time" in client.captured_request.user_prompt
    assert isinstance(analysis, CausalClusterAnalysis) and analysis.generated
    assert analysis.served_by == "fake-provider:fake-model"
    assert len(analysis.hypotheses) == 1
    hypothesis = analysis.hypotheses[0]
    assert hypothesis.implicated_mechanisms == ("opening_range_breakout",)
    assert hypothesis.confidence == 0.7
    assert "stops too tight" in hypothesis.suspected_common_cause


def test_confidence_is_clamped_and_bad_items_skipped():
    canned = {"hypotheses": [
        {"cluster_label": "c", "implicated_mechanisms": [], "suspected_common_cause": "x",
         "falsifiable_prediction": "y", "confidence": 1.8},   # clamps to 1.0
        "not-a-dict",                                          # skipped
    ]}
    analysis = _analyst(CapturingFakeLlmClient(canned)).analyze()
    assert len(analysis.hypotheses) == 1
    assert analysis.hypotheses[0].confidence == 1.0


def test_schema_is_forced_on_the_request():
    client = CapturingFakeLlmClient({"hypotheses": []})
    _analyst(client).analyze()
    assert client.captured_request.response_json_schema is CAUSAL_ANALYSIS_SCHEMA
    assert CAUSAL_ANALYSIS_SCHEMA["required"] == ["hypotheses"]


def test_pool_exhaustion_yields_a_non_generated_analysis():
    client = RoleScriptedFakeLlmClient(
        output_by_purpose={}, fail_with=LlmRateLimitError("fake", "pool exhausted")
    )
    analysis = _analyst(client).analyze()
    assert analysis.generated is False
    assert analysis.hypotheses == ()
    # grounding facts retained for transparency even on the blocked path
    assert any("CLUSTERS in time" in f for f in analysis.grounding_facts)
