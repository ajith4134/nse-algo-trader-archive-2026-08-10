# Research/138 — News + Sentiment Sense: Sourcing &amp; Acquisition Research (July 2026)

**Rule I acquisition research (Rule D: saved to file).** Skill used: `deep-research`, fanned out
as four parallel `general-purpose` sub-agents (model: sonnet, per the standing "research agents
use Sonnet" rule) — one per component area — after first reconciling against existing project
research to avoid duplicate work. Scope: source a NEWS + SENTIMENT sense for the autonomous NSE
(India) intraday trading bot (cash equity + options, index + ~210 stock underlyings, personal
non-distributed use — license is not a filter, but ToS/auth/no-scraping-bans are respected).

**As-of date: 2026-07-26.** Every claim below carries a source-credibility grade (A = primary/
official source fetched directly this session · B = reputable secondary/triangulated · C =
unverified single-source lead) established by each sub-agent doing its own multi-angle
search-and-fetch sweep, not a single search followed by a summary.

**Relationship to prior research** — this doc does NOT re-litigate ground already covered
elsewhere in `docs/research/`:
- `docs/research/57_corporate_actions_master_sourcing_consolidated.md` and
  `75_nse_corporate_actions_isin_delisting_free_data_sources.md` already cover **corporate
  ACTIONS** (dividend/split/bonus/rights) via `nselib.corporate_actions_for_equity()` →
  NSE's `api/corporate-actions?index=equities` endpoint. §1 below covers the ADJACENT-but-DISTINCT
  category of **corporate ANNOUNCEMENTS/EVENTS** (board meetings, results calendar, block/bulk
  deals, insider trades, credit ratings, general disclosures).
- `docs/research/61_point_in_time_rules_calendar_and_news_sourcing.md` §4 already did a first
  pass on deep HISTORICAL news depth (multi-year archives, paid-vendor pricing for TickerPlant/
  BSE Direct, GDELT's historical tiers). This doc's focus is the **live/intraday** side — what a
  running bot needs during market hours, today — and adds several sources/endpoints not found in
  that earlier pass (the `nse` PyPI library, RSS freshness testing, Marketaux/Upstox News API).
- `docs/research/97_free_tier_llm_provider_api_config_research.md` and
  `98_free_tier_llm_provider_registry_master_table.md` already fully source the **swappable
  free-tier multi-provider LLM pool** (14+ OpenAI-compatible providers, 10–6,000 RPM). §4 below
  treats that pool as existing infrastructure and researches only the prompting/architecture
  layer on top of it.

---

## Sourcing search log (Rule I / option-3 — honestly recorded, real searches run)

Four parallel sub-agents each ran multi-angle WebSearch/WebFetch sweeps (not a single search →
summary) and read primary sources directly. Representative queries actually run, and the concrete
GitHub/PyPI/HuggingFace artifacts evaluated with keep/reject reasoning:

- **§1 (announcements)**: queries incl. "NSE corporate board meetings API python", "nse pypi
  BennyThadikaran NseIndiaApi", "NSE insider trading PIT SAST API endpoint", "SEBI credit rating
  system driven disclosure 2025", "CRISIL ICRA CARE rating RSS API", "SEBI SCORES enforcement
  orders API". Repos fetched and read at source level: `BennyThadikaran/NseIndiaApi` (**vendored
  as the primary recommendation** — `src/nse/NSE.py` read directly, endpoints/rate-limit
  confirmed), `RuchiTanmay/nselib` (kept as secondary triangulation, docs too thin to lead on),
  `aeron7/nsepython` (kept as secondary triangulation), `bsedata` (**rejected** — confirmed via
  ReadTheDocs to cover only quotes/index/bhavcopy, no announcements), `jugaad-py/jugaad-data`
  (**rejected** — confirmed via GitHub fetch to cover only bhavcopy/OHLC, no announcements),
  `bsescraper` PyPI (flagged as an unverified lead, not vendored — single-source, untriangulated).
- **§2 (news feeds)**: queries incl. "moneycontrol RSS feed URL 2026", "economic times markets RSS
  feed", "livemint RSS", "reuters india RSS feed dead", "marketaux API NSE ticker", "finnhub India
  stock news API", "newsdata.io India stock ticker", "upstox news API instrument_key". Live-fetched
  and evaluated: Moneycontrol RSS (**rejected** — HTTP 200 but content frozen since 2016/2024,
  confirmed dead by comparing `pubDate` to fetch time), Reuters RSS (**rejected** — confirmed dead
  since June 2020, `feeds.reuters.com` doesn't resolve), ET Markets / LiveMint / CNBC-TV18 / Zee
  Business / The Hindu BusinessLine RSS (**BusinessLine + ET Markets vendored as primary** —
  freshest, robots.txt-clean, live-fetched and freshness-verified against wall-clock), Marketaux
  / NewsAPI.org / GDELT / Finnhub / NewsData.io / mediastack / Upstox News API pricing+docs pages
  (**Marketaux and Upstox News API flagged as pilot candidates**, the rest **rejected** for this
  use case — contractual production ban, North-America-only coverage, 100 calls/month, or
  12-hour delay, each reasoned explicitly in §2.2).
- **§3 (sentiment engines)**: queries incl. "FinBERT ProsusAI model card", "yiyanghkust finbert-tone
  vs ProsusAI", "VADER sentiment financial text accuracy benchmark", "pysentiment2 Loughran
  McDonald dictionary", "huggingface finance sentiment analysis smaller distilled model", "FinBERT
  India NIFTY SEntFiN benchmark". HuggingFace model cards fetched directly: `ProsusAI/finbert`
  (**vendored as primary** — 91-93% F1 on SEntFiN, the one India-specific benchmark found),
  `yiyanghkust/finbert-tone` (kept as a secondary option for analyst-report-style text, not
  headlines), `mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis` (flagged for
  pilot, not yet vendored), `Vansh180/FinBERT-India-v1` (flagged for pilot — weaker benchmark score
  than plain FinBERT, low adoption, not vendored outright), `ahmedrachid/FinancialBERT-Sentiment-
  Analysis` and `NOSIBLE/financial-sentiment-v1.1-base` (**rejected as primary** — self-reported
  benchmarks not independently corroborated / architecturally slower). `cjhutto/vaderSentiment`
  (**vendored as a light pre-filter only**, not primary — confirmed weaker on finance text via a
  direct comparative benchmark). `nickderobertis/pysentiment2` (**vendored as an alternative light
  pre-filter** — Loughran-McDonald finance dictionary). `TextBlob` (**rejected** — "very nearly
  random" on financial news per a direct benchmark).
- **§4 (LLM scoring)**: queries incl. "LLM financial sentiment analysis zero-shot", "Can ChatGPT
  forecast stock price movements Lopez-Lira Tang", "LLM headline sentiment consistency
  determinism", "batch prompting cost reduction LLM API", "FinBERT vs LLM sentiment trading
  performance hybrid", "adversarial headline manipulation LLM trading", "NIFTY 50 LLM sentiment
  RAG". Papers/repos read at source level: arXiv:2304.07619 (**cited as the founding prior-art
  reference**), arXiv:2506.04574 (**adopted as a direct design constraint** — no-CoT beats CoT on
  this task, read in full), arXiv:2601.13082 (**adopted as a threat model** — adversarial-headline
  attack, abstract read directly), `AI4Finance-Foundation/FinGPT` (evaluated, **not vendored** —
  it's a fine-tuning project, this bot needs pure-prompting against the existing free-tier pool),
  arXiv:2309.17322 / arXiv:2507.09739 / arXiv:2512.20082 (**flagged as open follow-ups**, not
  fully verified — PDF text extraction failed, recommend the `/html/` arXiv mirror next pass).

No blocker needed in `docs/BACKLOG.md` for the search step itself — every component area had a
real multi-query search-and-fetch pass with explicit keep/reject reasoning. The BACKLOG-worthy
follow-up items (endpoint reverse-engineering, ticker-matching NLP work, live API-key pilots) are
listed in §5's "Hard blockers to flag" and should be tracked there when this research moves to a
build phase.

---

## 0. Bottom line (direct answer)

**No single free source gives a true per-symbol, same-day, structured feed across the full
~2,000-stock + ~210-option-underlying universe for either announcements or news.** The realistic
free stack is a **combination of pieces**, each solid within its own scope:

- **Structured announcements**: the unofficial-but-actively-maintained `nse` PyPI library
  (`BennyThadikaran/NseIndiaApi`) is the strongest free wrapper found — it exposes board
  meetings, results calendar, bulk/block deals, and general corporate announcements as
  symbol-filterable, date-ranged NSE API calls, with a **documented 3 req/sec throttle**. Insider
  trading (PIT/SAST) and the new (Aug-2025) credit-rating "System Driven Disclosure" mechanism
  exist as live NSE pages but have **no library wrapper yet** — their JSON endpoints are
  unreverse-engineered, a genuine open gap.
- **News feeds**: no RSS or API gives native NSE-ticker tagging across the full universe. The
  freshest, most reliable RSS sources found are **The Hindu BusinessLine** and **Economic Times
  Markets** (both sub-hourly, robots.txt-clean, no bot-wall encountered) — but both are
  category-level firehoses requiring your own company-name→symbol matching layer.
  **Moneycontrol's and Reuters' RSS feeds are dead** (confirmed by live fetch — a real trap since
  Moneycontrol's feed URLs still return HTTP 200 with stale content). **Marketaux** is the best
  *structured* commercial API candidate (real `entities[].symbol/exchange/country` schema,
  100 req/day free) but its actual NSE/BSE depth is unverified without a live key test.
- **Sentiment engine**: **FinBERT (`ProsusAI/finbert`)** is the right default — heavy
  (torch+transformers, ~1-2.5GB installed) but throughput is a non-issue at this bot's volume
  (hundreds of headlines/minute ≈ 2-10/sec, vs. FinBERT's ~5-20/sec/core CPU unbatched), and it
  scores 91-93% F1 on **SEntFiN**, the one India-specific financial-headline benchmark found.
  **VADER is confirmed a poor fit for financial text** (56% agreement vs. FinBERT's 69% on a
  direct financial-news benchmark) — usable only as a near-zero-cost pre-filter, never as the
  primary signal.
- **LLM-based scoring**: well-supported prior art exists (the field-defining Lopez-Lira &amp; Tang
  2023 paper and several 2024-2026 follow-ups), and the bot's existing free-tier LLM pool is
  directly usable infrastructure. The single most load-bearing finding: **sentiment (tone) and
  materiality (price-impact likelihood) must be scored as separate fields** — a real study found
  FinBERT can be "accurate" on lexical sentiment while being **return-uncorrelated or actively
  misleading** for trading, and a hybrid **FinBERT-triage → LLM-escalation** architecture cut
  LLM call volume ~5x while producing an actually return-correlated signal.

**Hard blockers to flag explicitly:**
1. Both `nseindia.com` and `bseindia.com` require a **browser-session cookie handshake** — bare
   stateless HTTP fetches are blocked/redirected (confirmed repeatedly across this and prior
   research sessions). All free structured-announcement access depends on a working
   session-cookie layer, not just a URL.
2. **Insider-trading (PIT) disclosures are inherently T+2-lagged by SEBI regulation** — even a
   perfect real-time feed of the disclosure *publication* still lags the actual trade by design;
   this caps the category's intraday-signal value regardless of source.
3. **Moneycontrol and Reuters RSS are dead** but return misleadingly healthy HTTP 200 — any
   ingestion pipeline needs per-feed staleness detection (compare `pubDate`/`lastBuildDate` to
   wall-clock), not just HTTP-failure alerting.
4. Several outlets (CNBC-TV18, Zee Business, The Hindu BusinessLine) **explicitly ban
   AI-training/scraping use of their content in written ToS** — flagged per the project's
   personal-use framing (not a technical blocker), for a human decision, not silently ignored.
5. **Business Standard, NDTV Profit, and Reuters could not be reached at all from the research
   sandbox** (Akamai/DataDome bot-walls blocking even their homepages) — must be re-tested from
   the bot's actual production egress IP before ruling them in or out.

---

## 1. Structured corporate announcements / events

### 1.0 Key new finding: the `nse` PyPI library (a 5th OSS wrapper beyond the four named)

**`nse`** (PyPI package name), repo `BennyThadikaran/NseIndiaApi`
(`github.com/BennyThadikaran/NseIndiaApi`), docs
`bennythadikaran.github.io/NseIndiaApi/api.html`. 153 GitHub stars, actively maintained. **Grade
A** — read directly from source (`src/nse/NSE.py`), not just docs. This is the most complete free
wrapper found for this exact requirement, and was not in the brief's named list
(`nselib`/`nsepython`/`bsedata`/`jugaad-data`).

Confirmed exact endpoints, from source:

| Method | Endpoint | Covers | Params |
|---|---|---|---|
| `boardMeetings()` | `nseindia.com/api/corporate-board-meetings` | Forward-looking board-meeting intimations | symbol / fno-only / date range |
| `financial_results()` | `nseindia.com/api/corporates-financial-results` | Results-calendar metadata (broadcast dates, quarter, XBRL links) — no P&amp;L figures | symbol / date range |
| `results_comparison()` | `nseindia.com/api/results-comparision` | ~5 quarters P&amp;L summary per symbol | symbol |
| `bulkdeals()` | `nseindia.com/api/historicalOR/bulk-block-short-deals` | Bulk/block/short-selling deals | date range, **max 1-year span/query** |
| `blockDeals()` | `nseindia.com/api/block-deal` | Current-day block deals only | none |
| `announcements()` | `nseindia.com/api/corporate-announcements` | General corporate announcements (broad taxonomy, see §1.4) | symbol + date range |
| `actions()` | `nseindia.com/api/corporates-corporateActions` | Corporate actions (dividend/split/bonus — already covered by prior research) | symbol / date range |
| `shareholding()` | `nseindia.com/api/corporate-share-holdings-master` | Shareholding pattern (adjacent to SAST, NOT the same as PIT insider disclosures) | symbol |
| `annual_reports()` | `nseindia.com/api/annual-reports` | PDF links by year | symbol |

**Documented rate limit — the single most concrete figure found in the whole ecosystem** (direct
quote from this library's docs): "All requests through NSE are rate limited or throttled to **3
requests per second**." Recommendation: add an extra 0.5–1s sleep between requests; download
bulk/historical reports after market hours. By contrast, `nselib`'s README has **zero** mention
of throttling, and `nsepython`'s only advice is generic "avoid getting blocked" — the `nse`
library's number is the best working assumption for polling design.

Session handling matches the pattern already established in prior research (cookie captured via
an initial homepage load, held in a context-manager session).

Two OTHER independent library implementations of overlapping endpoints, confirming these are real
and stable (triangulation, not single-source):
- `nselib` (`RuchiTanmay/nselib`, Apache-2.0) also has `event_calendar_for_equity()` and
  `financial_results_for_equity()` — but its README has essentially no documentation depth
  (confirmed by direct fetch).
- `nsepython` (`aeron7/nsepython`, GPL-3.0) has `nse_events()` → `api/event-calendar`,
  `nse_results()` → `api/corporates-financial-results`, `nse_past_results()` →
  `api/results-comparision`, plus `nselib`-equivalents for bulk/block/short-selling data.

**`bsedata`** (PyPI, ReadTheDocs) — confirmed via direct fetch: purely live-quote/index/bhavcopy,
**does NOT cover** board meetings, announcements, insider trading, or bulk/block deals. Not
useful for §1. (A separate, unrelated package `bsescraper` claims BSE announcement scraping with
a "Board Meeting" category filter — grade C, untriangulated, worth a closer look for BSE-side
coverage specifically.)

**`jugaad-data`** — confirmed via GitHub fetch: does NOT expose board meetings, bulk/block deals,
announcements, or insider trading — focused on bhavcopy/historical OHLC only. Ruled out for this
entire brief.

### 1.1 Board meetings &amp; results calendar — Verdict: **GOOD**

Free, structured, per-symbol, forward-looking (board-meeting date announced ahead of the actual
meeting). Triangulated 3x across `nse`/`nsepython`/`nselib`. NSE also has a general combined page
`nseindia.com/companies-listing/corporate-filings-event-calendar`.

### 1.2 Block deals &amp; bulk deals — Verdict: **GOOD, but same-day-EOD not intraday-real-time**

Endpoint confirmed via two paths (possibly aliases of the same backend, not fully disambiguated):
`api/block-deal` (current-day snapshot) and `api/historicalOR/bulk-block-short-deals`
(date-ranged, 1-year cap). **Regulatory confirmation (grade A)**: bulk/block deals are "mandated
to be disseminated to the public on the same day **after market hours**" — same trading-day, but
end-of-day, not a live intraday print. `nselib` independently confirms via
`bulk_deal_data()`/`block_deals_data()`/`short_selling_data()`.

### 1.3 Insider trading (SAST/PIT disclosures) — Verdict: **MARGINAL/UNUSABLE as a free structured feed**

The NSE page exists (`nseindia.com/companies-listing/corporate-filings-insider-trading`,
React SPA) but **none of the 5 libraries checked wrap it** — confirmed by direct source-code grep
of the `nse` library (no PIT/SAST/insider strings found at all). The underlying JSON endpoint was
not discoverable via README/GitHub-code-search/blog research — would need live browser-devtools
inspection against the site, out of scope for pure research. Third-party freemium aggregators
exist (insiderscreener.com, grade B, confirmed by direct fetch — combines NSE+BSE PIT, states
delays "due to reporting timelines"; stockezee.com, web-dashboard-only, no API). **Structural
cap**: SEBI PIT regulations give insiders up to T+2 trading days to report — even a perfect
real-time feed of the *disclosure* still lags the actual *trade* by design, capping this
category's intraday value regardless of source.

### 1.4 Credit rating changes — Verdict: **MARGINAL-to-GOOD, pending endpoint discovery**

**Best finding**: NSE/BSE moved to an automated **"System Driven Disclosure" (SDD)** mechanism
for credit ratings as of a BSE circular dated **1-Aug-2025** (grade B, MMJC compliance-advisory
writeup, corroborated by a real filed Piramal Capital rating-intimation PDF hosted on
`nsearchives.nseindia.com` dated July 2026). Rating agencies now upload via standardized
templates with exchange-issued credentials, "relayed instantly and directly onto the stock
exchange website" — i.e. this is now a same-day/near-real-time, exchange-mediated feed, NOT
free-text press-release parsing. Confirmed page: `nseindia.com/companies-listing/corporate-sdd-
credit-rating-esg` (a UAT/staging mirror at `cmsuat.nseindia.com/...` was also found, suggesting
recent rollout). **The underlying JSON endpoint for this page has not yet been reverse-engineered
by any library** — grade C, a fresh lead worth pursuing via devtools since it's clearly a live
NSE-hosted structured page and no library has caught up to it yet.

Rating agencies' own free feeds are weak: **CRISIL** publishes a monthly (not real-time) "Rating
Actions" newsletter with no RSS/API. **ICRA** and **CARE/CareEdge**: no RSS or API found for
either; CARE's paid "Rating Tracker" portal offers "timely email alerts" (vague freshness),
no confirmed API. **None of the three major Indian rating agencies offer a free RSS or API** —
the new NSE/BSE SDD mechanism, once its endpoint is found, is the better bet than chasing agencies
directly.

### 1.5 General corporate announcements — Verdict: **GOOD**

Endpoint confirmed 3x (`nse` lib source, `nsepython`, NSE's own categories page):
`api/corporate-announcements`, default "all announcements for the current date," extendable via
`from_date`/`to_date`, symbol-filterable. **Rate limit: 3 req/sec** (see §1.0). Confirmed
category taxonomy from NSE's own filings page: Board Meetings, Corporate Actions, Financial
Results, Buy Back/Redemption, Event Calendar, Credit Rating Details, Default/Interest/Redemption
Payment Details, Debt Centralised Database — a broader tag set than dividend/split/bonus alone.
**Open gap**: no authoritative statement of the earliest date the live feed goes back to when
queried today; the only hard limit found is the 1-year max span per historical query (confirmed
for bulk deals, likely — not separately confirmed — for announcements too). Practical polling
cadence implied by the ecosystem's own norms: **1-5 minute intervals during market hours**, not
sub-minute continuous streaming (no library is built for that, and all warn against
excessive-frequency blocking).

### 1.6 SEBI SCORES / enforcement actions — Verdict: **MARGINAL** (RSS exists, but coarse)

**SEBI's aggregate RSS confirmed**: `sebi.gov.in/sebirss.xml` (confirmed via direct fetch of
`sebi.gov.in/rss.html`) — covers latest press releases, circulars, orders/rulings, but is a
**single firehose, not per-company/queryable**; would need the same free-text company-name
matching already used for corporate actions. SEBI's enforcement-orders page
(`sebi.gov.in/enforcement/orders.html`) is human-readable HTML only, no JSON API. **SEBI SCORES**
(`scores.sebi.gov.in`) is an individual investor-grievance tracker with no public API or bulk
database — not fit for purpose as a market-wide regulatory-event signal.

### 1.7 §1 summary table

| Sub-area | Best free source | Access | Freshness | Verdict |
|---|---|---|---|---|
| Board meetings / results calendar | NSE `api/corporate-board-meetings`, `api/corporates-financial-results` (via `nse`/`nsepython`/`nselib`, 3x triangulated) | Free, session-cookie scrape | Forward-looking, updated as filed | **Good** |
| Block / bulk deals | NSE `api/block-deal`, `api/historicalOR/bulk-block-short-deals` | Free, session-cookie scrape | Same trading-day, after market hours | **Good** |
| Insider trading (PIT/SAST) | NSE PIT page (endpoint unwrapped by any library) | Free but unwrapped; 3rd-party freemium (insiderscreener) | Inherently T+2-lagged by regulation | **Marginal** |
| Credit ratings | New NSE/BSE SDD mechanism (endpoint not yet reverse-engineered) | Free but unwrapped; agencies have no free API/RSS | Same-day per SDD (new Aug-2025) | **Marginal-to-Good** |
| General announcements | NSE `api/corporate-announcements` | Free, 3 req/sec throttle documented | Current-date default, date-range extendable | **Good** |
| SEBI enforcement | `sebi.gov.in/sebirss.xml` | Free RSS | Near-real-time but unstructured/aggregate | **Marginal** |

**Open items not resolved this pass**: exact JSON endpoints for the PIT page and the new
credit-rating SDD page; earliest-date boundary of the live announcements/board-meeting feeds;
whether the two block/bulk-deal endpoint aliases found are the same backend; CRISIL/ICRA/CARE
paid-tier options (out of scope — free/RSS only per the brief).

---

## 2. Financial news feeds (text, broad coverage)

### 2.0 Bottom line for §2

No RSS or API — free or paid — gives true per-NSE-ticker tagging across the full ~2,000-symbol
universe. The one near-exception is Upstox's brand-new News API (broker-native, `instrument_key`-
keyed, but 3 months old and 7-day lookback only). Everything else is a category-level firehose
requiring a custom company-name→NSE-symbol matching layer.

### 2.1 RSS feeds — verified findings

| Source | Grade | Working URL pattern | Freshness (live-fetched, 2026-07-26) | Ticker tagging | ToS risk |
|---|---|---|---|---|---|
| **Moneycontrol** | A | `moneycontrol.com/rss/{latestnews,buzzingstocks,results,marketreports,economy,business,MCtopnews,marketedge}.xml` | **Dead** — HTTP 200 but content frozen since Apr 2024 (some since Oct 2016); feed-index page is HTTP 410 | None | Unverified (503 on ToS page) |
| **Economic Times Markets** | A | `economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms` (+ Stocks `2146842`, Company `2143429`, IPOs `14655708`) | **Fresh** — 3 min to 2 hr gaps | Category only | Broad "no automated system" clause |
| **LiveMint** | A | `livemint.com/rss/{news,markets,companies,money,economy,...}` | **Fresh** — 5-90 min gaps | Category only | Explicit anti-bot clause; RSS is an official feature |
| **Business Standard** | A (archive) / blocked (live) | `business-standard.com/rss/markets-106.rss` pattern confirmed via Wayback (~4 min lag) | Fresh per archive; **site 403-blocks all automated traffic (Akamai) from this environment** | Unverified | Unverified — must retest from deploy host |
| **Reuters India/Business** | A | **No working RSS — confirmed dead since June 2020.** `feeds.reuters.com` doesn't resolve; DataDome blocks even the homepage | N/A | N/A | Paid Reuters Connect license required |
| **NDTV Profit** | C | Unverifiable — fully 403-blocked (Akamai) from every UA/protocol tried | Unknown | Unknown | Unknown |
| **CNBC-TV18** | A | `cnbctv18.com/commonfeeds/v1/cne/rss/{market,business,economy,latest,india,...}.xml` | **Fresh** — 40-90 min gaps (Sunday; tighter expected on trading days) | Category only | **Explicit written ban on scraping/AI-training use** |
| **Zee Business** | A | `zeebiz.com/{companies,india}.xml` fresh; `.../india-markets.xml` &amp; others **stale for months-to-a-year** | Category only | Explicit ban on "systematic downloading and storing" |
| **The Hindu BusinessLine** | A | `thehindubusinessline.com/{markets,markets/stock-markets,companies,economy,news}/feeder/default.rss` | **Best of all sources** — sub-hourly, `&lt;ttl&gt;60&lt;/ttl&gt;` polite-poll hint matched live | Category only, incl. dedicated Stock-Fundamentals/Technical-Analysis feeds | Blocks ClaudeBot/GPTBot by name in robots.txt |

**Cross-cutting findings:**
- **HTTP 200 ≠ fresh** — Moneycontrol and several Zee Business feeds return valid, live-looking
  XML wrappers with zero new content for months/years. Any ingestion pipeline needs per-feed
  staleness detection (compare `pubDate`/`lastBuildDate` to wall-clock), not just HTTP-failure
  alerting.
- **Akamai/DataDome bot-management, not robots.txt, is the real barrier** for Reuters, NDTV
  Profit, and Business Standard — blocks generic automated traffic outright. Results may differ
  on the bot's actual production IP.
- **ClaudeBot/GPTBot/PerplexityBot explicitly named and disallowed** in robots.txt on CNBC-TV18,
  Zee Business, and BusinessLine — use a neutral UA if strict robots.txt compliance matters.
- **CNBC-TV18's ToS explicitly names "creating large language models and/or training of A.I.
  tools"** as a prohibited scraped-content use — the most direct restriction found.

### 2.2 News APIs — verified findings

| API | Grade | Free tier (exact) | Paid entry | Ticker/symbol field? | NSE/BSE coverage | Freshness |
|---|---|---|---|---|---|---|
| **NewsAPI.org** | A | 100 req/day, 1-mo lookback, **contractually dev/test only — barred from production** | $449/mo (250k req, 5yr lookback) | No — keyword/`q` only | `country=in` filter exists, no named India sources found | Undocumented |
| **GDELT** | A | Free forever, **empirically ~1 req/5 sec throttle** (undocumented, discovered live) | N/A | No — Wikipedia-linked entity graph, not tickers | Live-verified ToI/Hindu BL/Hindi outlets present; academically documented English-language bias | ~&lt;1hr lag (matches documented 15-min refresh) |
| **Marketaux** | A (pricing) / C (India depth) | 100 req/day, 3 articles/req | $29/mo (2,500 req/day, 20 articles/req) | **Yes — the only one of these with a real `entities[].symbol/exchange/country` schema** | `countries=in` documented; **actual NSE/BSE ticker population unverified — needs live key test** | Claimed "instant"/"every minute," not independently verified |
| **Finnhub** | B/C | ~60 calls/min (secondary; primary pricing page a JS SPA, not directly verified) | ~$50/mo per market add-on (secondary) | Ticker-tagged, but **Company News endpoint explicitly restricted to North American companies** | **Effectively none for news** | N/A |
| **NewsData.io** | A | 200 credits/day × 10 articles/credit ≈ 2,000/day, but **12-hour delay** — disqualifying for intraday | $199.99/mo (real-time, 6-mo history) | `country=in` + category filters; no evidence of ticker-level tagging | Business-category India filter only | Real-time only from $199.99/mo up |
| **mediastack** | A | **100 calls/month** (too thin), delayed data | $24.99/mo (10k calls, still delayed unless higher tier) | `countries=in` + business category; no ticker tagging | Keyword/category aggregator only | Delayed even on paid entry tier |
| **Upstox News API** (broker API) | A | Free with a live Upstox trading account; 50 req/sec, 500/min, 2,000/30-min | N/A | **Yes — natively keyed by `instrument_key`** (e.g. `NSE_EQ\|INE040H01021`) | Real NSE instrument-native — launched Apr 2026 (~3 months old), untested at scale | 7-day lookback only; near-real-time by design |
| Zerodha Kite Connect | A | — | — | No news endpoint at all (confirmed via official docs) | — | — |
| Fyers / Groww / Angel One | B/C | — | — | No news endpoint found in any available docs | — | — |
| Alpha Vantage News &amp; Sentiment | C | Unverified (docs too large to render fully; demo key rejected real tickers) | Unverified | `.BSE`-suffixed quote tickers confirmed for general data; News&amp;Sentiment India ticker coverage unconfirmed | Unverified | Unverified |
| IndianAPI.in | B | Pricing dashboard-gated; bundles generic "Recent News" into company-profile endpoint, not a dedicated news product | Unverified | Implicit (attached to per-symbol profile), not a real entity schema | Plausible, unconfirmed | Unconfirmed |
| Polygon.io, Benzinga | C | — | — | Confirmed no meaningful India/NSE coverage | — | — |

### 2.3 Ranked verdict for this bot

1. **Best free combo**: **The Hindu BusinessLine + Economic Times Markets RSS** (category feeds)
   as the raw firehose, fed through a custom NER/company-name matcher against the NSE symbol
   master list. Freshest, most reliably reachable, no bot-wall encountered, robots.txt-clean.
   Requires real engineering effort for the matching layer — validate precision/recall against
   real headlines per Rule F before sign-off.
2. **Best structured-API pilot candidate**: **Marketaux free tier** (100 req/day) — the only
   candidate with a genuine `symbol/exchange/country` schema; empirically test a spread of ~30
   liquid + ~30 illiquid NSE names before committing. If India depth holds up, $29/mo (2,500
   req/day) would comfortably cover the full universe.
3. **Genuinely ticker-native long-shot**: **Upstox News API**, if an Upstox account is already
   held or opened — the only option ticker-linked by construction rather than inference. Treat as
   supplementary/experimental (~3-month track record, 7-day lookback, unverified full-universe
   coverage).
4. **Do not build on**: Moneycontrol RSS (dead), Reuters RSS (dead), NewsAPI.org free tier
   (contractually barred from production), mediastack free tier (100 calls/month), Finnhub
   (excludes non-North-American company news), NDTV Profit/Business Standard (currently
   network-blocked, retest from production host).
5. **GDELT** is a credible free supplementary broad-sentiment/volume layer (large depth,
   near-real-time, empirically India-covering) but its throttle and lack of a ticker concept make
   it a poor primary source at this scale — better as secondary corroboration.

### 2.4 What §2 did not cover

StockEdge news API (no lead found); Trendlyne/Tickertape/Screener.in private APIs (none publicly
documented); full Alpha Vantage `NEWS_SENTIMENT` parameter docs (page too large to render fully,
demo key rejected non-demo tickers); GDELT BigQuery-specific quota details.

---

## 3. Sentiment engines (score text tone)

### 3.0 Bottom line for §3

At this bot's actual volume — hundreds of headlines/minute ≈ **2-10/sec sustained** — throughput
is **not the binding constraint for any candidate here, including full FinBERT on CPU**. The real
trade-off is accuracy-on-financial-jargon vs. install/dependency weight. Recommended default:
**FinBERT (`ProsusAI/finbert`) as primary scorer**, **VADER or Loughran-McDonald
(`pysentiment2`) as a zero-dependency pre-filter**, **spaCy strictly for NER (ticker/company
extraction), not sentiment**.

### 3.1 FinBERT variants — HEAVY, transformer-based

**`ProsusAI/finbert`** (grade A, model card fetched directly, `huggingface.co/ProsusAI/finbert`):
BERT-base further pre-trained on financial corpus, fine-tuned on **Financial PhraseBank**. ~110M
params, ~440MB disk fp32 (~208-220MB fp16). Output: 3-class softmax (positive/negative/neutral).
Paper: arXiv:1908.10063 (Araci &amp; Genc, 2019). 6.68M downloads/month — the de-facto standard.
**Deps**: `transformers` + `torch` — CPU-only torch wheel is the critical install choice (pin
`--extra-index-url https://download.pytorch.org/whl/cpu`, shrinks total footprint to ~1.75GB vs.
2.5-8GB for a full CUDA build).

**`yiyanghkust/finbert-tone`** (grade A, model card fetched directly): trained on 4.9B tokens of
10-K/10-Q/earnings-call/analyst-report text, fine-tuned on 10,000 manually-annotated analyst-
report sentences — i.e. tuned for **formal corporate-disclosure language**, not news headlines.
944k downloads/month. In one direct benchmark it scored **lower** on general news headlines than
plain ProsusAI/finbert (53% vs 69% agreement) — better suited to earnings-call/analyst-report
text than punchy headlines.

**Speed** (grade B, no FinBERT-specific official benchmark exists): general BERT-base on CPU runs
~5-17 inferences/sec/core unbatched; a scaled service on a 36-core Xeon hits 3,000+/sec batched.
**ONNX Runtime INT8 quantization gives a well-documented 3-6x CPU speedup** with minimal accuracy
loss — a low-effort upgrade path if the full 2,000-stock universe ever needs near-simultaneous
scoring on a news burst. Even conservatively, unquantized FinBERT clears "hundreds/minute" with
large headroom.

**Accuracy on financial headlines**:
- **SEntFiN 1.0** (10,753 India-specific labeled financial headlines, arXiv:2305.12257) — the
  most India-relevant benchmark found: **FinBERT F1 = 93.27%, accuracy = 91.08%** (grade B).
- **Nosible benchmark** (250 hand-labeled real news stories 2014-2023, grade A — fetched
  directly): FinBERT 69% agreement, FinBERT-Tone 53%, VADER 56%, TextBlob "very nearly random."
  Explicit quote: **"VADER is 339x faster than FinBERT"** but less accurate.

**Smaller/distilled options found**: `mrm8488/distilroberta-finetuned-financial-news-sentiment-
analysis` (82M params vs 110M/125M, ~2x faster, PhraseBank-tuned — grade B, worth piloting if
FinBERT CPU latency ever becomes a real bottleneck). **India-specific**: `Vansh180/FinBERT-
India-v1` (fine-tune of finbert-tone on ~7,451 India headlines, MIT, grade A model card fetched)
— but reports **76.8% accuracy, noticeably weaker than generic FinBERT's SEntFiN scores, and only
810 downloads/month with minimal validation** — early-stage, pilot-test against real data before
trusting over plain FinBERT.

### 3.2 VADER (`vaderSentiment`) — LIGHT, lexicon/rule-based

Grade A (GitHub `cjhutto/vaderSentiment` + PyPI, both fetched directly). 126KB wheel, v3.3.2
(**last released May 2020**, unmaintained-but-stable, 5,000+ stars, MIT). Essentially zero
dependencies for core use. **Confirmed weak fit for finance**: built for social-media text, no
concept of financial-domain polarity ("beat estimates," "guidance cut," "circuit filter" mean
nothing to its lexicon). Nosible benchmark: 56% agreement vs FinBERT's 69%. A second source
(grade C, unverified) puts VADER at 44.3% vs FinBERT 59.7% on a financial task — directionally
consistent. **Verdict**: fast pre-filter/fallback only, never the primary signal.

### 3.3 Other HuggingFace finance-sentiment models found

| Model | Notes | Grade |
|---|---|---|
| `ahmedrachid/FinancialBERT-Sentiment-Analysis` | Claims 98% acc on its own PhraseBank split (232k downloads/mo) — likely overfit to PhraseBank's narrow style, treat skeptically | A(card)/C(claim) |
| `mrm8488/distilroberta-finetuned-financial-news-sentiment` | **82M params, ~2x faster than full BERT-base**, PhraseBank-tuned | B |
| `NOSIBLE/financial-sentiment-v1.1-base` | Qwen3-0.6B causal LM, 100k real financial snippets, claims to beat FinBERT — but **0.6B &gt; FinBERT's 110M and generative architecture is inherently slower per-inference**; new (Dec 2025), 149 downloads/mo, unproven at scale | A/C mix |
| `Vansh180/FinBERT-India-v1` | See §3.1 — India-specific but weaker/unproven | A(card)/C(reliability) |
| `bardsai/finance-sentiment-{pl,zh}-fast` | Polish and Chinese only — not applicable | B |

No credible Hindi/code-mixed finance sentiment model with meaningful adoption was found — likely
not a practical blocker given NSE headlines are essentially always in English (Reuters/PTI/
Moneycontrol/ET style), but flagged since the brief asked specifically about Indian-jargon fit.

### 3.4 `pysentiment2` — LIGHT, dictionary-based (finance-specific lexicon)

Grade B (PyPI page failed to render; recovered via GitHub/docs,
`nickderobertis/pysentiment` fork). Provides the **Loughran-McDonald Financial Sentiment
Dictionary** — purpose-built for 10-K/finance text to fix general lexicons' poor finance fit (the
same problem VADER has). Pure dictionary lookup, no torch/transformers, comparable speed class to
VADER (thousands/sec). Categories beyond positive/negative include "litigious," "uncertainty,"
"constraining." Tuned for formal SEC-filing language rather than punchy headlines, but a
meaningfully better lexical match for finance than VADER's social-media lexicon — good candidate
as a second light fallback.

### 3.5 spaCy — NOT a sentiment engine; role is NER/entity extraction

Grade B. spaCy ships no sentiment analysis natively — its core is tokenization/POS/dependency-
parsing/NER (18 entity types incl. ORG, GPE, MONEY, DATE). Sentiment requires `spacytextblob`
(just wraps TextBlob's lexicon, not finance-aware) or `spacy-transformers` (integration
convenience to run FinBERT through spaCy's pipeline, not a different model). **Realistic role**:
extract company/ticker mentions from headlines so a sentiment score attributes to the correct NSE
symbol — a real open-source project doing exactly this was found
(`RelativelyBurberry/Indian-Stock-News-Sentiment-Analysis`: NSE ticker mapping + FinBERT). spaCy's
out-of-the-box NER is trained on general Wikipedia/news entities and will likely need fine-tuning
or a gazetteer of NSE company names/aliases (RIL, M&amp;M, L&amp;T-style short-forms) to reliably
catch Indian-market references.

### 3.6 TextBlob — LIGHT, general lexicon-based (not finance-aware)

Grade A (PyPI fetched). 625KB wheel, NLTK-based, `polarity`/`subjectivity` scores. Nosible
benchmark (grade A): "very nearly random" on financial news — the weakest of all tested options.
**Verdict**: not recommended for the sentiment role; VADER and Loughran-McDonald are both
lexicon-based and both meaningfully better-suited to finance.

### 3.7 §3 comparison table

| Candidate | Weight | Offline | Speed class | Finance-tuned? | Best accuracy evidence | Verdict |
|---|---|---|---|---|---|---|
| **ProsusAI/finbert** | HEAVY (~1-2.5GB) | Yes | ~5-20/sec/core CPU; 1000s/sec batched+ONNX-INT8 | Yes (PhraseBank) | **91-93% F1 on SEntFiN** (India headlines) | **Primary recommendation** |
| **yiyanghkust/finbert-tone** | HEAVY | Yes | same class | Yes (analyst/10-K tuned) | 53% agreement (weaker on headlines) | Secondary — better for earnings-call text |
| **distilroberta-finetuned-financial-news** | MEDIUM (82M, ~2x smaller) | Yes | Faster than base FinBERT | Yes | Not independently benchmarked | Pilot if latency ever bottlenecks |
| **Vansh180/FinBERT-India-v1** | HEAVY | Yes | same class | Yes (India-specific) | 76.8% acc (weak, low adoption) | Promising direction, unproven — pilot only |
| **VADER** | **LIGHT** (~zero deps) | Yes | 1000s/sec (339x faster than FinBERT) | No | 56% agreement | Pre-filter/fallback only |
| **pysentiment2 (LM)** | **LIGHT** | Yes | comparable to VADER | Yes (LM dictionary) | Not independently benchmarked | Good light finance-aware fallback |
| **TextBlob** | LIGHT | Yes | Fast | No | "Very nearly random" | Not recommended |
| **spaCy (+spacytextblob)** | MEDIUM | Yes | Fast | No (sentiment via TextBlob) | N/A | **NER/ticker extraction only** |

### 3.8 Practical recommendation

1. **Primary: ProsusAI/finbert**, CPU-only torch build, batched inference; add ONNX+INT8
   quantization as a low-effort headroom upgrade if scoring the full universe near-simultaneously
   ever becomes necessary.
2. **Fast pre-filter/cross-check: VADER or pysentiment2** — near-zero cost, flag high-magnitude
   headlines for priority FinBERT processing, but never as the sole signal.
3. **spaCy (or a custom NSE gazetteer) for ticker/company NER**, feeding entity-tagged headlines
   into FinBERT so scores attribute to the correct symbol.
4. **Pilot-test `Vansh180/FinBERT-India-v1` and `mrm8488/distilroberta-finetuned-financial-news-
   sentiment`** against a held-out sample of real NSE headlines before deciding whether either
   beats plain ProsusAI/finbert for this specific corpus.
5. **Skip TextBlob** for sentiment entirely.

---

## 4. LLM-based headline scoring

### 4.0 Connection to existing infra

The bot already has a swappable free-tier multi-provider LLM pool (14+ OpenAI-compatible
providers — Groq, Gemini, Cerebras, Scaleway, SambaNova, OpenRouter, etc., 10-6,000 RPM
depending on provider/tier, JSON-schema/tool-calling supported — see `docs/research/97` and
`98`). This is directly usable as the inference backend for everything below — no new provider
integration is needed, only a prompt/schema layer and batching/routing strategy.

### 4.1 Prior art / published approaches

**Lopez-Lira &amp; Tang, "Can ChatGPT Forecast Stock Price Movements?"** (arXiv:2304.07619 /
SSRN 4412788, Apr 2023 → revised through v6 Oct 2025) — the field-defining paper, grade A (abstract
+ methodology read directly). ~50,000+ headlines (NYSE/Nasdaq/AMEX/small-cap), starting Oct 2022
(post-training-cutoff at the time, to rule out memorization). **Exact prompt used** (grade B,
verified via secondary sources): *"Forget all your previous instructions. Pretend you are a
financial expert... Answer 'YES' if good news, 'NO' if bad news, or 'UNKNOWN' if uncertain in the
first line. Then elaborate with one short and concise sentence on the next line."* Findings:
capability is emergent in larger models (small/basic models show no predictability); GPT-4 shows
significant return predictability, strongest in small-caps and negative news — but the paper's own
later revisions note **the edge decays as more market participants adopt LLM signals** (decaying
alpha, not permanent, consistent with market efficiency).

**Follow-up critique** (arXiv:2309.17322, "Assessing Look-Ahead Bias in Stock Return Predictions
Generated By GPT Sentiment Analysis") probes whether the apparent predictive power is contaminated
by post-cutoff leakage via other channels — grade C (title/topic confirmed, numeric conclusions
not extracted from a compressed PDF; flagged for a follow-up read).

**2024-2026 replications/extensions found** (titles/abstracts, grade B/C, several not fully read):
arXiv:2410.01987 (GPT/FinBERT comparison), arXiv:2507.09739 (LLM-vs-FinBERT trading performance,
S&amp;P 500), arXiv:2606.12210 (limits of zero-shot financial NLP), and — most relevant to this
project — **arXiv:2512.20082, "Adaptive Financial Sentiment Analysis for NIFTY 50 via
Instruction-Tuned LLMs, RAG and Reinforcement Learning"** — directly on the NIFTY 50 universe,
worth a dedicated follow-up read (grade C, lead only this pass).

**Open-source repos**: **FinGPT** (`AI4Finance-Foundation`) is the most mature project, but it's
primarily a **fine-tuning** project (LoRA on Llama-2/ChatGLM2), not pure prompting — benchmarked
FinGPT v3.3 at 0.882 weighted-F1 on PhraseBank vs. GPT-4 zero-shot 0.833 vs FinBERT 0.880 (grade B,
README read directly). No clean, general-LLM-prompting-only, JSON-batch-scoring pipeline
purpose-built for intraday equities was found — a genuine gap this bot would be filling, not
copying wholesale (though the component pieces exist separately).

### 4.2 Prompt design patterns

Converging patterns across sources (grade B, synthesized, no single canonical reference
implementation found verbatim):
1. **Binary/ternary directional label + rationale** (Lopez-Lira &amp; Tang's prompt) — simplest,
   oldest, but not machine-parseable without post-processing.
2. **Structured JSON schema** — the pattern for production use: per-headline object with
   `sentiment` (categorical or -1..+1), **`materiality`/`impact` as an explicitly separate
   field** ("does this news matter for price," distinct from tone), `confidence`, one-line
   rationale.
3. **Materiality-aware labeling instruction is explicit design guidance found repeatedly**: *"if
   an article is unlikely to impact price, its label should be neutral even if the overall tone is
   positive or negative."* This should be baked into the prompt instruction directly, not left
   implicit.
4. **JSON-array batch responses**: send N headlines as a numbered list in one prompt, request a
   JSON array with one object per index, matching input order — the concrete mechanism for §4.4's
   batching strategy.
5. A named "DK-CoT-JSON" pattern (domain-knowledge chain-of-thought + JSON emission) was found but
   **conflicts with §4.3's finding that CoT hurts accuracy on this task** — test both ways
   empirically rather than assuming CoT helps.

### 4.3 Consistency/determinism pitfalls

Well-documented, active problem, not a footnote:
- Named the **"Model Variability Problem" (MVP)** in a 2025 review (arXiv:2504.04462, grade B,
  abstract-level, full text not independently verified).
- **Temperature=0 alone does not guarantee determinism** — several sources note LLMs "often
  generate inconsistent responses even under supposedly deterministic settings," a known artifact
  of MoE-routing nondeterminism/batch-order floating-point effects on the *provider's* hardware,
  not just the sampling knob. This matters directly for this bot: several free-tier providers in
  the pool run on custom inference hardware (Groq, Cerebras) where batch-dependent nondeterminism
  is documented — temperature=0 is necessary but not sufficient.
- **"The Non-Determinism of Small LLMs"** (arXiv:2509.09705, Sept 2025) — evidences low answer-
  consistency specifically for small/free-tier-class models, directly relevant since this pool
  leans on smaller free-tier models (8B/20B-class).
- **Mitigations converging across sources**: (a) run identical input ≥3 times, compute an explicit
  **consistency score** as its own reliability metric, not just accuracy; (b) **self-consistency/
  majority-vote** — sample multiple completions, take the mode of the extracted structured field;
  (c) **constrain via JSON-schema/function-calling** (already supported across the pool per doc
  98) to eliminate free-text-parsing variance as a separate axis; (d) periodic calibration against
  a small labeled ground-truth set to catch drift.

### 4.4 Rate-limit / cost pitfalls at scale

- **Batch prompting** (arXiv:2301.08721, "Batch Prompting: Efficient Inference with LLM APIs") —
  pack N samples into one call, amortizing system-prompt overhead. Cost-optimization sources
  report ~30-50% cost reduction from batching alone, plus a larger separate win from **structured
  JSON output** (one cited example: ~200 tokens/response prose → ~30 tokens/response JSON, ~85%
  output-token reduction). Grade B (blog-level, directional not audited).
- **Concretely for this bot**: with potentially hundreds of headlines across ~2,000 symbols in a
  session, batching 10-20 headlines/call turns "hundreds of calls" into "tens of calls" — directly
  relevant against several Tier-2/3 providers' 5-30 RPM free-tier floors in the existing pool
  (Cerebras 5 RPM, GitHub Models 10-15 RPM, Cohere 20 RPM). This should be a **first-class design
  requirement, not a later optimization** — at 1 headline/call, even the best-provisioned free
  providers (Groq ~30 RPM shared) would bottleneck hard against the full universe within a single
  session.
- **Latency**: benchmarks found put GPT-4-class latency at 1.2-1.8s end-to-end, GPT-4o ~5s, some
  2026 mini-class models at 0.79-3.5s — all far above FinBERT/VADER's near-instant (&lt;50ms)
  local inference. Likely tolerable for headline-driven catalyst detection **if scored
  asynchronously in the background**, not synchronously blocking an order-decision loop on an LLM
  round-trip.
- **Rate-limit fallback**: the existing 14-provider failover pool is directly the right mitigation
  architecture already in place — no new research needed beyond wiring batch-array prompting into
  each provider's adapter (all confirmed OpenAI-compatible per doc 98).

### 4.5 LLM vs specialized model comparison — the strongest single finding

Head-to-head results are genuinely mixed and dataset-dependent — no universal winner on static
benchmark accuracy (fine-tuned FinBERT modestly beats zero-shot GPT-4o on PhraseBank in one
comparison; the reverse holds in others). **But: fine-tuned domain models tend to win on static
labeled-benchmark accuracy, while general LLMs tend to win — or at least compete — on actual
downstream return-predictiveness**, likely because materiality/context reasoning matters more for
real trading impact than lexical sentiment classification per se.

**Most concrete and directly relevant finding — the FinBERT-triage + LLM-escalation hybrid**
(Tommi Johnsen Substack, "Can LLMs Beat FinBERT for Stock Sentiment Trading?" — grade B, read
directly, methodology and limitations disclosed transparently, unusually rigorous for a blog):
- Architecture: FinBERT scores every headline first (cheap, instant); anything FinBERT calls
  **non-neutral** (34.6% of the dataset) escalates to an LLM (Claude) for a second opinion, which
  overrides FinBERT on disagreement — ~65% never incurs an LLM call.
- Dataset: 2,287 labeled articles, 12 semiconductor tickers, 30 days (Jan-Feb 2026), Google News
  RSS-sourced with dedup; price-move validation r=0.964 vs. S&amp;P Capital IQ on 213 matched
  observations (a real methodological check).
- **Key result: FinBERT-only showed near-zero/inverted correlation with actual subsequent returns
  despite 86-97% accuracy on standard classification benchmarks** — i.e. FinBERT can be
  "accurate" on lexical sentiment while being useless or actively misleading for trading. The
  hybrid pipeline achieved r=0.214 return-correlation.
- Cost: hybrid ~$0.10/day vs. ~$0.50/day for pure-LLM-on-everything (~200 headlines) — a 5x cost
  reduction from the triage step alone.
- Author-disclosed limitations: 30 days is below the recommended t&gt;3.0 statistical threshold
  (Harvey/Liu/Zhu 2016) for a credible finding; sector-specific; author cites Chen &amp; Velikov
  2022's 93% alpha-decay-after-transaction-costs figure as a reason even a working signal isn't
  automatically profitable.

**Counterintuitive but well-evidenced: reasoning/CoT hurts, doesn't help, on this task.**
**"Reasoning or Overthinking: Evaluating LLMs on Financial Sentiment Analysis"** (arXiv:2506.04574,
grade A, primary paper read directly). GPT-4o, GPT-4.1, o3-mini tested on Financial PhraseBank
(4,845 sentences). **No-CoT beat CoT and beat the reasoning-optimized model** — GPT-4o No-CoT
~0.73 macro-F1 vs ~0.67 with long CoT; o3-mini scored consistently lowest despite 4-5x more
tokens. Authors' explanation: financial sentiment is a "System-1" (fast/intuitive) judgment task
mirroring how human annotators actually label it; explicit reasoning induces "overthinking" that
drifts from the ground-truth label distribution. **Design implication: prefer a fast direct-
classification prompt over CoT, and do NOT default to a "thinking"/reasoning-tier model for this
task** — counter to the instinct to reach for the smartest available free-tier model.

### 4.6 Hallucination/reliability risk specific to trading (India-relevant)

- **Structural risk**: unlike most LLM-application domains, a hallucination here can trigger an
  *irreversible* action (an order fill) before any check catches it. Documented failure chains:
  erroneous entry on a fabricated fact, stop-loss cascades if other automated participants pick up
  the same false signal, confidence-based over-scaling because a fabrication is delivered with the
  same confident tone as truth. One cited (grade C, unverified, flagged as a lead not settled
  fact) benchmark found a finance-focused LLM fabricated content in 41% of probing test cases.
- **Adversarial-manipulation is a documented, actively-studied attack surface, not hypothetical**:
  **"Adversarial News and Lost Profits: Manipulating Headlines in LLM-Driven Algorithmic Trading"**
  (arXiv:2601.13082, grade A, primary abstract read directly). Demonstrates Unicode-homoglyph
  substitution and hidden-text-clause attacks against LLM-driven trading pipelines specifically.
  Measured impact: a sustained one-day-per-period attack over 14 months reduced simulated annual
  returns by up to **17.7 percentage points**, tested against FinBERT, FinGPT, and FinLLaMA;
  authors surveyed 27 FinTech practitioners on real-world feasibility.
- **India/NSE-specific gap is real, not theoretical**: general LLMs' training data skews heavily
  toward US/global financial press, amplifying training-cutoff and unfamiliarity risk for
  NSE-specific events (SEBI circulars, Indian corporate-action nuances, regional-press-only
  headlines). The closest on-point paper, **arXiv:2512.20082** (NIFTY-50-specific, §4.1), proposes
  **RAG (retrieval-augmented generation)** as the fix — grounding the LLM's judgment in retrieved
  real-time context (article body, recent price action, sector context) rather than a bare
  headline plus static training knowledge. Grade C — title/abstract-level lead, flagged for a
  dedicated follow-up read, not yet verified in full.
- **Mitigation patterns converging across sources**: never let an LLM score be the sole order gate
  — bind it to verifiable source text where possible, cross-validate against a second independent
  signal (price/volume confirmation), and cap position sizing on any single LLM-derived signal,
  since "current fact-checking mechanisms operate at second-scale latency, incompatible with
  millisecond trading decisions" — full verification-before-trade isn't achievable in real time,
  so risk-sizing is a necessary compensating control, not optional.

### 4.7 Synthesis — is this a good fit, and what must the design account for

**Yes, with specific guardrails** — this is well-supported prior art, not speculative, and the
existing free-tier pool is structurally the right infrastructure. Six concrete, non-optional
design requirements surfaced:
1. **Score sentiment and materiality as two explicit JSON fields**, prompt-instructed to judge
   materiality by likely price impact, not surface tone — the single most load-bearing finding
   (§4.5's FinBERT accurate-but-return-uncorrelated result shows tone-only scoring is actively
   misleading for trading).
2. **Do not default to a reasoning/"thinking" model or CoT prompt** (§4.5, primary-source finding).
3. **Batch headlines into JSON-array prompts (10-20/call)** as a first-class requirement to fit
   the 2,000-symbol universe against the pool's 5-30 RPM free-tier floors.
4. **Build in a consistency check** — majority-vote for borderline/high-materiality headlines, or
   periodic calibration against a hand-labeled set — temperature=0 alone is documented as
   insufficient on several of the pool's backends.
5. **Adopt the FinBERT-triage → LLM-escalation hybrid architecture** as the primary design pattern
   rather than LLM-on-every-headline: ~5x fewer LLM calls, and the pure-lexical FinBERT layer alone
   is demonstrably trading-uninformative on its own per §4.5 — so FinBERT should be a cheap triage
   filter, never the final trading signal.
6. **Treat India/NSE-specific materiality judgments as higher-hallucination-risk** than US-headline
   judgments; follow the RAG-grounding direction in arXiv:2512.20082 (needs a dedicated follow-up
   read); treat the adversarial-headline attack surface (arXiv:2601.13082, grade A) as a real
   threat model — cap exposure on any single LLM-derived signal, never let it be the sole order
   trigger without secondary price/volume confirmation.

**Open follow-ups flagged, not fully verified this pass**: arXiv:2309.17322 (look-ahead-bias
critique), arXiv:2507.09739 (S&amp;P 500 LLM-vs-FinBERT trading numbers), arXiv:2512.20082
(NIFTY-50 RAG paper) — all three resisted PDF text extraction; recommend fetching their
`arxiv.org/html/XXXX` mirror instead of the PDF route used this session.

---

## 5. Recommendation — best FREE stack to start

| Layer | Pick | What it provides | Hard blockers to flag |
|---|---|---|---|
| **Structured announcements** | `nse` PyPI library (`BennyThadikaran/NseIndiaApi`) wrapping NSE's `api/corporate-announcements`, `api/corporate-board-meetings`, `api/corporates-financial-results`, `api/block-deal`/`historicalOR/bulk-block-short-deals` | Per-symbol board meetings, results calendar, general announcements (results/buyback/litigation/etc.), same-day-EOD bulk/block deals | Requires a browser-session cookie handshake (bare fetches blocked); documented 3 req/sec NSE-wide throttle; insider-trading and the new credit-rating SDD endpoints have NO library wrapper yet (open gap, needs devtools reverse-engineering); NSE ToS reportedly restricts automated scraping (flagged, not independently re-verified this pass) |
| **News feed** | The Hindu BusinessLine RSS (+ Economic Times Markets RSS as a second firehose) | Sub-hourly, robots.txt-clean, reliably reachable general financial news | No native ticker tagging — requires a custom NER/company-name→NSE-symbol matcher, validated against real headlines (Rule F) before trusting; BusinessLine blocks AI-crawler UAs by name in robots.txt — use a neutral UA |
| **Sentiment engine** | `ProsusAI/finbert` (CPU-only torch build) | 3-class sentiment (pos/neg/neutral) on financial headlines, 91-93% F1 on the one India-specific benchmark found (SEntFiN) | Heavy install (~1-2.5GB torch+transformers) — one-time cost, not per-request; not a materiality signal by itself, pair with the LLM layer (§4) for price-impact judgment, not tone alone |

**Optional but recommended fourth layer**: wire the existing free-tier LLM pool (docs 97/98) as a
**materiality-escalation layer on top of FinBERT** (§4.5's hybrid pattern) — FinBERT triages every
headline cheaply; only FinBERT's non-neutral calls escalate to an LLM for a materiality judgment,
using direct-classification (no CoT) prompts with a JSON schema separating `sentiment` from
`materiality`, batched 10-20 headlines/call, with majority-vote consistency checks on
high-materiality flags. This directly addresses the finding that lexical sentiment alone can be
benchmark-accurate but return-uncorrelated.

**Hard blockers to flag before build sign-off** (per Rule K — track as BACKLOG items, don't
silently skip):
1. NSE/BSE session-cookie handshake mechanics (shared dependency across §1's entire announcement
   stack) — needs its own implementation/verification pass.
2. Insider-trading and credit-rating-SDD endpoint discovery — currently no free library wraps
   either; requires live devtools inspection against `nseindia.com`.
3. Ticker/company-name matching layer for RSS-sourced news (§2) — a real NLP/NER engineering task,
   not a data-sourcing one; needs its own Rule-F verification against real headlines.
4. Marketaux's actual NSE/BSE depth — unverified without a live paid-tier key test; pilot before
   committing budget.
5. ToS restrictions flagged at multiple outlets (CNBC-TV18 explicitly bans AI-training use;
   NSE/BSE restrict "systematic automated data collection") — surfaced for a human decision per
   this project's personal-use, non-distributed framing; not silently worked around.

---

## Sources

Full per-claim citations are inline throughout §1-§4, each tagged with a credibility grade. Key
primary sources fetched directly this session include: `bennythadikaran.github.io/NseIndiaApi/
api.html` + `github.com/BennyThadikaran/NseIndiaApi` source; `sebi.gov.in/rss.html`;
`huggingface.co/ProsusAI/finbert` and `huggingface.co/yiyanghkust/finbert-tone` model cards;
`github.com/cjhutto/vaderSentiment`; `nosible.com/blog/news-sentiment-showdown-who-checks-vibes-
best`; `arxiv.org/abs/2304.07619` (Lopez-Lira &amp; Tang), `arxiv.org/abs/2506.04574` (CoT-hurts
finding), `arxiv.org/abs/2601.13082` (adversarial-headline attack); live RSS-feed fetches for
`thehindubusinessline.com`, `economictimes.indiatimes.com`, `livemint.com`, `cnbctv18.com`,
`zeebiz.com`, `moneycontrol.com` (confirmed dead); `marketaux.com` pricing/docs/FAQ pages.

## What this doc did NOT cover

- Deep multi-year historical news/announcement archives (already covered in
  `docs/research/61` §4).
- Corporate ACTIONS (dividend/split/bonus/rights) sourcing mechanics (already covered in
  `docs/research/57` and `75`).
- Free-tier LLM provider signup mechanics, base URLs, and per-provider rate-limit tables (already
  covered in `docs/research/97` and `98` — §4 here only researches the prompting/architecture
  layer on top of that existing infrastructure).
- CRISIL/ICRA/CARE paid-tier rating-feed pricing (out of scope — brief asked for free sources
  only).
- Live endpoint-discovery work for insider-trading (PIT) and the new credit-rating SDD mechanism
  — both need direct browser-devtools inspection against `nseindia.com`, out of scope for a
  research-only pass; flagged as BACKLOG-worthy follow-ups per Rule K.
