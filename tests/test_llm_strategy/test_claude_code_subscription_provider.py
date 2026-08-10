"""Hermetic tests for the Claude-Code-subscription LLM provider (idea #8 slice 0.1).

Exercises the parse + error-mapping + factory behind a DI seam (a fake `sdk_query`) so no real
subscription usage is spent (Rule J). The real end-to-end pass runs under the subscription and is the
documented spike in `docs/research/llm_gateway_spec_2026-08-02.md` §6 (Rule F).
"""

import pytest

from nse_algo_trader.llm_strategy.claude_code_subscription_provider import (
    _TOKEN_LEDGER,
    ClaudeCodeSubscriptionProvider,
    _extract_text_and_model,
    build_claude_code_subscription_provider,
    subscription_token_ledger,
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


# --- Subscription token ledger (LLM Gateway "tokens consumed" surface) — hermetic, Rule J ---

class _MsgWithUsage:
    """A message stand-in carrying the REAL SDK usage shape, so the extractor's ledger capture runs
    without spending real subscription usage. `usage` is the flat dict the SDK puts on both
    AssistantMessage and ResultMessage (note the nested `server_tool_use` + string `service_tier` that
    must be ignored); `model` and `model_usage` mirror the SDK fields used to resolve the canonical model."""

    def __init__(
        self, usage: dict, text: str | None = None,
        model: str | None = None, model_usage: dict | None = None,
    ) -> None:
        self.content = [_Block(text)] if text is not None else []
        self.usage = usage
        if model is not None:
            self.model = model
        if model_usage is not None:
            self.model_usage = model_usage


def _real_shape_usage(inp: int, out: int, cread: int, cwrite: int) -> dict:
    """The exact flat usage dict the Anthropic API/Agent SDK emits — token ints alongside a nested
    `server_tool_use` dict and a `service_tier` string that the ledger must skip."""
    return {
        "input_tokens": inp, "output_tokens": out,
        "cache_read_input_tokens": cread, "cache_creation_input_tokens": cwrite,
        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
        "service_tier": "standard",
    }


@pytest.fixture(autouse=True)
def _reset_token_ledger():
    """The ledger is a process-wide global; clear it around each test so counts are deterministic."""
    with _TOKEN_LEDGER._lock:
        _TOKEN_LEDGER._by_model.clear()
    yield
    with _TOKEN_LEDGER._lock:
        _TOKEN_LEDGER._by_model.clear()


def test_real_flat_usage_ignores_server_tool_use_and_service_tier() -> None:
    # Regression: real usage carries a nested `server_tool_use` dict + `service_tier` string. The old
    # "any dict value ⇒ per-model" heuristic mis-parsed those and recorded 0 tokens for a real serve.
    _extract_text_and_model([
        _MsgWithUsage(_real_shape_usage(10, 2929, 15263, 3376),
                      text='{"label":"x"}', model="claude-haiku-4-5-20251001"),
    ])
    snap = subscription_token_ledger()
    row = snap["claude-haiku-4-5-20251001"]
    assert row["input"] == 10 and row["output"] == 2929
    assert row["cache_read"] == 15263 and row["cache_creation"] == 3376
    assert row["total"] == 10 + 2929 + 15263 + 3376
    assert row["serves"] == 1 and row["cache_hit_serves"] == 1  # cache_read > 0 → a hit
    assert snap["_all"]["total"] == row["total"]


def test_assistant_and_result_usage_not_double_counted() -> None:
    # One serve emits an AssistantMessage.usage AND a ResultMessage.usage with the SAME per-turn totals.
    # The extractor must record the aggregate ONCE, not twice.
    per_turn = _real_shape_usage(40, 12, 0, 0)
    _extract_text_and_model([
        _MsgWithUsage(per_turn, text='{"label":"x"}', model="claude-haiku-4-5-20251001"),  # assistant
        _MsgWithUsage(per_turn, model_usage={"claude-haiku-4-5-20251001": {  # result
            "inputTokens": 40, "outputTokens": 12, "canonicalModel": "claude-haiku-4-5",
        }}),
    ])
    snap = subscription_token_ledger()
    # model label resolved to the ModelUsage.canonicalModel; counted once (total 52, one serve).
    assert snap["claude-haiku-4-5"]["total"] == 52
    assert snap["claude-haiku-4-5"]["serves"] == 1
    assert snap["_all"]["total"] == 52


def test_multiple_serves_accumulate_and_count_calls() -> None:
    for _ in range(3):
        _extract_text_and_model([
            _MsgWithUsage(_real_shape_usage(5, 7, 100, 0), model="claude-haiku-4-5-20251001"),
        ])
    row = subscription_token_ledger()["claude-haiku-4-5-20251001"]
    assert row["serves"] == 3 and row["cache_hit_serves"] == 3
    assert row["input"] == 15 and row["output"] == 21 and row["cache_read"] == 300


def test_no_usage_message_records_nothing() -> None:
    _extract_text_and_model([_Msg('{"label":"x"}')])
    assert subscription_token_ledger()["_all"]["total"] == 0
    assert subscription_token_ledger()["_all"]["serves"] == 0


def test_real_serve_through_provider_populates_ledger() -> None:
    # End-to-end through generate_structured with a fake SDK message carrying the real usage shape.
    def query_with_usage(reply='{"label":"positive"}'):
        async def q(prompt, options):  # noqa: ARG001
            yield _MsgWithUsage(_real_shape_usage(40, 12, 0, 0), text=reply,
                                model="claude-haiku-4-5-20251001")
        return q

    ClaudeCodeSubscriptionProvider(sdk_query=query_with_usage()).generate_structured(_REQUEST)
    assert subscription_token_ledger()["_all"]["total"] == 52
    assert subscription_token_ledger()["_all"]["serves"] == 1


def test_factory_disabled_returns_none() -> None:
    assert build_claude_code_subscription_provider(env={"CLAUDE_SUBSCRIPTION_DISABLED": "1"}) is None


def test_factory_enabled_by_default() -> None:
    p = build_claude_code_subscription_provider(env={}, sdk_query=_fake_query())
    assert p is not None and p.provider_name == "claude-code-subscription"
