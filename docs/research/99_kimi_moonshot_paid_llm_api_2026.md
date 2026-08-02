# Kimi / Moonshot AI Paid LLM API Lineup — as of 2026-07-25

Research protocol: deep-research (multi-angle web search + primary-source WebFetch of official docs,
triangulated against 3+ independent secondary sources for pricing figures). All model IDs, context
windows, and prices below are read directly from Moonshot's official developer docs unless flagged
"secondary source."

## 0. Important platform-rebrand finding (grade A, primary)

As of this research date, **`platform.moonshot.ai` 301-redirects to `platform.kimi.ai`**, and
**`platform.moonshot.cn` 301-redirects to `platform.kimi.com`**. The API base URLs
(`api.moonshot.ai` / `api.moonshot.cn`) are unaffected and still work — only the *developer console /
docs* domains were renamed. Any bookmark to `platform.moonshot.ai/docs/...` still resolves correctly
via redirect. Treat `platform.kimi.ai` as the canonical docs URL going forward.

## 1. Current chat model lineup

| model_id | context window | max output tokens | input $/1M (cache-miss / cache-hit) | output $/1M | reasoning ("thinking")? | tool-calling / JSON | best_for |
|---|---|---|---|---|---|---|---|
| `kimi-k3` | 1,048,576 (1M) | default 131,072; settable up to 1,048,576 via `max_completion_tokens` | $3.00 / $0.30 | $15.00 | **Yes — always-on**, no disable toggle. Controlled via `reasoning_effort`: `low` / `high` / `max` (default `max`) | Full tool calling incl. `tool_choice="required"`; native **JSON Schema strict structured output** via `response_format` (constrains only the final `content` field, not `reasoning_content`) | Flagship — long-horizon coding, agentic knowledge work, deep numeric/logical reasoning, native vision, 1M long-context |
| `kimi-k2.7-code` | 262,144 (256K) | not published separately from context window | $0.95 / $0.19 | $4.00 | Thinking **always on**, cannot be disabled | Tool calling documented; JSON mode not separately documented for this SKU | Coding-agent tasks, high-reliability instruction following in long contexts |
| `kimi-k2.7-code-highspeed` | 262,144 | not published | $1.90 / $0.38 | $8.00 | Thinking always on | Same as k2.7-code | Same as k2.7-code, ~180 tok/s (up to ~260 tok/s short-context) — speed-optimized, 2x price |
| `kimi-k2.6` | 262,144 | not published | $0.95 / $0.16 | $4.00 | **Optional** — `thinking: {"type":"enabled"|"disabled"}` | Tool calling + vision (text/image/video input); JSON mode support not explicitly documented for this SKU (present on sibling k2.5) | General-purpose: chat, vision, coding, agent tasks |
| `kimi-k2.5` | 262,144 | not published | $0.60 / $0.10 | $3.00 | Optional — same `thinking` toggle as k2.6 | Explicitly documented: tool calling, **JSON mode**, partial mode, web search | Budget multimodal agent/coding tasks |
| `moonshot-v1-8k` (+ `-vision-preview`) | 8,192 | not published | $0.20 | $2.00 | No | Legacy | **Legacy — sunsetting Aug 31, 2026**, no longer offered to new signups |
| `moonshot-v1-32k` (+ `-vision-preview`) | 32,768 | not published | $1.00 | $3.00 | No | Legacy | Legacy, same sunset |
| `moonshot-v1-128k` (+ `-vision-preview`) | 131,072 | not published | $2.00 | $5.00 | No | Legacy | Legacy, same sunset |

All prices are **USD**, on the international `api.moonshot.ai` endpoint, per official pricing pages
(`platform.kimi.ai/docs/pricing/chat-{k3,k26,k27-code,k25,v1}`). Prices exclude tax, calculated at
checkout by jurisdiction. Context caching is **automatic** (no manual cache management needed) once a
repeated prompt prefix exceeds 256 tokens; cache-hit price is roughly 10x cheaper than cache-miss
across the lineup.

### Discontinued / do not use
- `kimi-k2` series (the original, non-versioned K2 line) — discontinued **May 25, 2026**.
- `kimi-latest` — discontinued **Jan 28, 2026**.
- `kimi-thinking-preview` — discontinued **Nov 11, 2025**.

### China region (secondary confirmation)
`platform.kimi.com` (China console) bills in **CNY (¥)** — e.g. cache-hit shown as "¥2.00 / MTok" for
one SKU — confirming a genuinely separate China pricing/account system from the international
`api.moonshot.ai` USD pricing above. The China API base URL `https://api.moonshot.cn/v1` is
well-triangulated across independent third-party integration docs (LiteLLM, VoltAgent, Portkey) but
was not re-confirmed on an official pricing page during this pass — treat as grade B (secondary,
triangulated) rather than grade A.

## 2. API access details

- **International base URL**: `https://api.moonshot.ai/v1` (grade A, official docs)
- **China base URL**: `https://api.moonshot.cn/v1` (grade B, triangulated secondary sources — separate
  account/billing in CNY)
- **Auth**: standard `Authorization: Bearer $MOONSHOT_API_KEY` header (grade A)
- **OpenAI compatibility**: confirmed — "Kimi API is compatible with OpenAI's interface specifications,"
  same `/v1/chat/completions` endpoint and message schema; official docs show swapping `base_url` and
  `api_key` in the stock OpenAI SDK as the only required change. `tool_choice` accepts `none` / `auto` /
  `required` (the `required` value is called out specifically for `kimi-k3`) / `null`. (grade A)
- **Notable OpenAI-API deltas**: `temperature` range is `[0, 2]` on OpenAI vs **`[0, 1]`** on Kimi;
  `temperature=0` with `n>1` errors instead of returning duplicate completions on Kimi.
- **Signup**: create an account at `https://platform.kimi.ai/` (redirects from `platform.moonshot.ai`),
  then generate a key at `https://platform.kimi.ai/console/api-keys`. Minimum **$1 recharge** required
  before the key can be used.

## 3. Rate limits / tier structure (grade A, official docs — `docs/pricing/limits`)

Tiers are keyed to **cumulative account recharge**, not calendar time or spend velocity:

| Tier | Cumulative recharge | Concurrency | RPM | TPM | TPD |
|---|---|---|---|---|---|
| Tier 0 | $1 | 1 | 3 | 500,000 | 1,500,000 |
| Tier 1 | $10 | 50 | 200 | 2,000,000 | Unlimited |
| Tier 2 | $20 | 100 | 500 | 3,000,000 | Unlimited |
| Tier 3 | $100 | 200 | 5,000 | 3,000,000 | Unlimited |
| Tier 4 | $1,000 | 400 | 5,000 | 4,000,000 | Unlimited |
| Tier 5 | $3,000 | 1,000 | 10,000 | 5,000,000 | Unlimited |

At $5 cumulative recharge a one-time $5 usage voucher is issued (does not itself advance the tier).
For a daily-cadence single-agent workload, Tier 0/1 is more than sufficient — the practical constraint
is just clearing the $1 minimum recharge to activate the key.

## 4. Recommendation for the "strategic analyst" use case

**Recommended: `kimi-k3`.**

The task needs (a) strong reasoning over structured numeric/statistical facts, (b) reliable forced
JSON/tool-call structured output, (c) reasonable cost, with (d) latency explicitly not a constraint
(daily cadence). `kimi-k3` is Moonshot's flagship reasoning model — thinking is **always on** (no risk
of accidentally calling it in a shallow non-thinking mode the way you could with k2.5/k2.6), and
`reasoning_effort` can be pinned to `"max"` for the deepest deliberation on each daily run, since
latency doesn't matter here. It has native `response_format` JSON-Schema **strict** mode, which is the
most reliable structured-output guarantee in the lineup (schema is enforced by the API, not just
prompted for) — a good match for "reads calibration facts, returns a strict JSON findings/hypotheses/
distrust-list reflection." Tool-calling includes a hard `tool_choice="required"` mode, useful if the
JSON output is implemented as a forced tool call rather than `response_format`. At $3/$15 per 1M
tokens, a once-daily analyst pass over a bounded set of calibration facts (order of low tens-of-
thousands of tokens in, low thousands out) costs a few cents to low tens of cents per run — trivial
against the value of a "pinned HIGH, reliable paid provider" role in the pool. Its 1M context window
is also generous headroom if the calibration-fact payload grows over time without needing to switch
models later.

**Cheaper fallback candidate**: `kimi-k2.6` with `thinking: {"type":"enabled"}` — roughly 3-4x cheaper
per token ($0.95/$4.00 vs $3/$15) and still supports tool calling + vision, but thinking is optional/
togglable (a misconfiguration risk) and it lacks k3's confirmed native strict JSON-Schema mode in the
docs reviewed. Good as a second paid provider in the pool for cost-sensitive runs, not as the primary
choice given the emphasis on reliability over cost here.

**Avoid**: any `moonshot-v1-*` model (legacy, sunsetting Aug 31 2026, no native thinking mode) and any
of the explicitly discontinued IDs (`kimi-k2`, `kimi-latest`, `kimi-thinking-preview`).

## 5. Sources (primary unless marked secondary)

- https://platform.kimi.ai/docs/models — model list, capabilities, discontinuation dates
- https://platform.kimi.ai/docs/api/models-overview — per-model parameter defaults, thinking-mode
  toggle mechanics, `reasoning_effort` field
- https://platform.kimi.ai/docs/pricing/chat-k3 — kimi-k3 pricing, context window
- https://platform.kimi.ai/docs/pricing/chat-k26 — kimi-k2.6 pricing
- https://platform.kimi.ai/docs/pricing/chat-k27-code — kimi-k2.7-code(-highspeed) pricing
- https://platform.kimi.ai/docs/pricing/chat-k25 — kimi-k2.5 pricing, capability list (tool/JSON/web
  search)
- https://platform.kimi.ai/docs/pricing/chat-v1 — moonshot-v1 legacy pricing
- https://platform.kimi.ai/docs/pricing/limits — rate-limit tier table
- https://platform.kimi.ai/docs/guide/migrating-from-openai-to-kimi — base URL, auth, OpenAI
  compatibility, tool-call migration notes
- https://platform.kimi.ai/docs/guide/kimi-k3-quickstart — `max_completion_tokens` default/max,
  `response_format` JSON-Schema strict example, tool-calling patterns, recommended use cases
- https://platform.kimi.ai/docs/api/tool-use — tools/tool_choice schema, `strict` parameter
- https://platform.kimi.ai/docs/guide/use-context-caching-feature-of-kimi-api — automatic prefix
  caching mechanics, 256-token minimum prefix, cache pricing
- https://platform.kimi.com/ — China console, confirms separate CNY billing (secondary confirmation of
  China region split)
- https://www.marktechpost.com/2026/07/16/moonshot-ai-releases-kimi-k3-... — secondary, triangulates
  K3 architecture (2.8T params / 16-of-896 experts MoE, Kimi Delta Attention, July 16 2026 release
  date) and pricing against the primary docs above. Note: this article's benchmark-competitor names
  appeared inconsistent with known real model names and were excluded from this report as
  unreliable/likely-garbled by the source; only the architecture/pricing/date facts (independently
  corroborated by the primary docs) were kept.
- LiteLLM PR #12804, VoltAgent docs, Portkey docs — secondary, triangulate `api.moonshot.cn/v1` as the
  China API base URL (not re-verified on an official pricing page in this pass)

## 6b. Independent re-verification (2026-07-25, session 2) — DECISION CONFIRMED

Before committing to a paid key, the `kimi-k3` recommendation was independently re-verified
against Moonshot's LIVE docs in a second session (the first pass's model IDs looked unfamiliar,
so they were treated as suspect until re-grounded). Every claim below was re-read from the
canonical `platform.kimi.ai` docs and cross-checked against ≥3 independent third parties
(OpenRouter, DeepInfra, Morph, APIpulse, CostGoat). **The original finding holds — `kimi-k3`
is real, current, and the right pick.** Confirmed values (primary, from the K3 quickstart):

| Property | Confirmed value (2026-07-25) |
|---|---|
| Exact API model ID | `kimi-k3` |
| Strict structured output | ✅ `response_format` `json_schema` with `strict: true` (constrains final `content`) |
| Forced tool calls | ✅ `tool_choice="required"` |
| Context / max output | 1M context; `max_completion_tokens` default 131,072, settable up to 1,048,576 |
| Reasoning | `reasoning_effort` = low / high / **max (default)** — always-on max reasoning |
| Price | $3.00 in / $15.00 out per 1M; cache-hit input $0.30/1M |
| Endpoint | `https://api.moonshot.ai/v1` (docs site moved to `platform.kimi.ai`; **API host unchanged**) |
| Activation | **$1 minimum recharge** required before a key works (Tier 0) |

Also re-confirmed the current lineup (`kimi-k3` flagship; `kimi-k2.7-code`, `kimi-k2.6`,
`kimi-k2.5` value tiers; `moonshot-v1-*` legacy) and that `kimi-k2` / `kimi-latest` /
`kimi-thinking-preview` are discontinued. Cheaper second-slot option remains `kimi-2.5`
($0.60/$3.00, documented JSON mode). **Action: obtain a `kimi-k3` key; wire as env
`MOONSHOT_API_KEY`, model `kimi-k3`, pinned above the free tier (backlog Layer 11 / #20).**

Re-verification sources: `platform.kimi.ai/docs/guide/kimi-k3-quickstart`,
`platform.kimi.ai/docs/pricing/chat`, morphllm.com/kimi-api, openrouter.ai/moonshotai/kimi-k2.6,
deepinfra.com/blog/kimi-k2-6-pricing-guide-deployment-tradeoffs.

## 6. What was not covered / residual gaps

- Exact `max_output_tokens` ceiling for `kimi-k2.5`, `kimi-k2.6`, `kimi-k2.7-code(-highspeed)` was not
  published on their individual pricing pages (only `kimi-k3`'s `max_completion_tokens` default/ceiling
  of 131,072 / 1,048,576 was explicit in docs).
- JSON Schema **strict structured output** was explicitly confirmed for `kimi-k3` and `kimi-k2.5`; for
  `kimi-k2.6` and the `k2.7-code` SKUs the capability likely exists (same model family/API surface) but
  was not explicitly documented on the pages fetched — verify empirically before depending on it in
  production for those specific SKUs.
- Official confirmation of `api.moonshot.cn/v1` as the live China base URL from an official pricing/docs
  page (only secondary/integration-library sources were checked, though 3 independent ones agree).
