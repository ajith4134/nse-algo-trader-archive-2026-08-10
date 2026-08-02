"""Hermetic test for the swap-on-limit orchestrator (Rule J): a rate-limited provider hands
off to the next; cooldowns are respected on a fake clock; an all-exhausted pool raises.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    StrategyLlmRequest,
)
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    AllLlmProvidersExhausted,
    SwappableMultiProviderLlmClient,
)
from tests.test_llm_strategy.llm_strategy_test_doubles import ScriptedLlmProvider


def _request():
    return StrategyLlmRequest(
        system_instruction="s", user_prompt="u",
        response_json_schema={"type": "object"},
    )


class _FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_fails_over_to_next_provider_on_rate_limit():
    primary = ScriptedLlmProvider("groq", "m1", [LlmRateLimitError("groq", "429")])
    backup = ScriptedLlmProvider("cerebras", "m2", [{"ok": True}])
    client = SwappableMultiProviderLlmClient([primary, backup], monotonic_clock=_FakeClock())

    response = client.generate_structured(_request())

    assert response.served_by_provider == "cerebras"
    assert response.parsed_output == {"ok": True}
    # The rate-limited primary was tried (and then skipped on cooldown).
    assert len(primary.calls) == 1


def test_rate_limited_provider_is_on_cooldown_until_it_expires():
    clock = _FakeClock()
    primary = ScriptedLlmProvider(
        "groq", "m1",
        [LlmRateLimitError("groq", "429", retry_after_seconds=30), {"recovered": True}],
    )
    backup = ScriptedLlmProvider("cerebras", "m2", [{"from": "backup"}, {"from": "backup"}])
    client = SwappableMultiProviderLlmClient([primary, backup], monotonic_clock=clock)

    first = client.generate_structured(_request())
    assert first.served_by_provider == "cerebras"  # primary rate-limited

    # Still within the 30s cooldown → primary skipped again.
    clock.t += 10
    second = client.generate_structured(_request())
    assert second.served_by_provider == "cerebras"
    assert len(primary.calls) == 1  # not retried during cooldown

    # After the cooldown, primary is tried again and recovers.
    clock.t += 30
    third = client.generate_structured(_request())
    assert third.served_by_provider == "groq"
    assert third.parsed_output == {"recovered": True}


def test_all_providers_exhausted_raises_with_reasons():
    a = ScriptedLlmProvider("groq", "m1", [LlmRateLimitError("groq", "429")])
    b = ScriptedLlmProvider("cerebras", "m2", [LlmProviderUnavailableError("cerebras", "500")])
    client = SwappableMultiProviderLlmClient([a, b], monotonic_clock=_FakeClock())

    with pytest.raises(AllLlmProvidersExhausted) as exc_info:
        client.generate_structured(_request())
    assert set(exc_info.value.failures) == {"groq", "cerebras"}


def test_describe_pool_reports_configured_and_serving():
    a = ScriptedLlmProvider("groq", "m1", [{"ok": 1}])
    b = ScriptedLlmProvider("cerebras", "m2", [])
    client = SwappableMultiProviderLlmClient([a, b], monotonic_clock=_FakeClock())
    client.generate_structured(_request())

    status = client.describe_pool()
    assert status.configured_count == 2
    assert status.last_served_by == "groq"
    assert [p.provider_name for p in status.providers] == ["groq", "cerebras"]
