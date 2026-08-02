# Autonomous Browsing/Vision Agent for Indian Financial News — OSS Tooling Research

Date: 2026-07-26
Purpose: source the best open-source tooling for an unattended, scheduled agent that
visits Indian financial-news websites (including behind a login), reads the rendered
page, and hands article text/screenshots to an LLM to extract trade-relevant news.
Target runtime: headless Linux **ARM64** server (not a phone). Personal, non-distributed
use — Rule E applies (license is not a filter). **No code was written for this pass —
research only**, per the user's explicit instruction.

Method: this is a synthesis of 4 parallel research agents (model: sonnet, per the
standing "research agents use Sonnet" rule) plus direct WebFetch/WebSearch follow-ups
run by the orchestrating session. Agents read live GitHub API data (stars/license/last
push), READMEs, docs pages, issue trackers, and — for the news sites — actual
`robots.txt`/RSS/ToS pages fetched with a browser-like User-Agent on 2026-07-26. Every
claim below is tagged with its source and a recency date. Where WebSearch's session
quota was exhausted mid-task (this happened repeatedly — see Gaps), that is flagged
explicitly rather than backfilled from memory.

---

## 0. Bottom line up front

**No single tool does everything.** The strongest stack for this use case is a
**feed-first + crawl4ai (Playwright-driven) + a DIY Claude-vision screenshot fallback**
combination, NOT one of the "autonomous browser agent" frameworks (browser-use,
Skyvern, Stagehand) used as the primary driver — those are built for *task automation*
(click through a flow, fill forms, complete a multi-step goal) and are heavier,
slower, and more expensive per page than what a scheduled "fetch article → extract"
job needs. They remain valuable as a **login-session bootstrap tool** (one-time or
periodic: log in, solve 2FA, save the authenticated storage state), after which
cheaper deterministic fetching takes over. Full recommendation in §5.

`docs/research/96_layer11_llm_agent_blueprint.md` and `docs/research/97-99` (free-tier
LLM provider research) are the natural companions to this doc for the "hand text to an
LLM" half of the pipeline; this doc covers the "get the text/screenshot" half.

---

## 1. "PhoneDriver" — verification result: NOT the tool the viral claim describes

**Finding: there is no real, canonical open-source project literally named "PhoneDriver"
that does "open 6 news apps, screenshot each, send to Claude."** The viral claim is not
substantiated by any discoverable public repo, package, or forum thread.

- GitHub repo search for "PhoneDriver" surfaces one repo with real traction:
  **OminousIndustries/PhoneDriver** — 1,553 stars, Apache-2.0, last push 2025-10-24,
  created 2025-10-14 (GitHub API, verified 2026-07-26). Its actual README: *"A
  Python-based mobile automation agent that uses Qwen3-VL vision-language models to
  understand and interact with Android devices through visual analysis and ADB
  commands."* It screenshots an Android phone via **ADB**, feeds the image to a
  **locally-hosted Qwen3-VL** model (needs ~24GB+ VRAM), and issues taps/swipes back
  via ADB. It does not open news apps and does not send anything to Claude/Anthropic —
  it's a general-purpose local vision-driven Android controller, unrelated to news
  reading. (Source: github.com/OminousIndustries/PhoneDriver, README fetched
  2026-07-26.)
- The other ~8 GitHub repos matching "PhoneDriver" are 0–8-star hobby projects,
  none matching the described workflow (GitHub search, 2026-07-26).
- PyPI has no "PhoneDriver" package. npm search returned HTTP 403 (inconclusive, not a
  confirmed negative) — flagged as unverified rather than assumed absent.
- Hacker News full-text search (Algolia API) returns **zero** stories/comments about a
  "PhoneDriver" AI tool as of 2026-07-26.

**Conclusion:** treat the "PhoneDriver" viral claim as either a private/informal script
someone named themselves (plausible — this is a simple pattern to DIY, see §2.2) or a
mislabeled/exaggerated description, not a real public project to adopt. Do not build on
a dependency named "PhoneDriver" — it doesn't exist as described. This also reinforces
§3's conclusion: even the actual repo that does exist under this name is phone/ADB-based,
not the headless-server web approach this project needs.

---

## 2. Web browser agents — the right category (server-side, not phone)

### 2.1 Comparison table — the three "autonomous agent framework" contenders

All stats live via GitHub API, checked 2026-07-26.

| | **browser-use** | **Skyvern** | **Stagehand** |
|---|---|---|---|
| Repo | github.com/browser-use/browser-use | github.com/Skyvern-AI/skyvern | github.com/browserbase/stagehand |
| Stars | 106,833 | 22,595 | 23,641 |
| License | MIT | AGPL-3.0 | MIT |
| Created / backing | Oct 2024, YC W25, $17M raised | Feb 2024, YC S23 | Mar 2024, Browserbase (hosted-browser company) |
| Drive mechanism | Playwright, hybrid DOM+vision | Playwright, **vision-first** (LLM "sees" the page, layout-change resistant) | Raw Chrome DevTools Protocol, DOM/accessibility-tree driven, not vision |
| Login/session | Reuses your existing Chrome profile / saved logins; syncs auth state to remote browsers | Strongest on paper: native Bitwarden/1Password/LastPass integration + TOTP/QR/email/SMS 2FA | Undocumented in README/docs reached — genuine gap |
| Known session bug | — | **Open issue #3897** (Nov 2025): "Cookies Not Persisting Between Workflows in Persistent Browser Sessions" — session persistence is a real, currently-unresolved pain point | — |
| Headless/server | Docker + `Dockerfile.fast` shipped; explicit ARM64 statement not found, but issue tracker shows only Mac-ARM PATH/Chromium-discovery fixes (#4680, #5033, #4254), no Linux-ARM64 blocker reported | Docker + Kubernetes self-host supported; one **closed** ARM64 issue — `ImportError: libstdc++.so.6 file too short` (#2412, resolved Jun 2025) confirms aarch64-linux use exists and is fixable, not a hard blocker | ARM64/headless-server details not documented in reachable pages; open issues are about headed-mode focus-stealing and a WSL2 path bug — nothing suggesting Linux-headless breakage |
| LLM flexibility | Anthropic, OpenAI, Gemini, Ollama/local, own hosted models | OpenAI, Anthropic, Bedrock, Azure OpenAI, Gemini, Ollama, OpenRouter — broadest of the three | Not fully confirmed, but designed LLM-agnostic per docs |
| Output for text extraction | Agent logs + custom-tool JSON; not clean prose by default | Structured JSON via `data_extraction_schema` — good for targeted extraction | `extract()` returns typed objects via Zod schemas — best of the three for clean structured output |
| Maturity signal | Very active issues (rapid iteration, some rough edges) | Active, but real session-state bugs open | Active, MIT, daily commits |

**Read on fit:** all three are designed for *goal-directed multi-step automation*
("book this flight," "fill this form"), which is more machinery than "fetch today's
articles and hand them to an LLM" needs, and all three cost a full LLM
reasoning-loop call (or several) per page rather than one extraction call. Their real
value here is narrow: **use one of them once (or on a schedule, e.g. weekly) to
perform the interactive login + 2FA flow and persist the authenticated cookie/storage
state**, then hand that saved session to a cheaper deterministic fetcher (crawl4ai or
Playwright) for the actual per-article work. Skyvern's 2FA/password-manager story is
the strongest for this narrow login-bootstrap role, but its cookie-persistence bug
(#3897) means the saved-session handoff must be tested end-to-end before relying on it;
browser-use's "reuse your Chrome profile" is the simplest fallback if Skyvern's session
bug bites.

### 2.2 DIY: Playwright/Puppeteer + vision LLM (architecture pattern, not one repo)

There is no single dominant shared library — this is a **composition pattern** many
people build from scratch: Playwright captures a screenshot (and/or extracts DOM/
accessibility-tree text), then sends the screenshot + prompt to a vision-capable LLM
(Claude or GPT-4V), which either extracts info directly from the image or returns
coordinates/actions fed back into Playwright. A GitHub code search for
`playwright+vision+llm+agent+screenshot` (2026-07-26) turned up many small (0–7 star)
independent implementations of exactly this pattern, confirming it's commonly
hand-rolled rather than shared as a maintained framework.

- **Pros for this project:** full cost control (pay only for LLM calls actually made),
  no dependency on a possibly-stale framework (see LaVague, §2.4), can mix cheap DOM
  text extraction with vision only when the DOM is messy or the page is a screenshot-only
  paywall — exactly the "fall back to screenshot+vision" requirement in the brief.
- **Cons:** you own session/cookie persistence, retries, scheduling, and rate limiting —
  none of it comes free.
- **ARM64/headless — officially confirmed.** Playwright's own docs
  (playwright.dev/docs/intro, fetched 2026-07-26) list supported Linux platforms as
  "Debian 12/13, Ubuntu 22.04/24.04/26.04 (x86-64 or **arm64**)" — headless ARM64
  Linux is an officially supported first-class target, the strongest ARM64 signal of
  anything surveyed in this report.

### 2.3 microsoft/OmniParser (screenshot → structured UI elements)

github.com/microsoft/OmniParser, README + issues fetched 2026-07-26: 25.2k stars,
2.2k forks, mixed license (core + v3 YOLOv9 icon detector = MIT; a legacy detector
component = AGPL). Converts a UI screenshot into structured icon/button/text elements
with captions, meant to ground a vision LLM's clicks more accurately (bundles
"OmniTool" to pair with GPT-4V/Claude/Qwen/DeepSeek for full desktop-VM control).
**Staleness flag:** last meaningful update February 2025 (v2), some March 2025
additions — ~16-17 months stale as of July 2026.
**Hardware flag:** open issue #241 (`erfinv_vml_cpu not implemented for 'Half'`)
confirms real CPU-only inference friction (fp16 ops not implemented on CPU); open PR
#288 ("Enable OmniParser support MPS on Mac M chip") is *still open*, confirming
**native Apple-Silicon/ARM support is not yet merged**, and there is no evidence of
Linux-ARM64-CPU support either. Given your target sites are read via rendered DOM
text/screenshots of article pages (not a dense desktop app UI needing icon-level
grounding), OmniParser is **overkill and a poor ARM64/CPU fit** for this use case —
not recommended as a dependency here.

### 2.4 lavague-ai/LaVague — status: de-facto abandoned, do not build on it

github.com/lavague-ai/LaVague, fetched 2026-07-26: Apache-2.0, 6.4k stars, 572 forks,
no formal GitHub "archived" banner and a still-published roadmap/Discord link — but
the commit history's most recent commit is dated **January 21, 2025** ("CI: drop cron
schedule run", #633), ~18 months stale with no newer activity visible. WebSearch quota
was exhausted before an independent check of a possible rename/acquisition could be
run (flagged gap, see §6) — but staleness alone is disqualifying for a new 2026
dependency. **Not recommended.**

### 2.5 unclecode/crawl4ai — strongest single fit for the "render + extract clean text" job

github.com/unclecode/crawl4ai, fetched 2026-07-26: Apache-2.0, **75k stars**, 7.7k
forks — the most mature/popular tool surveyed for this specific job. Drives the
browser via **Playwright** (Chromium/Firefox/WebKit), async-first. Explicitly supports
**persistent authenticated sessions** — "preserve browser states and reuse them for
multi-step crawling," persistent profiles with saved auth state, cookie/user-agent
handling — a direct match for "reads pages where a login is needed." Output is
**purpose-built clean/fit Markdown for LLM consumption**, plus structured-data
extraction, screenshots, and PDF output — exactly the "clean article text for LLM
extraction" requirement. LLM-provider-agnostic via `litellm` (Anthropic, OpenAI,
Ollama, etc.). Headless is a standard supported config.
**Known rough edge:** an open issue (#2092) reports the ARM64 Docker image ships
~2.4GB of wasted build artifacts from QEMU-emulated CI — annoying but avoidable by
building the image natively on the ARM64 box rather than pulling the emulated one;
plus a stale self-host migration guide (#2090) and a Docker Compose v5 compatibility
bug (#2091). None of these block ARM64 headless server use, just budget time for
Docker packaging friction.

### 2.6 mendableai/firecrawl — viable self-hosted, but loses its anti-bot edge

github.com/mendableai/firecrawl + docs.firecrawl.dev/contributing/self-host, fetched
2026-07-26: dual-licensed (core AGPL-3.0, SDKs/some UI MIT), **156.2k stars**, 5,986
commits — large and very active. Self-hostable via docker-compose, with JS rendering/
screenshots through a bundled Playwright service (not cloud-only). **Confirmed
cloud-gated features:** the `/agent` and `/browser` endpoints are explicitly "not
supported in self-hosting," and "Fire-engine" — their proprietary anti-bot/IP-block/
robot-detection evasion layer — is cloud-only. This matters directly: several of the
target Indian news sites run Akamai Bot Manager (§4), so **self-hosted Firecrawl will
face bot detection with no built-in evasion**, unlike the paid API. Login/session-
cookie handling for self-hosted was not documented in the reachable self-host guide —
flagged unverified, needs a hands-on test. No ARM64-specific self-host instructions
found either way.

### 2.7 Verdict for §2

**crawl4ai** is the strongest core driver: mature (75k★), Playwright-based (confirmed
ARM64-capable engine per §2.2), built-in persistent-login-session support, and output
specifically shaped for LLM consumption. Pair it with a **thin DIY Claude-vision
screenshot fallback** (§2.2, officially ARM64-supported via Playwright) for pages where
the DOM is a mess or truly screenshot-only. Use **Skyvern** (or browser-use as backup)
purely as an occasional **login/2FA session-bootstrap** tool, not as the main driver.
Skip LaVague (stale) and OmniParser (stale, CPU/ARM-unfriendly, wrong problem shape —
built for desktop-app icon grounding, not article-text extraction). Self-hosted
Firecrawl is a fallback option if crawl4ai's session handling proves insufficient, with
the caveat that its anti-bot evasion is paywalled away from the OSS self-host path.

---

## 3. Phone/GUI agents — surveyed for completeness, confirmed NOT the right choice

All four requested projects were checked (GitHub API + README, 2026-07-26):

| Project | Verified repo | Stars | License | Last push | Control mechanism |
|---|---|---|---|---|---|
| X-PLUG/MobileAgent | github.com/X-PLUG/MobileAgent (Alibaba Tongyi Lab) | 8,982 | MIT | 2026-07-07 (active) | ADB + ADB-Keyboard APK + vision grounding (GUI-Owl VLM). Physical device, emulator, or Alibaba's paid **Wuying Cloud Phone** |
| AppAgent | `mnotgod96/AppAgent` **404s** — real current repo is **TencentQQGYLab/AppAgent** | 6,824 | MIT | 2025-03-19 (**16+ months stale**) | ADB taps/swipes, no root; physical USB device or Android Studio emulator; GPT-4V primary |
| DroidRun | rebranded — real repo is **droidrun/mobilerun** (mobilerun.ai) | 8,861 | MIT | 2026-07-23 (active) | Requires a "Portal" companion app + Android accessibility service + ADB; physical device documented, emulator support unconfirmed; LLM-agnostic |
| Termux-based | No coherent maintained project found; GitHub code search for `termux+news+bot` returned 7 mostly-abandoned hits (best: 27★, last pushed 2021); `termux+LLM` returned 130 hits, all either on-device local-LLM servers or generic accessibility/root automation, none purpose-built for scheduled news reading | — | — | — | scattered hobbyist scripts, not a pipeline |

**Why the headless web agent on a Linux ARM64 server wins over any of these, for this
specific use case:**
- **Not actually headless.** All four require ADB debugging and/or an always-on
  accessibility service, which in practice means a screen-on, unlocked, network-
  attached device 24/7 — a fragile physical dependency vs. a stateless container.
  Even Alibaba's own MobileAgent team steers users toward a **paid cloud Android VM**
  (Wuying) for anything beyond one-off demos — implicit admission that bare local
  phones don't scale unattended.
- **UI stability.** AppAgent hasn't been updated in 16+ months and depends on screen
  coordinates/accessibility trees that break on every app UI redesign; website DOMs/
  RSS/APIs change far less often, and HTML parsing degrades gracefully (selector still
  finds *something*) where a vision-tap agent fails hard (a missed tap or popup blocks
  the whole flow).
- **Cost.** Vision-model-in-the-loop phone control (GPT-4V/GUI-Owl per action) costs
  materially more per page-view than one HTML/RSS fetch + one LLM text-extraction call.
- **Content parity.** No evidence any of the target Indian financial-news sites publish
  app-exclusive trade-relevant content not also on the website — so there's no content
  reason to pay the phone-automation overhead.
- **Native ARM64 fit.** None of the four projects run natively *on* a headless ARM64
  Linux server as the controlled endpoint — they all target *controlling a separate
  Android endpoint from* a host. A Playwright/crawl4ai-based web agent runs directly on
  the server with no second device in the loop at all.

---

## 4. Feed-first vs. scrape — Indian financial-news sites (checked 2026-07-26)

Direct `robots.txt`/RSS/ToS fetches with a browser-like User-Agent, from this server's
network, 2026-07-26:

| Site | RSS feed | robots.txt | Anti-bot | ToS on automated access |
|---|---|---|---|---|
| **Moneycontrol** | **Yes** — `moneycontrol.com/rss/latestnews.xml`, `.../rss/marketreports.xml` both live (200, valid RSS 2.0) | 200, permissive for RSS/articles; blocks `CCBot`/`GPTBot`/`ChatGPT-User`/`Google-Extended`/`Baiduspider`/`DataForSeoBot` explicitly; sitemaps incl. `stocks_technical_analysis.xml` | Akamai present (`_abck`/`bm_sz` cookies) but did not block RSS/robots fetches | ToS page 503'd twice — text unverified |
| **Economic Times / ETMarkets** | **Yes** — `economictimes.indiatimes.com/rssfeedsdefault.cms` live (200) | 200, broad `Allow: /`, narrow disallows | Strict CSP, no bot-challenge triggered | ToS (200, fetched) explicitly prohibits automated "robots/spiders/offline readers... that send numerous automated requests... which a human cannot reasonably send," and separately restricts subscriber/Refinitiv-sourced content to "personal, non-commercial use," **prohibiting aggregating, scraping, recreating or redistributing** it |
| **Business Standard** | Unknown | **403 Access Denied (AkamaiGHost)** on robots.txt itself, twice, from this server's egress — blocked outright | Akamai IP/bot-reputation block | Unverifiable — page unreachable |
| **LiveMint** | **Yes** — `livemint.com/rss/markets`, `.../rss/news` both live (200, `max-age=30`, actively refreshed) | 200, permissive | Akamai-fronted (via AmazonS3) but robots/RSS reachable | ToS (200, fetched) §7A explicitly bans bots/crawlers/scrapers even for public-search-engine-style indexing beyond what robots.txt allows, and **explicitly bars using content/metadata to train/fine-tune/evaluate AI/ML systems without a written licence**; §7B separately bars "automated scraping/crawling/bulk downloading" of API/data-feed/widget content |
| **NDTV Profit** | **No live feed found.** The legacy `feeds.feedburner.com/ndtvnews-business` URL returns 200 but is a **dead FeedBurner placeholder** (content dated 2020-2021) | **403 Access Denied (AkamaiGHost)** on robots.txt, twice — blocked outright | Akamai block | Unverifiable — page unreachable |
| **NSE India (technical levels / index data)** | No documented public feed | 200, fully permissive (`Allow: /`, one narrow disallow) | Akamai Bot Manager present; one unauthenticated test GET to `/api/marketStatus` returned live JSON, but this is **not** evidence of an open API — community libraries (`nsepython`, `jugaad-data`, `nsetools`) consistently document that NSE requires session-cookie bootstrapping from the homepage first, and intermittently rate-limits/blocks. Treat as a fragile, unofficial, undocumented surface |

Sources not independently re-checked in this pass despite being named in the brief:
Investing.com, TradingView India, Angel One blog, Zerodha blog — **Zerodha's Z-Connect
blog RSS (`zerodha.com/z-connect/feed`) was separately confirmed live** (valid RSS 2.0,
fetched 2026-07-26, current articles through July 24 2026 including a SEBI Closing
Auction Session explainer relevant to trading mechanics) — a good candidate feed source
for broker-side market commentary, though it is commentary/blog content, not raw
Nifty support/resistance numbers. Investing.com and TradingView India feeds were not
reached in this pass (WebSearch quota exhausted, see §6 gaps).

### Anti-bot pattern
Business Standard and NDTV Profit are both **hard-blocked at the network/IP-reputation
layer (Akamai 403) even for the most basic robots.txt request**, independent of any
scraping intent — this server's current egress IP is apparently already flagged.
Moneycontrol, ET, and LiveMint all run Akamai too but did not block the basic requests
made here. This means: (a) don't assume "Akamai present = automatically blocked" — test
each target site directly from the actual deployment IP before committing, and (b) for
Business Standard/NDTV Profit specifically, plan for either a different egress
path/residential-style IP, a browser-rendering approach that better mimics a real
browser fingerprint (crawl4ai/Playwright, not raw HTTP), or deprioritizing those two
sources in favor of the sites with working feeds.

### Legal/ToS risk — facts only, not legal advice
- Of the ToS documents actually readable (ET, LiveMint), **both explicitly and
  specifically prohibit automated/bot access and scraping**, independent of whether the
  requester is a logged-in subscriber — LiveMint's clause is not carved out for paying
  users, and ET frames its no-aggregation rule as a property-of-the-content restriction
  tied to its licensed data, not to login status. Moneycontrol's ToS could not be
  fetched (503 x2); Business Standard's and NDTV Profit's could not be fetched at all
  (403 x2 each) — no verified ToS text for those three either way.
- **Logging in with the user's own paid subscription does not appear to create a ToS
  safe harbor** on the two sites where the text was actually readable — automating
  access is restricted as a category, not just anonymous/public scraping.
- **India-specific legal context:** the IT Act 2000 provides Section 43 (civil penalty/
  compensation for unauthorized access to or damage of a computer system/network) and
  Section 66 (criminal "hacking," up to 3 years + ₹5 lakh fine) — these are the
  statutory hooks most likely to be invoked if automated access is framed as
  "unauthorized" (e.g., bypassing a technical/bot-detection barrier). No specific
  Indian court case squarely addressing *web scraping* (as opposed to hacking/computer-
  intrusion generally) was found in this pass — this is a genuine gap (WebSearch quota
  exhausted before it could be chased further, and a direct fetch of indiacode.nic.in's
  full statute text also failed with 403). **Do not treat "scraping is definitely legal/
  definitely illegal in India" as settled** — the honest state of the evidence is: (1)
  ToS violations are a contract-law exposure regardless of criminal-law framing, (2) the
  IT Act's unauthorized-access provisions are the plausible statutory risk if bot-
  detection bypass is involved, and (3) no controlling case law was located to say how
  Indian courts would apply either to a personal, non-commercial RSS/HTML polling setup
  that respects robots.txt. This warrants a dedicated `deep-research` pass with a fresh
  WebSearch budget before finalizing anything that logs into a paywalled site and
  automates content extraction at scale.

---

## 5. Recommendation

**Feed-first, scrape/render as fallback, vision as last resort — layered by site:**

1. **Tier 1 (RSS, no rendering needed):** Moneycontrol (`rss/latestnews.xml`,
   `rss/marketreports.xml`), Economic Times (`rssfeedsdefault.cms`), LiveMint
   (`rss/markets`, `rss/news`), Zerodha Z-Connect (`z-connect/feed`) — poll these
   directly on a schedule. Fastest, cheapest, and the only category confirmed
   robots.txt-clean. **Caveat:** ET's and LiveMint's ToS still forbid bulk automated
   scraping of full article pages even though polling the RSS headline feed itself
   is consistent with robots.txt — so use the feed for headline/monitoring triage,
   and treat full-article-body fetching as the higher-risk step needing its own
   ToS re-check per site (§4).
2. **Tier 2 (render via crawl4ai, Playwright-driven, session-aware):** for any site
   without a working feed (Business Standard, NDTV Profit) or where the RSS item
   needs the full article body — use **crawl4ai** as the core driver: persistent
   login-session support, clean Markdown output tailored for LLM consumption, and an
   officially ARM64-capable underlying engine (Playwright). For Business Standard/
   NDTV Profit specifically, first resolve the Akamai 403 at the network layer
   (different egress, or a full browser fingerprint via crawl4ai/Playwright rather
   than raw HTTP) before assuming they're reachable at all.
3. **Tier 3 (login/2FA bootstrap, occasional):** when a site needs an authenticated
   session (paywalled subscription), use **Skyvern** (best 2FA/password-manager
   support) or **browser-use** (simplest "reuse your Chrome profile" fallback) as a
   one-off/periodic session-refresh step — log in, pass 2FA, save the storage state —
   then hand that session to crawl4ai for the actual recurring fetch work. Test
   Skyvern's session-persistence bug (#3897) end-to-end before depending on it; fall
   back to browser-use if it doesn't hold up.
4. **Tier 4 (vision fallback, last resort):** for pages where the DOM is a mess, is
   screenshot-only, or genuinely needs visual reading (e.g., a chart image with no
   text alternative) — a **DIY Playwright screenshot + Claude vision** call. This is
   the officially-ARM64-supported path (§2.2) and gives full control over when the
   (more expensive) vision call is actually invoked, rather than defaulting to it.

**Explicitly not recommended as the core driver:** browser-use, Skyvern, and Stagehand
used as the primary per-article fetcher (too heavy/expensive for a scheduled read-and-
extract job — reserve for login bootstrap only); LaVague (de-facto abandoned, ~18mo
stale); OmniParser (stale, CPU/ARM64-unfriendly, wrong problem shape); self-hosted
Firecrawl unless crawl4ai's session handling proves insufficient (loses its paid
anti-bot evasion layer when self-hosted, which matters given the Akamai walls found in
§4); any phone/GUI agent (§3 — not headless, not ARM64-native, no content advantage);
"PhoneDriver" as named in the viral claim (§1 — doesn't exist as described).

### Hard blockers to resolve before building
1. **Business Standard & NDTV Profit are network-blocked (403) from this server's
   current egress, even for robots.txt.** Must be resolved (different IP/egress path,
   or full-browser-fingerprint rendering) or these two sources stay out of scope.
2. **NDTV Profit has no live RSS** (only a dead 2020-era FeedBurner placeholder) —
   will require rendering/crawl4ai regardless of the network-block issue above.
3. **No verified ToS carve-out for automating a logged-in personal subscription** on
   any site checked — this is a real, currently-open legal-risk question, not a
   solved one; flagged for a dedicated follow-up `deep-research` pass on Indian
   scraping/computer-access law (IT Act §43/§66 framing) before logging into any
   paywalled account programmatically.
4. **Credential security for login automation:** none of §2's tools were checked in
   this pass for how they store the saved session/credentials at rest (encrypted
   storage-state file? plaintext cookie jar? OS keychain?). Before wiring Skyvern/
   browser-use's login-bootstrap step to a real personal account, verify how/where it
   persists the authenticated session and ensure it's encrypted-at-rest and excluded
   from any repo/backup path that isn't secrets-managed (per this project's existing
   "never commit secrets" non-negotiable).
5. **NSE India's own site is a fragile, unofficial data surface** (session-cookie
   bootstrap required, intermittent blocking per community-library experience) — do
   not build a load-bearing dependency on `nseindia.com` endpoints without defensive
   retry/backoff and a documented fallback.

---

## 6. Gaps / what this pass did NOT fully cover

- **India-specific case law on web scraping** — not found; needs a dedicated
  `deep-research` follow-up with a fresh WebSearch budget (quota was exhausted
  session-wide partway through this research pass — see below).
- **Investing.com, TradingView India, and Angel One blog feeds** — not independently
  checked (only Zerodha's Z-Connect feed was confirmed as a stand-in broker-blog
  source).
- **ARM64-specific Docker images/instructions** for browser-use, Skyvern, and
  Stagehand — inferred from scattered issue-tracker signals (mostly Mac-ARM, one
  resolved Linux-aarch64 import bug for Skyvern), not confirmed via an actual
  official ARM64 build/run test on the target hardware.
- **Firecrawl self-hosted login/session-cookie handling** — not documented in the
  reachable self-host guide; needs a hands-on test.
- **LaVague's exact fate** (quiet rename/fold-in vs. simple abandonment) — inferred
  from ~18-month commit staleness only; an independent search to confirm/deny a
  rename could not be run (quota exhausted).
- **Moneycontrol's, Business Standard's, and NDTV Profit's ToS text** — could not be
  fetched (503/403) in this pass; only ET's and LiveMint's ToS were actually read.
- **Session note:** the orchestrating session's WebSearch tool hit its **200/200
  session-call budget** partway through this research (reported independently by
  three of the four parallel sub-agents, and again on direct follow-up searches by
  the orchestrator). All findings above come from WebFetch (direct page reads,
  robots.txt/RSS/GitHub-API fetches) rather than being blocked entirely, but any gap
  above that specifically needed a fresh web *search* (as opposed to fetching a known
  URL) is a real, not cosmetic, limitation of this pass. If a fuller legal-risk and
  feed-completeness picture is needed, re-run with `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`
  raised, ideally in a fresh session.
