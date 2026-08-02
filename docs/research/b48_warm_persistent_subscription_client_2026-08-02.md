# B48 — Warm-persistent Claude subscription client + cap→fallback verification

**Date:** 2026-08-02 · **Slice:** Phase-0 / 0.1 (LLM gateway) · **Rule P engine, Rule D design doc**
**Follows:** `docs/research/llm_gateway_spec_2026-08-02.md` (the gateway spec) ·
`src/nse_algo_trader/llm_strategy/claude_code_subscription_provider.py` (the lane this speeds up).

## Problem (measured, not assumed)
The subscription lane bridges the async Agent SDK with `anyio.run(self._run, request)` **per call**, and
`_run` uses the SDK's one-shot `query()`. Every `query()` **spawns a fresh `claude` CLI subprocess**,
loads the harness, then answers. That cold start dominates the ~4–9 s/call latency — the model inference
on Haiku is a small fraction. For a trading organism polling an LLM lane repeatedly, per-call subprocess
spawn is the wrong cost. **Warming the subprocess is the real speed lever** (spec §4 note).

## Goal
Keep ONE `claude` subprocess alive across calls so the 2nd…Nth structured generation skips cold start,
WITHOUT (a) leaking conversation context between independent calls, (b) blocking the sync provider pool,
or (c) turning a transport death into a hard failure. Preserve the exact `LlmProvider` contract and the
cap→failover behaviour (a cap/ban must DEGRADE to the next lane, never HALT).

## Grounded API facts (introspected from the installed SDK, not memory)
- `claude_agent_sdk` **0.2.128**, `anyio` **4.14.2**.
- `ClaudeSDKClient`: persistent bidirectional client — `connect()`, `query(prompt, session_id='default')`,
  `receive_response()` (async iterator until the turn's `ResultMessage`), `set_model(model)`, `disconnect()`.
- **`query()` takes a per-call `session_id`** → independent structured calls run in ISOLATED sessions on the
  SAME warm subprocess ⇒ warm speed with no context bleed. This is the crux that makes warming safe.
- `set_model()` switches model on the warm client with no reconnect.
- Sync↔async bridge: `anyio.from_thread.start_blocking_portal()` runs an event loop in a background
  thread; `portal.call(async_fn, *args)` invokes an async fn on that loop from any (sync) thread and
  blocks for the result. The persistent `ClaudeSDKClient` lives on that loop for its whole lifetime.

## Sourcing (Rule I / O.1 — actual evaluation, no new install introduced)
No NEW third-party package is added: the LLM transport was already decided in
`llm_gateway_spec_2026-08-02.md` (**official `claude-agent-sdk`**, installed 0.2.128), and the only new
need is a **sync→persistent-async bridge** for the process-lifetime client. Candidates evaluated for that
bridge (introspected on this box, not README prose):
- **`anyio.from_thread.BlockingPortal`** (`start_blocking_portal`) — CHOSEN. Already a transitive dep
  (anyio 4.14.2, confirmed importable); purpose-built to own a background event loop and run coroutines on
  it from sync threads; the `ClaudeSDKClient` is itself anyio-based, so no loop-mismatch. Zero new install.
- **Hand-rolled `threading.Thread` + `asyncio.new_event_loop` + `queue.Queue`/`Future`** — REJECTED
  (tier-2: I know the failure modes): reimplements exactly what `BlockingPortal` already provides
  (loop lifecycle, cross-thread call marshalling, exception propagation), more code to get wrong, no
  upside. Depth without function = padding (Rule P).
- **`asgiref.sync.AsyncToSync`** — REJECTED (tier-1): not installed; pulls the ASGI stack; designed for
  per-call loop bridging, not owning ONE long-lived connection across many calls (the whole point here).
- **`nest_asyncio`** — REJECTED (tier-1): monkeypatches the global event loop; fragile under uvicorn's
  running loop (the dashboard server), a known footgun. Not installed, would not add.
Conclusion: use the SDK's own `ClaudeSDKClient` + `anyio` portal already present — nothing to install.

## Design — `WarmClaudeSubscriptionSession` (the engine)
A process-lifetime singleton owning: a `BlockingPortal` (background event loop) + one connected
`ClaudeSDKClient` + a monotonic session counter.
- **Lazy start, once** (double-checked lock): first `run_structured()` opens the portal and connects the
  client with generic connect-time options (`model=Haiku`, `setting_sources=[]`, `allowed_tools=[]`,
  `max_turns=1`, a generic JSON-only `system_prompt`). Per-request `system_instruction` is folded into the
  prompt body (connect-time options are fixed), so one warm client serves every request shape.
- **Per-call isolation:** each `run_structured` uses `session_id=str(next(counter))` ⇒ clean context.
- **Warm speed:** the subprocess stays up between calls; only the first call pays cold start.
- **Reconnect on death:** a `CLIConnectionError`/`ProcessError`/broken-pipe marks the client dead; the next
  call reconnects transparently (bounded retry). A never-connecting client raises so the provider falls
  back to the one-shot path.
- **Graceful shutdown:** `atexit` disconnects the client and stops the portal.
- **Model override:** if a request's model differs from the warm client's current model, `set_model()`
  before the query (default path keeps Haiku, so no switch cost).

### Provider integration (degrade, never halt — Rule O.3)
`ClaudeCodeSubscriptionProvider.generate_structured` tries the warm session first; if the warm session
cannot start (SDK missing / connect fails) it falls back to the existing one-shot `anyio.run(query)` path.
Both paths feed the SAME `_extract_text_and_model` + `_first_json_object` + error-mapping code, so cap →
`LlmRateLimitError`, transient → `LlmProviderUnavailableError` is identical warm or cold. A
`CLAUDE_SUBSCRIPTION_WARM_DISABLED=1` escape hatch forces the cold path (self-calibrating, no hard-code).

## Acceptance criteria (Rule P gates)
1. **Real engine:** a genuine persistent-subprocess session with carried state (portal + client + counter),
   not a wrapper. ✔ by construction.
2. **Warm < cold on REAL data (Rule F):** measured on the live subscription, call #2 latency < call #1
   (cold) by a clear margin. Market-independent → runnable now, no blocker.
3. **No context bleed:** call B does not see call A's content (distinct `session_id`). Verified by a
   two-call probe whose 2nd answer cannot be contaminated by the 1st.
4. **Cap→fallback (Rule J hermetic):** a fake subscription lane raising `LlmRateLimitError` inside the real
   `SwappableMultiProviderLlmClient` ⇒ the NEXT lane serves; `served_by_provider` is the fallback. No prod
   leak (fake lives under tests/).
5. **Reconnect-on-death (Rule J hermetic):** an injected fake warm client that dies once ⇒ the session
   reconnects and the call still succeeds; a permanently-dead client ⇒ provider falls back to cold path.
6. **Error-mapping parity:** warm path maps cap/transient signals exactly like the cold path (shared code).
7. **Static gate:** ruff + mypy clean.

## Verification plan
- Hermetic (always): warm-session unit tests with an injected fake `ClaudeSDKClient` (connect-once,
  session-per-call, reconnect-once, permanent-death→raise) + the cap→fallback integration test through the
  real swappable client. DI seam: `client_factory` injected, prod uses the real SDK.
- Real-data (Rule F, runnable now): a one-off latency probe (`scripts/`) issuing 3 warm calls on the live
  subscription, asserting call #2/#3 ≪ call #1 and printing served-by/model. The single permissible open
  blocker if the OAuth token is expired at run time: log it, re-run after `claude` re-login.

## Depth justification (what a thin version would omit)
A thin version = "reuse a module-global client". It would leak context across calls (wrong answers +
runaway cost), deadlock the sync pool on the async client's loop, and turn any transport hiccup into a hard
failure. The engine's weight is the portal-owned loop, per-call session isolation, reconnect state machine,
and the cold-path fallback — each closes a real failure mode, none is padding.

## Dashboard surface + wiring (Rule G/N)
Consumer: the existing `strategic_llm_analyst` surface + LLM Gateway panel. Add a `transport` metric
(`warm` / `cold`) so the panel shows whether the fast path is live. No new panel needed.
