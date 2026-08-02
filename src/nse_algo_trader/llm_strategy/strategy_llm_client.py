"""The provider-neutral LLM seam for the Strategic-LLM layer (Layer 11; research/96).

This is the DI boundary the rest of Layer 11 depends on. Everything that wants LLM
reasoning (the memory-grounded analyst, later the debate/council slices) talks to a
`StrategyLlmClient` — never to a concrete vendor SDK — so:
  * PRODUCTION injects a `SwappableMultiProviderLlmClient` over the real free-tier cloud
    providers (Groq/Cerebras/SambaNova/NVIDIA/Gemini/... — swappable_multi_provider_llm_client.py),
  * TESTS inject a `FakeStrategyLlmClient` (lives under tests/, never in src/ — Rule J),
so the injected fake is structurally unable to reach a real network call.

A single provider (one vendor endpoint) implements the lower-level `LlmProvider`; the
swappable client composes an ordered pool of them and fails over on rate-limit. Both speak
the same request/response shape so the analyst is written once, provider-agnostically.

Structured output is requested by passing a JSON schema; a provider returns the parsed
object (via `response_format=json_object` on OpenAI-compatible providers, or a forced tool
call on the Anthropic provider). PURE contracts here — no I/O, no vendor imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StrategyLlmRequest:
    """One structured-reasoning ask, independent of which vendor serves it.

    `response_json_schema` is the JSON Schema the answer must satisfy — providers use it to
    force structured output and the caller parses against it. `purpose` is a short label used
    only for logging/observability (which analyst role asked)."""

    system_instruction: str
    user_prompt: str
    response_json_schema: dict
    max_output_tokens: int = 1400
    purpose: str = "strategy_reflection"


@dataclass(frozen=True)
class StrategyLlmResponse:
    """A structured answer plus which provider/model actually produced it (for the
    served-by trail on the dashboard and for failover accounting)."""

    parsed_output: dict
    served_by_provider: str
    served_by_model: str
    raw_text: str = ""


# ----- exception hierarchy: distinguishes "try the next provider" from "give up" -----


class LlmProviderError(Exception):
    """Base for any single-provider failure. The swappable client fails over on these."""

    def __init__(self, provider_name: str, message: str) -> None:
        super().__init__(f"[{provider_name}] {message}")
        self.provider_name = provider_name


class LlmRateLimitError(LlmProviderError):
    """A provider hit its free-tier rate/quota limit (HTTP 429 / quota exhausted). The
    swappable client puts this provider on cooldown (honoring `retry_after_seconds` when the
    provider tells us) and moves to the next one — the core of the swap-on-limit behaviour."""

    def __init__(
        self, provider_name: str, message: str, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(provider_name, message)
        self.retry_after_seconds = retry_after_seconds


class LlmProviderUnavailableError(LlmProviderError):
    """A transient provider fault (HTTP 5xx, timeout, connection error) — also a fail-over
    trigger, but with a shorter cooldown than a rate-limit."""


class LlmResponseFormatError(LlmProviderError):
    """The provider replied but the body wasn't the JSON object we required — treated as a
    provider fault so the pool can try another provider that may honour the schema."""


@runtime_checkable
class LlmProvider(Protocol):
    """One vendor endpoint. `provider_name`/`model_name` identify it in the served-by trail;
    `generate_structured` returns the parsed object or raises an `LlmProviderError` subclass
    (never a bare vendor exception — adapters translate)."""

    provider_name: str
    model_name: str

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse: ...


@runtime_checkable
class StrategyLlmClient(Protocol):
    """The seam Layer-11 roles depend on. A single provider OR a swappable pool both satisfy
    it, so callers never know (or care) how many providers stand behind it."""

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse: ...

    def describe_pool(self) -> "LlmPoolStatus": ...


@dataclass(frozen=True)
class LlmProviderStatus:
    """One provider's live state for the dashboard surface (Rule N)."""

    provider_name: str
    model_name: str
    cooling_down: bool = False
    last_served: bool = False


@dataclass(frozen=True)
class LlmPoolStatus:
    """The pool's live state: how many providers are configured and which is currently
    serving — what the feature surface renders so the swap behaviour is visible."""

    providers: tuple[LlmProviderStatus, ...] = field(default_factory=tuple)
    last_served_by: str = ""

    @property
    def configured_count(self) -> int:
        return len(self.providers)

    @property
    def available_count(self) -> int:
        return sum(1 for p in self.providers if not p.cooling_down)
