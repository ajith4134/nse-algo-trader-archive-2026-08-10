"""A single free-tier cloud LLM behind the `LlmProvider` seam, via the OpenAI-compatible
`/chat/completions` wire format (Layer 11; research/96).

Most free-tier clouds the user supplied — Groq, Cerebras, SambaNova, NVIDIA, Google AI
Studio (Gemini's OpenAI-compat endpoint), OpenRouter, DeepInfra, Fireworks, Hugging Face
router, Z.ai, DeepSeek, Alibaba DashScope, Cloudflare Workers AI — all speak the SAME
`POST {base_url}/chat/completions` shape with a `Bearer` key, so ONE adapter covers them
all; only base_url + model + key differ (llm_provider_registry.py wires those from .env).

Structured output is forced two ways at once (belt-and-suspenders across providers that vary
in support): `response_format={"type":"json_object"}` AND an explicit "reply with ONLY JSON
matching this schema" instruction carrying the schema. The reply's message content is parsed
as JSON. HTTP status is translated into the seam's exception hierarchy so the swappable pool
knows whether to fail over (429 → rate-limit cooldown; 5xx/timeout → unavailable).

Uses `requests` (already a project dependency) via an INJECTED `http_post` so tests drive it
with a fake transport — no real network in unit tests (Rule J).
"""

from __future__ import annotations

import json
from typing import Callable

import requests

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmResponseFormatError,
    StrategyLlmRequest,
    StrategyLlmResponse,
)

# The transport shape the adapter depends on (real: requests.post). Injected so tests supply
# a fake that returns canned responses without touching the network.
HttpPost = Callable[..., "requests.Response"]


class OpenAiCompatibleChatProvider:
    """One OpenAI-compatible chat endpoint as an `LlmProvider`. Construct one per vendor with
    its base_url/model/api_key; the swappable pool holds many and rotates on rate-limit."""

    def __init__(
        self,
        provider_name: str,
        base_url: str,
        api_key: str,
        model_name: str,
        request_timeout_seconds: float = 45.0,
        http_post: HttpPost | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self._chat_completions_url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._request_timeout_seconds = request_timeout_seconds
        self._http_post = http_post or requests.post
        self._extra_headers = dict(extra_headers or {})

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        system_text = (
            request.system_instruction
            + "\n\nReply with ONLY a single JSON object — no prose, no markdown fences — "
            + "that validates against this JSON schema:\n"
            + json.dumps(request.response_json_schema)
        )
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:  # keyless providers (e.g. OVHcloud anon tier) send no Bearer header
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = self._http_post(
                self._chat_completions_url,
                headers=headers,
                json=payload,
                timeout=self._request_timeout_seconds,
            )
        except requests.exceptions.RequestException as exc:  # timeout, connection, etc.
            raise LlmProviderUnavailableError(
                self.provider_name, f"transport error: {exc}"
            ) from exc

        self._raise_for_failover_status(response)
        parsed, raw_text = self._parse_first_choice(response)
        return StrategyLlmResponse(
            parsed_output=parsed,
            served_by_provider=self.provider_name,
            served_by_model=self.model_name,
            raw_text=raw_text,
        )

    def _raise_for_failover_status(self, response: "requests.Response") -> None:
        """Translate an error status into the seam's fail-over exceptions. 429 → rate-limit
        (with Retry-After when present); 5xx → unavailable; other non-2xx → unavailable too
        (so a single bad provider never sinks the whole pool)."""
        status = response.status_code
        if status == 429:
            raise LlmRateLimitError(
                self.provider_name,
                "rate/quota limit (HTTP 429)",
                retry_after_seconds=_retry_after_seconds(response),
            )
        if status >= 500:
            raise LlmProviderUnavailableError(
                self.provider_name, f"server error (HTTP {status})"
            )
        if status >= 400:
            # 401/403/400 — treat as this provider being unusable right now; fail over.
            raise LlmProviderUnavailableError(
                self.provider_name, f"request rejected (HTTP {status}): {response.text[:200]}"
            )

    def _parse_first_choice(self, response: "requests.Response") -> tuple[dict, str]:
        extracted = self._extract_completion_or_none(response)
        if extracted is None:
            raise LlmResponseFormatError(
                self.provider_name,
                "unexpected response envelope or non-JSON message content",
            )
        return extracted

    def _extract_completion_or_none(
        self, response: "requests.Response"
    ) -> tuple[dict, str] | None:
        """Pull `choices[0].message.content` and parse it as a JSON object, returning
        `(parsed, raw_text)` or None if the envelope is malformed / content isn't JSON.
        Non-raising so the soft-paywall path can probe a body before deciding to fail over."""
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        parsed = _parse_json_object(content)
        if parsed is None:
            return None
        return parsed, content


def _retry_after_seconds(response: "requests.Response") -> float | None:
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_json_object(content: str) -> dict | None:
    """Parse a JSON object out of the model's reply, tolerating a stray ```json fence some
    providers add despite response_format. Returns None if it isn't a JSON object."""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    text = text.strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        # Last resort: slice from the first { to the last } (drops any leading prose).
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            return None
    return parsed if isinstance(parsed, dict) else None
