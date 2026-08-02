"""Hermetic tests for the local rung's native constrained-decoding provider (B33).

The real-server pass is a separate Rule-F step; these bind the FUNCTIONAL contract via an injected
`http_post` fake (Rule J — the fake lives only here, production never selects it):

  * schema augmentation forces think-then-answer (leading, bounded `rationale`) without clobbering a
    caller that already reasons or a non-object schema;
  * the native `/api/chat` payload actually carries `format:<schema>` + resident keep-alive;
  * the injected rationale is stripped from `parsed_output` but retained in `raw_text`;
  * a timeout/transport error ABSTAINS (fails over) rather than hanging;
  * Ollama's error shapes (non-2xx, 200-with-`error`, malformed envelope) map to fail-over errors.
"""

from __future__ import annotations

import json

import pytest

from nse_algo_trader.llm_strategy.native_ollama_constrained_chat_provider import (
    DEFAULT_RATIONALE_MAX_CHARS,
    INJECTED_RATIONALE_FIELD_NAME,
    NativeOllamaConstrainedChatProvider,
    augment_object_schema_with_leading_rationale,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmResponseFormatError,
    StrategyLlmRequest,
)

_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "take_trade": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["take_trade", "confidence"],
    "additionalProperties": False,
}


class _FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = text

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _RecordingHttpPost:
    """Captures the last request and returns a preset response (or raises a preset exception)."""

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.last_url = None
        self.last_json = None
        self.last_timeout = None

    def __call__(self, url, headers=None, json=None, timeout=None):  # noqa: A002 - mirrors requests.post
        self.last_url = url
        self.last_json = json
        self.last_timeout = timeout
        if self._raises is not None:
            raise self._raises
        return self._response


def _native_ok_response(content_obj):
    return _FakeResponse(body={"message": {"role": "assistant", "content": json.dumps(content_obj)}})


def _make_request(schema=None, max_output_tokens=256):
    return StrategyLlmRequest(
        system_instruction="Decide.",
        user_prompt="RELIANCE at 2900, momentum up.",
        response_json_schema=schema if schema is not None else _DECISION_SCHEMA,
        max_output_tokens=max_output_tokens,
    )


def _provider(http_post):
    return NativeOllamaConstrainedChatProvider(
        provider_name="ollama-local",
        root_base_url="http://127.0.0.1:11434",
        model_name="granite4:micro",
        http_post=http_post,
    )


# ----- schema augmentation ------------------------------------------------------------------------


def test_augment_prepends_bounded_rationale_as_the_first_required_field():
    effective, injected = augment_object_schema_with_leading_rationale(_DECISION_SCHEMA)
    assert injected == INJECTED_RATIONALE_FIELD_NAME
    # Ordering is the whole point: rationale must be emitted BEFORE the decision fields.
    assert list(effective["properties"])[0] == INJECTED_RATIONALE_FIELD_NAME
    assert effective["required"][0] == INJECTED_RATIONALE_FIELD_NAME
    assert effective["properties"][INJECTED_RATIONALE_FIELD_NAME]["maxLength"] == DEFAULT_RATIONALE_MAX_CHARS
    # Original decision fields are preserved, not dropped.
    assert "take_trade" in effective["properties"] and "confidence" in effective["properties"]
    assert set(effective["required"]) == {"rationale", "take_trade", "confidence"}


def test_augment_leaves_a_schema_that_already_reasons_untouched():
    already = {
        "type": "object",
        "properties": {"reason": {"type": "string"}, "take_trade": {"type": "boolean"}},
        "required": ["reason", "take_trade"],
    }
    effective, injected = augment_object_schema_with_leading_rationale(already)
    assert injected is None
    assert effective["properties"] == already["properties"]


def test_augment_passes_non_object_schemas_through_untouched():
    array_schema = {"type": "array", "items": {"type": "string"}}
    effective, injected = augment_object_schema_with_leading_rationale(array_schema)
    assert injected is None
    assert effective == array_schema


def test_augment_does_not_mutate_the_callers_schema():
    original = json.loads(json.dumps(_DECISION_SCHEMA))
    augment_object_schema_with_leading_rationale(_DECISION_SCHEMA)
    assert _DECISION_SCHEMA == original  # the caller's dict is not modified in place


# ----- the native call ----------------------------------------------------------------------------


def test_payload_carries_constrained_format_and_resident_keepalive():
    http = _RecordingHttpPost(response=_native_ok_response({"rationale": "up", "take_trade": True, "confidence": 0.6}))
    _provider(http).generate_structured(_make_request(max_output_tokens=321))
    assert http.last_url == "http://127.0.0.1:11434/api/chat"
    sent = http.last_json
    assert sent["stream"] is False
    assert sent["keep_alive"] == -1
    assert sent["options"]["num_predict"] == 321
    # The schema handed to Ollama is the AUGMENTED one, and it is a full schema object (constrained).
    assert sent["format"]["type"] == "object"
    assert list(sent["format"]["properties"])[0] == INJECTED_RATIONALE_FIELD_NAME


def test_injected_rationale_is_stripped_from_parsed_but_kept_in_raw_text():
    http = _RecordingHttpPost(
        response=_native_ok_response({"rationale": "momentum up", "take_trade": True, "confidence": 0.7})
    )
    result = _provider(http).generate_structured(_make_request())
    assert result.parsed_output == {"take_trade": True, "confidence": 0.7}  # rationale stripped
    assert "momentum up" in result.raw_text  # ...but retained for the decision ledger
    assert result.served_by_provider == "ollama-local"
    assert result.served_by_model == "granite4:micro"


def test_caller_supplied_reasoning_field_is_returned_not_stripped():
    schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}, "take_trade": {"type": "boolean"}},
        "required": ["reason", "take_trade"],
    }
    http = _RecordingHttpPost(response=_native_ok_response({"reason": "breakout", "take_trade": True}))
    result = _provider(http).generate_structured(_make_request(schema=schema))
    assert result.parsed_output == {"reason": "breakout", "take_trade": True}


def test_timeout_abstains_by_failing_over_instead_of_hanging():
    class _Timeout(Exception):
        pass

    http = _RecordingHttpPost(raises=_Timeout("read timed out"))
    with pytest.raises(LlmProviderUnavailableError):
        _provider(http).generate_structured(_make_request())


def test_ollama_200_with_error_body_fails_over():
    http = _RecordingHttpPost(response=_FakeResponse(body={"error": "model requires more system memory"}))
    with pytest.raises(LlmProviderUnavailableError):
        _provider(http).generate_structured(_make_request())


def test_server_5xx_fails_over_and_429_is_a_rate_limit():
    with pytest.raises(LlmProviderUnavailableError):
        _provider(_RecordingHttpPost(response=_FakeResponse(status_code=503, text="boom"))).generate_structured(
            _make_request()
        )
    with pytest.raises(LlmRateLimitError):
        _provider(_RecordingHttpPost(response=_FakeResponse(status_code=429))).generate_structured(
            _make_request()
        )


def test_malformed_envelope_is_a_format_error():
    http = _RecordingHttpPost(response=_FakeResponse(body={"unexpected": "shape"}))
    with pytest.raises(LlmResponseFormatError):
        _provider(http).generate_structured(_make_request())


def test_non_json_content_is_a_format_error():
    http = _RecordingHttpPost(response=_FakeResponse(body={"message": {"content": "not json at all"}}))
    with pytest.raises(LlmResponseFormatError):
        _provider(http).generate_structured(_make_request())
