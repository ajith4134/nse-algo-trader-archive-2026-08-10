# 140 — News/Sentiment ingestion architecture (the user's browsing-agent idea)

**Status:** DESIGN DISCUSSION (Rule D) — building deferred until sourcing research (138 sources,
139 browsing-agent tooling) lands + the open decisions below are settled with the user.
**Trunk:** II SENSES — sentiment/news branch (was PAUSED for this discussion; now un-paused into design).
**Sourcing in flight:** research/138 (news sources + sentiment engines), research/139 (autonomous
browsing-agent OSS + "PhoneDriver" verification). Do NOT build until these return.

## The user's idea (2026-07-26, verbatim intent)
Inspired by a viral Threads post (`prediction_desk`): a phone auto-opens ~6 Chinese news apps every
half hour, screenshots headlines, sends summaries to an AI (Claude), which compares Polymarket odds and
gives betting calls — the edge being the **time lag** (Chinese news → English traders react, 20–50 min).
Post credits an OSS "PhoneDriver" that lets the AI view screens and operate apps like a human.

The user wants the NSE-trading analog:
- An AI agent that **autonomously visits ALL the Indian stock-market news sites** (Moneycontrol /
  "moneyview" and others), **logging in with the user's own email** where needed, **screenshotting /
  scraping** the pages.
- **Store only the updates relevant to OUR trading segments**, in **priority order**:
  1. **Index options first** — e.g. NIFTY **support & resistance levels** quoted in news articles
     (Moneycontrol etc.).
  2. **Stock news tied to stock OPTIONS or INTRADAY stocks.**

## Honest read (Rule I — acquire, but don't oversell)
- The viral *numbers* are marketing; ignore them. The *mechanism* — vision/LLM agent reads news, extracts
  a structured signal, trades the reaction lag — is real and buildable.
- The **phone** is a gimmick (good video). The professional build is a **headless browser-agent on this
  server**: more reliable, cheaper, no physical taps to break, runs unattended. (139 confirms the tool.)
- **Login with the user's real credentials = a real trade-off to surface, not hide:** most Indian
  financial news (Moneycontrol, ET, Business Standard) is **public — no login needed**. Login only helps
  for paywalled research, and it risks (a) ToS violation, (b) credential security, (c) account bans. →
  Default to **public/feed access, no login**; use the user's login ONLY on sites they explicitly choose,
  credentials via `.env`, never committed. (Open decision D3.)

## Proposed architecture — feed-first, vision-fallback (the sound version)
A **two-tier ingestion** → **extraction** → **relevance/priority filter** → **store** → **sense** →
**decision gate**. Tiering matters: screenshotting a page that publishes an RSS feed is 100× slower,
costlier, and more fragile. Screenshot only when there is no feed and the value is in rendered content.

```
                 ┌── Tier 1: FEEDS (cheap, reliable) ──────────────┐
 scheduler ──────┤   RSS / JSON / news-API pulls (research/138)    │
 (cadence in     │   + NSE/BSE structured announcements            │
  live service)  └──────────────────┬──────────────────────────────┘
                 ┌── Tier 2: BROWSING AGENT (research/139) ─────────┐
                 │   headless browser → article text; screenshot +  │
                 │   vision only when DOM is messy / feed absent /   │
                 │   user-login site (their choice)                 │
                 └──────────────────┬──────────────────────────────┘
                                    ▼
        EXTRACTION (our existing free-tier LLM pool + local FinBERT/VADER, research/138)
        headline/article → { segment, instrument, event_type, levels?, sentiment, confidence }
                                    ▼
        RELEVANCE + PRIORITY FILTER  (drop anything not in our segments; rank)
          P1 index-option levels (NIFTY/BANKNIFTY support & resistance numbers)
          P2 stock-option / F&O-stock catalysts (results, upgrades, block deals, ban-list)
          P3 intraday-stock movers / general market tone
                                    ▼
        STORE (SQLite: item, source, ts, segment, priority, extracted levels, sentiment, dedup key, decay)
                                    ▼
        NEWS/SENTIMENT SENSE (per-underlying flags + market-wide mood) — the Trunk-II branch
                                    ▼
        DECISION CONSUMER (entry gate): defer/size-down on adverse news or a pending event on the
        underlying; NIFTY S/R levels inform option strike/stop context. (Rule K: not done until wired.)
```

### The real prize = STRUCTURED extraction, not collection
Collecting headlines is easy; the value is turning an article into numbers the bot can act on, e.g.
`{underlying: NIFTY, type: support_resistance, support:[24800,24650], resistance:[25100,25320],
source:"moneycontrol", ts:..., confidence:0.7}`. That is an LLM-extraction prompt over the fetched text
(we already have the pool). Same for per-stock: `{symbol: INFY, event: results, when: today_amc,
stance: caution}`. This is what makes it a SENSE and not a news reader.

### Latency-edge analog for NSE (the post's actual insight)
India's version of the "news→reaction lag": pre-open reactions, results-day moves, and **global cues**
(GIFT/SGX Nifty, US close, Asian-session news) that Indian retail reacts to with a delay. Worth tagging
items with freshness so the gate can weight breaking vs stale.

## Decomposition → parts (building-features-from-ideas)
1. **Scheduler/cadence** — reuse the live-service `_maybe_run_*` pattern (EXISTS).
2. **Feed pullers** — RSS/API clients per source (research/138 picks the sources).
3. **Browsing agent** — headless browser + vision fallback + optional login (research/139 picks the tool).
4. **Extractor** — LLM-pool prompt + local sentiment model → structured records (parts EXIST: LLM pool,
   + FinBERT/VADER to vendor per 138).
5. **Relevance/priority filter + dedup + decay** — thin custom glue (self-describing names).
6. **Store** — extend the SQLite store (EXISTS: `market_data_sqlite_store` pattern).
7. **Sense** — `news_sentiment` module: per-underlying flags + market mood (NEW, pure).
8. **Dashboard surface** + **entry-gate consumer** (Rule N + Rule K).

## Build order (slices, one at a time — Rule A)
- **S1 Feed base:** tier-1 public feeds → extractor → store → sense → dashboard surface (no browsing
  agent yet, no login). Fastest path to a live, real-data-verified news sense.
- **S2 Structured levels:** NIFTY/BankNifty support/resistance extraction (P1) — the user's #1 ask.
- **S3 Source reliability:** per-source reputation (beta-reputation) + Stouffer weighting + calibration
  gate + manipulation flag — wired so every stored item carries a source-reliability weight. (Reuses
  VI/XIII organs → gives them a real consumer.)
- **S4 Browsing agent:** headless browser for feed-less sites + broker/TradingView (tier-2) + vision
  fallback (research/139 stack).
- **S5 Social tier:** X/FinTwit + Telegram ingestion (tier-3) — advisory-until-proven via S3's gate;
  early-warning role only.
- **S6 Login seam:** build the disabled-by-default login path (config flag + `.env` slot); NOT enabled
  until the user decides free data is insufficient (D3).
- **S7 Decision consumer:** wire the sense into the entry gate (defer/size on adverse news + S/R
  context), reliability-weighted; social alone can't act. (Rule K: the sense isn't "done" until here.)

## SOURCE RELIABILITY & TRUST (user's idea, 2026-07-26 — the keystone guardrail)
The user asked: after testing all 3 source tiers, give each data source a **reliability score**,
especially for the noisy **social-media + Telegram** tier. STRONGLY ENDORSED — and it reuses trust
machinery WE ALREADY BUILT, so it's wiring, not from-scratch. This also finally gives the XIII/VI
reputation organs a real consumer (Rule K win).

- **Per-source reputation (reuse VI/XIII beta-reputation):** each source (per site AND per Telegram
  channel / X handle) has α successes / β failures → `reliability = α/(α+β)` with uncertainty. A claim
  ("NIFTY support 24800", "INFY gaps up") is later SCORED against outcome (did price respect the level /
  did the catalyst hit) → update the source's reputation. Social/Telegram start **untrusted, must earn
  it**; public news gets a modest prior.
- **Weighted evidence combination (reuse Stouffer's Z):** an item's influence = its content × its
  source reliability. A low-reliability source **alone never moves the entry gate**; independents that
  corroborate combine (Stouffer) to cross threshold.
- **Tier roles (the latency edge, made safe):**
  | Tier | Speed | Trust | Role |
  | Social/Telegram | fast | earned-only | EARLY-WARNING — raises attention, can't act alone |
  | Public news (MC/ET/BS/LiveMint/NDTV Profit) | medium | modest prior | CONFIRMATION |
  | Broker research / TradingView ideas | medium | per-source track record | the S/R numbers |
- **Calibration-gate (reuse the LLM-risk-gate pattern):** a channel's signals stay ADVISORY until its
  measured reliability crosses a bar — an unproven pump channel cannot drag the bot into a trap.
- **Manipulation flag (reuse XIII misinformation-resistance):** social/Telegram items get a
  pump/coordination check (that tier is where pump-and-dumps live).

## Open decisions — RESOLVED with the user (2026-07-26)
- **D1 Ingestion priority:** ✅ **feed-first + vision-fallback.** Browsing agent for the gaps.
- **D2 Site list / tiers:** ✅ **ALL 3 tiers** — (1) big public: Moneycontrol, Economic Times Markets,
  Business Standard, LiveMint, NDTV Profit; (2) broker research / TradingView ideas (explicit S/R
  levels); (3) social: X/FinTwit + Telegram. **Each tier + source gets the reliability score above.**
- **D3 Login/paywall:** ✅ **public-only ACTIVE now**; **also build the login path behind a
  DISABLED-BY-DEFAULT seam** (config flag + `.env` credential slot, never committed) so it can be
  enabled later "if the free data becomes insufficient" (user's words). Not wired to real logins until
  the user flips it. (Rule J seam — never leaks to prod while off.)
- **D4 Sentiment engine mix:** ✅ LLM pool + FinBERT/VADER (BOTH) — LLM for nuance/level-extraction,
  local model for cheap bulk polarity. Confirm split at S1.

## SOURCED STACK — resolved from research/138 + /139 (2026-07-26, real searches)
The two sourcing passes landed. The recommended **free** stack:

| Part | Chosen | Why (from 138/139) | Notes / risk |
|---|---|---|---|
| Structured announcements | **`nse` PyPI (`BennyThadikaran/NseIndiaApi`)** | Only free wrapper exposing board-meetings, results-calendar, bulk/block deals, general announcements; **documented 3 req/s throttle** | Needs NSE session-cookie handshake; poll 1–5 min in-hours |
| News feeds (tier-1) | **The Hindu BusinessLine + Economic Times Markets RSS** | Freshest, most reliably reachable, sub-hourly | Category firehose → need our own company-name→NSE-symbol matcher |
| — Moneycontrol | **verify-at-runtime** | 138 says RSS dead (stale-behind-200); 139 says specific URLs live from this box | **Per-feed staleness detection required** (pubDate vs wall-clock) — resolves the conflict empirically |
| Sentiment engine | **FinBERT (`ProsusAI/finbert`)** primary + **VADER/pysentiment2** light pre-filter | 91–93% F1 on SEntFiN (India headlines); VADER poor on finance (pre-filter only) | HEAVY: CPU-only torch ≈ **1.75 GB installed**; throughput fine at our volume |
| LLM scoring | **existing free-tier LLM pool** (materiality-escalation) | FinBERT-triage → LLM-escalation hybrid = ~5× fewer LLM calls, actually return-correlated | Score **sentiment AND materiality as separate fields**; **no chain-of-thought** (hurts this task); batch 10–20 headlines/call; async (don't block the order loop) |
| Ticker/company NER | **spaCy + an NSE-name gazetteer** | headlines lack ticker tags; must map company→symbol | needs an NSE alias gazetteer (RIL/M&M/L&T short-forms) |
| Rendering (tier-2) | **crawl4ai** (Playwright) | mature (75k★), persistent login sessions, LLM-clean Markdown, ARM64-capable | only for feed-less sites / full article bodies |
| Login bootstrap (tier-3) | **Skyvern** (or browser-use) behind the disabled seam | best 2FA/password-manager support | seam DISABLED by default (D3) |
| Browsing "PhoneDriver" | **REJECTED — doesn't exist as claimed** | 139 verified: the viral tool is unsubstantiated; the one real repo is an unrelated Android-ADB/Qwen controller | build the headless-server version |

### Real risk flags to surface (human decisions, per Rule I — not silently ignored)
- **ToS/legal on full-article scraping:** ET's and LiveMint's ToS **explicitly prohibit automated
  scraping**, even for logged-in subscribers; IT Act §43/§66 is the statutory hook; **no controlling
  Indian case law found**. Polling the **RSS headline feed** is consistent with robots.txt and low-risk;
  **fetching full article bodies** is the higher-risk step. → **S1 uses RSS headlines only**; full-body
  fetch (S4) is a separate gated decision needing a dedicated legal-risk `deep-research` pass first.
  (Tracked in BACKLOG.)
- **Business Standard + NDTV Profit:** Akamai-403-blocked from this egress even for robots.txt; NDTV
  Profit has no live RSS. → out of S1 scope; retest from production egress later (BACKLOG).
- **FinBERT heavy dep (~1.75 GB CPU torch):** one-time install; pin the CPU-only wheel. Confirm with user.
- **NSE/BSE session-cookie fragility:** all free announcement access depends on a working cookie layer
  + defensive retry/backoff (BACKLOG).
- **Insider-trading (PIT) is T+2-lagged by SEBI regulation; credit-rating SDD endpoint not yet
  reverse-engineered** — both capped/deferred (BACKLOG), not in the early slices.

## Rules ledger
- Rule D: this doc IS the persisted design (pre-build). Rule I: sourcing via 138/139 (real searches).
- Rule K: the entry-gate consumer (S5) is the PRIMARY consumer — the sense is NOT "done" until S5 lands;
  tracked in BACKLOG. Rule G: every slice wires forward (no orphan). Rule F/J: each slice real-data
  verified (news is available even market-closed → real pass is feasible without an open session).
