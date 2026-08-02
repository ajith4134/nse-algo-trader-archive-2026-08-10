"""Hermetic test for the OpenAI-compatible provider adapter (Rule J): a fake HTTP transport
drives every branch — 200/JSON parse, 429→rate-limit, 5xx→unavailable, fenced-JSON tolerance.
No real network.
"""

from __future__ import annotations

import json

import pytest
import requests

from nse_algo_trader.llm_strategy.openai_compatible_chat_provider import (
    OpenAiCompatibleChatProvider,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    StrategyLlmRequest,
)


class _FakeResponse:
    def __init__(self, status_code, body=None, text="", headers=None):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _chat_body(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _request():
    return StrategyLlmRequest(
        system_instruction="analyse", user_prompt="facts",
        response_json_schema={"type": "object", "properties": {"findings": {}}},
    )


def _provider(fake_post):
    return OpenAiCompatibleChatProvider(
        provider_name="groq", base_url="https://api.groq.com/openai/v1",
        api_key="k", model_name="llama-3.3-70b-versatile", http_post=fake_post,
    )


def test_parses_a_clean_json_object_response():
    captured = {}

    def fake_post(url, headers, json, timeout):  # noqa: A002 - matches requests.post kw
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        return _FakeResponse(200, _chat_body('{"findings": ["a"], "hypotheses": []}'))

    response = _provider(fake_post).generate_structured(_request())

    assert response.parsed_output == {"findings": ["a"], "hypotheses": []}
    assert response.served_by_provider == "groq"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    # The schema is embedded in the system message so schema-less providers still comply.
    assert "findings" in captured["payload"]["messages"][0]["content"]


def test_tolerates_a_markdown_json_fence():
    def fake_post(*_a, **_k):
        return _FakeResponse(200, _chat_body('```json\n{"findings": ["x"]}\n```'))

    response = _provider(fake_post).generate_structured(_request())
    assert response.parsed_output == {"findings": ["x"]}


def test_429_maps_to_rate_limit_with_retry_after():
    def fake_post(*_a, **_k):
        return _FakeResponse(429, text="slow down", headers={"Retry-After": "42"})

    with pytest.raises(LlmRateLimitError) as exc_info:
        _provider(fake_post).generate_structured(_request())
    assert exc_info.value.retry_after_seconds == 42.0


def test_5xx_maps_to_unavailable():
    def fake_post(*_a, **_k):
        return _FakeResponse(503, text="down")

    with pytest.raises(LlmProviderUnavailableError):
        _provider(fake_post).generate_structured(_request())


def test_transport_exception_maps_to_unavailable():
    def fake_post(*_a, **_k):
        raise requests.exceptions.ConnectionError("no route")

    with pytest.raises(LlmProviderUnavailableError):
        _provider(fake_post).generate_structured(_request())


def test_keyless_provider_omits_authorization_header():
    captured = {}

    def fake_post(url, headers, json, timeout):  # noqa: A002
        captured["headers"] = headers
        return _FakeResponse(200, _chat_body('{"findings": []}'))

    provider = OpenAiCompatibleChatProvider(
        provider_name="ovhcloud-ai-endpoints",
        base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        api_key="", model_name="Meta-Llama-3_3-70B-Instruct", http_post=fake_post,
    )
    provider.generate_structured(_request())
    assert "Authorization" not in captured["headers"]  # no `Bearer ` sent when keyless
