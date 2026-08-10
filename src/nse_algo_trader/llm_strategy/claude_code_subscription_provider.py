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
import threading
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


# ---- process-shared warm session + live transport telemetry (B48 follow-up, task #1) -----------------
# ONE warm subprocess per process (every provider instance — the serving pool AND the throwaway pool the
# dashboard builds each render — reuses it) + a process-wide counter of REAL serves by transport, so the
# LLM Gateway panel shows the actual warm/cold mix rather than a configured flag.
_shared_warm_lock = threading.Lock()
_shared_warm_session: Any = None


class _SubscriptionTransportTelemetry:
    """Thread-safe process-wide tally of successful subscription serves, split by transport."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.warm_calls = 0
        self.cold_calls = 0
        self.last_transport = ""

    def record(self, transport: str) -> None:
        with self._lock:
            if transport == "warm":
                self.warm_calls += 1
            elif transport == "cold":
                self.cold_calls += 1
            self.last_transport = transport

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "warm_calls": self.warm_calls,
                "cold_calls": self.cold_calls,
                "total_calls": self.warm_calls + self.cold_calls,
                "last_transport": self.last_transport,
            }


_TRANSPORT_TELEMETRY = _SubscriptionTransportTelemetry()


def subscription_transport_telemetry() -> dict:
    """Live snapshot of how the subscription lane has actually been served (warm vs cold). Read by the
    dashboard's LLM Gateway surface so it reflects the REAL serving pool, not the configured transport."""
    return _TRANSPORT_TELEMETRY.snapshot()


# Canonical token-field name → normalized ledger bucket. The Agent SDK reports usage in either snake_case
# (`input_tokens`, seen in real ~/.claude jsonl) or camelCase (`inputTokens`), so we normalize both.
_TOKEN_FIELD_ALIASES: dict[str, str] = {
    "input_tokens": "input", "inputtokens": "input",
    "output_tokens": "output", "outputtokens": "output",
    "cache_read_input_tokens": "cache_read", "cachereadinputtokens": "cache_read",
    "cache_creation_input_tokens": "cache_creation", "cachecreationinputtokens": "cache_creation",
}
_TOKEN_BUCKETS = ("input", "output", "cache_read", "cache_creation")


class _SubscriptionTokenLedger:
    """Thread-safe process-wide tally of tokens actually consumed on the subscription lane, split by
    canonical model. Fed from the SDK `usage`/`modelUsage` metadata of every real serve (the same message
    stream the text/model extractor already walks) so the LLM Gateway panel can show REAL Haiku-4-5 token
    consumption for this session, not an estimate."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # model → {input, output, cache_read, cache_creation, serves}. `total` is derived on snapshot.
        self._by_model: dict[str, dict[str, int]] = {}

    def record(self, model: str, tokens: dict[str, int]) -> None:
        """Add one serve's per-bucket token counts under `model`. A serve with no usable usage still
        increments `serves` so the panel distinguishes 'served, no usage reported' from 'never served'."""
        key = model or DEFAULT_SUBSCRIPTION_MODEL
        with self._lock:
            row = self._by_model.setdefault(
                key,
                {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
                 "serves": 0, "cache_hit_serves": 0},
            )
            for bucket in _TOKEN_BUCKETS:
                row[bucket] += int(tokens.get(bucket, 0) or 0)
            row["serves"] += 1
            if int(tokens.get("cache_read", 0) or 0) > 0:  # a serve that read from the prompt cache = a hit
                row["cache_hit_serves"] += 1

    def snapshot(self) -> dict:
        """`{model: {input,output,cache_read,cache_creation,total,serves}, "_all": {...aggregate...}}`."""
        with self._lock:
            out: dict[str, dict[str, int]] = {}
            agg = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
                   "total": 0, "serves": 0, "cache_hit_serves": 0}
            for model, row in self._by_model.items():
                total = sum(row[b] for b in _TOKEN_BUCKETS)
                out[model] = {**{b: row[b] for b in _TOKEN_BUCKETS}, "total": total,
                              "serves": row["serves"], "cache_hit_serves": row["cache_hit_serves"]}
                for b in _TOKEN_BUCKETS:
                    agg[b] += row[b]
                agg["total"] += total
                agg["serves"] += row["serves"]
                agg["cache_hit_serves"] += row["cache_hit_serves"]
            out["_all"] = agg
            return out


_TOKEN_LEDGER = _SubscriptionTokenLedger()


def subscription_token_ledger() -> dict:
    """Live snapshot of tokens consumed on the subscription lane this process, keyed by canonical model
    (plus an `_all` aggregate). Read by the dashboard's LLM Gateway surface so the panel shows REAL
    Haiku-4-5 token consumption for the session."""
    return _TOKEN_LEDGER.snapshot()


def _usage_tokens_from_mapping(usage: dict) -> dict[str, int]:
    """Pull normalized per-bucket token counts out of ONE flat usage mapping (int-valued token fields),
    tolerating camelCase/snake_case and ignoring non-int / non-token entries."""
    tokens: dict[str, int] = {}
    for raw_key, value in usage.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        bucket = _TOKEN_FIELD_ALIASES.get(str(raw_key).replace("-", "_").lower())
        if bucket is not None:
            tokens[bucket] = tokens.get(bucket, 0) + int(value)
    return tokens


def _shared_warm_session_for(model_name: str) -> Any:
    """The process-shared `WarmClaudeSubscriptionSession` (built once, thread-safe). Keeps a single warm
    `claude` subprocess alive across every provider instance so telemetry + speed are consistent."""
    global _shared_warm_session
    with _shared_warm_lock:
        if _shared_warm_session is None:
            from nse_algo_trader.llm_strategy.warm_claude_subscription_session import (
                WarmClaudeSubscriptionSession,
            )

            _shared_warm_session = WarmClaudeSubscriptionSession(model_name)
        return _shared_warm_session


def _extract_text_and_model(messages: list[Any]) -> tuple[str, str]:
    """Pull the assistant text + the canonical model out of the SDK message stream, defensively
    (message classes vary by SDK version, so read by attribute/blocks, not isinstance).

    Side effect: folds each message's token usage into the process-wide `_TOKEN_LEDGER`, so the LLM
    Gateway panel shows REAL Haiku-4-5 token consumption. This is the ONE place every serve's message
    stream is walked — cold via `_run`, warm via the injected `extract` callback — so capturing here
    covers 100% of real serves without threading a new return value through the warm-session seam.
    Tokens are counted at extraction (before JSON parse) because they are spent regardless of parse
    outcome. Nested per-model usage is attributed per key; a flat usage mapping is attributed to the
    resolved canonical model AFTER the full stream is read (so `canonicalModel`, if present anywhere,
    labels it correctly)."""
    text_parts: list[str] = []
    weak_model = DEFAULT_SUBSCRIPTION_MODEL  # AssistantMessage.model ("claude-haiku-4-5-20251001")
    canonical_model = ""                     # ModelUsage.canonicalModel ("claude-haiku-4-5") — preferred key
    # One serve emits several usage-bearing messages (AssistantMessage.usage AND ResultMessage.usage carry
    # the SAME per-turn totals for a max_turns=1 call), so accumulating every one DOUBLE-COUNTS. We collect
    # each message's per-turn flat token dict and record only the LARGEST (the aggregate) once per serve.
    # We deliberately read the FLAT `usage` (reliably per-turn) for the counts and use `model_usage` only to
    # resolve the canonical model label — a warm client's `model_usage` can report session-cumulative totals.
    flat_candidates: list[dict[str, int]] = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                block_text = getattr(block, "text", None)
                if isinstance(block_text, str):
                    text_parts.append(block_text)
        elif isinstance(content, str):
            text_parts.append(content)
        msg_model = getattr(msg, "model", None)
        if isinstance(msg_model, str) and msg_model:
            weak_model = msg_model
        # ResultMessage.model_usage: dict[model_name → ModelUsage]; used ONLY for the canonical label here.
        model_usage = getattr(msg, "model_usage", None)
        if isinstance(model_usage, dict):
            for name, mu in model_usage.items():
                cm = mu.get("canonicalModel") if isinstance(mu, dict) else None
                canonical_model = cm if isinstance(cm, str) and cm else (canonical_model or str(name))
        # AssistantMessage.usage / ResultMessage.usage: flat int token fields alongside nested
        # `server_tool_use` + string `service_tier` — `_usage_tokens_from_mapping` picks out only the ints.
        usage = getattr(msg, "usage", None)
        if isinstance(usage, dict):
            toks = _usage_tokens_from_mapping(usage)
            if toks:
                flat_candidates.append(toks)
    model = canonical_model or weak_model
    if flat_candidates:
        _TOKEN_LEDGER.record(model, max(flat_candidates, key=lambda t: sum(t.values())))
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

    def __init__(
        self,
        model_name: str = DEFAULT_SUBSCRIPTION_MODEL,
        sdk_query: Any = None,
        warm_session: Any = None,
    ) -> None:
        self.provider_name = "claude-code-subscription"
        self.model_name = model_name
        self._sdk_query = sdk_query  # None → resolve the real SDK lazily (import only when actually used)
        self._ClaudeAgentOptions: Any = None
        # Warm-persistent transport (B48): keeps one `claude` subprocess alive across calls so only the
        # first call pays cold start. Injected for tests; else built lazily from the real SDK. The cold
        # one-shot path stays the fallback, so a warm-start failure DEGRADES (never halts) the lane.
        self._warm_session = warm_session
        self._warm_disabled = os.environ.get(
            "CLAUDE_SUBSCRIPTION_WARM_DISABLED", ""
        ).strip().lower() in {"1", "true", "yes"}
        self._warm_build_failed = False
        self.last_transport = "cold"  # 'warm' | 'cold' — surfaced on the LLM Gateway dashboard panel

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
        prompt = self._build_prompt(request)
        messages: list[Any] = []
        async for msg in query(prompt=prompt, options=opts):
            messages.append(msg)
        return _extract_text_and_model(messages)

    def _get_warm_session(self) -> Any:
        """The warm session, or None to force the cold path. Warm only when driving the REAL SDK
        (`sdk_query is None`) — the injected-test path is one-shot by design. A build failure disables warm
        for the process (cold-path thereafter), never crashes."""
        if self._warm_disabled or self._warm_build_failed:
            return None
        if self._warm_session is not None:
            return self._warm_session
        if self._sdk_query is not None:
            return None  # injected fake query → no warm subprocess to keep alive
        try:
            return _shared_warm_session_for(self.model_name)  # ONE warm subprocess process-wide
        except Exception:  # noqa: BLE001 — no warm engine available → degrade to cold, never halt
            self._warm_build_failed = True
            return None

    def _invoke(self, request: StrategyLlmRequest) -> tuple[str, str]:
        """Pick transport: warm-persistent first, cold one-shot as the fallback. Raises raw vendor errors
        (mapped by the caller). A `WarmSessionUnavailable` (start/transport death) silently drops to cold —
        a usage cap does NOT, so it can fail the whole lane over to the next provider."""
        from nse_algo_trader.llm_strategy.warm_claude_subscription_session import (
            WarmSessionUnavailable,
        )

        warm = self._get_warm_session()
        if warm is not None:
            try:
                prompt = self._build_prompt(request)
                text, model = warm.run_structured(
                    request.system_instruction, prompt, self.model_name, _extract_text_and_model
                )
                self.last_transport = "warm"
                return text, model
            except WarmSessionUnavailable:
                pass  # warm cannot serve → fall through to cold on the same subscription
        self.last_transport = "cold"
        return anyio.run(self._run, request)

    def _build_prompt(self, request: StrategyLlmRequest) -> str:
        return f"{request.user_prompt}\n\nRequired JSON schema:\n{json.dumps(request.response_json_schema)}"

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        try:
            text, model = self._invoke(request)
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
        _TRANSPORT_TELEMETRY.record(self.last_transport)  # count the REAL serve for the live panel
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
