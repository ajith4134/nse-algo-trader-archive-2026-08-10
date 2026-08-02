"""Hermetic tests for the Claude-Code-subscription LLM provider (idea #8 slice 0.1).

Exercises the parse + error-mapping + factory behind a DI seam (a fake `sdk_query`) so no real
subscription usage is spent (Rule J). The real end-to-end pass runs under the subscription and is the
documented spike in `docs/research/llm_gateway_spec_2026-08-02.md` §6 (Rule F).
"""

import pytest

from nse_algo_trader.llm_strategy.claude_code_subscription_provider import (
    ClaudeCodeSubscriptionProvider,
    build_claude_code_subscription_provider,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProvider,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmResponseFormatError,
    StrategyLlmRequest,
)

_REQUEST = StrategyLlmRequest(
    system_instruction="You are a terse classifier.",
    user_prompt="Classify sentiment.",
    response_json_schema={"type": "object", "properties": {"label": {"type": "string"}}},
)


class _Block:
    def __init__(self, text: str) -> None:
        self.text = text


class _Msg:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


def _fake_query(reply_text: str = '{"label": "positive"}', raise_exc: Exception | None = None):
    async def query(prompt, options):  # noqa: ARG001 — signature must match the SDK
        if raise_exc is not None:
            raise raise_exc
        yield _Msg(reply_text)
    return query


def _provider(reply_text: str = '{"label": "positive"}', raise_exc: Exception | None = None):
    return ClaudeCodeSubscriptionProvider(sdk_query=_fake_query(reply_text, raise_exc))


def test_satisfies_llm_provider_protocol() -> None:
    assert isinstance(_provider(), LlmProvider)


def test_parses_plain_json() -> None:
    resp = _provider('{"label": "positive"}').generate_structured(_REQUEST)
    assert resp.parsed_output == {"label": "positive"}
    assert resp.served_by_provider == "claude-code-subscription"


def test_parses_json_inside_fences_and_prose() -> None:
    resp = _provider('Sure!\n```json\n{"label": "negative"}\n```\nDone.').generate_structured(_REQUEST)
    assert resp.parsed_output == {"label": "negative"}


def test_bad_json_raises_format_error() -> None:
    with pytest.raises(LlmResponseFormatError):
        _provider("no json here at all").generate_structured(_REQUEST)


def test_cap_signal_maps_to_rate_limit_for_failover() -> None:
    with pytest.raises(LlmRateLimitError):
        _provider(raise_exc=RuntimeError("Claude usage limit reached, resets 7pm")).generate_structured(_REQUEST)


def test_transient_signal_maps_to_unavailable() -> None:
    with pytest.raises(LlmProviderUnavailableError):
        _provider(raise_exc=RuntimeError("connection reset by peer")).generate_structured(_REQUEST)


def test_factory_disabled_returns_none() -> None:
    assert build_claude_code_subscription_provider(env={"CLAUDE_SUBSCRIPTION_DISABLED": "1"}) is None


def test_factory_enabled_by_default() -> None:
    p = build_claude_code_subscription_provider(env={}, sdk_query=_fake_query())
    assert p is not None and p.provider_name == "claude-code-subscription"
