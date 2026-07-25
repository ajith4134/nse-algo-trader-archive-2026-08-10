# Research/59 — Deep-History PRICE + UNIVERSE Sourcing (NSE full-history replay)

**Rule I acquisition research (Rule D: saved to file).** Skill used: `deep-research`
(4 parallel multi-angle sweeps, one per numbered item below, WebFetch-verified against
primary NSE/SEBI/BSE documents and live endpoints, cross-triangulated). Companion to
`53_market_open_simulation_idea_map.md` §10 (full-history walk) and §11 (silent
corruptors), and to the already-done `54_nse_microstructure_data_sourcing.md` (tick/L2/L3/
options/participant data — not repeated here) and `55_replay_rl_lob_technique_and_oss_parts.md`
(replay engine + OSS parts — not repeated here). This pass answers the **remaining** four
acquisition targets §53 flagged: (1) exact NSE Data & Analytics licensing scope, (2)
survivorship-bias-free universe reconstruction, (3) the corporate-actions master, (4)
per-segment inception dates. A companion pass on point-in-time market rules/calendar/news
(§9.4/§11.3/§11.4) lives separately in `61_point_in_time_rules_calendar_and_news_sourcing.md`
(pre-existing, not redone here).

**As-of date: 2026-07-24.** All facts below are dated inline where volatile (pricing,
circular numbers); re-verify before build-time reliance. Detailed source-by-source findings
live in the companion files listed at the end of each section — this document is the
synthesized, cross-linked map.

**A note on file numbering:** four parallel sub-agents each wrote detailed findings
directly to `docs/research/` per this project's Rule D, and two independently picked
already-used numbers. This was resolved by renumbering the two orphaned/colliding files
(`56_nse_segment_inception_dates_verification.md` → `60_...`, and a pre-existing unrelated
`57_point_in_time_rules_calendar_and_news_sourcing.md` → `61_...`) rather than disturbing
the three files (`56_corporate_actions_vendors_ace_capitaline_trendlyne.md`,
`56_yfinance_nse_and_symbol_isin_merger_sourcing.md`, `57_corporate_actions_master_sourcing_
consolidated.md`, `58_point_in_time_universe_reconstruction_nse.md`) that are already
cross-linked from `docs/flowcharts/00_project_overview.md` and from each other. Content of
the renamed files is unchanged.

---

## 0. Bottom line

**None of the four items is a hard blocker for the core replay simulator.** Three are
fully or largely solved for free from NSE/BSE first-party endpoints (universe
reconstruction, corporate actions, inception dates); the fourth (deep licensed tick/L2
history from NSE Data & Analytics) is achievable but **costs real money and has a
non-trivial eligibility/pricing structure now concretely known** (previously it was an
unpriced "quote-based" unknown — that gap is closed). The one genuine, confirmed-hard
blocker across this whole pass is **ISIN-extinguishing merger/amalgamation swap-ratio
records** — a narrow subset of the universe (only companies that actually merged), not a
blocker to the overall feature.

| Item | Status | Cost | Confidence |
|---|---|---|---|
| 1. NSE Data & Analytics historical dissemination | **Achievable, priced** (₹22k–31.3L/yr depending on product/tier) | ₹ (see §1.4) | A (official tariff, read in full) |
| 2a. Listing/delisting master | **Achievable (free)**, one narrow sub-gap | Free | A, one B-item (delisted.xlsx unverified) |
| 2b. F&O-eligibility snapshots | **Fully solved (free)** | Free | A |
| 2c. Index-constituent history | **Fully solved (free)** | Free | A |
| 3. Corporate-actions master | **Achievable (free)**, one hard sub-blocker (mergers) | Free (mergers: paid/manual) | A |
| 4. Segment inception dates | **Fully verified** | N/A | A |

---

## 1. NSE Data & Analytics historical dissemination — exact scope

*(Full detail: this section's sub-agent reported inline, not to a separate file — findings
consolidated here in full since there is no companion doc for item 1.)*

### 1.1 Two distinct products exist (a correction to the prior §54 assumption)

NSE Data & Analytics (formerly DotEx) actually sells **two different historical
products**, not one, with materially different depth:

- **Product A — "Historical Trade Data" (legacy, trades + discrete order-book snapshots).**
  CM coverage **"from late 1995 onwards"**; F&O dissemination directory starts **`200301`
  (Jan 2003)** even though F&O trading itself began June 2000/2001 (§4 below) — so **~2.5
  years of early F&O history (2000–2002) exists as trading activity but is NOT in this
  dissemination archive.** Order-book snapshots (discrete, a handful of times/day — CM
  shows 11am/1pm/2pm in the spec, with an internal inconsistency also mentioning noon; F&O
  shows 5×/day: 11/12/1/2/3) ride alongside the trades data from the same start dates.
  Source: `archives.nseindia.com/content/press/Data_details_CM.pdf` and
  `Data_Details_F_n_O.pdf` (Grade A, read in full; independently mirrored at
  `library.iima.ac.in/public/resource/CM_FAO.pdf`, identical text).
- **Product B — "Historical Order & Trade Data" (current, full per-order tick data —
  order entry/cancel/modify, not just trades).** Per its own revision history (spec v1.18,
  dated 18 May 2026, `NSE_Hist_Order_Trade_Data_1.18_20260618155600.pdf`, Grade A, read in
  full): **v1.0 issued 24-Dec-2007 for CM and F&O.** Currency Derivatives added Aug-2008.
  Commodity Derivatives added Dec-2023. **This means true per-order tick data is only
  available from ~Dec 2007** — the 1995–2007 (CM) / 2003–2007 (F&O) window has ONLY the
  older trades-only + discrete-snapshot product (Product A).

**Options — all strikes confirmed for both products.** Both schemas carry `Strike Price`,
`Option Type` (CE/PE), `Expiry Date`, `Instrument` (OPTIDX/OPTSTK/FUTIDX/FUTSTK) as normal
per-record fields — every strike/expiry/underlying is a row, not an aggregate.

### 1.2 Earliest-date summary table

| Data type | Earliest date | Product/source |
|---|---|---|
| CM every-trade tick | late 1995 | Product A (Historical Trade Data) |
| F&O every-trade tick, all strikes | Jan 2003 (dissemination archive start; trading itself started 2000/2001, see §4) | Product A |
| CM/F&O discrete LOB snapshots (few×/day) | same as trades above (1995 CM / 2003 F&O) | Product A |
| CM/F&O **full per-order** tick (entry/cancel/modify) | **~24 Dec 2007** | Product B (Historical Order & Trade Data) |
| Currency Derivatives per-order tick | ~24 Aug 2008 | Product B |
| Commodity Derivatives per-order tick | ~15 Dec 2023 | Product B |

**Net for the §53 full-history replay:** true order-level microstructure only goes back to
~2007; 1995–2007 (cash) and 2003–2007 (F&O) replay is trades-only + discrete book
snapshots, not continuous order flow — this is a firm fidelity ceiling for the oldest
years, independent of budget.

### 1.3 File formats

- **Product A**: gzipped, mostly pipe-delimited. Bhavcopy 11 fields (CM)/16 (F&O). Trades:
  CM 6 fields, F&O 10 fields (adds Instrument/Expiry/Option Type/Strike). Snapshots: CM 14
  fields/record, F&O 18 fields, one file per snapshot time (`hhmmss.gz`), sorted by price.
  Masters: CM 5 fields (ISIN/Symbol/Series/Name/Deleted flag), F&O 12 fields.
- **Product B**: fixed-length records, `.DAT.gz`, delivered as **Trim** (lean) or **Full**
  (all fields) since 18-May-2026. CM Orders (Trim) = 10 fields/68 bytes incl. Transaction
  Time in **Jiffies** (1/65536 sec, epoch 1-Jan-1980). CM Trades (Trim) = 9 fields/82 bytes,
  linking both Buy and Sell order numbers per trade. FAO adds an `Instrument` field. Files
  split into multiple numbered per-day streams (FAO grew 6→18 streams 2020–2024 as volume
  rose). **Compliance-mandated delivery lag: trade data delayed 30 calendar days; order
  data delayed 90 calendar days** from the trade/order date — irrelevant for deep-history
  backfill, relevant if anyone hoped to use this feed for anything near-live.
- **Delivery mechanism**: SFTP (RSA key-pair, 3-day rolling retention) for daily files, a
  Windows-only Downloader Client (requires exact JDK 21.0.8) for bulk historical backfill,
  or AWS S3-to-S3 transfer (client provisions their own `ap-south-1` bucket; cross-region
  egress is the client's cost). Gzip-compressed, **not encrypted**.
- **Free samples exist right now, no login**: `.zip` samples (2.9–8.8MB) for CM/F&O/CD
  Order & Trade Data are downloadable directly from `eod-historical-data-subscription` —
  worth pulling to validate a parser before committing to any subscription.

### 1.4 Pricing — the previously-unpriced gap is now closed

NSE Data & Analytics publishes a full tariff card **effective 1 April 2026** (domestic and
international PDFs, `nsearchives.nseindia.com/web/mediaattachment/2026-04/Download_
Pricing_file_-_{Domestic,International}_clients_20260424*.pdf`, Grade A, read in full —
not previously found by the §54 pass, which correctly flagged pricing as unpublished at
the time).

| Product | Segment | Domestic commercial (₹/yr) | Domestic Student/Researcher (₹/yr) | International ($/yr) |
|---|---|---|---|---|
| Historical Trade Data (legacy) | CM | 1,10,000 | 22,000 (80% off) | 1,810 |
| Historical Trade Data | F&O | 1,10,000 | 22,000 | 1,810 |
| Historical Trade Data | WDM | 30,000 | 6,000 | 600 |
| Historical Order & Trade Data (full order book), single site | CM | 12,50,000 | 6,25,000 (50% off) | 20,000 |
| Historical Order & Trade Data, single site | F&O | 12,50,000 | 6,25,000 | 20,000 |
| Historical Order & Trade Data, single site | CD | 1,30,000 | 1,30,000 (no discount) | 2,000 |
| Historical Order & Trade Data, global/multi-site | CM/F&O | 31,30,000 | — | 50,000 |
| EOD data, per medium | CM/F&O | 1,00,000 | — | 5,500 |

Printed conditions: fees exclusive of taxes; buying the same data through a second vendor
is charged 50% of the applicable rate; each additional delivery channel costs +50% of the
product fee. **SEBI circulars dated 24-May-2024 and 29-Jan-2025** (cited directly on the
tariff sheet) restrict near-real-time data for educational use, forcing a data lag on the
discounted tier specifically.

**Critical eligibility caveat.** The "Student/Researcher" discount sits under the policy's
"Non-Commercial User" category (`NSE_DataUsageandSharingPolicy.pdf` §14(g)/(k)): research
is defined as activity "for purposes other than trading or profit." **A personal
algo-trading project that will actually trade is very likely NOT eligible for the
discounted tier** — the realistic commercial figures are ₹1,10,000/yr (CM, Product A
trades-only) up to ₹12,50,000/yr (CM, Product B full order data) domestically. NSE Data
retains audit/termination rights for tier misuse (policy §12.3).

**Domestic vs international**: clearly cheaper to register as a domestic Indian client —
e.g. Historical Order & Trade Data CM is ₹12,50,000/yr (~$14,400 at ~₹86.7/$1) domestically
vs $20,000/yr under the international tariff for the identical product.

**FPI free-trial provision** (policy §5) — up to 6 months of tick data free, extendable to
12 with written approval — applies only to **prospective foreign portfolio investors**
declaring they are not yet trading in India. Not applicable here.

### 1.5 Procurement path — concrete steps

1. **Self-service portal exists**: `https://dotexdata.nseindia.com/` — login → Activities →
   "Subscribe Data" → choose segment / subscription type (Daily/Monthly) / date range /
   Orders and/or Trades / payment / region (Mumbai) / delivery bucket. Not purely a
   quote-by-email process as previously assumed.
2. **Initial contact**: `marketdata@nse.co.in` / +91-22-2659-8385 (per the
   `eod-historical-data-subscription` landing page) — **but** the spec PDF's own Contact
   Information page (§9) lists a *different* address, `marketdata@nseids.co.in`, same
   phone. **Genuine disagreement between two current official NSE documents** — confirm
   which is live before relying on either.
3. **Required paperwork**: a "Historical Order & Trade Data Undertaking" (downloadable
   .doc) plus execution of a bilateral "Relevant Agreement" under the Data Usage Policy —
   not a self-checkout purchase. A "Customer Order Form Template.xlsx" is also downloadable.
4. **Delivery setup is engineering-heavy**: 25+ pages of the spec are a literal SFTP/AWS
   setup walkthrough (RSA key-pair via PuTTYgen/WinSCP, or the Windows Downloader Client,
   or an AWS S3 bucket the client provisions themselves).
5. **Whether an individual (not a registered entity) can even open an account through the
   portal is unconfirmed** — the policy's "Subscriber" definition is broad (Data Vendors,
   Research Entities/Analysts, Overseas Entities) but doesn't explicitly rule individuals
   in or out; untestable without an actual account. **Open item — email to confirm before
   assuming eligibility.**

### 1.6 Third-party resellers — cross-checked, none clearly cheaper or clearly official

- **TickData** (`tickdata.com/equity-data/national-stock-exchange-of-india`) — NSE cash
  tick-by-tick Level-I quotes+trades **since 2-Jan-2012 only** (far shorter than NSE's own
  archive). Leased license, unpriced publicly. Whether it's NSE's official archive or
  TickData's own captured feed is **unresolved** from the page text.
- **LSEG/Refinitiv Tick History** — claims coverage "as early as 1994" but the page does
  not state whether this is NSE's official archive or LSEG's independently-captured feed.
  **Unresolved.**
- Domestic vendors (TrueData, GlobalDatafeeds, broker feeds) are real-time redistribution
  licensees, not resellers of the deep historical archive.
- **No reseller was confirmed cheaper than going direct** at domestic rates; the
  domestic-vs-international pricing gap observed above (₹12.5L vs $20,000 for the same
  product) suggests direct-from-NSE, domestic-registered, dominates any reseller markup.

### 1.7 2025/2026 changes worth flagging

- The comprehensive public tariff card (§1.4) is new as of **1 April 2026** — did not exist
  in this form when `research/54` ran its pass.
- Trim/Full split for Historical Order & Trade Data launched **18 May 2026**.
- SEBI circulars (24-May-2024, 29-Jan-2025) confirmed real and dated, restricting
  near-real-time educational-tier data.
- Commodity Derivatives added to the order-data product only **Dec 2023**; its Trim
  version only **May 2026** — shallow history if ever relevant.
- CM record byte-lengths grew multiple times through 2025 as order-quantity fields
  outgrew their original size — **re-check the spec version before any integration
  build**, field layouts are not stable across years.

### 1.8 Open items (carry to BACKLOG)

1. Does the old discrete Snapshot product still exist as a sellable line item? Not listed
   separately in the April-2026 tariff — may have been superseded by the fact that the
   full order-data product lets you reconstruct the book yourself. Needs a direct email
   confirmation.
2. `marketdata@nse.co.in` vs `marketdata@nseids.co.in` — which is authoritative.
3. No individual/anecdotal real-world pricing datapoint found to cross-check the official
   tariff (WebSearch budget exhausted before this could be pursued) — the primary tariff
   PDF is strong evidence regardless.
4. Whether TickData/LSEG source from NSE's official archive or their own capture.
5. Whether an individual (not a registered business entity) can open a `dotexdata.nseindia.com`
   account at all.

---

## 2. Point-in-time UNIVERSE reconstruction (survivorship-bias-free)

**Full detail:** `58_point_in_time_universe_reconstruction_nse.md` (companion, referencing
`56_corporate_actions_vendors_ace_capitaline_trendlyne.md` and
`56_yfinance_nse_and_symbol_isin_merger_sourcing.md`). Summary below.

### 2a. Historical listing/delisting master

**Backbone (free, Grade A): NSE daily equity bhavcopy presence/absence**, coverage from
**Nov-1994 (NSE cash-segment launch)**, confirmed by multiple community tools
(`riyaz-ali/bhav-copy`, `tilak999/NSE-Data-bank`, `getbhavcopy.com`) that document Jan-1994
onward archives. A working precedent at scale exists:
`HaloHunter480/Survivorship-Bias-in-Emerging-Market-Small-Cap-Indices` (GitHub)
reconstructed NIFTY Smallcap 250 point-in-time membership for **2016–2025** from 2,459
daily bhavcopy files, explicitly including delisted names "unlike commercial databases."

**Symbol/ISIN renames — SOLVED**: `archives.nseindia.com/content/equities/symbolchange.csv`
(free, ~1,800 rows, Jan-2000→present: Company Name/Old Symbol/New Symbol/Effective Date),
joined against `archives.nseindia.com/content/equities/EQUITY_L.csv` (current ISIN↔symbol
master — **note the correct path uses plural "equities"**, a `equity`/`equities`
pluralization mismatch caused one sub-agent's probe to 404 initially).

**Three concrete case studies confirm bhavcopy-presence is necessary but NOT sufficient
alone**:
- **DHFL** — RBI board supersession Nov-2019, Piramal reverse-merger Sep-2021; exact NSE
  delisting date not found via Wikipedia, needs a circular lookup.
- **Yes Bank** — **never delisted**; the Mar-2020 RBI moratorium was a 30-day withdrawal
  cap, not a listing event — a naive "restructuring ⇒ delisted" heuristic would be WRONG
  here; bhavcopy-presence correctly shows continuous listing.
- **Satyam** — removed from the Nifty INDEX Jan-2009, but the NSE-listed SYMBOL kept
  trading, renamed "Mahindra Satyam" Jul-2009, only legally merged away Jun-2013. **This is
  the sharpest argument for tracking universe membership by ISIN, not trading symbol** — a
  symbol-presence-only check would misclassify this as an early-2009 delisting.

**Residual gaps (not full blockers):**
- No single bulk NSE/SEBI "master list of all delisted companies with exact dates" was
  found; `https://www1.nseindia.com/content/equities/delisted.xlsx` is a promising lead
  that SSL-errored this session (unverified, needs a manual/headless-browser retry).
- Suspension-vs-delisting cannot yet be distinguished from bhavcopy alone (untested
  empirically against a known suspension case).
- **ISIN-extinguishing mergers** — see §3 below, the one confirmed hard blocker.
- SEBI itself has **no** centralized delisted-companies database (confirmed negative,
  Kar Committee report is policy-only).
- Vendor cross-check: only **Ace Equity Nxt** publishes self-serve pricing (₹1,25,000/yr
  ≈ $3,500) among Ace/Capitaline/CMIE Prowess/Bloomberg/Refinitiv — all others are
  institutional-library/sales-only with no public price. **Not needed**, since the free
  first-party paths cover the bulk of the need.

### 2b. Historical F&O-eligibility snapshots — fully solved, no blocker

**Primary method**: the daily **F&O bhavcopy archive itself** is the exact eligible-symbol
list for any date — no circular-parsing needed.
- Old format (2-Jul-2001 → 5-Jul-2024):
  `nsearchives.nseindia.com/content/historical/DERIVATIVES/{YYYY}/{MON}/fo{DD}{MON}{YYYY}bhav.csv.zip`
  — verified live including day one (`fo02JUL2001bhav.csv.zip` = exactly 31 `OPTSTK` names
  on launch day: ACC, BAJAJAUTO, BHEL, BPCL, RELIANCE, SBIN, TISCO, etc.).
- New UDiFF format (8-Jul-2024 → present):
  `nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip`.
- Filter `INSTRUMENT` ∈ {FUTSTK, OPTSTK}, distinct `SYMBOL` = that day's exact F&O-eligible
  universe. Free, no login, needs a browser-like User-Agent (bare `curl` gets blocked).

**Supporting layer**: NSE's Exchange Communication Circulars API
(`nseindia.com/api/circulars?sub=<keyword>&dept=FAO`, session-cookie-gated but reliable
once primed) gives the "why" behind each addition/removal — 215 "Introduction of Futures"
circulars found (Nov-2001→present) plus matching exclusion circulars. SEBI's current
eligibility rulebook (SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/116, 30-Aug-2024, read in full):
top-500 avg. daily market cap + ADTV, Median Quarter Sigma Order Size ≥ ₹75L, MWPL ≥
₹1,500cr, ADDV ≥ ₹35cr rolling 6-month, 3-month exit trigger, 1-year re-entry lockout.

**Confirmed-distinct pitfall**: the F&O **ban list** (`fo_secban.csv`, MWPL-based
short-term restriction, historical dated copies also fetchable) is NOT the same as
segment-eligibility — a stock cycles in/out of the ban list dozens of times a year while
remaining permanently F&O-eligible. Conflating the two would corrupt the reconstruction.

### 2c. Historical index-constituent history — fully solved, no blocker

**`niftyindices.com/press-release`** (free, official NSE Indices Ltd / IISL, server-
rendered plain HTML) is a **1,027-entry index-change press-release archive spanning
2-Sep-1998 → present**, covering all 5 target indices from each one's real launch: NIFTY
50/NIFTYNXT50 (from 1998), BANKNIFTY (launched as "CNX Bank Index" 15-Sep-2003),
MIDCPNIFTY (launched 14-Sep-2021), FINNIFTY base index (7-Sep-2011, variant launches
May-2020/Feb-2022). Each entry: exact decision + effective ("w.e.f.") date,
downloadable PDF, symbol-level inclusion/exclusion detail.

Cross-check layer: NSE F&O circulars ("Change in the Constituents of Indices",
`nsearchives.nseindia.com/content/circulars/FAOP<number>.pdf`) sometimes carry LATER
amendments not in the original press release (confirmed example: a Sep-2024 Midcap
Select change postponed to 25-Oct-2024).

**Fast-start bootstrap datasets** (Nifty 50 only, not the other 4 indices):
`vishalvx/nifty-indices-datasets` (GitHub, MIT, 2008–present, monthly binary in/out) and
Hugging Face `AMP4010/Historical_Nifty_50_Constituent_Weights_20Y` (Jan-2008 to Aug-2025,
actual weight percentages, CC BY-NC-SA 4.0 — usable for this personal project per Rule E).

**Effort, not availability**: reconstructing the full structured event table requires
scraping + `pdftotext`-parsing ~1,027 PDFs with format drift across 28 years — a one-time
engineering task, not a data-access blocker.

### 2d. Cross-cutting infrastructure note (applies to all of §2 and §3)

`nseindia.com`'s main pages are Akamai-bot-protected, JS-rendered SPAs that return 403/
timeout to stateless fetch tools. The `archives.nseindia.com`/`nsearchives.nseindia.com`
static-file subdomains and the `/api/circulars` and `/api/corporates-corporateActions`
endpoints are reliably fetchable with a plain browser-like User-Agent. **Production code
should target the archive/API paths, never the JS-rendered pages directly**, and reserve a
real headless-browser session (Playwright/Selenium with cookie persistence) for the
handful of pages with no static-file equivalent (e.g. the unverified `delisted.xlsx`).

---

## 3. Corporate-actions master (~20yr, splits/bonus/dividends/rights/renames/mergers)

**Full detail:** `57_corporate_actions_master_sourcing_consolidated.md` (companion,
referencing `56_corporate_actions_vendors_ace_capitaline_trendlyne.md` and
`56_yfinance_nse_and_symbol_isin_merger_sourcing.md`). Summary below.

### Bottom line
**Buildable for free from NSE + BSE first-party endpoints, back to 1995.** Not a hard
blocker. One genuine hard sub-blocker: ISIN-extinguishing mergers.

### 3.1 NSE — SOLVED, Grade A, verified live
`https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY`
— **verified live**: a single call for 01-01-1995→31-12-2025 returned **41,979 records**
(~13MB JSON, HTTP 200, no pagination cap), earliest record **04-Jan-1995**. Fields:
symbol, isin, comp, series, faceVal, `subject` (free-text action description), exDate,
recDate, book-closure/no-delivery dates, broadcast date. Free, no key. Caveat: action
type + ratio live only in the free-text `subject` field — **2,600+ distinct subject
variants** need a regex normalizer. Undocumented endpoint — needs defensive session-cookie
priming at production scale. A per-symbol RELIANCE spot-check showed a 1996–2003 gap that
the bulk (no-symbol-filter) query does NOT have — **use the bulk query, not per-symbol.**

### 3.2 BSE — cross-check, Grade A, verified live
`https://api.bseindia.com/BseIndiaAPI/api/CorpactCSVDownload/w?...` with blank Scripcode
returns an all-scrip CSV. **Earliest coverage ~30-Jun-2000** (despite BSE dating to 1875).
Free, no key. Role: cross-validate/backfill NSE from 2000 onward; for 1995–2000, NSE is the
only free bulk source found.

### 3.3 SEBI — confirmed dead end, Grade A negative
No corporate-actions database exists at SEBI; its public system is IPO/prospectus filings
+ investor grievances. Under LODR, actions are filed with and published by the exchanges,
not duplicated at SEBI.

### 3.4 OSS tools — `nselib` wins
Of `jugaad-data`, `nsepython`, `nselib`: **only `nselib.corporate_actions_for_equity()`**
wraps the correct structured NSE endpoint (source read directly). jugaad-data only exposes
free-text announcements (wrong endpoint); nsepython's rumored `dividend_timeline()` doesn't
exist. `nselib` is the most actively maintained (last commit 18-Jul-2026). No built-in
price-adjustment; multi-year depth against the full 2,000+ universe not yet empirically
verified (probe timed out on anti-bot session) — a Rule-F pass is needed before trusting it.

### 3.5 Paid vendors — no confirmed affordable API-accessible CA master
Bloomberg (~$24–32k/yr/seat) and Refinitiv/LSEG (enterprise sales-only) ruled out for a
personal project. **Ace Equity Nxt** ₹1,25,000/yr (~$3,500) is the one confirmed self-serve
price but CA-module granularity is unconfirmed. **Trendlyne** is the most promising lead
(secondary-reported ₹2,190–₹11,900/yr with splits/dividends/M&A/board-meetings + Excel
export) but is **primary-unverified** — the site 405-blocked all automated fetches; flagged
for a manual human-browser follow-up. Given items 3.1–3.2 are free and cover the bulk of
the need, paid vendors matter only for the merger/swap-ratio gap (§3.7).

### 3.6 Yahoo Finance / yfinance — cross-check only, not primary
`yfinance`'s `Ticker.splits`/`.dividends`/`.actions`/`.capital_gains` are genuine structured
objects (not exchange-gated) for `.NS` tickers. **Data-quality risk**: 7 GitHub issues show
a repeatable pattern of NSE-specific correctness bugs closed "not planned" (e.g. a spurious
65% single-day drop on RAYMOND.NS). Use to VALIDATE the NSE/BSE master, never to build it —
diffing adjusted-vs-raw close cannot disambiguate combined split+dividend factors without
the structured actions series.

### 3.7 Renames SOLVED / mergers = the one hard blocker
- **Renames — SOLVED**: `archives.nseindia.com/content/equities/symbolchange.csv` (free,
  ~1,800 rows, Jan-2000→Jun-2026) joined to `EQUITY_L.csv` on ISIN. This **overturns the
  initial assumption that renames would be the hardest sub-case** — corroborated
  independently by §2's Satyam case study.
- **Mergers/amalgamations — HARD BLOCKER**: ISIN-extinguishing events with swap ratios and
  surviving-entity mapping have **no free canonical source**. MCA portal 403s, NSE
  per-company announcement UIs are bot-gated, Moneycontrol blocked, Screener.in's CA tab is
  JS-rendered/inconclusive. Requires a paid vendor (Trendlyne/Ace — unverified for this
  specific need) or semi-manual per-event research. **Scope is narrow**: only companies
  that actually merged, not the full universe.

### 3.8 Recommended build path (from the consolidated companion doc)
1. Primary pull: NSE `corporates-corporateActions` API, chunked by year, 1995→present.
2. Cross-validate/backfill: BSE all-scrip CSV, 2000→present.
3. Normalize the free-text `subject`/`Purpose` fields via a regex parser (the real
   engineering effort — 2,600+ variants).
4. Renames: join `symbolchange.csv` + `EQUITY_L.csv` on ISIN.
5. Validate (Rule F) against yfinance's structured actions series across the full
   2,000+-symbol universe; key on ISIN, not symbol (per the RELIANCE anomaly).
6. Mergers: track separately in BACKLOG; source via a verified paid vendor or per-event
   manual work.
7. Always preserve the unadjusted point-in-time print; store adjustment factors alongside
   so continuity is *derived*, never destructive of the raw tape.

---

## 4. Per-segment INCEPTION dates — verified, not assumed

**Full detail:** `60_nse_segment_inception_dates_verification.md` (companion; renamed from
`56_...` to resolve a numbering collision — content unchanged). Summary below.

### 4.1 Founding segments (all Grade A, single authoritative NSE PDF read in full, plus
independent secondary corroboration)

| Segment | Exact date |
|---|---|
| Nifty index futures | **Monday, 12 June 2000** |
| Nifty index options | **Monday, 4 June 2001** |
| NSE single-stock options | **Monday, 2 July 2001** |
| NSE single-stock futures | **Friday, 9 November 2001** |

Source: `archives.nseindia.com/content/press/Data_Details_F_n_O.pdf` — *"The derivatives
trading on the exchange commenced with S&P CNX Nifty Index futures on June 12, 2000. The
trading in index options commenced on June 4, 2001 and trading in options on individual
securities commenced on July 2, 2001. Single stock futures were launched on November 9,
2001."* All four commonly-cited informal dates are confirmed correct at day-level
precision — no disagreement across any source checked.

### 4.2 Weekly index-option introduction, per index (each verified via NSE's own launch
circular, read in full)

| Index | Weekly options launch | Note |
|---|---|---|
| BANKNIFTY | **27 May 2016** | NSE/FAOP/32329 |
| NIFTY 50 | **11 February 2019** | NSE/FAOP/39894 |
| FINNIFTY | **11 January 2021** | Weekly from day one of F&O launch (index itself launched 7-Sep-2011) |
| MIDCPNIFTY | **24 January 2022** | Weekly from day one of F&O launch. Corrects the commonly-cited "2023," which is actually a later *expiry-day* change (Wed→Mon), not the weekly launch |
| **NIFTYNXT50** | **Never introduced** | Launched 24-Apr-2024 as **monthly-only from day one** — its contract-cycle spec lists only "3 serial monthly contracts," unlike the other three indices' launch circulars which explicitly list weekly cycles |

### 4.3 2024–2025 rationalization (SEBI circular SEBI/HO/MRD/TPD-1/P/CIR/2024/132,
1-Oct-2024, read in full)

SEBI mandated **one weekly-expiry product per exchange**, effective **20 November 2024**.
NIFTY 50 became the sole NSE index retaining weekly expiry. Last weekly-expiry trading
days: BANKNIFTY 13-Nov-2024, MIDCPNIFTY 18-Nov-2024, FINNIFTY 19-Nov-2024 (Grade B — 4+
matching secondary sources, primary NSE discontinuation-circular number not locatable).
Separately, NSE's expiry weekday moved **Thursday → Tuesday effective 1 September 2025**
(NSE circular FAOP/68747, read in full), with BSE Sensex swapping Tuesday→Thursday to
avoid same-day collision.

### 4.4 Practical replay-simulator rule derived from this

```
BANKNIFTY weekly data exists:   2016-05-27 → 2024-11-13 only
FINNIFTY weekly data exists:    2021-01-11 → 2024-11-19 only
MIDCPNIFTY weekly data exists:  2022-01-24 → 2024-11-18 only
NIFTY weekly data exists:       2019-02-11 → present, continuously
NIFTYNXT50 weekly data:         never exists, at any point — monthly-only
Expiry weekday:                 Thursday-based through 2025-08-31, Tuesday-based
                                 from 2025-09-01 — any "days-to-expiry" inference
                                 from a fixed weekday must branch on this date.
```

---

## 5. Gaps & hard blockers — consolidated table

| # | Item | Severity | Mitigation / status |
|---|---|---|---|
| G1 | ISIN-extinguishing merger/amalgamation swap-ratio + surviving-entity records | **Hard, confirmed** | No free bulk source (MCA/Moneycontrol/NSE UIs bot-gated). Paid vendor (verify Trendlyne/Ace) or per-event manual sourcing. Scope = only merged companies, not the full universe. |
| G2 | Single bulk NSE/SEBI master list of ALL delisted companies with exact dates | Medium (sourcing) | Not found despite multi-angle search. `delisted.xlsx` (www1.nseindia.com) is an unverified lead (SSL-errored this session) — needs a manual/headless-browser retry. Fallback: derive from bhavcopy-presence gaps + circular lookups via `/api/circulars`. |
| G3 | Suspension-vs-delisting distinction from bhavcopy alone | Medium (build) | No source confirms/denies whether a suspended-but-not-delisted stock disappears from bhavcopy the same way. Must be tested empirically against a known SEBI-suspension case. |
| G4 | NSE Data & Analytics: two contact addresses disagree (`marketdata@nse.co.in` vs `marketdata@nseids.co.in`); old Snapshot product's current sellable status unconfirmed; individual (non-entity) eligibility for the `dotexdata.nseindia.com` portal unconfirmed | Open (verify) | Direct email to NSE Data & Analytics before assuming any of these. |
| G5 | True per-order (Product B) tick history only starts ~Dec 2007; 1995–2007 (CM) / 2003–2007 (F&O) is trades+discrete-snapshot only | **Hard, structural (not sourcing)** | Fidelity ceiling for the oldest replay years — tag provenance/fidelity-tier accordingly per §53 §8.2/§10.4. |
| G6 | NSE F&O dissemination archive itself starts Jan 2003, even though F&O trading began Jun 2000/Jul 2001 | **Hard, structural** | ~2.5 years of early F&O trading (2000–2002) has no dissemination-archive tick data; if needed, would require a separate, likely unavailable, historical source. |
| G7 | Real-world/anecdotal pricing cross-check for the NSE tariff; TickData/LSEG provenance (official archive vs own capture) | Low (verify) | Tariff PDF is strong primary evidence regardless; low priority to chase further. |
| G8 | `nselib.corporate_actions_for_equity()` multi-year depth across the full 2,000+ universe not empirically load-tested | Medium (Rule F pending) | Needs a real-data verification pass before production reliance. |

---

## 6. Ranked acquisition plan

**Design principle** (consistent with `research/54`'s fidelity-laddered approach):
everything free and first-party should be built FIRST — it fully covers three of the four
items in this pass — before spending on the one item that costs real money.

**Rank 1 — build now, free, no blockers:**
- **Universe reconstruction** (§2): bhavcopy-presence backbone (1994→present) +
  `symbolchange.csv`/`EQUITY_L.csv` rename pipeline + F&O bhavcopy filter (2001→present,
  fully solved) + `niftyindices.com/press-release` scrape (1998→present, fully solved).
- **Corporate-actions master** (§3): NSE `corporates-corporateActions` API pull
  (1995→present) + BSE cross-check (2000→present) + `nselib` wrapper, with a regex
  normalizer for the free-text action fields as the main engineering task.
- **Segment inception dates** (§4): already fully verified — bake the exact dates and the
  weekly-expiry-availability windows directly into the replay simulator's per-segment
  bounds and expiry-weekday-cutover logic now.

**Rank 2 — cheap/manual follow-ups to close residual gaps in Rank 1:**
- Manually/headless-browser retry `delisted.xlsx` (G2) and `niftyhistory.in`/
  `exchangecirculars.com` (bot-blocked leads worth a human-browser confirmation).
- Empirically test the suspension-vs-delisting bhavcopy behavior (G3) against a known case.
- Run the Rule-F real-data load test on `nselib.corporate_actions_for_equity()` and on the
  NSE actions API across the full 2,000+-symbol universe (G8).
- Manually verify Trendlyne's actual corporate-actions coverage/pricing (G1/§3.5 lead) as
  the cheapest realistic path to the merger/swap-ratio gap, before assuming it's unsolved.

**Rank 3 — the paid, licensed, deep-fidelity source (only item that costs real money):**
- **License NSE Data & Analytics.** Concretely, given the true fidelity ceiling (G5 — full
  order data only from ~2007), the recommended purchase is the **Historical Order & Trade
  Data product for CM + F&O, domestic tier** (₹12,50,000/yr each, or ₹25,00,000/yr combined
  commercial — confirm whether the "Student/Researcher" 50%-off tier is honestly claimable,
  §1.4 caveat) for 2007→present order-level fidelity, **plus** the cheaper legacy
  **Historical Trade Data product** (₹1,10,000/yr CM, ₹1,10,000/yr F&O = ₹2,20,000/yr) to
  cover the 1995–2007 (CM) / 2003–2007 (F&O) trades-only era. Action: email
  `marketdata@nse.co.in` (cross-check `marketdata@nseids.co.in`) to confirm individual
  eligibility (G4) and the researcher-tier classification question before committing budget.

**Do NOT pursue:** chasing TickData/LSEG as a cheaper alternative to NSE direct (no
evidence of a price or coverage advantage, §1.6); SEBI as a corporate-actions or delisting
source (confirmed dead end, §2a/§3.3); per-symbol NSE corporate-actions queries instead of
the bulk endpoint (has era gaps the bulk query does not, §3.1).

---

## 7. What this pass did NOT cover

- Building the actual reconstruction/parsing pipelines (regex normalizer for corporate
  actions, PDF-parsing for index press releases) — that is a `sourcing-oss-parts`/
  `building-features-from-ideas` follow-up, not this sourcing pass.
- Point-in-time market rules (expiry cycles, lot sizes, tick sizes, circuit bands, STT,
  margin regime), trading calendar (holidays/muhurat), and deep historical news — covered
  separately in the pre-existing `61_point_in_time_rules_calendar_and_news_sourcing.md`.
- Empirical confirmation of NSE Data & Analytics individual-eligibility and the exact
  authoritative contact address (G4) — needs a direct email, not further web research.
- A full Google Scholar/SSRN academic-literature sweep for either corporate-actions
  reconstruction or Nifty-reconstitution research (light-touch only, low priority given
  the primary free sources already fully answer both needs).
- BSE/MCX equivalents of items 2 and 4 (out of Phase-1 scope per `CLAUDE.md`).

---

## Companion files (this pass)

- `56_corporate_actions_vendors_ace_capitaline_trendlyne.md`
- `56_yfinance_nse_and_symbol_isin_merger_sourcing.md`
- `57_corporate_actions_master_sourcing_consolidated.md`
- `58_point_in_time_universe_reconstruction_nse.md`
- `60_nse_segment_inception_dates_verification.md` (renamed from `56_...`)
- `61_point_in_time_rules_calendar_and_news_sourcing.md` (renamed from `57_...`,
  pre-existing separate pass, not redone here)
