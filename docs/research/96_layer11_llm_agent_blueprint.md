# research/96 — Layer 11 (Strategic LLM / Autonomous-Research-Agent) BLUEPRINT + slice 1

**Date:** 2026-07-25
**Status:** BLUEPRINT (Rule D) + slice-1 BUILD. Layer 11 = the generative/agentic-AI layer,
grounded in the real Layer-10 memory (340 experiences, calibration, opponent ledger, info
diet). Skill: building-features-from-ideas (decompose → source per part → assemble).

## Target (whole layer)
An LLM layer that READS the real §9/§10 memory and produces higher-order strategic reasoning —
critique, debate, causal analysis, allocation — that feeds back into the bot's decisions and
monitoring. NOT a chatbot; a structured, grounded, gated reasoning layer whose outputs are
tracked and (eventually) trusted only after they earn calibration, exactly like every mechanism.

## Decomposition into slices (each a buildable feature)
1. **LLM client seam** (FOUNDATIONAL — slice 1): `StrategyLlmClient` protocol + a Claude-backed
   impl behind a DI seam + an injected fake for hermetic tests. Structured output via the
   Anthropic tool-use pattern. Everything else depends on this.
2. **Memory-grounded analyst role** (slice 1, the first consumer): builds a structured prompt
   from the REAL memory (worst-calibrated mechanisms, forecast skill, opponent lean, diet
   health) → LLM → a structured `StrategicReflection` (findings + hypotheses + a distrust list).
   Surfaced on the dashboard (feature registry). Read-only (advisory) at first.
3. **Debate-as-risk-check** (slice 2): bull/bear/risk roles debate a mechanism/thesis →
   disagreement score = a risk signal; wired into the entry gate (like the opponent-ledger
   defer). Advisory→gating only after it earns calibration.
4. **Causal analysis** (slice 3): LLM over the multi-hop outcome clusters → causal hypotheses
   about WHY a mechanism fails, feeding the assumption registry.
5. **Meta-strategy allocator** (slice 4): LLM weights strategies/champion-configs from memory.
6. **Prediction-market council weighting** (slice 5): combine multiple model/role opinions,
   weighted by their track record.
7. **Synthetic stress rehearsal** (slice 6): LLM generates stress scenarios for the per-trade
   pre-mortem (ties to Layer 7.5).

## Sourcing (per part)
- **LLM client:** the official **`anthropic` Python SDK** (DEPEND; Rule I — installed). Models
  per the `claude-api` skill (claude-opus-4-8 / claude-sonnet-5 / claude-haiku-4-5). Structured
  output via a forced tool call. No lighter fit — the SDK is the right piece.
- **Agent orchestration** (debate/council): start with plain sequential SDK calls (no framework);
  revisit the SDK's tool-runner/managed-agents only if orchestration grows. Avoid heavy agent
  frameworks (LangChain etc.) — not needed for structured single/few-shot calls.
- **Prompt/context building + output schema:** project-specific glue — build.

## Slice 1 — LLM seam + memory-grounded analyst (THIS BUILD)
**Files:**
- `src/nse_algo_trader/llm_strategy/strategy_llm_client.py` — `StrategyLlmClient` protocol,
  `ClaudeStrategyLlmClient` (anthropic SDK, forced-tool structured output), `FakeStrategyLlmClient`
  (tests). Never hardcodes a key — reads `ANTHROPIC_API_KEY` at the composition root.
- `src/nse_algo_trader/llm_strategy/memory_grounded_strategy_analyst.py` — builds the prompt from
  the real memory read-model and returns a `StrategicReflection`.
- feature-surface row + manifest entry; hermetic tests (fake LLM); a real-Claude verify script.

**Success test (Rule F/J):** hermetic — an injected fake LLM returns a canned structured
reflection; assert the prompt CONTAINS the real memory facts (worst mechanism, forecast bits,
opponent lean) and the parsed `StrategicReflection` is surfaced. **Real-Claude pass = OPEN
BLOCKER** until `ANTHROPIC_API_KEY` is provided (then a real reflection over the 340-experience
memory).

## ADDENDUM (2026-07-25) — slice 1 BUILT + user pivot to a swappable multi-provider pool
The user redirected: **not Anthropic-only** — supply ~14 FREE-TIER cloud LLM keys now (paid
Anthropic later) and **"create a swappable system where when limit hit you use the other."**
So slice 1's client became a **swap-on-limit multi-provider pool**, not a single Claude client:

- `strategy_llm_client.py` — provider-neutral seam (`StrategyLlmRequest/Response`,
  `StrategyLlmClient` + `LlmProvider` protocols, exception hierarchy: `LlmRateLimitError` /
  `LlmProviderUnavailableError` / `LlmResponseFormatError` / `AllLlmProvidersExhausted`).
- `openai_compatible_chat_provider.py` — ONE generic HTTP adapter (`requests`, injected) covering
  every OpenAI-compatible free-tier cloud (Groq, Cerebras, SambaNova, NVIDIA, Google AI Studio,
  OpenRouter, DeepInfra, Fireworks, HuggingFace router, DeepSeek, Z.ai, Alibaba DashScope,
  Mistral, Cloudflare Workers AI). Forces JSON via `response_format` + schema-in-prompt.
- `anthropic_claude_provider.py` — optional (lazy `anthropic` import) for the future paid key;
  pins FIRST in the pool when `ANTHROPIC_API_KEY` is present.
- `swappable_multi_provider_llm_client.py` — ordered pool; on 429 → cooldown (honours
  Retry-After) and try next; injected monotonic clock for deterministic tests; served-by trail.
- `llm_provider_registry.py` — builds the pool from `.env`, self-sizing to whatever keys exist
  (0 keys → empty pool → dashboard shows "blocked"; per-provider `{NAME}_MODEL` overrides).
- `memory_grounded_strategy_analyst.py` — unchanged intent: grounds a `StrategicReflection` in
  the REAL §10 calibration facts.

**Keys:** stored in gitignored `.env` under canonical names; NEVER committed/echoed.
**Wiring (Rule G):** `live_paper_trading_service._maybe_run_strategic_reflection` runs the
analyst on a daily cadence; surface `strategic_llm_analyst` (Rule N).
**Verification:** hermetic 17 tests (fake LLM/provider — Rule J) AND **REAL-DATA pass done
(Rule F)** — `scripts/verify_layer11_strategic_analyst_realdata.py`: Groq served a grounded
reflection over the real 340 experiences, flagging the +64pp / +42pp over-confident ORB
mechanisms and distrusting them. The earlier "real-Claude pass blocked on key" is now RESOLVED
via the free-tier pool. Model IDs are sensible defaults; a background research pass on free-tier
providers refines them (see docs/research index).

## Rules / blockers
- **Rule I:** `anthropic` SDK installed; the API KEY is a user secret → Rule-F blocker (build
  behind DI, hermetic-verify now, real pass pending key — the broker-creds pattern).
- **Rule G/N:** the analyst's reflection is surfaced on the dashboard (real consumer). Feeding
  LLM outputs into DECISIONS (the gate) is gated behind calibration — slice 2+, queued.
- **Rule K:** slices 2–6 + the gating-consumer are queued in BACKLOG.
- **Never commit the key** — `.env` gitignored, same as broker creds.
