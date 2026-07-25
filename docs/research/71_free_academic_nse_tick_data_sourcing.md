# Research/71 — Is NSE Tick / Trade-by-Trade History Free Anywhere? (Free/Academic/Public Sweep)

**Rule I acquisition research (Rule D: saved to file).** Skill used: `deep-research`
(4-angle parallel sweep + source triangulation + credibility grading). Narrower,
sharper follow-up to `54_nse_microstructure_data_sourcing.md` (2026-07-24), which
already established NSE Data & Analytics (₹22k–31.3L/yr, per `59`) as the only deep
official archive. **This pass asks one question only: is there a genuinely FREE,
free-tier, academic, or public route to NSE tick/trade-by-trade history — and if so,
who can actually use it?**

**As-of date: 2026-07-25.** Four independent search angles run in parallel
(academic/university, Kaggle/GitHub/HuggingFace, NSE-free-archives + forums,
free-tier vendors). Every source below was WebFetched and read, not cited from a
search snippet, unless explicitly marked "snippet-only" (fetch blocked/timed out).

---

## 0. Bottom line (the direct answer)

**No. Real NSE tick-level or trade-by-trade historical data is not genuinely free
for an individual/personal user through any legitimate channel found.** Every free
or free-tier tick offering that exists is gated to a population a personal project
does not belong to (enrolled campus researchers, Foreign Portfolio Investors) or
explicitly excludes tick data from its free layer (the new SEBI/NSE academic
data-sharing policy). The only thing that is truly free and unrestricted is
**recording your own tick stream going forward** from a free broker websocket —
which is free and genuine tick, but starts accumulating history only from the day
you turn it on; it cannot backfill the past. For backfill, paid remains
unavoidable — this confirms rather than overturns `54`'s conclusion, and adds the
academic/free-tier detail `54` only sketched.

---

## 1. Ranked list (most free-coverage first)

| Rank | Source | What's free | Who can actually get it | Tick/trade granularity | Legitimacy |
|---|---|---|---|---|---|
| 1 | **Record your own live tick via a free broker websocket** (Fyers, Upstox, Angel One SmartAPI, Zerodha Kite Ticker) | Unlimited, free with any trading account, forward-only | Any individual with a demat account | **True tick** (every quote/trade update) | Grade A — your own account, personal use, ToS-clean |
| 2 | **SEBI "Policy for Sharing Data for Research/Analysis" (20-Dec-2024) + NSE Data Usage & Sharing Policy (Oct-2024)** | Up to 2 GB/researcher/year, free, for *accredited academic institutions* — but only the "first basket" (OHLC, index, volumes, margins — **aggregate, not tick**) | Faculty/researchers at SEBI-accredited institutions who file a Data Seeking Request Form | **None** — tick-by-tick order/trade data is explicitly placed in the *restricted* "second basket", not the free researcher tier | Grade B (real, current, legitimate — but doesn't answer the tick question) |
| 3 | **IIM Ahmedabad Vikram Sarabhai Library — NSE historical tick-by-tick licence** (CM Jan-1999–present, F&O Jan-2000–present, order-book 2019–2020) | Free to the IIMA campus community only (no fee to the student/faculty who uses it) | IIMA students/faculty/staff only — no alumni, guest, or paid-outsider tier found | **True tick + order-book** | Grade A legitimacy, Grade C accessibility (closed campus) |
| 4 | **NSE's own free 6-month tick-by-tick trial** (NSE Data & Analytics "Data Usage and Sharing Policy") | Free, up to 6 months of historical tick-by-tick order + trade data | **Prospective/new Foreign Portfolio Investors (FPIs) only** — an institutional onboarding incentive, not open to retail/individuals | **True tick + trade** | Grade B (real per NSE's own policy doc, but gated to a category a personal project can't join) |
| 5 | **`lebedov/nseindia_lob`** (GitHub) — LOB-reconstruction code | Free, open-source | Anyone, but it only *parses* NSE's own paid historical snapshot files — you must already own those | Order-level (near-L3) *if* fed NSE's paid snapshots | Grade B (legitimate tool, not itself a data source); Python-2, unmaintained since ~2013 |
| 6 | **GDFL / TrueData free trials** | 2–10 day live-feed trial to evaluate the API | Anyone who signs up | True tick, but **time-boxed live-only** — nothing is retained/downloadable after the trial ends, and even paid retention is only 2–5 days | Grade A/B (legitimate vendors) but functionally not a "free dataset" |
| 7 | **Kaggle "NSE tick data" / GitHub tick-named repos / HuggingFace "NIFTY" datasets** | Free download | Anyone | **None verified** — every one opened turned out to be 1-min/5-min/daily bars mislabeled "tick," or an unrelated dataset (HF's "NIFTY" = an LLM dataset acronym, not the Indian index) | Grade C — not tick data at all; one (`Nifty50GPT-Final` DuckDB) has undisclosed data provenance and should not be trusted/recommended |
| 8 | **yfinance / nsepy / nsepython / Alpha Vantage / Google Finance / Investing.com** | Free | Anyone | **1-minute at finest** (yfinance intraday capped to last 7–60 days); nsepy/nsepython are EOD/bhavcopy scrapers with no tick capability at all | Grade B (legitimate tools) but confirmed non-tick |

---

## 2. Detail per angle

### 2.1 Academic/university (WRDS, IIMs, ISI, CMIE, SEBI/NSE research policy)
- **WRDS (Wharton)** — dead end. WRDS's own tick products (TAQ/ISSM) are US-only;
  no Refinitiv/LSEG Tick History (TRTH) module is offered on WRDS itself. Some
  universities (e.g. Yale, `guides.library.yale.edu/LSEG_Tick_History`) licence
  LSEG Tick History **directly through their own library**, bypassing WRDS — but
  no India/NSE coverage or non-affiliate access route was found. WRDS account
  eligibility (`wrds-www.wharton.upenn.edu/pages/about/wrds-account-types/`,
  checked 2026-07-25) is strictly faculty/PhD/Master's/staff/visitor at a
  *subscribing institution* — no guest, alumni, or paid independent tier exists.
- **IIM Ahmedabad** — `library.iima.ac.in/a-to-z-databases/N.html` (checked
  2026-07-25) confirms a genuine NSE historical tick-by-tick licence: CM from
  Jan-1999, F&O from Jan-2000, plus order-book data for 2019–2020 and CM/F&O
  trade data for 2022, delivered by DVD/download with a user guide, contact
  `database@iima.ac.in`. **Campus-authenticated only** — no external path found.
  IIMA also hosts the "NSE Centre for Behavioral Science in Finance, Economics
  and Marketing" and the Mattu Centre for Research in Security Pricing — research
  centres, not open data-grant programs.
- **ISB, ISI, NISM** — no NSE tick-data programme found (negative finding). NISM's
  NSE Academy partnership (a joint PG programme, Aug-2025) is training, not data
  access.
- **CMIE Prowess dx** (`cmie.com`, checked 2026-07-25) — covers NSE/BSE listed
  companies since 1990 but is **aggregate/EOD financial + market time-series,
  not tick or order-book data.** Dead end for this question.
- **SEBI circular (20-Dec-2024), "Policy for Sharing Data for Research or
  Analysis"** — per a third-party summary (taxguru.in, checked 2026-07-25; the
  primary PDF hosts on `nsdl.co.in`/`nsearchives.nseindia.com` and both timed out
  on direct fetch, so this is corroborated via independent secondary summaries,
  not a single primary read) — requires exchanges/depositories to give
  SEBI-accredited academic institutions free access up to **2 GB/researcher/year**
  via a "Data Seeking Request Form," beyond which cost-basis fees apply. Data is
  split into a free-to-researchers **"first basket"** (OHLC, index data, volumes,
  margins — aggregate) and a restricted **"second basket"** that explicitly names
  **"tick-by-tick order/trade data with client identities."** NSE's own
  corresponding "Data Usage and Data Sharing Policy" (Oct-2024) and a dated
  data-list PDF (28-Jul-2025) could not be directly fetched (`nsearchives.nseindia.com`
  timed out repeatedly) — contact point found via secondary sources is
  `nseri@nse.co.in`. **This is a real, current, legitimate government-mandated
  channel — but by SEBI's own categorisation it excludes tick data from the free
  researcher tier.** Grade B (real policy, doesn't solve the tick question).
- **Papers using NSE tick data** (arXiv "Order Book Filtration and Directional
  Signal Extraction at High Frequency" 2025; SSRN "Optimizing Order Types in
  Indian Futures Market") use NSE tick/LOB data but disclose no reusable public
  acquisition channel beyond implied commercial/institutional purchase —
  negative finding.

### 2.2 Kaggle / GitHub / HuggingFace
Nothing beyond the already-known `lebedov/nseindia_lob` (parsing code, not a data
source) qualifies as genuine tick/order-level data with clean provenance:
- **Kaggle**: every "NSE/Nifty tick data" listing opened (`debashis74017/nifty-50-minute-data`,
  `.../stock-market-data-nifty-50-stocks-1-min-data` — actually 5-min despite its
  title, `rohanrao/nifty50-stock-market-data`, `akshaypawar7/nse-daily-bhavcopy`)
  is 1-min/5-min/daily bars. `thehdk/banknifty-and-its-all-banks-tickdata` could
  not be opened (JS-rendered page) — unverified, treat with the same suspicion as
  every other similarly-titled dataset until manually confirmed.
- **GitHub**: `ShabbirHasan1/NSE-Data` mixes confirmed 1-min bars with an
  ambiguous "live tick data" folder sourced via the Alice Blue broker API — real
  granularity of that folder was not confirmed from the README; `rthennan/ZerodhaWebsocket`
  is a self-collection *tool*, not a dataset; `imanojkumar/NSE-India-All-Stocks-Tickers-Data`
  is daily OHLCV despite its name.
- **HuggingFace**: `raeidsaqur/NIFTY` is an unrelated LLM dataset (acronym
  collision, not the Indian index); `StudentOne/Nifty50GPT-Final` bundles a
  DuckDB of undisclosed-provenance daily data — flagged as **not to be
  recommended** (unclear whether legitimately sourced).
- **No repo found redistributes NSE's own paid tick/LOB data at scale** — the
  closest is `lebedov/nseindia_lob`, which is code to parse NSE's own
  (separately-purchased) historical snapshot files.

### 2.3 NSE's own free archives + retail community consensus
- NSE's own **"Data Usage and Sharing Policy"** document states NSE Data &
  Analytics provides free historical tick-by-tick order+trade data (**up to 6
  months**) as a trial — **explicitly restricted to Prospective/New Foreign
  Portfolio Investors**, not retail/individuals
  (`nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_DataUsageandSharingPolicy.pdf`,
  corroborated via two independent search-result extractions; direct fetch
  timed out twice — snippet-corroborated, not primary-read-confirmed).
- NSE's public paid-data pages (`nseindia.com/static/market-data/eod-historical-data-subscription`)
  describe only paid tick/order/trade subscriptions, quote-on-request via
  `marketdata@nse.co.in` — no general-public free tier.
- The **SEBI-mandated free TBT feed** that trading members receive is a
  **live, colocation-only real-time feed**, not a historical download —
  confirmed via a Zerodha co-founder's forum comment: "TBT data feed can't be
  streamed to clients, you have to be colocated to consume it," colocation
  running into lakhs/month
  (`tradingqna.com/t/free-tick-by-tick-data/36336`, read 2026-07-25). Easily
  confused with "free tick data" but is not retail-accessible at all.
- Zerodha TradingQnA threads confirm retail consensus: no free tick route exists;
  NSE's tick-vending licence is "extremely expensive" (~₹1,400/user/month plus
  colocation), NSE membership itself needs a ₹50L deposit
  (`tradingqna.com/t/how-do-i-get-tick-by-tick-data-directly-via-nse/55045`,
  `tradingqna.com/t/purchase-historical-tick-by-tick-rates-on-nse-f-o/122925`,
  both read 2026-07-25). No substantive Reddit threads on this topic were found.
- **Kite Connect Historical API confirmed still capped at 1-minute candles**
  (60-day/request, since 2015) — official docs and forum state tick history is
  not offered; "approach an exchange-authorised data vendor" is NSE's own
  standard answer (`kite.trade/docs/connect/v3/historical/`,
  `tradingqna.com/t/kite-api-historical-data-retreival-limit/177114`, read
  2026-07-25).
- **Key distinction confirmed across all brokers checked** (Zerodha, Upstox,
  Angel One, Dhan, Fyers, ICICI Direct, Groww, 5paisa): free/paid **live tick
  streaming** (lets you start recording from "now") is common and often free
  with an account; a free **downloadable historical tick archive for past
  dates** does not exist anywhere in this set.

### 2.4 Free-tier vendors — trial terms actually read
- **GDFL** (`globaldatafeeds.in/start-a-free-trial/`, fetch blocked HTTP 403,
  snippet-corroborated) — free trial exists but is a time-boxed live-feed
  evaluation; even paid tick retention is only ~2 days, so nothing is
  "kept" free. Paid ~₹3,199/mo.
- **TrueData** (`feedback.truedata.in/knowledge-base/article/getting-started-with-truedata-market-data-api`,
  fetched 2026-07-25) — explicit 10-day trial, extendable another 10 days; a
  live-API integration window, not a retained dataset. Paid ₹1,439–2,796/mo.
- **AlgoTest** (`docs.algotest.in/getting-started/pricing-breakdown/backtest-pricing/`)
  — free tier is "25 free backtests/week" on their UI, not bulk tick export.
- **Sensibull / Opstra / StockMock / GoCharting** — no free tick tier at any of
  the four (Opstra's backtester is EOD-only; Sensibull has no backtesting;
  StockMock has no free trial, only weekly-index backtests; GoCharting has no
  downloadable tick data at any tier).
- **Broker free/paid boundary** (all checked 2026-07-25): Zerodha Kite Connect
  ₹500/mo for any market data (free "Personal" tier excludes all market data);
  Fyers, Upstox, Angel One SmartAPI — trading + data APIs free with a demat
  account, live tick + OHLC candle history free, **no tick-level historical
  download** on any of them; Dhan — trading API free, live tick Data API
  ₹499+GST/mo, historical candles (1–60 min) free, no tick history; 5paisa —
  free APIs, 6-month-max candle history, no tick data.
- **Global free tools confirmed non-tick**: yfinance (1-min floor, 7–60 day
  intraday cap — `github.com/ranaroussi/yfinance` issues #1436/#219); nsepy/
  nsepython (EOD/bhavcopy scrapers, no intraday tick — `github.com/swapniljariwala/nsepy`,
  `pypi.org/project/nsepython`); Alpha Vantage (US-oriented, unreliable/delayed
  for NSE per `alphavantage.co/documentation`); Google Finance/Investing.com
  expose no programmatic intraday API at all.

---

## 3. Blunt verdict

**Real NSE tick / order-level historical data is not free for an individual,
anywhere, legitimately.** The only two places genuine historical tick exists for
free are gated by population, not by request: an IIMA campus licence (student/
faculty only, no outside tier) and NSE's own 6-month FPI onboarding trial
(foreign institutional investors only). The newest, most current free channel —
SEBI's Dec-2024 academic data-sharing mandate — is real and growing but
*by design* keeps tick-by-tick order/trade data out of the free researcher
basket; it only frees aggregate/EOD data. Every Kaggle/GitHub/HuggingFace listing
claiming "NSE tick data" that could be verified turned out to be minute/daily
bars or unrelated data; none should be relied on. Every vendor free trial
(GDFL, TrueData) is a live-only evaluation window with no retained history, and
every broker's free-tier historical API — even paid — tops out at 1-minute
candles.

**The one legitimately free thing that is real tick data**: recording your own
live broker websocket stream (Fyers/Upstox/Angel One/Kite) from today forward,
free, unlimited, genuine per-print tick — which is exactly what `54`'s Rank-1
recommendation already prescribes. It cannot retroactively produce history.
**For any backfill before "today," paid is unavoidable** — cheapest near-tick is
ICICI Breeze's 1-second candles, then TrueData/GDFL (~₹1.4k–3.2k/mo, shallow
retention), and the only deep, full-universe, multi-year, order-level archive
remains **NSE Data & Analytics** itself (₹22k–31.3L/yr, per `59`). This pass
does not change `54`'s acquisition plan — it closes out the "is there a free
door we missed" question with a documented **no**, so the plan can proceed on
the paid/self-recorded hybrid without revisiting this angle.

---

## 4. What this pass did NOT cover
- Primary-source read of the SEBI 20-Dec-2024 circular and NSE's Oct-2024 policy
  PDF (both hosts timed out repeatedly; findings rest on independent secondary
  summaries — re-verify directly if this channel is ever pursued for aggregate
  academic data).
- Whether becoming IIMA-affiliated (e.g. an executive-education short course) is
  a realistic/proportionate path to the campus licence — not evaluated, likely
  disproportionate for this project's needs.
- Manual (non-automated, browser) inspection of `thehdk/banknifty-and-its-all-banks-tickdata`
  on Kaggle and the ambiguous "live tick data" folder in `ShabbirHasan1/NSE-Data`
  — both were inaccessible to automated fetch; if either becomes relevant, open
  manually before trusting.
- Formal outreach to `nseri@nse.co.in` / `marketdata@nse.co.in` to ask directly
  whether an individual researcher (not an accredited institution) can access
  even the SEBI first-basket free tier — not attempted in this pass.

*Stopping condition: 4 parallel angles (academic/university, Kaggle/GitHub/
HuggingFace, NSE-free-archives + community forums, free-tier vendors) each ran
their own multi-query sweep and converged on the same negative finding — no
additional angle surfaced a new legitimate free tick source.*
