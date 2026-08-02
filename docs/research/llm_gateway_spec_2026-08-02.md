# SPEC — Universal LLM Gateway (Claude-subscription-backed, Ollama-style endpoint)

**Idea (idea #11):** one Ollama-style callable LLM endpoint that the ENTIRE organism's agents/organs call
for ALL current + future LLM needs, **replacing pay-as-you-go APIs**. Headline lane = the **Claude Max/Pro
subscription exposed as that endpoint** (maximized for flat cost); local (Ollama) + free-cloud as fallback
lanes; auto-fallback when the Claude lane is capped. "Advanced like game NPCs" = it drives autonomous
agentic behavior (personas, tools, multi-turn), not one-shot completions.
**Date:** 2026-08-02 · via `idea-to-institutional-spec` (interview answered) · **Status:** SPEC (build-ready pending confirm)

## 1. Intent & the decision it changes
Every LLM-using organ (news NLP, dual-LLM quarantined reader, browser/online-research, tipster parsing,
DSPy self-evolution, arbiter narration, and all FUTURE ones) currently would each hit a metered API. This
engine inserts **one internal LLM interface** all organs call; behind it a **router** picks a lane by the
cost-ladder ([[feedback_llm_cost_routing_ladder]]), **maximizing the Claude subscription** lane. It changes
the system's unit-economics (flat vs metered) and makes LLM capability a shared, swappable substrate — no
organ ever binds to a provider (mirrors the broker-swappable rule).

## 2. Interview answers (locked)
- **Scope:** unified gateway, but the STAR lane = Claude Max/Pro subscription exposed like an Ollama
  endpoint; local + free-cloud + paid-last also lanes.
- **Build vs reuse:** find existing first, build only if none fits.
- **Workloads:** ALL current + future LLM features route through it (it replaces metered API usage).
- **Risk/limits:** MAXIMIZE the Claude lane, AND auto-fallback when capped/limited.

## 3. Sourcing (real, via `gh` 2026-08-02 — WebSearch exhausted; deeper mechanical triage owed)
| Part | Adopt | ⭐/note | Verdict |
|---|---|---|---|
| **Universal gateway shell** | **LiteLLM** (BerriAI) | 55k, OpenAI-compat proxy, 100+ providers, **fallback chains**, Ollama lane, budgets/keys | **ADOPT** — don't rebuild the router |
| **Local lane** | **Ollama** | 177k | **ADOPT** — the local-endpoint lane + the mental model |
| **Claude-subscription lane** | **🟢 LOCKED: official Claude Agent SDK** as a LiteLLM custom provider (user, 2026-08-02) | (CLI-wrap + wrapper-repos were the alternatives — rejected for brittleness) | **BUILD-THIN** — ~150-line LiteLLM custom handler driving the **Claude Agent SDK**; ⚠️ **KEY VERIFY: configure it to run on the Max/Pro SUBSCRIPTION auth (Claude Code OAuth), not a metered API key** — this is the make-or-break check |
| Front-ends (not needed as backend) | open-webui / LibreChat | 147k/41k | reference only |
**Owed (Rule K):** mechanical-fact triage of the specific CLI-wrapper repos (installs? uses subscription
OAuth vs API key? maintained? streaming? tool-use passthrough?) — a `sourcing-oss-parts` pass when WebSearch resets.

## 4. Architecture (SOTA analog: LiteLLM gateway + Ollama local-endpoint pattern)
```
organs (news NLP · quarantined reader · browser research · tipster parse · DSPy · arbiter · FUTURE…)
   → ONE OpenAI-compatible interface  (base_url = local gateway; model = "organism/<tier>")
   → ROUTER (LiteLLM) picks a lane by policy + live health:
        lane 1  CLAUDE SUBSCRIPTION  (claude -p / Agent SDK, flat cost)   ← maximize
        lane 2  local Ollama         (MiniCPM/Qwen/Llama, free)
        lane 3  free-tier cloud      (rotating keys)
        lane 4  paid API             (Kimi/Anthropic, last resort, sparingly)
   → on cap/429/ban/error on a lane → automatic FALLBACK to the next
   → returns OpenAI-schema response (with tool-calls) → organ acts (agentic/NPC pattern)
```
- **"Game-NPC" agentic pattern:** each organ = an agent object with a **persona/system-prompt + tools +
  its own memory** (idea #5: Graphiti), all calling the one gateway — like an Ollama-backed game NPC.
- **Never on the hot trade path:** LLM organs PROPOSE/READ; the deterministic gate decides (idea #4
  invariant). So gateway latency (subscription can be seconds) is fine.
- **🟢 MODEL-ROUTING RULE (user directive 2026-08-02, MEASURED):** the Claude lane defaults to **Haiku**
  (bulk/simple) → **Sonnet** (medium reasoning); **NEVER Opus by default** — escalate to Opus only on a
  *demonstrated* shortfall (mirrors the cost-ladder / crypto-bot Rule 1). ALWAYS minimal options
  (`setting_sources=[]`, no tools unless the organ needs them, terse system prompt). Use **exact model IDs**
  (`claude-haiku-4-5`, `claude-sonnet-…`), not loose aliases ("sonnet" mis-resolved to haiku in testing).
  Measured effect: **$0.34 (Opus default) → $0.037 (Haiku+minimal) → $0.0006 (cache-warm)** per call.
- **🟢 SPEED RULE (user directive 2026-08-02, MEASURED):** benchmark — Haiku 5.9s/9.0s, Sonnet 4.4s/4.7s on
  a reasoning task → **latency is dominated by per-call Agent-SDK HARNESS STARTUP (~3–5s), NOT the model**
  (Haiku ≈ Sonnet). ⟹ **the real "fast" lever is a PERSISTENT WARM gateway** — long-lived SDK client /
  reused session / **streaming** tokens, never cold-spawn per request. Secondary: **thinking OFF + effort
  `low`** for simple organs (SDK params `thinking`/`effort`/`max_thinking_tokens` exist but are TYPED
  objects, not bools — wire exact schema at build), thinking ON only for hard-reasoning organs (arbiter,
  self-evolution). **Reasoning safety net:** LLM only PROPOSES; the deterministic gate does the real math,
  so an occasional model slip (Haiku got the 160-pt spread math right, Sonnet slipped to 60) is caught —
  never trust the number, verify it. ⚠️ warm calls can resolve to the prior model's cache → pin exact model
  ID per call; use `fallback_model` for lane resilience.

## 5. Engine-grade acceptance criteria (Rule P)
1. A running **OpenAI-compatible endpoint** (`/v1/chat/completions`, streaming, tool-calls) all organs call.
2. **≥3 live lanes** wired (Claude-subscription, Ollama-local, one cloud) with a **policy router** that
   prefers/maximizes the subscription lane.
3. **Automatic fallback** proven: kill/cap lane 1 → request still succeeds on lane 2 (test).
4. **Usage/limit awareness**: tracks the Claude lane's cap state; backs off + falls back before hard-fail;
   logs per-lane spend/usage (dashboard surface).
5. **Swappable seam**: no organ imports a provider SDK directly — all go through the gateway client (Rule G).
6. Tests: unit (router policy, fallback) · adversarial (lane down / 429 / malformed) · **Rule-F real call
   through EACH lane, outputs inspected**.

## 6. Verification (Rule F/J)
**🟢 SUBSCRIPTION LANE — REAL-DATA VERIFIED 2026-08-02 (spike passed):**
- `claude -p "…SPIKE_OK_1234"` → returned exact sentinel, **4s, exit 0**, no `ANTHROPIC_API_KEY` in env,
  OAuth `~/.claude/.credentials.json` present → **subscription-backed completion WORKS**.
- **Claude Agent SDK v0.2.128** (`pip install claude-agent-sdk`) → `query(...)` returned the sentinel,
  `provider:firstParty`, no API key → **also subscription-backed**. Transport choice (Agent SDK) confirmed usable.
- **⚠️ EFFICIENCY FINDING (build-critical):** that trivial call reported **`costUSD≈0.34`, model
  `claude-opus-5`, ~33.7k cache-creation tokens** — the Agent SDK loads the FULL Claude Code agent harness
  (system prompt + tools + Opus-5 default) PER CALL. Heavy → would burn the 5-hr/weekly caps fast at volume.
  **Mitigations (into the build):** (a) set a cheap model per call (Haiku/Sonnet) via options; (b) strip
  system prompt + disable tools for simple completions; (c) route only HEAVY reasoning to the Claude lane,
  send bulk/small calls (news sentiment etc.) to **Ollama/local** — the cost-ladder + fallback already does this.
- Still to verify: Ollama lane + a cloud lane + forced-cap→fallback (Rule F). Sim (Rule J): fake lane for
  router/fallback unit tests. **Minor owed:** confirm the `costUSD` is telemetry-only (subscription), not
  metered billing (no API key present ⇒ subscription, but confirm no balance decrements).

## 7. Depth justification (not a thin proxy)
A thin version = a single hardcoded curl to one endpoint. This engine has: a real **policy router** (lane
selection by cost-ladder + live health + cap-state), **fallback state machine**, **usage/limit tracking**,
per-organ **persona/tool/memory agent wrapper**, streaming + tool-call passthrough, and a swappable
provider registry — genuine infra, LOC justified by function.

## 8. Honest blockers to surface (Rule O)
- **ToS/ban risk:** exposing the Max/Pro subscription as a programmatic backend likely violates Anthropic
  terms → account-suspension risk. User accepted (personal use) + wants maximize-with-fallback → the
  fallback lanes ARE the mitigation (a ban degrades, doesn't halt). Surfaced, not blocked (per user rule).
- **Usage caps:** Max = 5-hour + weekly limits, not high-QPS → the router must throttle/queue heavy
  batch LLM work and shed to local/free lanes; never assume unlimited.

## 9. Decomposition (build order)
(a) LiteLLM gateway stood up + Ollama lane · (b) Claude-subscription custom provider (CLI/Agent-SDK, verify
subscription auth) · (c) policy router (cost-ladder + cap-state) + fallback state machine · (d) per-organ
agent wrapper (persona+tools+memory) · (e) usage/limit tracking + dashboard surface · (f) migrate existing
`llm_strategy` + news_sentiment organs onto the gateway (Rule G, no orphan). Next: `building-engine-grade-features`.
