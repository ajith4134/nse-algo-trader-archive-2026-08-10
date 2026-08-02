# Free-Tier Cloud LLM Provider Registry — Master Table & Failover Order

Date: 2026-07-25
Purpose: consolidated, sourced enumeration of cloud LLM API providers with a free tier
or free API access, for pre-populating a swappable multi-provider client with
rate-limit failover. Complements `docs/research/97_free_tier_llm_provider_api_config_research.md`
(which has the deep per-provider detail + source citations for Fireworks, NVIDIA NIM,
Scaleway, Z.ai, OVHcloud, Pollinations, and the rejected-candidates list). This file adds
the remaining 12 providers researched (Groq, Gemini, Cerebras, OpenRouter, Together AI,
Mistral, Cohere, GitHub Models, Cloudflare Workers AI, Hugging Face, SambaNova,
Hyperbolic) and merges everything into one master table + recommended failover order.

Method: 4 parallel research agents (model: sonnet) fetched official docs pages directly
via WebFetch (not search snippets only). Claims are graded — see per-provider detail
docs for exact source URLs and explicit A/B-grade flags. Numbers that could only be
found on login-gated dashboards (Gemini, Mistral) or that conflict across sources
(NVIDIA NIM, Z.ai RPM) are marked "unverified" below — poll the account/response
headers at runtime instead of hardcoding those.

---

## Master table

| Provider | OpenAI-compatible? | Base URL | Auth header | Free-tier limits | Example free model IDs | JSON / tool-calling | Signup URL |
|---|---|---|---|---|---|---|---|
| **Groq** | Yes | `https://api.groq.com/openai/v1` | `Authorization: Bearer` | 30 RPM (shared, all models); varies by model: `llama-3.1-8b-instant` 14.4K RPD/500K TPD; `llama-3.3-70b-versatile` 1K RPD/100K TPD; `gpt-oss-120b/20b` 1K RPD/200K TPD | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `groq/compound` | Both (JSON Schema structured outputs + native tool use; not combinable with streaming) | https://console.groq.com/keys |
| **Google Gemini** | Yes (compat shim) + native | Compat: `https://generativelanguage.googleapis.com/v1beta/openai/`; native: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` | Compat: `Authorization: Bearer`; native: `x-goog-api-key` | Not statically published — dashboard-gated (aistudio.google.com/rate-limit). Secondary-source approx: `gemini-2.5-flash` ~10-15 RPM / 250K-1M TPM / 250-1,500 RPD. **Unverified — poll dashboard.** | `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemma-4` | Both (`response_schema` JSON mode + function calling, composable with built-in tools) | https://aistudio.google.com/app/apikey |
| **Cerebras** | Yes | `https://api.cerebras.ai/v1` | `Authorization: Bearer` | 5 RPM / 30K TPM / 1M TPH / 1M TPD, per model (Free Trial tier) | `gpt-oss-120b`, `zai-glm-4.7`, `gemma-4-31b` | Both (JSON-Schema structured outputs + tool use) | https://cloud.cerebras.ai |
| **OpenRouter** (`:free` models) | Yes | `https://openrouter.ai/api/v1` | `Authorization: Bearer` | 20 RPM always; 50 RPD if never bought credits, **1,000 RPD once ≥$10 lifetime credits purchased** (permanent unlock) | `openai/gpt-oss-20b:free`, `google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-nano-9b-v2:free` | Both, but **per-model** — check `structured_outputs` capability flag; `:free` variants often weaker at tool-calling | https://openrouter.ai/keys |
| **Together AI** | Yes | `https://api.together.ai/v1` | `Authorization: Bearer` | **No free tier** — $5 minimum prepaid balance required (policy since Jul 2025); no numeric RPM/TPM published, discovered via `x-ratelimit-reset` header only | None confirmed callable at $0 | Both (`response_format` json_object/json_schema/regex; `tools`/`tool_choice`) | https://api.together.ai/ |
| **Mistral AI** (La Plateforme) | Compatible via `base_url` override (native SDK) | `https://api.mistral.ai/v1` | `Authorization: Bearer` | "Free mode" — enabled by default, **no card required**, but no numeric limits published (admin-panel-gated at `admin.mistral.ai`) | `labs-leanstral-2603` ($0 hosted, limited-time feedback model); other Apache-2.0 models are priced but reachable in Free mode | Both (JSON mode + JSON Schema; `tools`/`tool_choice`) | https://console.mistral.ai |
| **Cohere** | Yes, via `/compatibility/v1` (native `/v2/chat`) | Compat: `https://api.cohere.ai/compatibility/v1`; native: `https://api.cohere.com/v2/chat` | `Authorization: Bearer` | Trial key: **20 req/min** (chat), **1,000 API calls/month total**, non-commercial use only | `command-r7b-12-2024`, `command-a-03-2025` | Both (`response_format` json_object + JSON Schema; `tools`/`tool_choice`/`strict_tools`) | https://dashboard.cohere.com/welcome/register |
| **GitHub Models** | Yes | `https://models.github.ai/inference/chat/completions` | `Authorization: Bearer <GitHub PAT>` (`models: read` scope) | Copilot Free tier: **Low-tier models** 15 RPM/150 RPD; **High-tier** 10 RPM/50 RPD; **Custom** (o1/o3/gpt-5 family) not available on Free | `openai/gpt-4o-mini`, `meta/llama-3.3-70b-instruct`, `mistral-ai/mistral-small-2503`, `deepseek/deepseek-v3-0324`, `microsoft/phi-4` | Both, **per-model** — flagged in each catalog entry's `capabilities` array | Any GitHub account; PAT at github.com/settings/tokens |
| **Cloudflare Workers AI** | Yes | `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1` | `Authorization: Bearer <api_token>` | 10,000 "Neurons"/day/account (normalized compute budget, not RPM) | `@cf/meta/llama-3.3-70b-instruct-fp8-fast`, `@cf/meta/llama-3.1-8b-instruct`, `@cf/openai/gpt-oss-120b` | Both (JSON mode not combinable with streaming; function calling on select models) | https://dash.cloudflare.com/sign-up/workers-and-pages |
| **Hugging Face** (Inference Providers) | Yes | `https://router.huggingface.co/v1` | `Authorization: Bearer <HF_TOKEN>` | **$0.10/month free credit** (real-dollar cap across all partner providers) — trivially exhausted, not a meaningful chat tier | `openai/gpt-oss-120b`, `deepseek-ai/DeepSeek-V3-0324` (routed to partner providers) | Tool-calling yes; JSON/structured output is provider-dependent (not uniform at router level) | https://huggingface.co/join |
| **SambaNova Cloud** | Yes | `https://api.sambanova.ai/v1` | `Authorization: Bearer` | 20 RPM / 20 RPD / 200,000 TPD per model, no card required | `Meta-Llama-3.3-70B-Instruct`, `DeepSeek-V3.1`, `gpt-oss-120b` | Both (`response_format` json_object; `tools`/`tool_calls`) | https://cloud.sambanova.ai |
| **Hyperbolic** | Yes | `https://api.hyperbolic.xyz/v1` | `Authorization: Bearer` | Basic tier (no deposit): **60 RPM**; hard per-IP DDoS cap 600 RPM | `meta-llama/Meta-Llama-3.1-8B-Instruct`, `meta-llama/Meta-Llama-3.1-70B-Instruct`, `Qwen/Qwen2.5-7B-Instruct` | Both (function calling documented on 18+ models; JSON mode + schema) | https://app.hyperbolic.ai/signup |
| **Fireworks AI** | Yes | `https://api.fireworks.ai/inference/v1` | `Authorization: Bearer` | **No permanent free tier** — $1 signup credit; 10 RPM without a payment method | `accounts/fireworks/models/gpt-oss-20b` (cheapest, not $0) | Both (JSON mode/schema; tool calling auto-enables JSON mode) | https://app.fireworks.ai/signup |
| **NVIDIA NIM** (build.nvidia.com) | Yes | `https://integrate.api.nvidia.com/v1` | `Authorization: Bearer <nvapi-...>` | "Trial... for evaluation and prototyping" only — **no fixed numeric limits in current docs**; stale third-party "1,000 credits" figures unconfirmed for 2026 | `meta/llama-3.3-70b-instruct`, `deepseek-ai/deepseek-v4-flash`, `qwen/qwen3-coder-480b-a35b-instruct` | Both, per-model (`tools`/`tool_choice`; `guided_json`/`nvext` structured gen) | https://build.nvidia.com/settings/api-keys |
| **Scaleway** (Generative APIs – Serverless) | Yes ("drop-in OpenAI replacement") | `https://api.scaleway.ai/v1` | `Authorization: Bearer ${SCW_SECRET_KEY}` | **1,000,000 free tokens/account, ongoing** (not a time-limited trial); 300-600 RPM depending on account verification level | `gpt-oss-120b`, `llama-3.3-70b-instruct`, `mistral-small-3.2-24b-instruct-2506`, `glm-5.2` | Both (`response_format`; `tools`/`tool_choice`) | https://account.scaleway.com/register |
| **Z.ai** (GLM, formerly BigModel) | Yes | `https://api.z.ai/api/paas/v4/` | `Authorization: Bearer` | `glm-4.5-flash`/`glm-4.7-flash` listed **$0, ongoing**; ~60 RPM/~1,000 RPD is third-party-sourced, **unverified** on official docs | `glm-4.5-flash`, `glm-4.7-flash` | Function calling confirmed for glm-4-plus/4.6/5 tier; Flash-tier tool support only third-party-corroborated. JSON output documented. | https://z.ai/chat |
| **OVHcloud AI Endpoints** | Yes | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` | `Authorization: Bearer` (or anonymous, keyless) | Anonymous: **2 RPM/IP/model, no signup**; registered tier higher but unpublished | `Meta-Llama-3_3-70B-Instruct`, `gpt-oss-120b`, `gpt-oss-20b`, `Mistral-Nemo-Instruct-2407` | Both, per-model (`response_format` json_schema/json_object; function calling) | https://www.ovhcloud.com/en/public-cloud/ai-endpoints/ |
| **Pollinations AI** | Yes | `https://text.pollinations.ai/` (POST `/openai`) | `Authorization: Bearer` (optional — anonymous works) | Anonymous: **1 req/15s, no signup**; Seed (free signup): 1 req/5s (~12 RPM) | `openai`, `mistral` (rotating aliases — least stable model IDs of all providers) | Both (`"json": true`; tool definitions + execution) | https://auth.pollinations.ai (optional) |

---

## Recommended failover order

Ranked by **free-tier generosity × reliability × structured-output/tool-calling support**.
Grouped into tiers so the client can walk down a tier before falling to the next.

### Tier 1 — Primary (put these first; high daily ceilings, major infra, full JSON+tools)
1. **Groq** — highest sustained token ceiling among reliable providers (up to 500K TPD on the 8B model), fast inference, full structured-output + tool support. Best default primary.
2. **Google Gemini** — backed by Google infra, full JSON-schema + function-calling, generous in practice even though numeric limits are dashboard-only. Watch for the "unrestricted key" auto-block reported June 2026 — always mint keys via AI Studio.
3. **Cerebras** — 1M tokens/day per model is very generous despite only 5 RPM; good for background/batch-style calls, not bursty ones.

### Tier 2 — Solid backups (real ongoing free tiers, decent limits, full API compatibility)
4. **Scaleway Generative APIs** — genuine 1M-token pool, not a expiring trial, 300-600 RPM, EU-hosted, full JSON/tools.
5. **SambaNova Cloud** — 200K TPD / 20 RPM, no card, solid model roster (DeepSeek-V3.1, Llama-3.3-70B).
6. **OpenRouter `:free`** — useful precisely because it's an aggregator: if one underlying free model is down/rate-limited, OpenRouter still exposes ~20 different `:free` IDs behind one key. 20 RPM / 50-1,000 RPD. Verify tool-calling per model before relying on it.
7. **Cloudflare Workers AI** — 10K Neurons/day is roughly generous for small models; Cloudflare's global network makes it low-latency and reliable. No RPM cap documented (soft risk of undocumented abuse-throttling).
8. **Hyperbolic** — 60 RPM no-card tier, function calling on 18+ models; smaller company, less proven at scale than the above.

### Tier 3 — Narrow but usable (tight limits or partial verification — use as tertiary/emergency)
9. **Z.ai (GLM)** — genuinely $0 ongoing models (glm-4.5-flash/4.7-flash), but rate limits are third-party-sourced only; build in headroom.
10. **GitHub Models** — free with zero extra signup (any GitHub account), wide model diversity (OpenAI/Meta/Mistral/DeepSeek/Microsoft), but tight RPM/RPD (10-15 RPM, 50-150 RPD) and no reasoning/custom-tier models on Free.
11. **Cohere** — only 1,000 calls/month total on trial keys; fine as a rarely-hit fallback, not a workhorse.
12. **Mistral AI (Free mode)** — no card required, but numeric limits are opaque (admin-dashboard-gated) — treat conservatively, verify at runtime.
13. **OVHcloud AI Endpoints** — keyless anonymous access is a nice zero-friction absolute-last-resort (2 RPM/IP), EU-hosted, decent model list.
14. **Pollinations AI** — 1 req/15s anonymous is very slow and model IDs (`openai`, `mistral`) are rotating aliases (unstable for reproducibility) — true last resort only.

### Excluded from the free-tier failover chain (verified NOT genuinely free)
- **Together AI** — no free tier at all since Jul 2025 policy change; $5 prepay required.
- **Fireworks AI** — $1 one-time credit only, 10 RPM without a card; treat as pay-as-you-go, not free.
- **Hugging Face Inference Providers** — $0.10/month cap is trivially exhausted; not a meaningful chat-completions free tier despite being technically "free."
- **NVIDIA NIM / build.nvidia.com** — officially "trial... for evaluation," no fixed numeric free allotment confirmed for 2026; usable opportunistically but not reliably schedulable.
- Also checked and rejected (see `docs/research/97` for full detail): DeepInfra, Novita AI, xAI/Grok, Alibaba DashScope/Qwen (intl. free tier discontinued Apr 2026), Baseten, Replicate, Chutes AI, Nebius AI Studio, GLHF.chat, SiliconFlow, AI21, DeepSeek platform, Featherless AI — all one-time trial credits, discontinued, or unverifiable.

### Practical client design notes
- All 18 evaluated providers (Together/Fireworks/HF/NVIDIA included, since they still expose an API even without a real free tier) speak an **OpenAI-compatible `/chat/completions` shape**, so a single request/response adapter covers the whole registry — only base URL, auth header name, and model ID differ per provider.
- Two providers use a non-`Authorization: Bearer` header in their **native** (non-compat) mode: Gemini native (`x-goog-api-key`) — always use its OpenAI-compat endpoint instead to stay uniform.
- Where free-tier numbers are dashboard-gated or third-party-only (Gemini, Mistral, NVIDIA NIM, Z.ai RPM), the failover client should **read live `x-ratelimit-*` response headers / 429 bodies at runtime** rather than hardcoding static thresholds — several providers (Together, NVIDIA) only expose limits this way already.
- Re-verify OpenRouter's "≥$10 lifetime credits → 1,000 RPD" unlock and Scaleway's verification-tier RPM jump when building the registry — both are step-function upgrades worth encoding as config flags (`account_verified: bool`).

---

## Sources
Full per-claim citations (official doc URLs) are in the batch research this file consolidates:
- Groq, Gemini, Cerebras, OpenRouter — fetched from console.groq.com/docs, ai.google.dev/gemini-api/docs, inference-docs.cerebras.ai, openrouter.ai/docs (July 2026).
- Together AI, Mistral, Cohere, GitHub Models — fetched from docs.together.ai, docs.mistral.ai, docs.cohere.com, docs.github.com (July 2026).
- Cloudflare Workers AI, Hugging Face, SambaNova, Hyperbolic — fetched from developers.cloudflare.com/workers-ai, huggingface.co/docs/inference-providers, docs.sambanova.ai, hyperbolic.ai/docs (July 2026).
- Fireworks AI, NVIDIA NIM, Scaleway, Z.ai, OVHcloud, Pollinations, and the rejected-candidate list — see `docs/research/97_free_tier_llm_provider_api_config_research.md` for full source URLs.

## What was NOT covered
- Numeric Gemini/Mistral/NVIDIA-NIM free-tier RPM/TPM tables (dashboard-gated, no static official source found — flagged for runtime polling instead).
- Non-chat capabilities (embeddings, rerank, image/audio generation) beyond noting a few embedding/ASR model IDs in passing — this report is scoped to chat-completions.
- Enterprise/negotiated free tiers (e.g. startup credit programs, academic grants) — out of scope; only self-serve free tiers reachable via public signup were covered.
