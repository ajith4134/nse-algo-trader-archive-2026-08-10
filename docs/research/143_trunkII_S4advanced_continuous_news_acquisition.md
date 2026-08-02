# research/143 — Trunk II SENSES · S4-advanced: continuous multi-site live news acquisition

**Origin:** user idea (2026-07-26, with 6 screenshots of a "top open-source tools" carousel). Not
just "fetch article bodies once" (the original S4), but an **in-built browser that keeps ALL the
Indian market-news sites open and captures live, line-by-line updates as fast as possible** — by
whatever method wins per source (feed → structured API → rendered DOM scrape → change-detection diff
→ screenshot+vision). Goal: more news, fresher, from sites plain RSS/HTTP can't reach.

Built via `building-features-from-ideas` (this doc) + `sourcing-oss-parts` (per part). Supersedes /
expands the original S4 ("crawl4ai full bodies") in research/140's slice plan.

## The 6 screenshot projects, mapped to our decisions (user's ask: "use any / pick useful pieces")
| Project | ★ | What it is | Verdict for THIS feature |
|---|---|---|---|
| **Crawl4AI** | 67.8K | Any website → clean LLM-ready data; handles JS-heavy pages | ✅ **Already our S4 core renderer** (research/139). Core of Part 1+2. |
| **Browser Use** | 83.5K | AI agent drives any website (navigate/scrape/fill on command) | ✅ **Already our tier-2/3 agent** (research/139). Part 3 (feed-less nav + login). |
| **Maxun** | 15.7K | No-code point-click scraper → turns a site into an API/spreadsheet | 🆕 **New candidate** — Part 4 (selector "recipes" for feed-less sites without hand-coding CSS). Evaluate: embeddable/headless? ARM64? or is it a full webapp? |
| **Open WebUI** | 140K | Local ChatGPT UI + Ollama | ➖ We already have a free LLM pool + FinBERT. Not needed. |
| **OpenHands** | 75.8K | Autonomous coding agent (writes code, runs commands) | ➖ A dev agent (like the one building this). Not a news pipeline piece. |
| **Coolify** | 56.4K | Self-hosted deploy/PaaS | ❌ Infra, not news. |

**Takeaway:** the screenshots independently validate last session's picks (Crawl4AI + Browser Use).
The genuinely new pieces to evaluate are **Maxun** + purpose-built **live-change-detection** tooling
(the "line-by-line updates" part the current plan doesn't yet have).

## STEP 1 — Pinned target
A continuous acquisition subsystem that, per source, picks the FRESHEST viable method and normalizes
into the existing `news.sqlite3` (RawNewsItem shape), feeding S2 extraction + S3 reliability + S7 gate.
- **Input:** the source registry (tier-1 public sites incl. the feed-less/blocked ones — Business
  Standard, NDTV Profit, Moneycontrol-live — plus broker/TradingView pages later).
- **Output:** normalized, deduped news items landing in the store within **seconds-to-a-minute** of
  appearing on the page (vs the current ≤15-min RSS poll), each tagged with acquisition-method +
  source for S3 reliability.
- **Success test (Rule F):** on the REAL ARM64 box, (a) pull fresh items from ≥1 site that plain
  RSS/HTTP could NOT reach last session (Business Standard / NDTV Profit 403), AND (b) detect a NEW
  headline appearing on a live-updating page and store it within ~1 min — all headless, no GUI.

## STEP 2 — Decomposition (the parts to go shopping for)
1. **Headless render engine** — JS-heavy pages, persistent sessions, ARM64. (cand: Crawl4AI/Playwright)
2. **Clean article extraction** — rendered page → structured title/body. (cand: Crawl4AI extraction;
   trafilatura / readability-lxml as a light fallback)
3. **Agentic navigation** — feed-less sites, click-through, paywall/login. (cand: Browser Use; Skyvern)
4. **No-code selector recipes** — turn a site into a structured feed without hand-coding CSS, robust
   to layout drift. (cand: **Maxun**; or hand-authored CSS/XPath recipes)
5. **Live change-detection** — watch a page/section, emit ONLY new/changed lines (the "line updates").
   (cand: **changedetection.io** diff engine; or a bespoke DOM-hash differ)
6. **Vision fallback** — screenshot → LLM reads it when the DOM is hostile/anti-scrape. (cand: our LLM
   pool + Playwright screenshot)
7. **Feed expanders** — synthesize RSS for sites that don't publish it. (cand: **RSSHub**)
8. **Orchestrator/scheduler** — per-source cadence, concurrency, ban-resistance (rotating UA/fingerprint,
   backoff), dedup into the store, method-selection ladder. (bespoke glue over the existing runner)

## STEP 3 — Sourcing (IN FLIGHT — Rule I / sourcing-oss-parts; NO build until it lands)
Real online sourcing agents (Sonnet, per memory) evaluate each part's CURRENT capabilities +
**ARM64 confirmation** + embeddable-as-library vs standalone-webapp + how the pieces compose. License
is NOT a filter (Rule E — personal use). Findings append below; the build slices are gated on them.
- Agent A — Crawl4AI + Browser Use + Skyvern: live/streaming, persistent sessions, ARM64 Docker/pip,
  embedding as a library on our box; best method for the feed-less/JS-heavy/403 Indian sites.
- Agent B — Maxun + changedetection.io + RSSHub: can they run headless/embedded on ARM64; do they
  expose the extracted data via API/DB we can consume; fit for continuous "line-update" monitoring.
- Agent C — the fast/advanced angle: push/WebSocket/live news for Indian markets, vision-fallback
  patterns, and the ban-resistance + orchestration design that ties parts 1–8 into one loop.

### Sourcing findings — Agent A (render + agentic-nav layer), landed 2026-07-26
Real web sweep (PyPI, GitHub, docs.crawl4ai.com, docs.skyvern.com, Playwright system-reqs, Akamai
literature). Verdicts:
- **Crawl4AI → USE (workhorse).** Plain embeddable async Python lib (`pip install -U crawl4ai` +
  `crawl4ai-setup`); tiny wheel, weight is Playwright+**Chromium ~300–400MB** (skip torch/transformer
  extras). **ARM64: documented** — Playwright ships Chromium aarch64 builds (Chrome proper is x86-only,
  but Crawl4AI defaults to Chromium) + official multi-arch Docker (`*-arm64`). Continuous-capture
  primitive = **`arun_many(stream=True)`** with `MemoryAdaptiveDispatcher`/`SemaphoreDispatcher`
  (yields as results complete; deep-crawl w/ checkpointing) — exactly our "read many sites fast" shape.
  Persistent sessions/profiles, JsonCss/XPath extraction, LLM-markdown, and a **stealth→undetected**
  (`UndetectedAdapter`, CDP-patch) escalation ladder. NOT personally run on our Ampere box → Rule-F
  pending.
- **Browser Use → PARTIAL (occasional login/nav only).** Embeddable `Agent` lib; accepts LangChain
  `ChatOpenAI(base_url=…)` so it can point at our own pool. Good for login/click-through, but every
  step is an LLM+vision call → **~15–120s/task**, expensive → NEVER the hot polling loop; invoke only
  where Crawl4AI can't pass a wall. **ARM64 unconfirmed** (inherits Playwright's Chromium-arm64, no
  direct proof).
- **Skyvern → REJECT for core.** Drags in Postgres (SQLite fallback only in ≥1.0.31), ARM64
  unconfirmed, same LLM-agent latency. Its one edge = strong 2FA/OTP/password-manager login. Keep as a
  backlog-only escape hatch for a 2FA-gated source, ARM64-test first.
- **The 403 problem (Business Standard / NDTV Profit):** literature says most 2026 403s are
  **datacenter-IP reputation** — an Oracle Cloud VM egress is exactly what Akamai down-scores. A real
  browser engine fixes the TLS/JA3 layer but NOT an IP block → these two sites likely need a
  **residential/mobile proxy egress** (a new acquire-item, Rule I), stacked with Crawl4AI stealth.
  Moneycontrol stale-RSS → just render the live HTML page instead of trusting the feed. **All of this
  needs the Rule-F live test from our box — literature establishes technique, not proof.**
- Real URLs recorded in this doc's task + the agent transcript (crawl4ai/browser-use/skyvern repos +
  docs, Playwright system-requirements, ScrapFly/Marsproxies Akamai guides).

### Sourcing findings — Agent B (recipes + change-detection + feed-expanders), landed 2026-07-26
Real sweep (GitHub source trees, Docker Hub arch manifests, docs, GitHub Contents API). Verdicts:
- **changedetection.io → USE (the core live-update engine).** The standout fit. **Confirmed ARM64**
  (explicit `arm64`/RPi support — the ONLY tool with a documented ARM claim). Min recheck floor **3s**
  (`MINIMUM_SECONDS_RECHECK_TIME`) → sub-minute trivial. Purpose-built **"only trigger when unique
  lines appear"** + `{{diff_added}}`/`{{diff_added_clean(lines=N)}}` tokens → emits ONLY new headline
  lines (exactly goal-b). CSS/XPath/JSONPath/visual selectors; JS pages via Playwright/sockpuppet mode.
  **Python-consumable 3 ways:** REST API, **per-watch RSS** (`/rss/watch/{id}` → `feedparser`), Apprise
  `json://` webhook. Runs standalone `docker run dgtlmoon/changedetection.io`. → solves goals (b) live
  detection + (c) feed for any single feed-less page, zero code.
- **Maxun → PARTIAL (complementary, ARM64-risk).** Genuine self-host (docker-compose: postgres17 +
  redis7 + minio + backend + frontend — **5 services, heavy**). Point-and-click "robot" infers
  selectors by demonstration → best for turning a feed-less headline LIST into structured rows without
  hand-coding CSS. Python via **REST API + webhook** (Node SDK only; we call plain JSON). **ARM64
  UNCONFIRMED** (no doc/issue/arch-tag — biggest risk; may need build-from-source) + **incremental
  dedup undocumented** (dedupe by URL/title hash in our consumer). Schedule/run-based, NOT a live-diff
  engine → weaker than changedetection.io for the "line update" job.
- **RSSHub → REJECT.** Enumerated its live `lib/routes` via GitHub Contents API: **ZERO** routes for
  moneycontrol/ET/livemint/business-standard/ndtvprofit/cnbctv18/trendlyne/screener etc. Its whole
  value (feed-less → feed) doesn't apply since ET/MC/Mint/BS already ship native RSS; for the rest we'd
  hand-write TS/cheerio routes = the brittle-selector work we're avoiding. RSS-Bridge same gap → reject.
- **Also noted:** `urlwatch` (tiny pure-Python cron differ — a native-RSS fallback), Huginn (too
  heavy), and **`feedparser` + ETag/If-Modified-Since** (roll-your-own, zero extra service — best for
  the sites that ALREADY have native RSS: our current S1 feeds).

### Sourcing findings — Agent C (live/push news + vision + orchestration), landed 2026-07-26
Real sweep (broker API docs, NSE/BSE libs, news-API tiers, scraping/anti-bot literature). Verdicts:
- **No free push-NEWS from brokers.** Kite WebSocket streams ticks only + costs ₹500/mo; Upstox/Angel/
  Breeze/Fyers WS = ticks/orders, **no news channel**. Upstox has a REST `/news` (past-7-day pull, not
  faster than RSS). → brokers are a dead end for headlines.
- **NSE/BSE official announcements = the fastest FREE filings option.** No public API; the unofficial
  libs (`NseIndiaApi`, `BseIndiaApi`, both BennyThadikaran) poll the exchange's OWN JSON backend →
  seconds after a filing, faster than any RSS re-crawl. But it's a scrape: session cookies +
  browser-headers + self-throttle ~3 req/s + ban risk. **Best free primary for corporate filings.**
- **Telegram = fastest free "crowd relay".** Bot API subscribes to public channels → effectively push,
  often beats RSS-indexed sites; noisy/variable trust → matches our tier-3 SOCIAL plan (advisory,
  S3-reliability-gated). **X/Twitter → DEAD END** (free tier removed Feb 2026, Nitter collapsed).
- **Paid true-push** (stockinsights.ai tagged-announcement, MarketMaker.in) exists but pricing
  unpublished → flag as a user cost decision, not assumed. Finnhub free 60/min = backup aggregator only.
- **Vision fallback best practice:** CROP to the headline region before screenshot (cuts tokens +
  hallucination), name exact fields, force JSON (word "json" in prompt). Caveat: **vision only solves
  PARSING — a stealth browser/session is a prerequisite** (anti-bot 403s before a pixel is captured).
- **Orchestration (reusable OSS):** **APScheduler** for per-source cadence + bounded concurrency;
  **arq** (Redis async) for workers if needed (Celery only at multi-machine scale); **Scrapy
  AutoThrottle** pacing formula (`delay = latency / target_concurrency`) even outside Scrapy; a
  **method-selection ladder** (feed→API→rendered→change-detect→vision) that caches the last-successful
  method per source + tracks rolling success to auto-promote/demote.
- **Ban-resistance (highest-leverage first):** **`curl_cffi`** to impersonate real Chrome TLS/JA3
  (defeats the fingerprint layer that instantly flags `requests`/`httpx`) — the single biggest fix;
  current UA; **residential/ISP proxy ONLY on sites with a real anti-bot layer** (NSE/BSE, the 403
  news sites) — ~90-99% vs ~20-60% datacenter; session/cookie persistence; adaptive pacing; robots as
  a hint. All public-page plumbing — no auth-bypass/intrusion.

## STEP 4 — Sourced stack + composition (all 3 agents in)
| Part | Chosen | Role |
|---|---|---|
| 1 render engine | **Crawl4AI** (`arun_many` stream + MemoryAdaptiveDispatcher, stealth→undetected) | hot polling of feed-less/JS pages, ARM64-OK |
| 2 clean extract | **Crawl4AI** JsonCss/markdown (+ trafilatura fallback if needed) | page → title/body |
| 3 agentic nav | **Browser Use** (our LLM pool via `ChatOpenAI base_url`) — sparingly | login/click-through only, NOT hot loop |
| 4 no-code recipes | **Maxun** (ARM64-test-first) or hand CSS recipes | feed-less headline LIST → structured rows |
| 5 change-detect | **changedetection.io** (ARM64-confirmed, 3s floor, diff_added, per-watch RSS) | the "new lines only" live-update engine |
| 6 vision fallback | **our LLM pool + Playwright screenshot** (crop→JSON) | anti-scrape pages, last resort |
| 7 filings (fastest free) | **`NseIndiaApi` / `BseIndiaApi`** | corporate announcements, seconds after filing |
| 8 orchestrator | bespoke **method-ladder** over **APScheduler** + **`curl_cffi`** TLS-impersonation | per-source cadence, ban-resistance, dedup→store |
| — social relay | **Telegram Bot API** (tier-3, S5) | fastest free crowd signal, advisory |
| REJECTED | Skyvern (heavy/ARM?), RSSHub/RSS-Bridge (0 India routes), X/Twitter (paid/dead), brokers-for-news | — |

**New acquire-items (Rule I):** `curl_cffi`, `crawl4ai`(+Chromium), `changedetection.io`(docker),
`NseIndiaApi`/`BseIndiaApi`, `APScheduler` — all free/pip/docker. **Residential/mobile proxy for the
403 sites = the one that costs money → USER DECISION** (Business Standard/NDTV Profit unreachable
without it; everything else works from our datacenter egress).

## Slice plan — FINALIZED (supersedes original S4; one at a time, Rule A)
- **S4a — Crawl4AI render+extract seam** over the sites reachable from our egress (feed-less/JS pages
  that RSS missed; Moneycontrol live-page instead of stale feed) → normalize into `news.sqlite3` →
  surface. Behind the existing `fetch_bytes`-style DI seam (Rule J). Real-data: pull fresh items from
  a JS/feed-less page from our box. **Best first slice — pure win, no proxy/cost needed.**
- **S4b — changedetection.io live-update rung**: run it (docker, ARM64), point watches at high-value
  headline regions, consume its per-watch RSS via `feedparser` → sub-minute new-line capture into the
  store. Real-data: detect a new headline within ~1 min.
- **S4c — `curl_cffi` + NSE/BSE announcements**: fastest-free corporate-filings poller with TLS
  impersonation + ban-resistance; method-ladder + APScheduler cadence.
- **S4d — vision fallback + (optional, user-gated) residential proxy** for the 403 sites; Maxun
  recipes if a site needs demonstrated selectors. Browser Use only where a login wall requires it.

## Rule notes

## Slice plan (to be finalized after sourcing) — supersedes original S4
S4a headless render + clean extraction (Crawl4AI) over the feed-less/403 tier-1 sites → store.
S4b live change-detection layer (fresh-within-a-minute) on the highest-value pages.
S4c no-code recipes (Maxun or hand recipes) + RSSHub feed expanders for breadth.
S4d vision fallback for anti-scrape pages. (tier-2 broker/TradingView + tier-3 social stay S5/S6.)
Each slice: design-confirm → build → Rule-F real-data → map/dashboard/backlog, one at a time (Rule A).

## Rule notes
- **Rule A/M ordering:** this is a REPRIORITIZATION — S3 (source reliability) was the queued next
  slice. S4-advanced is bigger and the user asked for it now; S3 stays queued (BACKLOG) and is a
  natural pair (S3 scores the extra sources this feature adds). Surface the choice to the user.
- **Rule E:** copyleft/no-license is fine (personal, non-distributed). **Legal:** research/141 graded
  personal scraping LOW; full-body/live capture was user-authorized. **Ban-resistance** is required
  engineering ([[feedback_personal_use_no_tos_legal_gating]]), never auth-bypass/intrusion.
- **Rule J:** where a live site isn't reachable at build time, verify behind the fetch DI seam; the
  real-site pass stays an open blocker.
