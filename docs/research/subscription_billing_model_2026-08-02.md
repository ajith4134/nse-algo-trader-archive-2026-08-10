# Claude subscription billing model — does the bot's LLM lane cost dollars or burn usage? (2026-08-02)

**Backlog #2** (confirm `total_cost_usd` is telemetry, not billing) + the user's question "does the Claude
subscription rely on tokens present/left, not cost?". Grounded in (a) direct machine observation on this VPS
and (b) deep-research of Anthropic's official docs (Agent A, all grade-A first-party sources).

## Bottom line
The subscription lane is governed by a **rolling usage window (tokens/messages), NOT a dollar balance.**
`ResultMessage.total_cost_usd` / `model_usage[...].costUSD` are **client-side ESTIMATES** (tokens × bundled
list price), explicitly "not authoritative billing data" per Anthropic. So the bot's flat-cost subscription
lane spends *usage allowance*, not money — exactly why we default to Haiku + minimal options (stretch the
window) and fail over on cap.

## Machine evidence (directly observed on this box, 2026-08-02)
- Credential `~/.claude/.credentials.json`: `subscriptionType=max`, `rateLimitTier=default_claude_max_5x`,
  scopes incl. `user:inference`. No `ANTHROPIC_API_KEY` in env.
- A real Haiku call's `ResultMessage`:
  - `total_cost_usd = 0.0073762` — but derived from `usage` token counts
    (input 10, output 65, cache_read 15232, cache_creation 2464).
  - `model_usage[...].provider = 'firstParty'` — served on the subscription/first-party path, not a metered
    API key. Per-model `costUSD` is a computed figure, not a balance decrement.
  - Usage is reported entirely in **tokens** (input/output/cache); no dollar balance appears.
- SDK `RateLimitInfo` type exposes `utilization`, `resets_at`, `rate_limit_type`, `overage_status`,
  `overage_resets_at` — a utilization-that-resets governor (rolling window), not a wallet.

## Official-docs evidence (Agent A — all grade A, Anthropic first-party)
**Q1 — subscription OAuth vs API key billing.**
- `code.claude.com/docs/en/authentication.md`: Claude Code authenticates via a **Claude Pro/Max
  subscription login** OR an `ANTHROPIC_API_KEY`; the subscription OAuth from `/login` is the default for
  Pro/Max/Team/Enterprise. "If you have an active Claude subscription but also have `ANTHROPIC_API_KEY` set…
  the API key takes precedence once approved." → **our setup (no API key) runs on the subscription.**
- `code.claude.com/docs/en/costs.md`: "Claude Max and Pro subscribers have usage included in their
  subscription, so the session cost figure isn't relevant for billing purposes." "Usage inside the seat
  allowance isn't metered in dollars." (API-key path: "billed per token to your organization.")

**Q2 — `total_cost_usd` / `costUSD` is telemetry, not billing.** (CONFIRMED — closes #2)
- `code.claude.com/docs/en/agent-sdk/cost-tracking.md`: "The `total_cost_usd` and `costUSD` fields are
  **client-side estimates, not authoritative billing data**. The SDK computes them locally from a price
  table bundled at build time, so they can drift from what you are actually billed… **Do not bill end users
  or trigger financial decisions from these fields.**"
- `costs.md`: "Claude Code computes the dollar figure locally from token counts priced at standard list
  rates… may differ from your actual bill."

**Q3 — rolling-window usage, not a dollar balance.**
- Pro plan (`support.claude.com/.../8325606`): "session-based usage limit will reset every five hours" +
  "a weekly usage limit that applies across all models."
- Max plan (`support.claude.com/.../11049741`): "Max plans also have two weekly usage limits: one across
  all models and another for Sonnet models only." "Weekly limits reset at a fixed time each week."
- Usage credits (`support.claude.com/.../12429409`): "session limits reset every five hours as usual";
  **usage credits** = an OPTIONAL dollar-balance top-up "charged separately… appear as additional charges"
  that only activates AFTER the time-window allowance is exhausted. ← this is the `overage_status` concept.

### Not verified by A (open)
- No single Anthropic page states the "5-hour window" for the **Max** plan by name (only Pro + the credits
  article state 5-hour explicitly; Max's own page states only the weekly reset). Numeric Max-5x caps not
  published as hard numbers.
- Q4 (ToS on programmatic/bot use of the subscription via the SDK) — pending Agent C.
- Practitioner triangulation — pending Agent B.

## Practitioner triangulation + policy timeline (Agent B — GitHub Issues, HN; grades noted)
- **Subscription window, not dollars — triangulated.** `code.claude.com/docs/en/costs` (A): "Claude Max and
  Pro subscribers have usage included in their subscription." HN benchmark author (C, 2026-07): chose "Claude
  Max subscription rather than metered API billing" for cost. GitHub #45572 (C): audit found pure OAuth
  `claudeAiOauth` + `rateLimitTier: default_claude_max_5x`, no API key — matches our box exactly.
- **⚠️ Agent-SDK billing is a MOVING TARGET.** Anthropic announced (May 2026, HN #48133373/#48124760) a
  monthly dollar credit for Agent SDK + `claude -p` usage separate from the subscription window (Pro $20,
  **Max 5x $100**, Max 20x $200); went live ~June 15; **PAUSED June 16** (HN #48550740/#48562079; live
  support article 15036540: "nothing has changed: Claude Agent SDK, `claude -p`, and third-party app usage
  **still draw from your subscription's usage limits**"). **Net as of 2026-08-02: our SDK-driven lane draws
  the subscription 5-hour/weekly window** — favorable, but Anthropic may re-attempt the credit split; if they
  do, our lane would hit a $100/mo (Max 5x) credit then stop unless overage enabled. Watch for this.
- **`total_cost_usd` unreliable — confirmed 2×–100× off.** GitHub #53371 ("~$0.03 expected vs $3.67
  reported"), #74297 (one 37-min session reported $1175 vs org's whole-day real $642), #64701 (stale price
  map). Every source says compute cost from token counts, ignore the field. Reinforces: telemetry only.
- **At the cap → hard rate-limit error, not silent dollar spend.** `costs` (A): "'You've hit your session
  limit' / 'weekly limit'… shows when the window resets." GitHub #83025 (C): an 82-agent fan-out hit "5-hour
  utilisation 101% → 'You've hit your session limit'". Our `LlmRateLimitError` fail-over is the right handler.
- **ToS (Q4) — MATERIAL, surfaced not gated (per `personal_use_no_tos_legal_gating`).**
  `code.claude.com/docs/en/legal-and-compliance` (A): "Advertised usage limits for Pro and Max plans assume
  **ordinary, individual usage** of Claude Code and the Agent SDK." + "**OAuth authentication is intended
  exclusively for purchasers** of … subscription plans … **Developers** building products … including those
  using the Agent SDK, **should use API key authentication.**" The 2025 rate-limit announcement (HN
  #44713757) explicitly targets "running Claude 24/7 in the background" + "advanced usage patterns."
  **Read for us:** an always-on trading organism driving the subscription via the SDK is outside the
  "ordinary individual" framing Anthropic assumes, and 24/7 background use is a named clamp target. This is a
  personal, never-distributed project (user policy: don't scope-down over ToS; build ban-resistant), so the
  feature stays — the fail-over pool (groq/google/local) IS the ban-resistance. But the honest risk: the
  subscription lane can be rate-limited or (if the credit split returns) capped; the organism must never
  depend on it. Our design already treats it as a best-effort lead lane with automatic fail-over. ✔

## Max-5x limits + ToS depth (Agent C — grades noted)
**Limits (A4/A1/A2/A3).**
- 5-hour rolling session window: confirmed live (support 9797557 / 12429409, updated 2026-05-18) but
  Anthropic publishes NO absolute message/token number — it "varies" by message length, context, tool use,
  model, effort; users see their own figure at `claude.ai/settings/usage`.
- Two weekly caps on Max: one all-models + one Sonnet-only (support 11049741). Current live page gives only
  the relative multiplier ("Max 5x = 5× Pro per session"), NO absolute hours.
- Historical numbers (Grade B, TechCrunch 2025-07-28, effective 2025-08-28, "as of Aug 2025 — currency
  unverified today): **Max 5x ≈ 140–280 h Sonnet/wk + 15–35 h Opus/wk**; Pro ≈ 40–80 h Sonnet/wk; Max 20x ≈
  240–480 h Sonnet + 24–40 h Opus. Anthropic said <5% of subscribers affected.
- Measurement = model/context-weighted consumption (not flat message count); cached content doesn't recount.
- Overage = opt-in **usage credits**: bill at standard API rates past the included allowance, **$2,000/day**
  redemption cap, set a monthly ceiling; 5-hour window still resets as usual. This is `overage_status`.

**ToS (B1–B4) — the reconciliation.**
- Consumer Terms (A, eff. 2025-10-08) §3.7: bars automated/bot access "**Except when you are accessing our
  Services via an Anthropic API Key or where we otherwise explicitly permit it**." Also bars reselling +
  training-on-output.
- The **explicit permission** exists: support 15036540 (A, 2026-06-16) — Agent SDK / `claude -p` /
  third-party-app usage on subscription auth is documented + draws the subscription window. `code.claude.com/
  docs/en/authentication` (A) ships **`claude setup-token`** → a **one-year OAuth token** via
  `CLAUDE_CODE_OAUTH_TOKEN` explicitly "For CI pipelines, scripts, or other environments where interactive
  browser login isn't available" that "authenticates with your Claude subscription," and its docs anticipate
  "sessions that run unattended." → Anthropic BUILDS FOR unattended subscription automation.
- The restriction that DOES bite (agent-sdk/overview, A): "Anthropic does **not allow third party developers
  to offer claude.ai login or rate limits for their products** … Use API key authentication instead." Read
  with B2, this targets **multi-tenant products that log in OTHER people's** claude.ai creds
  (reselling/exposing subscription auth to end users) — NOT a single developer automating their OWN
  subscription. **nse-algo-trader is personal, non-distributed → this does not apply.**
- Usage Policy (A, eff. 2025-09-15): anti-abuse targets multi-account evasion, spam, automated
  account-creation, reselling — **no clause against a single-account personal trading bot.** No Anthropic
  text names "trading bot" as permitted or forbidden.

## BOTTOM LINE (all 4 sub-questions, triangulated A-grade)
1. **Billing model:** subscription auth (no API key) draws the **rolling 5-hour + weekly USAGE window**, not
   dollars. Our box: `provider:firstParty`, token-based usage, `rateLimitTier=default_claude_max_5x`. ✔
2. **`total_cost_usd`/`costUSD`:** **client-side ESTIMATE, not billing** — Anthropic says so outright;
   practitioners measured it 2×–100× wrong. Never use it for a financial decision. **#2 CLOSED.** ✔
3. **Limits:** 5-hour rolling + two weekly caps (all-models + Sonnet-only); absolute numbers unpublished
   today (≈140–280 h Sonnet/wk for Max 5x per 2025 press, currency unverified); overage = opt-in usage
   credits at API rates, $2k/day cap. Cap → hard `rate-limit` error, not silent spend. ✔
4. **ToS for our use:** personal, single-user automation of your OWN Max subscription via the Agent SDK is an
   **officially-supported, documented path** (`claude setup-token` is purpose-built for it). The "use API
   key" rule targets multi-tenant products, not personal automation. Caveat: limits assume "ordinary
   individual usage"; a 24/7 organism can exhaust the window / be rate-limited, and Anthropic once tried
   (paused) to split SDK usage onto a $100/mo credit. So treat the subscription lane as best-effort with
   fail-over — which our design already does. ✔ (Surfaced, not gated — personal-use policy.)

## Implication for our architecture
- Subscription lane correctly modelled: cap = rate-limit window (not out-of-money) → `LlmRateLimitError`
  fail-over to groq/google is right. The organism must NEVER hard-depend on it (it doesn't). ✔
- **`total_cost_usd` is telemetry** — do not drive any decision from it. **#2 CLOSED.**
- **Actionable follow-ups (Rule K → BACKLOG):**
  (a) durability — mint a one-year token via `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` for the VPS so
  the always-on lane doesn't depend on interactive re-login;
  (b) watch for the paused Agent-SDK **credit-split** returning (would cap our lane at $100/mo Max-5x then
  stop unless overage enabled) — if it returns, revisit the lead-lane choice;
  (c) surface `RateLimitInfo.utilization`/`resets_at` as a **cap gauge** on the LLM Gateway panel (the real
  governor is window utilization, not cost).
