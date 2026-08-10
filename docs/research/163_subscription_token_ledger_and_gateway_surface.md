# 163 — Subscription Haiku-4-5 token ledger + LLM Gateway surface

**Ask (user, 2026-08-03):** on the LLM Gateway — subscription-backed provider pool panel, show the
**tokens consumed for the Claude Haiku 4.5 subscription** (session usage — user picked "Show session
usage", pointed at the LLM Gateway panel in a photo).

## What "tokens consumed" means here — scope decision
The panel is the **bot's** LLM Gateway (`strategic_llm_analyst` surface), whose LEAD lane is
`claude-code-subscription · claude-haiku-4-5`. So "tokens consumed for the Haiku subscription" =
tokens the bot's gateway has burned through the subscription lane **this process/session**, split by
canonical model.

Two candidate sources considered:
1. **Claude Code CLI session jsonl** (`~/.claude/projects/**/*.jsonl`) — has real `usage` per assistant
   message and 282 `claude-haiku-4-5-20251001` messages across logs. REJECTED as the primary source: it
   mixes the dev-session harness with the bot subprocess and is not scoped to the gateway's serves; it is
   also off-process file scraping for a number the provider already receives in-band.
2. **SDK `ResultMessage.usage` on each subscription serve** — the provider *already* walks the message
   stream in `_extract_text_and_model` and reads `usage`/`modelUsage` (today only pulls `canonicalModel`,
   discards the token counts). CHOSEN: authoritative, exactly scoped to the Haiku lane, in-band, and it
   reuses the **same process-wide-telemetry pattern** the panel already trusts for warm/cold serve counts
   (`_SubscriptionTransportTelemetry`). Rule F real-data source = the actual SDK usage of real serves.

## Sourcing (Rule O.1) — no OSS part needed
This is a ~single-file thread-safe integer accumulator over an SDK-provided dict. No library is a better
fit than stdlib `threading.Lock` + a dict (cf. `_SubscriptionTransportTelemetry` two structs above it in
the same file). No OSS rejection to surface — building a bespoke counter here is the right call, and it is
a complete implementation, not a lite subset.

## Design
- **`_SubscriptionTokenLedger`** (new, in `claude_code_subscription_provider.py`, mirrors the transport
  telemetry struct): thread-safe, per-canonical-model accumulation of `input`, `output`, `cache_read`,
  `cache_creation`, derived `total`, plus `serves` count. Module global `_TOKEN_LEDGER`; public
  `subscription_token_ledger()` returns a snapshot `{model: {input,output,cache_read,cache_creation,
  total,serves}, "_all": {...}}`.
- **Capture seam:** `_extract_text_and_model` is the ONE place every serve's message stream is walked
  (cold via `_run`, warm via the injected `extract` callback in `WarmClaudeSubscriptionSession`). It now
  also folds each message's `usage`/`modelUsage` into the ledger, keyed by the resolved canonical model.
  Handles BOTH real SDK shapes defensively:
  - flat `{"input_tokens":N, "output_tokens":M, "cache_read_input_tokens":.., "cache_creation_input_tokens":..}`
    (the shape seen in real jsonl) → attribute to the resolved model;
  - nested per-model `{"<model>": {"inputTokens":.., "canonicalModel":".."}}` → attribute per key.
  Field-name normalization tolerates camelCase/snake_case. Non-int values ignored. Tokens are counted at
  extraction (before JSON parse) because they are spent regardless of parse success.
- **Surface:** `_strategic_llm` in `live_paper_trading_service.py` reads the ledger for the lead model and
  adds a `tokens` metric (`"12,904 (in 3.1k · out 1.2k · cache 8.6k) · 4 serves"` style, compact) to the
  `strategic_llm_analyst` surface. Zero serves → `"0 (idle)"`.
- **Render:** `render_dashboard_html.py` appends a `tokens` KPI to the gateway KPI row.

## Verification
- **Rule J (hermetic):** unit test injects a fake SDK message stream carrying a real-shaped `usage` dict
  through the SAME `_extract_text_and_model` seam and asserts ledger totals + panel metric string. No
  subscription usage spent.
- **Rule F (real-data):** the ledger populates automatically on the next real subscription serve (the
  daily reflection cadence / any live gateway call). Until a real serve lands this process, the panel
  honestly shows `0 (idle)`. Logged as the one permitted Rule-K activation blocker (function complete;
  real-serve population is automatic, no code change).

## Rules touched
H/H.1 SYSTEM_MAP + diagram · B flowchart 09 · N dashboard surface + re-verify · K BACKLOG entry ·
C self-describing names · G wired into the live serve path (no orphan).
