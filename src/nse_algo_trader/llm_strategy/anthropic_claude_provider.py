"""The Anthropic Claude endpoint as an `LlmProvider`, for when a paid Anthropic key is added
later (Layer 11; research/96). It joins the SAME swappable pool as the free-tier providers —
typically pinned FIRST in the order so Claude serves when its quota allows and the free tier
catches the overflow.

Structured output uses the Anthropic-recommended pattern: a single forced tool call whose
`input_schema` is the request's JSON schema, so `tool_use.input` is the validated object
(per the claude-api skill). Model defaults to `claude-opus-4-8`.

The `anthropic` SDK is an OPTIONAL dependency — it is imported lazily inside the constructor,
so this module (and the whole pool) loads fine when the SDK isn't installed. Construction
raises a clear error only if you actually try to use the Claude provider without the SDK.
Vendor exceptions are translated into the seam's fail-over hierarchy so Claude rate-limits
hand off to the free-tier pool exactly like any other provider.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmResponseFormatError,
    StrategyLlmRequest,
    StrategyLlmResponse,
)

_STRUCTURED_TOOL_NAME = "emit_strategic_reflection"


class AnthropicClaudeProvider:
    """Claude behind the `LlmProvider` seam. Only instantiate when an Anthropic API key is
    present; `llm_provider_registry` does that conditionally."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-opus-4-8",
        provider_name: str = "anthropic-claude",
        client: object | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        if client is not None:  # injected (tests / custom transport)
            self._client = client
        else:
            try:
                import anthropic  # lazy — optional dependency
            except ImportError as exc:  # pragma: no cover - exercised only without the SDK
                raise LlmProviderUnavailableError(
                    provider_name,
                    "the 'anthropic' SDK is not installed; run `pip install anthropic` "
                    "to enable the Claude provider",
                ) from exc
            self._client = anthropic.Anthropic(api_key=api_key)
            self._anthropic_module = anthropic

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        try:
            message = self._client.messages.create(
                model=self.model_name,
                max_tokens=request.max_output_tokens,
                system=request.system_instruction,
                tools=[
                    {
                        "name": _STRUCTURED_TOOL_NAME,
                        "description": "Return the structured strategic reflection.",
                        "input_schema": request.response_json_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _STRUCTURED_TOOL_NAME},
                messages=[{"role": "user", "content": request.user_prompt}],
            )
        except Exception as exc:  # translate vendor errors into the seam's hierarchy
            raise self._translate_vendor_error(exc) from exc

        for block in getattr(message, "content", []):
            if getattr(block, "type", None) == "tool_use":
                return StrategyLlmResponse(
                    parsed_output=dict(block.input),
                    served_by_provider=self.provider_name,
                    served_by_model=self.model_name,
                    raw_text="",
                )
        raise LlmResponseFormatError(
            self.provider_name, "no tool_use block in the Claude response"
        )

    def _translate_vendor_error(self, exc: Exception) -> Exception:
        module = getattr(self, "_anthropic_module", None)
        if module is not None:
            if isinstance(exc, getattr(module, "RateLimitError", ())):
                return LlmRateLimitError(self.provider_name, str(exc))
            status_error = getattr(module, "APIStatusError", None)
            if status_error is not None and isinstance(exc, status_error):
                if getattr(exc, "status_code", 0) >= 500:
                    return LlmProviderUnavailableError(self.provider_name, str(exc))
            conn_error = getattr(module, "APIConnectionError", None)
            if conn_error is not None and isinstance(exc, conn_error):
                return LlmProviderUnavailableError(self.provider_name, str(exc))
        return LlmProviderUnavailableError(self.provider_name, f"claude error: {exc}")
