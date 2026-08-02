# Free-Tier / Free-API Cloud LLM Providers — Research for Multi-Provider Failover Client

Date: 2026-07-25
Purpose: source data for a swappable multi-provider LLM API client config (base URL, auth header,
free-tier limits, model IDs) with rate-limit failover across providers.

Method: parallel research agents (model: sonnet) fetched official docs pages directly via WebFetch
(not just search snippets) for each provider. Every claim below is cited to a specific official
doc URL. Where a claim could only be corroborated by third-party sources or where official docs
conflicted/were stale, it is explicitly flagged as unverified/B-grade — do not hardcode those
numbers into the config without re-checking at integration time.

---

## Part 1 — Named providers

### 1. Fireworks AI

| Field | Value |
|---|---|
| Provider name | Fireworks AI |
| OpenAI-compatible? | Yes |
| Base URL | `https://api.fireworks.ai/inference/v1` |
| Chat completions endpoint | `https://api.fireworks.ai/inference/v1/chat/completions` |
| Auth header | `Authorization: Bearer $FIREWORKS_API_KEY` |
| Free tier | No permanent free model tier. New accounts get **$1 free credit**. Without a payment method: capped at **10 RPM**. With a payment method + credits: account ceiling **6,000 RPM** (fixed, not adaptive). Spend tiers gate monthly budget: Tier 1 $50/mo (card on file) → Tier 2 $500/mo (spent/added $50) → Tier 3 $5,000/mo → Tier 4 $50,000/mo → Unlimited (sales). |
| Example model IDs | `accounts/fireworks/models/gpt-oss-20b` ($0.07/$0.30 per M, cheapest text model), `accounts/fireworks/models/deepseek-v4-flash`, `accounts/fireworks/models/gpt-oss-120b`, `accounts/fireworks/models/llama-v3p1-8b-instruct`, `accounts/fireworks/models/llama-v3p2-1b-instruct`. None confirmed literally $0 — all pay-per-token against the $1 credit. |
| Signup URL | `https://app.fireworks.ai/signup` (email or Google/GitHub/LinkedIn OAuth). API keys: `https://app.fireworks.ai/settings/users/api-keys` |
| JSON / tool calling | Yes, both. `response_format: json_object` or `json_schema` (JSON Schema 2020-12 subset). Tool/function calling supported; enabling it auto-enables JSON mode. Separate BNF grammar mode also available. |
| Sources | docs.fireworks.ai/tools-sdks/openai-compatibility · docs.fireworks.ai/getting-started/quickstart · fireworks.ai/pricing · docs.fireworks.ai/guides/quotas_usage/account-quotas · docs.fireworks.ai/serverless/pricing · docs.fireworks.ai/structured-responses/structured-response-formatting |
| Flags | Per-model RPM/TPM sub-limits beyond the account-wide 10/6,000 RPM ceiling were not directly fetched from `docs.fireworks.ai/guides/quotas_usage/rate-limits` — confirm before hardcoding. `flux-1-schnell` / `firefunction-v2` showed no listed price on one catalog pull; not confirmed free, don't assume. |

### 2. NVIDIA NIM / build.nvidia.com

| Field | Value |
|---|---|
| Provider name | "NVIDIA NIM" (microservice tech) served via the "NVIDIA API Catalog" at the **build.nvidia.com** portal — used interchangeably in official sources. |
| OpenAI-compatible? | Yes |
| Base URL | `https://integrate.api.nvidia.com/v1` |
| Chat completions endpoint | `https://integrate.api.nvidia.com/v1/chat/completions` |
| Auth header | `Authorization: Bearer <NVIDIA_API_KEY>` (key generated at build.nvidia.com, typically prefixed `nvapi-`) |
| Free tier | Officially described only as a **"trial experience... for evaluation and prototyping"**, with rate limits that **"vary per model... and may vary based on the number of concurrent users."** No fixed numeric RPM/RPD/TPM in current official docs. **Conflict found:** an NVIDIA staff forum reply (June 2025) states the credits system was removed; multiple 2026-dated third-party blogs still repeat a stale "1,000 credits / 5,000 max / ~40 RPM" figure that could not be confirmed on any current official page — treat as **unverified/stale**. No documented hard stop at the limit — only "extended wait times." No official statement that billing is required to continue. |
| Example model IDs | `meta/llama-3.1-8b-instruct`, `meta/llama-3.1-70b-instruct`, `meta/llama-3.3-70b-instruct`, `mistralai/mixtral-8x22b-instruct`, `mistralai/mistral-nemotron`, `qwen/qwen3-coder-480b-a35b-instruct`, `qwen/qwen3-next-80b-a3b-instruct`, `deepseek-ai/deepseek-v4-flash`, `deepseek-ai/deepseek-v4-pro`, `nvidia/llama-3.3-nemotron-super-49b-v1.5`, `nvidia/nemotron-3-ultra-550b-a55b` |
| Signup URL | `https://build.nvidia.com/settings/api-keys` (or any model page → "Get API Key") |
| JSON / tool calling | Yes, both, but **per-model support varies** (NVIDIA flags this explicitly). Tool calling: OpenAI-compatible `tools`/`tool_choice` via vLLM's tool-calling engine. Structured output: `guided_json` / `guided_regex` / `guided_grammar` via `extra_body={"nvext": {...}}` (NVIDIA's recommended approach); plain `response_format: json_object` also supported but de-emphasized. |
| Sources | docs.api.nvidia.com/nim/reference/create_chat_completion_v1_chat_completions_post · docs.api.nvidia.com/nim/reference/llm-apis · developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members · forums.developer.nvidia.com/t/nvidia-nim-faq/300317 · docs.nvidia.com/nim/large-language-models/latest/advanced-use-cases/tool-calling-and-mcp.html · docs.nvidia.com/nim/large-language-models/1.12.0/structured-generation.html |
| Flags | **No verified numeric free-credit balance or fixed RPM for July 2026** — the single biggest gap in this research. Recommend the failover client poll the account's live rate-limit display/headers at build.nvidia.com rather than hardcoding a number. build.nvidia.com itself is a client-rendered SPA — could not read content directly via fetch, only confirmed reachable. |

### 3. Scaleway Generative APIs

| Field | Value |
|---|---|
| Provider name | "Generative APIs – Serverless" (2026 branding; formerly "Scaleway Generative APIs"). Do not confuse with "Generative APIs – Dedicated Deployment" (paid, provisioned capacity, formerly "Scaleway Managed Inference"). |
| OpenAI-compatible? | Yes, explicitly documented as "drop-in replacement for the OpenAI APIs." |
| Base URL | `https://api.scaleway.ai/v1` (project-scoped variant `https://api.scaleway.ai/{project_id}/v1`; default project omits the ID) |
| Chat completions endpoint | `https://api.scaleway.ai/v1/chat/completions` |
| Auth header | `Authorization: Bearer ${SCW_SECRET_KEY}` (NOT `X-Auth-Token` — that legacy header is for Scaleway's general infra API only) |
| Free tier | **Genuine ongoing free tier**: 1,000,000 tokens (text) or 60 min audio transcription per account/org, applied to most-expensive tokens first, no stated expiry (recurring product mechanic, not a one-time trial). Rate limits scale with account verification level — e.g. `mistral-small-3.2-24b-instruct-2506`: 200k→2,000k TPM (base→verified); `llama-3.3-70b-instruct`: 200k→400k TPM; all serverless models: 300→600 RPM; concurrency 50 both tiers; `whisper-large-v3`: 1,800→3,600 TPM. Separately, new **Business/Professional** accounts get a €100 signup credit (general Scaleway platform credit, not Gen-AI-specific), valid 3 months, redeemed within 24h of email. |
| Example model IDs | `glm-5.2`, `gpt-oss-120b`, `whisper-large-v3`, `qwen3.6-35b-a3b`, `qwen3.5-397b-a17b`, `qwen3-235b-a22b-instruct-2507`, `qwen3-embedding-8b`, `qwen3-coder-30b-a3b-instruct`, `gemma-4-26b-a4b-it`, `gemma-3-27b-it`, `llama-3.3-70b-instruct`, `mistral-medium-3.5-128b`, `mistral-small-3.2-24b-instruct-2506`, `voxtral-small-24b-2507`, `pixtral-12b-2409`, `devstral-2-123b-instruct-2512`, `bge-multilingual-gemma2`. **Caveat: `llama-3.1-8b-instruct` (used in the official quickstart code sample) is marked EOL for Serverless on the live supported-models page — the quickstart is stale, don't hardcode it.** |
| Signup URL | `https://account.scaleway.com/register` (append `?accountType=corporate&service=console` for the Business/credit-eligible flow) |
| JSON / tool calling | Yes, both. `response_format` (structured outputs) and `tools`/`tool_choice` (function calling) documented and supported. Explicitly **unsupported** params: `frequency_penalty`, `n`, `logit_bias`, `user`. |
| Sources | www.scaleway.com/en/docs/generative-apis/faq/ · www.scaleway.com/en/docs/generative-apis/api-cli/using-generative-apis/ · www.scaleway.com/en/docs/generative-apis/api-cli/using-chat-api/ · raw.githubusercontent.com/scaleway/docs-content/main/pages/organizations-and-projects/additional-content/organization-quotas.mdx · www.scaleway.com/en/docs/generative-apis/reference-content/supported-models/ · www.scaleway.com/en/generative-apis-signup/ · www.scaleway.com/en/docs/billing/how-to/redeem-voucher-code/ |
| Flags | €100 credit terms only confirmed via the signup landing page's embedded JSON (marketing copy, B-grade) vs. the docs.mdx facts (A-grade). |

---

## Part 2 — Additional providers (genuine ongoing free tiers, not trial credits)

Excluded from consideration (already covered elsewhere): Groq, Google Gemini, Cerebras, OpenRouter,
Together AI, Mistral, Cohere, GitHub Models, Cloudflare Workers AI, Hugging Face, SambaNova,
Hyperbolic, plus the 3 above.

### 4. Z.ai (Zhipu AI / GLM, formerly BigModel)

| Field | Value |
|---|---|
| OpenAI-compatible? | Yes |
| Base URL | `https://api.z.ai/api/paas/v4/` |
| Chat completions endpoint | `https://api.z.ai/api/paas/v4/chat/completions` |
| Auth header | `Authorization: Bearer <api_key>` |
| Free tier | `glm-4.5-flash` and `glm-4.7-flash` listed as **"Free" ($0 input/output/cached)** on the official pricing page — ongoing, not a trial. Official rate-limit language is thin ("refer to package benefits"); third-party sources converge on **~1 req/sec (~60 RPM), ~1,000 requests/day**, 128K context — treat as approximate/unconfirmed on primary docs. |
| Example model IDs | `glm-4.5-flash`, `glm-4.7-flash` (free); `glm-4.6v-flash` (vision) |
| Signup URL | `https://z.ai/chat` (email or Google login) → profile → API Keys; alt: `https://z.ai/model-api`. No card required. |
| JSON / tool calling | Function calling documented (`tools`, `tool_choice`, `tool_calls`) — confirmed for glm-4-plus/glm-4.6/glm-5; Flash-tier tool support only corroborated by third-party benchmarks, not the function-calling doc itself. Structured/JSON output documented separately. |
| Sources | docs.z.ai/guides/overview/pricing · docs.z.ai/guides/overview/quick-start · docs.z.ai/guides/capabilities/function-calling.md · docs.z.ai/guides/capabilities/struct-output.md |

### 5. OVHcloud AI Endpoints

| Field | Value |
|---|---|
| OpenAI-compatible? | Yes |
| Base URL | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` |
| Chat completions endpoint | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions` |
| Auth header | `Authorization: Bearer <api_key>` (registered tier). Anonymous, keyless access also works at a lower limit. |
| Free tier | **Ongoing, two levels.** Anonymous: **2 RPM per IP per model, no signup**. Registered (free API key via OVHcloud Manager): higher per-model RPM, exact number not published — note some Public Cloud "Discovery mode" (no payment method) projects may be blocked from the service; verify at signup whether a card-free account still unlocks the higher tier. |
| Example model IDs | `Meta-Llama-3_3-70B-Instruct`, `Mistral-Nemo-Instruct-2407`, `Qwen3.5-9B`, `gpt-oss-120b`, `gpt-oss-20b`, `BGE-M3` (embeddings), `whisper-large-v3-turbo` (ASR) — 20-40+ open-weight models total, EU-hosted. |
| Signup URL | `https://www.ovhcloud.com/en/public-cloud/ai-endpoints/` → OVHcloud Manager → Public Cloud → AI & Machine Learning → AI Endpoints → API keys |
| JSON / tool calling | Function calling supported (documented example). JSON output via `response_format: {"type": "json_schema", "json_schema": {...}}` (deterministic, schema-validated) or legacy `json_object`. Not all models support it — check the per-model "Response Format" field in the catalog. |
| Sources | docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-getting-started · GitHub ovh/docs structured-output guide |

### 6. Pollinations AI

| Field | Value |
|---|---|
| OpenAI-compatible? | Yes |
| Base URL | `https://text.pollinations.ai/` |
| Chat completions endpoint | `POST https://text.pollinations.ai/openai` (proxies `/v1/chat/completions` semantics) |
| Auth header | `Authorization: Bearer <token>` for registered ("Seed") tier; anonymous IP-based access needs no key at all (optional `?referrer=` param). |
| Free tier | **Ongoing, tiered by request interval, not credits.** Anonymous: 1 request/15 sec, no signup. Seed (free signup): 1 request/5 sec (~12 RPM). Paid tiers above ("Flower", "Nectar") are optional upgrades, not required. |
| Example model IDs | `openai`, `mistral` (aliases routing to underlying open models; exact backing model rotates — least stable of all providers researched for pinning a model ID) |
| Signup URL | `https://auth.pollinations.ai` (optional — anonymous access works without any account) |
| JSON / tool calling | Function/tool calling with tool definitions and execution — documented. JSON/structured output via `"json": true` request parameter. Streaming supported. |
| Sources | github.com/pollinations/pollinations/blob/main/APIDOCS.md |

---

## Rejected Part-2 candidates (checked, ruled out — no ongoing free tier)

- **DeepInfra** — $5 one-time signup credit, expires in 90 days; no ongoing free tier (separate "DeepStart" program is startup-only).
- **Novita AI** — Credit-based ($0.50 trial); its two $0 models (Ling-3.0-flash, Macaron V1 Venti) are explicitly labeled time-limited promotional free, not permanent.
- **xAI (Grok)** — No permanent free API tier; only a $25 one-time promo credit and an uncorroborated "$150/mo data-sharing" claim.
- **Alibaba DashScope/Qwen** — International OAuth free tier **discontinued April 15, 2026**; remaining signup bonus (70M tokens) requires a Chinese phone number, paid keys only afterward.
- **Baseten** — $30 one-time signup credit only.
- **Replicate** — Small one-time signup credit, pay-by-compute-time afterward.
- **Chutes AI** — Was community-subsidized/free via Bittensor in 2024-25; official pricing now confirms no free tier, moved to paid subscriptions ($3-20/mo) + PAYG in 2025.
- **Nebius AI Studio** — Only one-time/promo credits ($25-50 codes, startup credits); no ongoing free tier on official pricing docs.
- **GLHF.chat** — Site returned HTTP 522 (origin unreachable) on repeated fetch attempts — likely dead/unstable, not recommended.
- **SiliconFlow** — Conflicting evidence: third-party blogs claim 3 permanently-free models, but official pricing pages show them priced at $0.05-0.06/M tokens. Excluded for lack of verification.
- **AI21 (Jamba)** — $10 trial credit, 3-month expiry.
- **DeepSeek platform API** — 5M free tokens on signup, expires in 30 days.
- **Featherless AI** — No free tier; flat paid plans only, starting $25/mo.

---

## Summary table (config-ready)

| # | Provider | Base URL | Auth header | Genuine ongoing free tier? |
|---|---|---|---|---|
| 1 | Fireworks AI | `https://api.fireworks.ai/inference/v1` | `Authorization: Bearer $FIREWORKS_API_KEY` | No (10 RPM w/o card, $1 credit) |
| 2 | NVIDIA NIM (build.nvidia.com) | `https://integrate.api.nvidia.com/v1` | `Authorization: Bearer <NVIDIA_API_KEY>` | "Trial only" per NVIDIA, no fixed numbers — unverified |
| 3 | Scaleway Generative APIs | `https://api.scaleway.ai/v1` | `Authorization: Bearer ${SCW_SECRET_KEY}` | **Yes** — 1M free tokens/account, ongoing, plus rate-limited free tier |
| 4 | Z.ai (GLM) | `https://api.z.ai/api/paas/v4/` | `Authorization: Bearer <api_key>` | **Yes** — glm-4.5-flash/glm-4.7-flash $0, ongoing |
| 5 | OVHcloud AI Endpoints | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` | `Authorization: Bearer <api_key>` (or anonymous) | **Yes** — anonymous 2 RPM/IP, no signup needed |
| 6 | Pollinations AI | `https://text.pollinations.ai/` | `Authorization: Bearer <token>` (or anonymous) | **Yes** — anonymous 1 req/15s, ongoing |

All 6 are OpenAI-compatible at `/chat/completions` or an equivalent path, so a single adapter shape
should work across the whole failover chain with per-provider base URL + auth header + model ID
substitution.

## Key gaps / follow-ups before hardcoding into config

1. **NVIDIA NIM free-tier numeric limits are unverified for 2026** — poll the account dashboard or
   response headers (`x-ratelimit-*`) at runtime rather than hardcoding a number.
2. **Fireworks per-model RPM/TPM sub-limits** (below the account-wide 10/6,000 RPM ceiling) not
   directly confirmed — check `docs.fireworks.ai/guides/quotas_usage/rate-limits` before relying on it.
3. **Z.ai free-tier RPM/RPD figures are third-party-sourced**, not from Z.ai's own docs — re-verify
   or treat conservatively (build in headroom) in the failover logic.
4. **Pollinations model IDs (`openai`, `mistral`) are aliases that can rotate underlying weights** —
   least suitable of the six for pinning behavior/benchmarks across time.
5. Scaleway's official quickstart still references an EOL model (`llama-3.1-8b-instruct`) — always
   cross-check the live supported-models page, not cached examples, when selecting a model ID.
