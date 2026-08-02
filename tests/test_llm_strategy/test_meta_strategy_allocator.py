"""Hermetic test for the meta-strategy allocator (Layer 11 slice 4, research/103; Rule J):
grounding carries the per-strategy aggregate + champion config, the schema is forced, the LLM's
weights are re-normalised to sum 1 (even when un-normalised / negative / degenerate), and pool
exhaustion is a non-generated allocation. No network, no real LLM.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.llm_strategy.meta_strategy_allocator import (
    META_ALLOCATION_SCHEMA,
    MetaStrategyAllocation,
    MetaStrategyAllocator,
    _normalised_weights,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import LlmRateLimitError
from tests.test_llm_strategy.llm_strategy_test_doubles import (
    CapturingFakeLlmClient,
    InMemoryExperienceMemoryStub,
    RoleScriptedFakeLlmClient,
)


class _FakeChampionStore:
    def load_champion_or_default(self, market_regime=None):
        class _Config:
            opening_range_minutes = 20
            target_risk_reward_ratio = 2.5

        return _Config()


def _allocator(client, champion_store=None):
    return MetaStrategyAllocator(client, InMemoryExperienceMemoryStub(), champion_store)


def test_grounding_carries_per_strategy_aggregate_and_champion_config():
    facts = "\n".join(
        _allocator(CapturingFakeLlmClient({}), _FakeChampionStore()).build_grounding_facts()
    )
    assert "Strategy 'orb' (n=120)" in facts  # aggregated up from the mechanism rows
    assert "actual win-rate 41%" in facts
    assert "Current global champion ORB config: opening range 20m, target reward 2.5R." in facts


def test_llm_weights_are_renormalised_to_sum_one():
    canned = {"allocations": [
        {"strategy_tag": "a", "weight": 2.0, "rationale": "strong"},
        {"strategy_tag": "b", "weight": 1.0, "rationale": "ok"},
        {"strategy_tag": "c", "weight": 1.0, "rationale": "weak"},
    ], "overall_rationale": "lean into a"}
    allocation = _allocator(CapturingFakeLlmClient(canned)).allocate()

    assert isinstance(allocation, MetaStrategyAllocation) and allocation.generated
    weights = allocation.weight_by_strategy()
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["a"] == pytest.approx(0.5)
    assert weights["b"] == pytest.approx(0.25)
    assert allocation.overall_rationale == "lean into a"


def test_normalisation_clamps_negatives_and_handles_degenerate():
    # negative weight clamps to 0, the rest re-normalise
    w = {x.strategy_tag: x.weight for x in _normalised_weights(
        [{"strategy_tag": "a", "weight": -5}, {"strategy_tag": "b", "weight": 3}]
    )}
    assert w == {"a": 0.0, "b": 1.0}
    # all-zero → equal split (still a valid allocation)
    w2 = {x.strategy_tag: x.weight for x in _normalised_weights(
        [{"strategy_tag": "a", "weight": 0}, {"strategy_tag": "b", "weight": 0}]
    )}
    assert w2 == {"a": 0.5, "b": 0.5}
    assert _normalised_weights("not-a-list") == ()


def test_schema_is_forced_on_the_request():
    client = CapturingFakeLlmClient({"allocations": [], "overall_rationale": ""})
    _allocator(client).allocate()
    assert client.captured_request.response_json_schema is META_ALLOCATION_SCHEMA
    assert META_ALLOCATION_SCHEMA["required"] == ["allocations", "overall_rationale"]


def test_pool_exhaustion_yields_a_non_generated_allocation():
    client = RoleScriptedFakeLlmClient(
        output_by_purpose={}, fail_with=LlmRateLimitError("fake", "pool exhausted")
    )
    allocation = _allocator(client).allocate()
    assert allocation.generated is False
    assert allocation.weights == ()
    assert any("Strategy 'orb'" in f for f in allocation.grounding_facts)
