"""The LOCAL rung's provider, talking Ollama's NATIVE `/api/chat` with grammar-constrained decoding.

Why a native provider instead of reusing `OpenAiCompatibleChatProvider` for local:

* **Constrained decoding.** Ollama's native endpoint accepts `format: <full JSON schema>`, which
  switches on grammar-constrained sampling — the model can only emit tokens that keep the output a
  valid instance of the schema, from the very first token. The OpenAI-compatible `/v1` surface only
  offers `response_format: {"type": "json_object"}`, which *asks* for JSON but does not *constrain*
  it. Constrained decoding removes JSON parse failures on the local rung entirely and slashes output
  tokens (no room for prose/thinking ramble). Verified on `granite4:micro` (design doc
  `docs/research/local_ollama_constrained_decoding_provider_design_2026-07-27.md`).

* **Think-then-answer, inside the contract.** Rather than a separate reasoning round-trip (which
  would couple two rungs and save no tokens), this provider *augments* the caller's schema with a
  short bounded `rationale` field placed FIRST — see `augment_object_schema_with_leading_rationale`.
  Because Ollama emits object keys in schema-declared order, the model is forced to write a brief
  chain-of-thought before the decision, and `maxLength` caps its token spend. The rationale is
  stripped back out of `parsed_output` (downstream sees the schema it asked for) but retained in
  `raw_text` for the decision ledger.

* **Abstain, never hang.** Grammar-constrained sampling on a CPU box can be slow (measured: a
  *reasoning* model did not finish within 8 minutes under `format:`). Every call carries a wall-clock
  timeout; on expiry it raises `LlmProviderUnavailableError` so the pool fails over to the next rung
  rather than stalling a live feature stage. This mirrors the timeout-driven fail-over the cloud
  rungs already get from `requests`.

This provider is used ONLY for the local Ollama rung. Cloud rungs keep `OpenAiCompatibleChatProvider`
— they honour `json_schema`/`json_object` on their own `/v1` surfaces and never suffer Ollama's
reasoning-field diversion, so they need neither the native endpoint nor the rationale injection.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from nse_algo_trader.llm_strategy.openai_compatible_chat_provider import HttpPost
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmResponseFormatError,
    StrategyLlmRequest,
    StrategyLlmResponse,
)

try:  # `requests` is the project's HTTP client; the seam lets tests inject a fake and skip it.
    import requests
except ImportError:  # pragma: no cover - requests is a hard dependency in production
    requests = None  # type: ignore[assignment]

#: Field names that already carry the model's reasoning. If the caller's schema has one of these,
#: the provider does NOT inject its own — the caller already gets think-then-answer for free.
_REASONING_FIELD_NAMES: frozenset[str] = frozenset(
    {"rationale", "reason", "reasoning", "thoughts", "thought", "explanation", "analysis"}
)

#: The field this provider injects when the caller's object schema has no reasoning field of its own.
INJECTED_RATIONALE_FIELD_NAME = "rationale"

#: Cap on the injected rationale, in characters. Enough for a one-to-two sentence chain-of-thought;
#: small enough that constrained decoding cannot burn the token budget on it (the qwen3 failure mode).
DEFAULT_RATIONALE_MAX_CHARS = 240

#: Keep the model resident between calls (Ollama's "never evict" sentinel), so we do not re-pay the
#: cold-start cliff that `pin_local_model_resident` exists to avoid.
_KEEP_RESIDENT_SENTINEL = -1

#: Wall-clock ceiling for one constrained generation. On expiry the provider ABSTAINS (fails over)
#: rather than hanging the caller. Generous because warm constrained decoding on granite is ~5-6 s
#: but a cold or contended box is slower; still far below the 8-minute hang we must never allow.
DEFAULT_NATIVE_REQUEST_TIMEOUT_SECONDS = 90.0


def augment_object_schema_with_leading_rationale(
    response_json_schema: Mapping[str, Any],
    rationale_field_name: str = INJECTED_RATIONALE_FIELD_NAME,
    rationale_max_chars: int = DEFAULT_RATIONALE_MAX_CHARS,
) -> tuple[dict[str, Any], str | None]:
    """Return `(effective_schema, injected_field_or_None)` — the caller's object schema with a short
    bounded reasoning field placed FIRST, so constrained decoding forces think-then-answer.

    Non-destructive and conservative:
      * only augments a well-formed object schema (`type == "object"` with a `properties` dict);
        anything else is passed through untouched (injected field = None);
      * if the schema already carries a reasoning-style field, it is left exactly as-is — the caller
        already asked the model to reason, so we neither duplicate nor reorder;
      * the injected field is prepended to `properties` (dicts preserve insertion order, and Ollama
        emits keys in schema order) and added to `required`, so the model must produce it before the
        decision fields — and `maxLength` bounds its cost.
    """
    if not isinstance(response_json_schema, Mapping):
        return dict(response_json_schema), None
    schema = dict(response_json_schema)
    properties = schema.get("properties")
    if schema.get("type") != "object" or not isinstance(properties, Mapping):
        return schema, None
    existing_field_names = {name.strip().lower() for name in properties}
    if existing_field_names & _REASONING_FIELD_NAMES:
        return schema, None  # caller already reasons; do not touch their contract

    reasoned_properties: dict[str, Any] = {
        rationale_field_name: {
            "type": "string",
            "maxLength": rationale_max_chars,
            "description": (
                "One or two sentences of reasoning for the decision below. Write this FIRST, "
                "then fill the remaining fields consistently with it."
            ),
        }
    }
    reasoned_properties.update(properties)
    schema["properties"] = reasoned_properties

    existing_required = schema.get("required")
    required_names = list(existing_required) if isinstance(existing_required, list) else []
    schema["required"] = [rationale_field_name, *[n for n in required_names if n != rationale_field_name]]
    return schema, rationale_field_name


class NativeOllamaConstrainedChatProvider:
    """One local Ollama endpoint as an `LlmProvider`, driven through native `/api/chat` + `format:`.

    Speaks the exact `LlmProvider` protocol the swappable pool expects (`provider_name`,
    `model_name`, `generate_structured`), so it drops into the pool beside the cloud rungs. Uses the
    same injectable `http_post` seam (`requests.post`-shaped) as the cloud providers, keeping the
    layer's hermetic-test strategy uniform.
    """

    def __init__(
        self,
        provider_name: str,
        root_base_url: str,
        model_name: str,
        http_post: HttpPost | None = None,
        request_timeout_seconds: float = DEFAULT_NATIVE_REQUEST_TIMEOUT_SECONDS,
        rationale_max_chars: int = DEFAULT_RATIONALE_MAX_CHARS,
        keep_alive: int = _KEEP_RESIDENT_SENTINEL,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        #: Native API sits at the server ROOT (`/api/chat`), NOT under the `/v1` OpenAI prefix.
        self._chat_url = root_base_url.rstrip("/") + "/api/chat"
        if http_post is not None:
            self._http_post: HttpPost = http_post
        elif requests is not None:
            self._http_post = requests.post
        else:  # pragma: no cover - only when requests is absent AND no seam injected
            raise RuntimeError("no http_post seam and `requests` is unavailable")
        self._request_timeout_seconds = request_timeout_seconds
        self._rationale_max_chars = rationale_max_chars
        self._keep_alive = keep_alive

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        effective_schema, injected_field = augment_object_schema_with_leading_rationale(
            request.response_json_schema, rationale_max_chars=self._rationale_max_chars
        )
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": request.user_prompt},
            ],
            "stream": False,
            "format": effective_schema,  # <- grammar-constrained decoding
            "keep_alive": self._keep_alive,
            "options": {"num_predict": request.max_output_tokens},
        }
        try:
            response = self._http_post(
                self._chat_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self._request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - includes requests.Timeout/ConnectionError → abstain
            # A timeout here is the ABSTAIN guard doing its job: fail over instead of hanging.
            raise LlmProviderUnavailableError(
                self.provider_name, f"native transport error/timeout: {exc}"
            ) from exc

        self._raise_for_failover_status(response)
        parsed, raw_text = self._parse_native_message(response, injected_field)
        return StrategyLlmResponse(
            parsed_output=parsed,
            served_by_provider=self.provider_name,
            served_by_model=self.model_name,
            raw_text=raw_text,
        )

    def _raise_for_failover_status(self, response: Any) -> None:
        """Translate a non-2xx status into the pool's fail-over exceptions. An on-box loopback server
        rarely rate-limits, but we still honour 429 for symmetry with the cloud rungs; 5xx and other
        4xx become `unavailable` so one bad local state never sinks the pool."""
        status = getattr(response, "status_code", 200)
        if status == 429:
            raise LlmRateLimitError(self.provider_name, "local server reported 429")
        if status >= 500:
            raise LlmProviderUnavailableError(
                self.provider_name, f"local server error (HTTP {status})"
            )
        if status >= 400:
            body_text = getattr(response, "text", "")
            raise LlmProviderUnavailableError(
                self.provider_name, f"local request rejected (HTTP {status}): {body_text[:200]}"
            )

    def _parse_native_message(
        self, response: Any, injected_field: str | None
    ) -> tuple[dict[str, Any], str]:
        """Pull `message.content` from the native envelope, parse the constrained JSON, and strip the
        injected rationale out of the returned object (keeping the full reasoned JSON in `raw_text`).

        Raises `LlmResponseFormatError` on a malformed envelope, a non-JSON body, or an Ollama-level
        `{"error": ...}` payload — so the pool tries another provider rather than trusting garbage.
        """
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            raise LlmResponseFormatError(
                self.provider_name, "native response body was not JSON"
            ) from exc
        if isinstance(body, Mapping) and body.get("error"):
            # Ollama can return 200 with an error field (e.g. model not loaded / bad options).
            raise LlmProviderUnavailableError(
                self.provider_name, f"native server error: {str(body['error'])[:200]}"
            )
        try:
            content = body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LlmResponseFormatError(
                self.provider_name, "native envelope missing message.content"
            ) from exc
        parsed = _parse_json_object_or_none(content)
        if parsed is None:
            raise LlmResponseFormatError(
                self.provider_name, "constrained content was not a JSON object"
            )
        raw_text = content if isinstance(content, str) else json.dumps(parsed)
        if injected_field is not None:
            parsed.pop(injected_field, None)
        return parsed, raw_text


def _parse_json_object_or_none(content: Any) -> dict[str, Any] | None:
    """Parse `content` into a JSON object, or None if it isn't one. Constrained decoding makes this
    all-but-guaranteed to succeed, but we never trust the wire — a stray non-object still fails over."""
    if isinstance(content, Mapping):
        return dict(content)
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None
