# Conversational assistant — dashboard chat box wired to the LLM gateway

**Seed (user):** *"a chat box on the dashboard to chat with the bot and ask questions — connect that chat
box with this Claude-Code LLM."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring · backend = [idea #8 gateway](../research/llm_gateway_spec_2026-08-02.md) · state = [idea #5 memory](advanced_intelligence_stack_catalog.md)

---

## 1. The bigger picture (expand-idea)
A **conversational agent interface to the organism** — natural-language Q&A + explanation over the bot's
LIVE state/memory, powered by idea #8's Claude-subscription gateway. The "talk to your trading bot" panel
+ the explainability/trust layer + the game-NPC conversational feel the user wants. Category = an
**LLM assistant grounded in the system's own real state** (not a generic chatbot).

## 2. Components
1. **Chat panel (frontend)** — a dashboard panel with streaming replies (WebSocket/SSE) for responsiveness.
   **REUSE the existing dashboard** (`dashboard_server` / `render_dashboard_html` / feature-surface
   registry) — add a panel + a `/chat` streaming endpoint, no new app. *(dataviz skill governs the panel's
   visual design + any chart the bot renders inline.)*
2. **Assistant agent (backend, the "NPC" persona)** — question → **retrieve relevant internal state**
   (RAG over positions · P&L · regime · engine health · the experience/trade ledger · SYSTEM_MAP · docs,
   via idea #5 memory/Graphiti) → answer via the gateway (**Haiku default, Sonnet for deep analysis,
   streaming**, thinking-off for simple Qs). Grounded — **never hallucinate a number**, always cite the
   real state it read.
3. **Read-only STATE-TOOL layer** the assistant may call: `get_positions` · `get_pnl` · `get_regime` ·
   `explain_last_trade` (the SHAP/mechanism trail from idea #4) · `get_engine_health` · `query_ledger` ·
   `get_backlog`. Deterministic tools return real data; the LLM narrates.
4. **Action layer (optional, GATED)** — if you ask it to DO something (pause a strategy, flatten, change a
   param), it **PROPOSES → you confirm → routes through the risk gate** (never autonomous). Default = read-only.

## 3. Example questions it answers
"Why did it trade RELIANCE?" (→ explain_last_trade + SHAP) · "What regime are we in and why?" · "How's the
premium-seller engine doing?" · "What's my open risk / Greeks right now?" · "Which tipster sources are
surviving?" · "What did the news organ see on HDFC today?" · "Pause the ORB engine" (→ propose+confirm+gate).

## 4. Security (ties to idea #4 §7-security)
The assistant is a **PRIVILEGED reader** of internal state → it must **NOT place orders autonomously**
(only propose→confirm→gate), must **never expose secrets/.env**, and its tools are an allowlisted
read-only set. Your chat input is trusted (it's you), but the same no-web→capital-without-the-gate
invariant holds: nothing the chat says places a trade without the deterministic risk gate + your confirm.

## 5. Base → Advanced → Ultra
- **Base ✅:** chat panel + streaming + Haiku assistant grounded in positions/P&L/regime read-only tools.
- **Advanced 🚀:** full state-tool set + `explain_last_trade` (SHAP) + memory recall (Graphiti) + inline
  charts (dataviz) + Sonnet for deep analysis.
- **Ultra 🌌:** proactive push ("⚠️ engine #2 drifting, want me to pause it?"), voice, the assistant as the
  reflective-memory narrator (turns the ledger into spoken lessons), gated action execution.

## 6. Wiring / reuse (Rule G)
Backend → **idea #8 gateway** (Haiku/streaming). State → **idea #5 memory** + existing
`dashboard/*`, `memory_reflection`, `risk_management`, engine surfaces. Frontend → existing dashboard +
new chat panel + `/chat` stream. New: `assistant_agent` + read-only `state_tools` + the chat endpoint.

## 7. Owed (Rule K)
Build-time: the visual panel via the **dataviz skill**; sourcing a chat-UI component only if the existing
dashboard frontend can't host it (likely it can). Verify streaming latency on the gateway (warm client).

## 8. Finalized decision _[pending — recommend build AFTER idea #8 gateway (its backend) + a first engine to talk about]_
