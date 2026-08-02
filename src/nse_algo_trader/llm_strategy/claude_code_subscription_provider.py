"""Claude Code Max/Pro SUBSCRIPTION as an `LlmProvider` — the flat-cost lane (idea #8, spec
`docs/research/llm_gateway_spec_2026-08-02.md`).

Why this exists: the whole swap-on-limit gateway (pool + failover + free-tier + Ollama) already lives in
`swappable_multi_provider_llm_client` + `llm_provider_registry`. The one missing lane is the user's
**Claude Code subscription** (flat monthly) driven programmatically via the official **Claude Agent SDK**
under the logged-in OAuth credentials (NOT a metered API key). Registered FIRST in the pool so the
subscription is MAXIMIZED (user directive), and when it hits its 5-hour/weekly cap the existing swappable
client transparently fails over to the free-tier/local lanes.

Verified 2026-08-02 (spec §6, real spike): a real `query()` returned under subscription auth
(`provider:firstParty`, no `ANTHROPIC_API_KEY`); **Haiku + minimal options = ~$0.001–0.04/call vs $0.34
for the Opus-5 default** — so this provider defaults to Haiku, strips settings/tools, and uses a terse
system prompt (user rule: never Opus by default; derive nothing hard-coded that data can supply).

Cost/limit discipline lives here: on a usage-cap / limit signal we raise `LlmRateLimitError` so the pool
puts this lane on cooldown and moves on — a ban/cap DEGRADES, never HALTS, the organism.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import anyio

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmResponseFormatError,
    StrategyLlmRequest,
    StrategyLlmResponse,
)

# Default = cheapest capable model (user rule: Haiku→Sonnet, never Opus by default). Exact IDs only —
# loose aliases ("sonnet") mis-resolved to Haiku in testing (spec §4). Override via env, no code change.
DEFAULT_SUBSCRIPTION_MODEL = os.environ.get("CLAUDE_SUBSCRIPTION_MODEL", "claude-haiku-4-5")

# Substrings in an SDK error/result that mean "the subscription lane is capped/limited right now" →
# fail over (LlmRateLimitError), not a hard failure. Not a rate NUMBER (those are live/opaque) — the shapes.
_CAP_SIGNALS = ("usage limit", "rate limit", "429", "quota", "exceeded", "capacity", "overloaded",
                "resets", "try again")
_TRANSIENT_SIGNALS = ("timeout", "timed out", "connection", "econnreset", "network", "500", "503")


def _extract_text_and_model(messages: list[Any]) -> tuple[str, str]:
    """Pull the assistant text + the canonical model out of the SDK message stream, defensively
    (message classes vary by SDK version, so read by attribute/blocks, not isinstance)."""
    text_parts: list[str] = []
    model = DEFAULT_SUBSCRIPTION_MODEL
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                block_text = getattr(block, "text", None)
                if isinstance(block_text, str):
                    text_parts.append(block_text)
        elif isinstance(content, str):
            text_parts.append(content)
        # ResultMessage carries usage/model metadata
        usage = getattr(msg, "usage", None) or getattr(msg, "modelUsage", None)
        if isinstance(usage, dict):
            for v in usage.values():
                if isinstance(v, dict) and isinstance(v.get("canonicalModel"), str):
                    model = v["canonicalModel"]
    return "\n".join(text_parts).strip(), model


def _first_json_object(text: str) -> dict:
    """Robustly parse the first balanced JSON object from model text (handles ```json fences +
    prose before/after). Raises LlmResponseFormatError if none parses."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        break
    if candidate is None:
        raise LlmResponseFormatError("claude-code-subscription", f"no JSON object in reply: {text[:200]!r}")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LlmResponseFormatError("claude-code-subscription", f"unparseable JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LlmResponseFormatError("claude-code-subscription", "reply JSON was not an object")
    return parsed


class ClaudeCodeSubscriptionProvider:
    """`LlmProvider` backed by the Claude Code subscription via the Agent SDK. Sync-facing (bridges the
    SDK's async `query` with `anyio.run`) so it drops into the existing sync provider pool unchanged.

    `sdk_query` is injected (defaults to the real SDK) so tests exercise the parse/error mapping behind a
    DI seam without spending subscription usage (Rule J)."""

    def __init__(self, model_name: str = DEFAULT_SUBSCRIPTION_MODEL, sdk_query: Any = None) -> None:
        self.provider_name = "claude-code-subscription"
        self.model_name = model_name
        self._sdk_query = sdk_query  # None → resolve the real SDK lazily (import only when actually used)
        self._ClaudeAgentOptions: Any = None

    def _resolve_query(self):
        if self._sdk_query is not None:
            # Injected (test) path: options is just a kwargs dict the fake query can ignore (DI seam).
            if self._ClaudeAgentOptions is None:
                self._ClaudeAgentOptions = lambda **kw: kw
            return self._sdk_query
        try:
            from claude_agent_sdk import ClaudeAgentOptions, query
        except ImportError as exc:  # SDK not installed → this lane is simply unavailable, pool skips it
            raise LlmProviderUnavailableError("claude-code-subscription", f"Agent SDK missing: {exc}") from exc
        self._ClaudeAgentOptions = ClaudeAgentOptions
        return query

    async def _run(self, request: StrategyLlmRequest) -> tuple[str, str]:
        query = self._resolve_query()
        opts = self._ClaudeAgentOptions(
            model=self.model_name,
            max_turns=1,
            setting_sources=[],      # do NOT load CLAUDE.md/harness → cuts the ~33k-token cache load
            allowed_tools=[],        # no tools for a structured-generation call
            system_prompt=(request.system_instruction
                           + "\nReply with ONLY a single JSON object matching the required schema. No prose."),
        )
        prompt = (f"{request.user_prompt}\n\nRequired JSON schema:\n{json.dumps(request.response_json_schema)}")
        messages: list[Any] = []
        async for msg in query(prompt=prompt, options=opts):
            messages.append(msg)
        return _extract_text_and_model(messages)

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        try:
            text, model = anyio.run(self._run, request)
        except (LlmProviderUnavailableError, LlmRateLimitError, LlmResponseFormatError):
            raise
        except Exception as exc:  # noqa: BLE001 — translate ANY vendor error into a pool-failover signal
            blob = str(exc).lower()
            if any(s in blob for s in _CAP_SIGNALS):
                raise LlmRateLimitError("claude-code-subscription", f"subscription capped: {exc}") from exc
            if any(s in blob for s in _TRANSIENT_SIGNALS):
                raise LlmProviderUnavailableError("claude-code-subscription", f"transient: {exc}") from exc
            raise LlmProviderUnavailableError("claude-code-subscription", f"sdk error: {exc}") from exc
        parsed = _first_json_object(text)
        return StrategyLlmResponse(
            parsed_output=parsed,
            served_by_provider=self.provider_name,
            served_by_model=model or self.model_name,
            raw_text=text,
        )


def build_claude_code_subscription_provider(
    env: dict | None = None, sdk_query: Any = None
) -> ClaudeCodeSubscriptionProvider | None:
    """Factory for the pool: return the subscription provider when it should lead the failover order,
    else None so the pool self-sizes (Rule G — no orphan, no crash).

    Enabled by default (the whole point is to MAXIMIZE the subscription). Disable explicitly with
    `CLAUDE_SUBSCRIPTION_DISABLED=1` (e.g. to avoid the ToS/cap risk on a given run — spec §8). If a
    metered `ANTHROPIC_API_KEY` is set we still prefer the subscription lane here; the paid Anthropic
    provider remains a separate, lower-priority pool entry."""
    env = env if env is not None else dict(os.environ)
    if env.get("CLAUDE_SUBSCRIPTION_DISABLED", "").strip() in {"1", "true", "yes"}:
        return None
    model = env.get("CLAUDE_SUBSCRIPTION_MODEL", DEFAULT_SUBSCRIPTION_MODEL)
    return ClaudeCodeSubscriptionProvider(model_name=model, sdk_query=sdk_query)
