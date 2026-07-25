# Research/54 — Sourcing Historical Intraday Microstructure Data for NSE Replay

**Rule I acquisition research (Rule D: saved to file).** Skill used: `deep-research`
(multi-angle sweep + source triangulation + credibility grading). Companion to
`53_market_open_simulation_idea_map.md` — this pass answers §53's caveat #3 and §6:
*where can we legitimately source NSE tick + L2/L3 depth + intraday options/participant
data* to drive the 24/7 market-open simulation.

**As-of date: 2026-07-24.** Volatile facts (prices, retention windows, API features)
are dated inline; re-verify before relying on any single figure.

---

## 0. Bottom line (the direct answer)

For a **personal, non-distributed** project the realistic acquisition strategy is a
**hybrid**, tier by tier:

- **Faithful deep-tick history (all option strikes, back years):** the ONLY legitimate
  bulk source is **NSE's own Historical Data Dissemination** (NSE Data & Analytics /
  ex-DOTEX) — a research-licensed archive of *every trade* + periodic *limit-order-book
  snapshots* for CM (since 1995) and F&O (since 2003). Quote-priced; pursue by email.
- **Near-tick history, cheap & now, incl. options with OI:** **ICICI Direct Breeze API**
  serves **1-second historical candles** (cash confirmed; options via the same v2
  endpoint) — the single best price/effort retail source and we already plan to hold an
  ICICI data adapter.
- **Deep order-book depth (20–200 level):** **no vendor sells it historically for NSE.**
  It exists only **live** — record it ourselves from **Dhan (20/200-level)**, **Fyers
  (50-level)**, **Upstox (30-level)**, or **Kite (5-level)** through our own broker feed.
- **True L3/MBO (order-by-order):** exists only as NSE's **co-location TBT multicast** —
  **not obtainable by a personal user. Hard blocker.** The closest legitimate substitute
  is NSE's historical LOB *snapshots* (order-level rows at discrete times) — near-L3, not
  a continuous event stream.
- **Intraday participant/FII-DII flow:** **EOD-only, permanently.** NSE never discloses it
  intraday. Free daily CSVs; intraday is a **hard blocker (regulatory non-existence, not a
  sourcing gap).**

The 24/7 sim should therefore be built **fidelity-laddered**: start on data we can get now
(broker candles + our own recorded live depth + ICICI 1-second), and raise fidelity as the
NSE research archive is licensed.

---

## 1. Source-credibility note

Grades used throughout: **A** = primary/official (NSE specs, broker API docs read
verbatim, SEBI circulars) · **B** = reputable secondary (authorised vendor pages, major
outlets, well-known OSS, expert commentary) · **C** = forum/blog/unverified (leads only,
never sole support). Every important claim below was triangulated across ≥2 independent
sources where possible; single-source claims are flagged. `nseindia.com` frequently
returns HTTP 403 to automated fetches, so several NSE facts were confirmed via archived
PDFs (`archives.nseindia.com`) + independent corroboration rather than the live site.

---

## 2. TIER 1 — Full tick / time-and-sales (every trade print)

The recurring trap: almost every Indian vendor advertises "tick data" but *stores* only
1-minute bars (or a rolling 2–5 day tick window). True deep every-print archives come from
very few places.

### 2.1 NSE Historical Data Dissemination — the only official every-trade archive · Grade A
NSE Data & Analytics Ltd (formerly DotEx International) runs a formal historical-data
program. Proof is NSE's own specs:
- **Capital Market:** <https://archives.nseindia.com/content/press/Data_details_CM.pdf> —
  coverage "from late 1995 onwards", six directories incl. **Trades** ("a database of every
  single trade") and **Snapshots** ("snapshots of the limit order book at many time points").
- **F&O:** <https://archives.nseindia.com/content/press/Data_Details_F_n_O.pdf> — starts
  `200301` (Jan 2003), same **Trades** + **Snapshots** structure; gzipped, pipe-delimited,
  16 fields incl. Symbol / Instrument (FUTSTK/OPTIDX…) / Expiry / Option Type (CE/PE) /
  Strike → **full options coverage, all strikes/expiries**.
- Access: NSE Data & Analytics, `marketdata@nse.co.in`, +91-22-2659-8385; landing
  <https://www.nseindia.com/static/nse-data-and-analytics/data-information-vending>. Paid
  EOD/historical page <https://www.nseindia.com/static/market-data/eod-historical-data-subscription>.
- **GAP:** current INR pricing is **not published** — quote-based, historically requires a
  written request/licence, with **lower researcher/student rates** (forum-level, Grade C).
  This is the single most valuable item to pursue directly.

### 2.2 ICICI Direct Breeze API — 1-second historical, cheap, options + OI · Grade A/B
`get_historical_data_v2(interval="1second", …)` returns **1-second** historical candles;
ICICI's own FAQ confirms "users can easily fetch 1sec, 1min data for historical backtesting"
(<https://www.icicidirect.com/faqs/fno/does-breeze-api-allows-fetching-of-1sec-data>). Cash
is documented; **options second-level** history is demonstrated by the OSS package
`madmay247/breeze-historical-options` (<https://github.com/madmay247/breeze-historical-options>,
PyPI `breeze-historical-options`) which fetches NIFTY/BANKNIFTY/etc. option strikes at
second granularity, and Breeze historical uniquely includes an **Open Interest** column.
1-second bars ≈ near-tick fidelity. **This is the best price/effort retail source for
near-tick history and it aligns with our planned ICICI data adapter.** GAPs: how far back
the 1-second archive extends and per-request size limits are undocumented (contact ICICI);
known intermittent empty-response bugs on the 1-second endpoint (GitHub issues #114/#116).

### 2.3 TickData.com — deep tick, CASH only · Grade A
<https://www.tickdata.com/equity-data/national-stock-exchange-of-india> — true
tick-by-tick **Level-I quotes (bid/ask+size)** AND **tick trades** for all NSE equities
**since 2-Jan-2012**, ms timestamps, corp-action adjusted, zipped CSV, leased licence,
price-on-request. Cleanest deep every-print CASH source — **no options/derivatives.**

### 2.4 LSEG / Refinitiv Tick History (RTH) · Grade B
<https://www.lseg.com/en/data-analytics/financial-data/pricing-and-market-data/equities-market-data/national-stock-exchange-india>
— enterprise tick-by-tick, NSE equities + derivatives, "history as early as 1994/1996",
REST API. Genuinely tick-level but enterprise-priced (~$5k–$25k+, negotiated) and
heavyweight → institutional-only. GAP: options depth/pricing unverified.

### 2.5 GDFL & TrueData — real-time tick, SHALLOW history · Grade A/B
Both NSE-authorised; excellent to **capture our own forward tick history**, poor as bulk
archives:
- **GDFL / GlobalDataFeeds** (<https://globaldatafeeds.in/>): real tick feed (cash, F&O,
  all option strikes). Retention: **tick ≈ 2 days, 1-min ≈ 60 days, EOD since 2010**.
  NimbleData ProPlus ≈ **₹3,199/mo** ex-tax (225 symbols/segment) — pricing via reseller
  <https://tradersgurukul.com/product/56717/> (main pricing pages 403 to fetch).
- **TrueData** (<https://www.truedata.in/price>): Velocity **₹1,439–₹2,796/mo**; Python API;
  retention **tick ≈ 5 days, 1–60-min ≈ 6 months, daily 10+ yrs**
  (<https://feedback.truedata.in/knowledge-base/article/historical-real-time-data-availability-through-market-data-api>).
  Deeper 1-min "IEOD" CSVs on request. Options covered.

### 2.6 Negative/weak · Grade B/C
FirstRate Data, Polygon.io, Databento — broad but **no NSE coverage** (US/global). Kaggle
NSE sets are 1-min/OHLC-OI, not every-print (Grade C). No public **LOBSTER-equivalent**
message-level NSE dataset exists (academic gap).

---

## 3. TIER 2 — Order-book depth (L2 5-level / 20-level, and L3/MBO)

### 3.1 What "depth" exists at NSE · Grade A/B
NSE disseminates: L1 (best bid/ask), **L2 = 5-level MBP**, **L3 = 20-level MBP**, and the
co-location **TBT (tick-by-tick) order-level** feed
(<https://www.nseindia.com/static/market-data/real-time-data-subscription>; explainer
<https://www.truedata.in/blog/levels-real-time-data-nse-bse-mcx>).

### 3.2 TBT is true MBO/L3 — but co-location-gated · Grade A
NSE's own protocol docs ("MTBT_CM_NNF_PROTOCOL 6.0",
<https://archives.nseindia.com/technology/content/nnf/MTBT_CM_NNF_PROTOCOL_6.0.pdf>)
describe a multicast stream of *every order add/modify/cancel* — genuine order-by-order.
**Access requires:** trading-member or exchange-empanelled-vendor status, a co-location
rack inside NSE, a DOTEX licence, and a leased line from an NSE POP
(<https://www.nseindia.com/static/market-data/nse-data-policy>). **NOT obtainable by a
retail/personal user — hard blocker.** (Historical context: the TBT feed was the subject
of the SEBI co-location scam, which is why access is now tightly governed —
<https://en.wikipedia.org/wiki/NSE_co-location_scam>.)

### 3.3 Broker depth APIs — LIVE only, record-it-yourself · Grade A
| Broker | Live depth | Notes |
|---|---|---|
| **Dhan (DhanHQ v2)** | **20-level** (`wss://depth-api-feed.dhan.co/twentydepth`, 50 instr/conn) + **200-level** (1 instr/conn), NSE EQ+F&O | Launched 14-Jan-2025. Deepest retail feed. **Depth packets reportedly lack timestamps** (replay-fidelity risk). No historical depth. <https://dhanhq.co/docs/v2/full-market-depth/> |
| **Fyers** | **50-level TBT depth** (15-symbol sub cap), 2025 | <https://www.marketcalls.in/fintech/unveiling-fyers-50-market-depth-the-next-level-of-market-transparency.html> |
| **Upstox** | **30-level** (V3 protobuf ws, ~Nov 2024) + 5-level | <https://upstox.com/developer/api-documentation/v3/get-market-data-feed/> |
| **Kite (Zerodha)** | **5-level** (`MODE_FULL`) | <https://kite.trade/docs/connect/v3/websocket/> |
| **Groww** | depth in market-data payload (buy/sell px+qty) | <https://groww.in/trade-api/docs/curl/live-data> |
| **Finvasia Shoonya** | 5-level | free API |

**All live-only. No broker sells historical depth.** Recording our own broker feed is the
only route to a depth history.

### 3.4 Vendors selling historical depth — essentially none · Grade B
GDFL is authorised only as an **L1** vendor; its "snapshots" are single best bid/ask, not
multi-level. TrueData explicitly says L3/TBT "carry prohibitive exchange costs" and does
not sell historical NSE depth. **No mainstream vendor sells historical NSE order-book
depth.**

### 3.5 The near-L3 legitimate historical route: NSE LOB Snapshots · Grade A
NSE's CM Historical Dissemination (§2.1) **Snapshots** directory is order-level: each record
is one individual limit order with 14 fields — Order ID, symbol, series, qty, price,
timestamp, buy/sell, day-flags (day/GTD/**cancel**/IOC), qty-flags (min-fill/AON/disclosed),
price-flags (ATO/market/SL), book type (RL/SL), min-fill, disclosed, GTD date. This is
effectively **order-level (near-L3)** data — but **discrete snapshots (a few times/day) +
a full trades log, NOT a continuous inter-snapshot event stream.** Between snapshots you
cannot reconstruct every transient order. Reconstructable with `lebedov/nseindia_lob`
(<https://github.com/lebedov/nseindia_lob>, but Python-2/unmaintained since ~2013).

---

## 4. TIER 3 — Intraday options chain + participant/flow

### 4.1 Intraday options chain (per-strike LTP/IV/greeks/OI) · Grade A/B
- **NSE itself does NOT sell/publish historical option-chain snapshots** — the option-chain
  page is live-only (recomputes each load). NSE sells **F&O bhavcopy** (daily EOD OHLC +
  settlement + per-contract OI) and the raw historical **Trades** dump (§2.1) from which a
  chain could be reconstructed. Intraday chain history is a **third-party problem.**
- **TrueData** — best retail source: **historical expired-options 1-min OHLC+OI back to
  Feb-2020** via Market Data API (`truedata` PyPI). Live stream includes IV+greeks, but
  *historical* greeks are self-computed (compute from price+strike+expiry).
  <https://www.truedata.in/products/marketdataapi>. Grade B.
- **GDFL** — options history only **≈ 1 month** (KB). Not deep. Grade B.
- **ICICI Breeze** — 1-second/1-min historical **with OI column** for options (§2.2) —
  strong, cheap, includes derivatives. Grade A/B.
- **Backtest platforms (UI-locked, no bulk export):** AlgoTest (~7 yrs, 1-min, NIFTY/
  BANKNIFTY + 500 stocks, ₹499/mo — <https://algotest.in/blog/free-options-backtesting/>),
  Opstra/Definedge (EOD since ~2014; intraday sim 5-min min), StockMock, GoCharting. Good
  for validation, **not a data feed.** Grade B.
- **niftytrader.in premium** — intraday chain snapshots at **9:30/11:30/13:30/15:00** (4/day,
  not 1-min) + CSV export. Grade B.
- **Stolo** (<https://stolo.in/>) — claims complete minute-by-minute expired-chain history;
  unverifiable (bot-blocked). Grade C — confirm directly.
- **Free (Kaggle/GitHub)** — mostly index/underlying 1-min; per-strike OI coverage spotty,
  NIFTY/BANKNIFTY-centric, not full universe. Grade C.

### 4.2 Participant / flow data — EOD-ONLY · Grade A
- **Participant-wise Open Interest** (FII/DII/Pro/Client × index-fut/stock-fut/index-call/
  index-put/stock-call/stock-put, L/S): **daily EOD** CSV,
  `https://archives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv`; sibling
  volumes `fao_participant_vol_DDMMYYYY.csv`. Landing
  <https://www.nseindia.com/all-reports-derivatives>. Published ~17:00–18:00 IST.
- **FII/DII activity** (derivatives + cash provisional): daily EOD,
  <https://www.nseindia.com/reports/fii-dii>.
- **There is NO intraday participant-wise OI or FII/DII flow — NSE never discloses it
  intraday.** This is a **permanent blocker (regulatory non-existence, not sourcing).**
- Repackagers (same EOD data, cleaner history): Trendlyne, StockEdge, Sensibull, niftytrader.
- OSS scrapers (2026 status): **jugaad-data** best-maintained (caching to dodge blocking);
  **nsepython** maintained (has FII/DII helpers); **nsepy** largely stale/broken. The
  `archives.nseindia.com` static CSVs are far less bot-protected than `www.nseindia.com`
  JSON endpoints — fetchable with a browser-like User-Agent (but see Tier 6 ToS).

---

## 5. TIER 4 — Broker APIs we already have access to (historical granularity)

We plan swappable data adapters for Kite, Upstox, Angel SmartAPI, ICICI Breeze, Groww
(CLAUDE.md §Stack). What each exposes **historically** vs **live**:

| Broker | Historical candles (min interval / lookback) | Historical tick? | Historical depth? | Live depth | Grade |
|---|---|---|---|---|---|
| **ICICI Breeze** | **1-second** & 1-min, incl. options w/ OI | **1-sec ≈ near-tick** ✔ | ✗ | (via quotes) | A/B |
| **Kite Connect** | 1-min (60-day/req, ~3 yrs total; daily to 1990s) | ✗ candle-only | ✗ | 5-level (live) | A |
| **Upstox** | 1-min intraday + historical candles | ✗ | ✗ | 30-level (live) | B |
| **Angel SmartAPI** | 1-min `getCandleData` (~5s delay) | ✗ | ✗ | ws quotes | B |
| **Groww** | 1-min OHLC+vol+OI, **since 2020, up to 3-month window** | ✗ | ✗ | depth payload (live) | B |
| **Dhan** | candles (intraday ~5-day / 90-day poll; daily long) | ✗ | ✗ | **20/200-level (live)** | A |
| **Fyers** | OHLCV candles | ✗ | ✗ | **50-level (live)** | A/B |

Sources: Kite <https://kite.trade/docs/connect/v3/historical/> (1-min=60d/req, 2-min=60d,
3–5min=100d, 10–15min=200d, 60min=400d, daily=2000d; 1-min archived ~3 yrs);
ICICI Breeze <https://www.icicidirect.com/faqs/fno/does-breeze-api-allows-fetching-of-1sec-data>;
Groww <https://groww.in/trade-api/docs/curl/historical-data> & `/backtesting`;
Angel <https://smartapi.angelbroking.com/topic/4905/>; Dhan
<https://docs.dhanhq.co/api/v2/historical-data/get-daily-historical>.

**Verdict for Tier 4:** Broker *historical* APIs top out at **1-minute** — **except ICICI
Breeze's 1-second**, the one exception and our best cheap near-tick backfill. For anything
finer than 1-min or any **depth**, **recording the live websocket ourselves is the only
path** — which the §53 router seam is already positioned to do (record live → replay).
Best recording targets: **Dhan (20/200-level)** and **Fyers (50-level)** for deep book;
**Kite** for 5-level alongside execution.

---

## 6. TIER 5 — Third-party vendors + OSS tools (consolidated)

**Vendor comparison** (NSE coverage / granularity / cost / API):

| Vendor | NSE tick? | NSE depth history? | Options | Cost | Grade |
|---|---|---|---|---|---|
| NSE Data & Analytics (DOTEX) | **✔ every-trade (1995/2003+)** | **✔ LOB snapshots (discrete)** | ✔ all strikes | quote (research rates) | A |
| TickData.com | ✔ cash BBO+trades (2012+) | ✗ (no L2) | ✗ | leased, quote | A |
| LSEG/Refinitiv RTH | ✔ eq+deriv | L1/L2/L3 MBP feed | ✔ | enterprise $$$ | B |
| TrueData | tick 5-day retention | ✗ | ✔ 1-min since 2020 | ₹1.4k–2.8k/mo | A/B |
| GDFL | tick 2-day retention | ✗ (L1 only) | ✔ ~1mo history | ~₹3.2k/mo | A/B |
| AlgoTest | ✗ (backtest UI only) | ✗ | ✔ 1-min ~7yr (no export) | ₹499+/mo | C (not a feed) |
| Kaggle/GitHub free | ✗ (1-min bars) | ✗ | partial | free | C |
| FirstRate/Polygon/Databento | ✗ **no NSE** | ✗ | — | — | C |

**OSS tools** (maintenance as of 2026):
- **OpenAlgo** (<https://github.com/marketcalls/openalgo>) — actively maintained, 34 broker
  plugins, unified API incl. **Level-5 depth** + historical; strongest base for a live NSE
  recorder wired to a real broker session. Grade A.
- **pykiteconnect** (`KiteTicker`) — official, exposes 5-level full-mode depth; write our own
  persistence. Grade A building block.
- **marketcalls/dhan-20depth** (<https://github.com/marketcalls/dhan-20depth>) — records/
  decodes Dhan's live 20-level feed. Grade B ready-made recorder.
- **lebedov/nseindia_lob** — NSE-specific LOB reconstruction from order-level add/cancel/
  modify CSVs (matches §2.1 snapshots) but **Python-2, unmaintained**. Grade B (adapt).
- Generic LOB engines to replay from depth diffs: `mansoor-mamnoon/limit-order-book`,
  the `limit-order-book` GitHub topic, `orderbooktools/crobat` (records L2 diffs). Grade B.
- **jugaad-data / nsepython / nselib** — EOD/bhavcopy/participant-report scraping only, **no
  intraday tick/depth**. Grade B (right for Tier 3 participant CSVs, wrong for microstructure).
- **No maintained off-the-shelf NSE depth-recorder exists** — the glue (broker ws → timestamped
  writer → LOB replay engine) is ours to assemble.

---

## 7. TIER 6 — Legal / ToS / redistribution (personal, non-distributed use)

License/copyleft is **not** our blocker (Rule E). The real surface is **(a) NSE website ToS
(anti-scraping)** and **(b) broker-API redistribution bans**. SEBI's real-time-data rules
bind the *exchanges/intermediaries who share* data, **not** a retail end-user consuming
their own feed.

**Lines we must NOT cross:**
1. **No automated scraping/crawling of `nseindia.com`** (option-chain JSON, live quotes,
   participant-OI endpoints, cookie/anti-bot evasion). NSE ToS
   (<https://www.nseindia.com/static/nse-terms-of-use>) explicitly bans "systematic or
   automated data collection (scraping, data mining, extraction, harvesting)". Manual/light
   download of the **published files** NSE deliberately puts out (bhavcopy, EOD archives,
   the `archives.nseindia.com` participant CSVs) = personal-use GREEN; a high-frequency
   crawler across 2,000+ symbols = RED. **Line: download the published file, don't build a
   scraper against the live site.** Grade A.
2. **No redistribution/public display of NSE real-time data** to anyone → triggers a paid
   NSE Data & Analytics (DOTEX) data-vend licence (~₹20L/yr, Grade C figure). Personal
   consumption of downloaded/free data = GREEN; rebroadcast/public display = RED. Grade B.
3. **No sharing broker-API data with any other person/account.** Kite terms
   (<https://kite.trade/terms/>) bar creating permanent/cached copies **"with intent of
   redistributing"** and public display — but **expressly permit** an individual building
   "a private interface exclusively for customising personal trading". → **Recording our own
   ticks/depth to our own disk for personal replay = permitted (YELLOW-GREEN)**, as long as
   it never leaves our machine/account and isn't displayed publicly. Assume the same for
   Dhan/Angel/Upstox (formal clauses not all locatable; industry norm = account-holder use
   only, no redistribution). Grade A (Kite) / C (others).
4. **No offering real-time-data-driven virtual-trading/gaming/simulation to third parties**
   — SEBI May-2024 + NSE Apr-2023 circulars bar exchanges/intermediaries from *sharing* live
   data; they killed third-party virtual-trading apps. A personal, non-distributed
   backtester on our own feed is **not** the regulated actor (GREEN for personal / RED if
   shared). Grade A. (<https://trilegal.com/knowledge_repository/trilegal-update-sebis-bar-on-sharing-live-stock-market-data-implications-for-virtual-trading-apps/>)

**Net:** our design (own broker feed + own account + record to own disk + private replay,
never shared/displayed) sits in the GREEN/YELLOW zone. The one behavioural rule to enforce
in code: **prefer official broker APIs and NSE's published file archives; do NOT build a
scraper hammering the live `nseindia.com` JSON endpoints.**

---

## 8. Gaps & hard blockers (record against the §53 feature)

| # | Blocker | Severity | Mitigation / substitute |
|---|---|---|---|
| B1 | **True L3/MBO (order-by-order) live feed** — co-location TBT only; not for personal users | **Hard, permanent** | Use NSE historical LOB *snapshots* (near-L3, discrete) + reconstruct; or record broker 20/200-level depth as the practical ceiling |
| B2 | **Continuous historical MBO event stream** — not sold to anyone as retail | **Hard** | NSE snapshots + trades log = discrete approximation only |
| B3 | **Historical order-book DEPTH from any vendor** — does not exist for NSE | **Hard (sourcing)** | **Record our own live depth** (Dhan 20/200, Fyers 50, Upstox 30, Kite 5) going forward |
| B4 | **Intraday participant-wise OI / FII-DII flow** — NSE discloses EOD only | **Hard, permanent (regulatory)** | Use EOD CSVs as a daily context feature; do not promise intraday flow |
| B5 | **NSE Data & Analytics historical-archive INR pricing & individual eligibility** | **Open (verify)** | Email `marketdata@nse.co.in`; ask for researcher rate + individual licence terms |
| B6 | **ICICI Breeze 1-second archive depth (how far back) & request limits** | **Open (verify)** | Contact ICICI; empirically probe the v2 endpoint |
| B7 | **Dhan 20/200-level depth packets reportedly lack timestamps** | **Medium** | Stamp on receipt at recorder; validate clock; prefer a timestamped feed if fidelity-critical |
| B8 | **No maintained off-the-shelf NSE depth recorder/replayer** | **Medium (build)** | Assemble: OpenAlgo/broker SDK → our timestamped writer → generic LOB replay engine |
| B9 | **Pre-2020 intraday options history** outside NSE archive | **Medium** | NSE F&O Trades dissemination (2003+) is the only deep route; reconstruct chain |

All B-items must be logged in `docs/BACKLOG.md` under the §53 simulation feature and as
tracked tasks (Rule K) when that feature is scheduled.

---

## 9. Ranked acquisition plan (the recommendation)

**Design principle:** fidelity-laddered — deliver 24/7 replay on data we can get NOW, raise
fidelity as licensed sources arrive. This matches §53's "BASE on data we already have, raise
fidelity as the research pass proves what we can source."

**Rank 1 — NOW, ~free, on data we already reach (BASE tier):**
- **Record our own live broker feed** through the §53 router seam: **Kite 5-level depth +
  ticks** (we hold Kite for execution) and, for deeper book, **Dhan 20/200-level** and/or
  **Fyers 50-level** as dedicated data adapters. Persist timestamped snapshots to disk →
  replay. (ToS-clean: own account, private use.)
- **ICICI Breeze 1-second historical** candles (cash + options w/ OI) as immediate near-tick
  *backfill* for past days — the cheapest deep-ish history, and we already plan an ICICI
  adapter.
- **Free EOD context:** bhavcopy + participant-OI + FII/DII CSVs from `archives.nseindia.com`
  (download published files, no live-site scraping) as daily regime/flow features.

**Rank 2 — cheap paid, fills 1-min options + forward tick capture (ADVANCED backfill):**
- **TrueData** (₹1.4k–2.8k/mo): historical 1-min options OHLC+OI since 2020 across the
  universe, + real-time tick to grow our own archive. Alternatively **GDFL** (~₹3.2k/mo).

**Rank 3 — the deep, official, faithful-fidelity source (fidelity ceiling for replay):**
- **License NSE Data & Analytics Historical Dissemination** — every-trade (CM 1995+, F&O
  2003+, all strikes) + LOB **snapshots** (near-L3). This is the *only* legitimate route to
  faithful deep tick + order-level history for the full universe. Action: email
  `marketdata@nse.co.in`, request researcher/individual pricing (B5). This is what upgrades
  the sim from "broker-candle + recorded-depth" fidelity to true microstructure.

**Rank 4 — deep global tick, only if budget allows / cash-only need:**
- **TickData.com** (NSE cash BBO+trades since 2012) or **LSEG RTH** (eq+deriv, enterprise
  $$$). Optional; NSE's own archive dominates on coverage for our universe.

**Do NOT pursue:** co-location TBT/L3 (B1 — impossible for us), any "intraday participant
flow" (B4 — doesn't exist), FirstRate/Polygon/Databento (no NSE), AlgoTest-as-a-feed (UI
only), scraping `nseindia.com` live JSON (ToS red line).

**Fidelity map — what each tier realistically gets us:**

| Fidelity tier | Realistic source | Cost | Status |
|---|---|---|---|
| Tick / time-and-sales | NSE archive (deep) · ICICI Breeze 1-sec (now) · record live | quote / ~free | Achievable |
| L2 5-level depth | Record Kite live | ~free | Achievable (forward only) |
| L2 20–200-level depth | Record Dhan/Fyers/Upstox live | ~free | Achievable (forward only; B7 timestamp caveat) |
| Near-L3 order-level (historical) | NSE LOB snapshots | quote | Achievable (discrete, not continuous) |
| True L3/MBO continuous | co-location TBT | — | **Blocked (B1/B2)** |
| Options surface (IV/greeks/OI intraday) | TrueData 1-min + ICICI 1-sec + self-computed greeks | ₹1.4k+/mo | Achievable |
| Participant/FII-DII flow | NSE EOD CSVs | free | Achievable **EOD-only (B4)** |

---

## 10. What this pass did NOT cover
- Exact NSE Data & Analytics INR pricing / individual-eligibility (B5 — needs direct email).
- BSE/MCX equivalents (out of Phase-1 scope per CLAUDE.md).
- Stolo's true depth/pricing (bot-blocked; verify directly).
- Binding contract text behind broker signup wizards (only public docs read).
- Empirical probing of the ICICI Breeze 1-second archive's real lookback (B6).
- The build design of the recorder/replayer itself (that is a `sourcing-oss-parts` /
  `building-features-from-ideas` follow-up, not this sourcing pass).

*Stopping condition: loop-until-dry across six modalities (definition, vendor-by-name,
practitioner forums, official/primary, failure-mode, recency) — a full additional pass
surfaced only confirmations, no new legitimate sources.*
