"""Builds the swappable provider pool from environment credentials (Layer 11; research/96).

The user supplied ~14 free-tier cloud LLM keys. Each is declared once here as an
`LlmProviderConfig` (display name, env-var name, OpenAI-compatible base URL, default free
model). At composition time `build_free_tier_provider_pool(env)` instantiates an
`OpenAiCompatibleChatProvider` for every config whose key is PRESENT and non-empty, and skips
the rest — so the pool self-sizes to whatever keys exist (0 keys → empty pool, no crash), and
adding a key later just lets that provider join. A paid `ANTHROPIC_API_KEY`, when present, is
pinned FIRST via `AnthropicClaudeProvider`.

The ORDER of `FREE_TIER_PROVIDER_CONFIGS` is the failover order: fastest/most-generous free
tiers first (Groq, Cerebras, SambaNova, NVIDIA), then the broad OpenAI-compatible clouds. The
swappable client walks this order and rotates on rate-limit.

Model IDs are sensible current free-tier defaults; override per-provider via
`{ENVNAME}_MODEL` env vars without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from nse_algo_trader.llm_strategy.openai_compatible_chat_provider import (
    HttpPost,
    OpenAiCompatibleChatProvider,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import LlmProviderUnavailableError, LlmProvider


@dataclass(frozen=True)
class LlmProviderConfig:
    """One vendor's wiring: how to find its key and where its OpenAI-compatible endpoint is.
    `base_url_template` may contain `{account_id}` (Cloudflare) filled from `account_id_env`.

    `keyless=True` marks a provider that works with NO API key (OVHcloud anon tier): it joins
    the pool even when its `api_key_env` is absent, and if a key IS later supplied it is used
    (raising the anon rate limit)."""

    provider_name: str
    api_key_env: str
    base_url_template: str
    default_model: str
    model_env: str = ""
    account_id_env: str = ""
    keyless: bool = False


# Failover order = declaration order, set by the free-tier research pass (docs/research/98):
# GENUINELY-free, ongoing, no-card providers first (Groq → Gemini → Cerebras → SambaNova →
# OpenRouter:free → Cloudflare → Z.ai → Mistral), then paid-platform / trial-credit providers
# (Alibaba, DeepSeek, NVIDIA trial, DeepInfra, Fireworks $1-credit, HF $0.10/mo), and finally
# the KEYLESS anonymous last-resort tier (OVHcloud ~2 RPM/IP/model) — it joins even with no key
# so the pool is never empty. Those may 402/429 quickly and the pool simply fails over. Rate
# limits are NOT hardcoded (they are dashboard-gated / change often); the client honours live
# 429 + Retry-After instead.
FREE_TIER_PROVIDER_CONFIGS: tuple[LlmProviderConfig, ...] = (
    # --- Tier 1: genuinely free, ongoing ---
    LlmProviderConfig(
        "groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile", "GROQ_MODEL",
    ),
    LlmProviderConfig(
        "google-ai-studio", "GOOGLE_AI_STUDIO_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.0-flash", "GOOGLE_AI_STUDIO_MODEL",
    ),
    LlmProviderConfig(
        "cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
        "llama-3.3-70b", "CEREBRAS_MODEL",
    ),
    LlmProviderConfig(
        "sambanova", "SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1",
        "Meta-Llama-3.3-70B-Instruct", "SAMBANOVA_MODEL",
    ),
    LlmProviderConfig(
        "openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
        "meta-llama/llama-3.3-70b-instruct:free", "OPENROUTER_MODEL",
    ),
    LlmProviderConfig(
        "cloudflare-workers-ai", "CLOUDFLARE_API_KEY",
        "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "CLOUDFLARE_MODEL",
        account_id_env="CLOUDFLARE_ACCOUNT_ID",
    ),
    LlmProviderConfig(
        "zai", "ZAI_API_KEY", "https://api.z.ai/api/paas/v4",
        "glm-4-flash", "ZAI_MODEL",
    ),
    LlmProviderConfig(
        "mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1",
        "mistral-small-latest", "MISTRAL_MODEL",
    ),
    # --- Tier 2: paid-platform / trial-credit — last-resort overflow ---
    LlmProviderConfig(
        "alibaba-dashscope", "ALIBABA_DASHSCOPE_API_KEY",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "qwen-plus", "ALIBABA_DASHSCOPE_MODEL",
    ),
    LlmProviderConfig(
        "deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1",
        "deepseek-chat", "DEEPSEEK_MODEL",
    ),
    LlmProviderConfig(
        "nvidia", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1",
        "meta/llama-3.3-70b-instruct", "NVIDIA_MODEL",
    ),
    LlmProviderConfig(
        "deepinfra", "DEEPINFRA_API_KEY", "https://api.deepinfra.com/v1/openai",
        "meta-llama/Llama-3.3-70B-Instruct", "DEEPINFRA_MODEL",
    ),
    LlmProviderConfig(
        "fireworks", "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/llama-v3p3-70b-instruct", "FIREWORKS_MODEL",
    ),
    LlmProviderConfig(
        "huggingface", "HUGGINGFACE_API_TOKEN", "https://router.huggingface.co/v1",
        "meta-llama/Llama-3.3-70B-Instruct", "HUGGINGFACE_MODEL",
    ),
    # --- Tier 3: KEYLESS last-resort (joins with no key; a supplied key raises the anon limit) ---
    # OVHcloud AI Endpoints (research/97-98): OpenAI-compatible, anonymous ~2 RPM/IP/MODEL (the
    # cap is per-model, so the pool still serves). Live-verified 2026-07-25: /v1/models lists the
    # model and Mistral-7B served a real schema-shaped JSON completion; a busy model's 429 just
    # fails over (rate buckets are per-model). EU-hosted zero-friction bottom fallback.
    # (Pollinations was researched as the 2nd keyless provider but REJECTED — see docs/BACKLOG.md:
    # its anonymous tier has a ~0 "pollen" budget and hard-402s on any non-trivial structured
    # request, so it can never serve this pool's forced-JSON calls.)
    LlmProviderConfig(
        "ovhcloud-ai-endpoints", "OVHCLOUD_API_KEY",
        "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        "Meta-Llama-3_3-70B-Instruct", "OVHCLOUD_MODEL",
        keyless=True,
    ),
)


#: B33 — the operator's standing LLM cost ladder: local -> free cloud -> PAID last, sparingly.
#: Paid providers are appended AFTER every free tier so the swappable client only reaches them once
#: the free tiers are rate-limited, and drops straight back down as soon as a free tier refreshes.
#: Kimi (Moonshot) is the designated paid tier; Anthropic is kept as a secondary paid fallback.
PAID_PROVIDER_CONFIGS: tuple[LlmProviderConfig, ...] = (
    LlmProviderConfig(
        provider_name="kimi-paid",
        api_key_env="MOONSHOT_API_KEY",
        base_url_template="https://api.moonshot.ai/v1",
        default_model="kimi-k2.6",
        model_env="MOONSHOT_MODEL",
    ),
)


def build_free_tier_provider_pool(
    env: Mapping[str, str],
    configs: tuple[LlmProviderConfig, ...] = FREE_TIER_PROVIDER_CONFIGS,
    http_post: HttpPost | None = None,
    anthropic_provider_factory: Callable[[str], LlmProvider] | None = None,
    paid_configs: tuple[LlmProviderConfig, ...] = PAID_PROVIDER_CONFIGS,
    market_is_open: bool | None = None,
    local_provider_factory: Callable[[Mapping[str, str]], LlmProvider | None] | None = None,
) -> list[LlmProvider]:
    """Instantiate a provider for every config whose API key is present in `env`, in COST ORDER.

    B33 (operator's standing rule): free tiers first, PAID LAST and sparingly. The swappable client
    walks this list in order and rotates on rate-limit, so appending paid providers at the end means
    they are only reached once every free tier is exhausted — and are dropped again the moment a free
    tier refreshes. Paid is never sticky.

    This previously pinned the paid `ANTHROPIC_API_KEY` FIRST, i.e. it spent money on every call
    while free capacity sat unused.

    Returns [] when no keys exist (Rule F: the empty pool is the honest 'no live providers' state,
    surfaced as blocked on the dashboard).
    """
    providers: list[LlmProvider] = []

    # LOCAL RUNG (B33) — free and unmetered, so it always outranks PAID; whether it also outranks the
    # free CLOUD tiers is decided by the market clock, per the operator's rule: local off-market
    # (batch work, latency irrelevant), cloud during market hours (latency is on a decision path).
    # Absent server → None → the rung is simply omitted; it is optional infrastructure.
    local_provider = (local_provider_factory or _build_local_ollama)(env)
    if local_provider is not None and _local_rung_leads(market_is_open):
        providers.append(local_provider)

    for config in configs:
        api_key = _present(env, config.api_key_env)
        if not api_key and not config.keyless:
            continue  # keyed provider with no key → skip; keyless joins with api_key=""
        base_url = config.base_url_template
        if config.account_id_env:
            account_id = _present(env, config.account_id_env)
            if not account_id:
                continue  # Cloudflare needs the account id too
            base_url = base_url.format(account_id=account_id)
        model = _present(env, config.model_env) or config.default_model
        providers.append(
            OpenAiCompatibleChatProvider(
                provider_name=config.provider_name,
                base_url=base_url,
                api_key=api_key,
                model_name=model,
                http_post=http_post,
            )
        )

    # During market hours the local rung sits AFTER the free cloud tiers but still ahead of paid —
    # it is free, so reaching for a metered provider before it would burn money for nothing.
    if local_provider is not None and not _local_rung_leads(market_is_open):
        providers.append(local_provider)

    # PAID TIER — appended last so it is the fallback of last resort, never the default.
    for paid_config in paid_configs:
        paid_key = _present(env, paid_config.api_key_env)
        if not paid_key:
            continue
        providers.append(
            OpenAiCompatibleChatProvider(
                provider_name=paid_config.provider_name,
                base_url=paid_config.base_url_template,
                api_key=paid_key,
                model_name=_present(env, paid_config.model_env) or paid_config.default_model,
                http_post=http_post,
            )
        )
    anthropic_key = _present(env, "ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            providers.append(_build_anthropic(anthropic_key, anthropic_provider_factory))
        except LlmProviderUnavailableError as unavailable:
            # B33: an OPTIONAL paid fallback whose SDK is not installed must not take the whole pool
            # down with it. Previously this raised out of pool construction, so a stale key for an
            # uninstalled provider left the system with NO llm at all — the free tiers never even
            # got built.
            print(f"[llm-pool] paid fallback unavailable, skipping: {unavailable}", flush=True)
    return providers


def _local_rung_leads(market_is_open: bool | None) -> bool:
    """True when the on-box model should be tried FIRST — i.e. outside market hours.

    `None` means the caller did not say, so the clock is consulted. Defaulting to the real clock
    rather than to a constant keeps the operator's time-dependent rule true for every call site that
    has not been updated yet, instead of silently pinning one side of it.
    """
    if market_is_open is not None:
        return not market_is_open
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock

    return not NseMarketClock().is_market_open(datetime.now(ZoneInfo("Asia/Kolkata")))


def _build_local_ollama(env: Mapping[str, str]) -> LlmProvider | None:
    from nse_algo_trader.llm_strategy.local_ollama_llm_provider import (
        build_local_ollama_provider,
    )

    return build_local_ollama_provider(env)


def _present(env: Mapping[str, str], key: str) -> str:
    if not key:
        return ""
    return (env.get(key) or "").strip().strip('"')


def _build_anthropic(
    api_key: str, factory: Callable[[str], LlmProvider] | None
) -> LlmProvider:
    if factory is not None:
        return factory(api_key)
    from nse_algo_trader.llm_strategy.anthropic_claude_provider import (
        AnthropicClaudeProvider,
    )

    return AnthropicClaudeProvider(api_key=api_key)
