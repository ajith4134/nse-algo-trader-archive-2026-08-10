# 58 — Point-in-Time NSE Universe Reconstruction: Listing/Delisting, F&O Eligibility, Index Membership

Research date: 2026-07-24. Primary-source research for the survivorship-bias-free historical
market replay simulator: given ANY past date, reconstruct exactly which equities were
listed/tradeable, which had listed F&O contracts, and which were members of NIFTY 50 / BANKNIFTY /
FINNIFTY / MIDCPNIFTY / NIFTYNXT50 — not today's lists projected backward.

**Method:** 3 parallel research agents (one per sub-topic, 8-10+ search angles each) plus a direct
follow-up pass to close flagged gaps. `WebSearch` budget (200/session, shared across all
parallel agents) was exhausted partway through; remaining research used direct `WebFetch` of
primary URLs, `curl`/raw HTTP probing, GitHub source/API reads, and DuckDuckGo-HTML-page fetches
as a search substitute. Every claim below traces to a page actually opened, not a search snippet
alone, except where explicitly marked "unverified"/"C-grade."

**Related prior research (read for context, cross-linked below, not re-derived here):**
`research/56_corporate_actions_vendors_ace_capitaline_trendlyne.md` (Ace/Capitaline/CMIE-adjacent
vendor pricing), `research/56_yfinance_nse_and_symbol_isin_merger_sourcing.md` (NSE
`symbolchange.csv` — **already solves the symbol/ISIN-rename problem this pass initially
flagged as an open gap**, see §A5), `research/57_corporate_actions_master_sourcing_consolidated.md`
(NSE `corporates-corporateActions` API, 1995→present, 41,979 records verified live),
`research/26_continuous_replay_market_hours_handoff_findings.md` (the replay engine this data
feeds).

---

## Bottom line

All three sub-topics are **buildable primarily from free, first-party NSE endpoints** —
none is a hard blocker for the *core* reconstruction, though each has a specific residual gap:

- **A (listing/delisting):** Backbone = daily equity bhavcopy presence, free, **NSE cash segment
  launched 3-Nov-1994** (Wikipedia-corroborated) and bhavcopy tooling documents coverage from
  Jan 1994. Residual gap: no single bulk NSE/SEBI "master list of all delisted companies with
  exact dates" was found — must be assembled from bhavcopy gaps + circular PDFs. Symbol-rename
  problem is **already solved** by `research/56`'s `symbolchange.csv` finding.
- **B (F&O eligibility):** **Fully solved, no residual gap.** NSE's daily F&O bhavcopy archive
  (free, gap-free, 2-Jul-2001→present) gives the exact F&O-eligible symbol set for any date by
  filtering `FUTSTK`/`OPTSTK` rows — no circular-parsing needed as the primary method.
  Ban-list (short-term MWPL restriction) is confirmed **distinct** from segment-eligibility and
  must not be conflated.
- **C (index constituents):** **Fully solved, no residual gap.** `niftyindices.com/press-release`
  is a free, official, server-rendered archive of 1,027 index-change press releases spanning
  Sep-1998→present, covering all 5 target indices from each one's actual launch date. Effort is
  purely a one-time scrape-and-PDF-parse job, not a data-availability problem.
- **Institutional point-in-time vendors** (Ace Equity/Capitaline/CMIE Prowess/Bloomberg/Refinitiv):
  real, but confirmed **no public self-serve pricing** except Ace Equity Nxt
  (₹125,000/yr ≈ USD 3,500, per `research/56`) — all others are sales-contact/institutional-library
  only. Given the free first-party paths above fully cover the need, **paid vendors are not
  necessary** for this project; noted for completeness only.

---

## A. Historical listing/delisting master (point-in-time listed universe)

### Ranked sources

**A1. NSE historical daily equity bhavcopy archive — Grade A (primary), READILY AVAILABLE (mechanism), ACHIEVABLE BUT EFFORTFUL (as a delisting-detector)**
- Community tooling confirms NSE bhavcopy coverage from **January 1994** (`riyaz-ali/bhav-copy`,
  GitHub — Go tool → SQLite, documents NSE from Jan 1994 / BSE from Jan 2007, bulk date-range
  downloader with an explicit warning that aggressive bulk pulls can trigger a temporary NSE
  IP-blacklist — chunk downloads by quarter/half-year).
- Independently corroborated: **NSE's cash-equity segment launched 3-Nov-1994** (Wikipedia,
  cross-checked against the Jan-1994 tooling claim — the small gap is explained by NSE's Nov-1994
  launch date vs. some tools rounding to "1994" generically; either way, ~31 years of daily
  archive is real).
- Other tooling confirming the same technique: `tilak999/NSE-Data-bank` (GitHub, 2+ decades, daily
  auto-updated), `getbhavcopy.com`/`hemenkapadia/getbhavcopy` (free downloader, Metastock/Amibroker
  format), `nser` R package (CRAN/Zenodo — but its convenience function `bhav1()` is **hard-coded
  to only Jan-2016→Jul-2024**, a maintenance-risk red flag; don't depend on it beyond that window).
- **Mechanism:** presence/absence of a SYMBOL in a given day's bhavcopy is a reasonable
  point-in-time "was this tradeable" proxy, but is NOT by itself a clean delisting signal — see
  caveats below.
- **Cost:** free. **Format:** CSV inside a daily file, one URL-per-day pattern.
- **Procurement:** direct HTTP pull per date (all tooling above scrapes NSE's own public
  daily-report endpoints — same site, so subject to the same bot-mitigation risk noted in A2).
- **Precedent this technique works at scale:** `HaloHunter480/Survivorship-Bias-in-Emerging-Market-Small-Cap-Indices`
  (GitHub) reconstructed NIFTY Smallcap 250 point-in-time membership for **2016–2025** from 2,459
  daily bhavcopy files (3.85M rows), explicitly stating it *"includes delisted stocks (unlike
  commercial databases)"* — a working proof of concept for exactly this project's need, though
  only a 9-year window and using a market-cap-proxy ranking rather than a literal per-ISIN
  tradeable flag.

**A2. NSE's own site (delisting-specific pages) — Grade A for existence, content UNVERIFIED this session**
- `https://www.nseindia.com/static/list/orders-of-delisting` — delisting-committee orders.
- `https://www.nseindia.com/static/list/list-of-companies-proposed-to-be-delisted` — pending
  delistings (rolling, current-state).
- `https://www1.nseindia.com/content/equities/delisted.xlsx` — a direct Excel export surfaced by
  search; the legacy `www1` subdomain returned an SSL error on fetch this session, so **content
  unverified** — worth a manual/authenticated-browser retry, as this is the single most promising
  lead for a genuine bulk delisted-companies list and was not conclusively ruled in or out.
- **Blocker, confirmed directly:** `nseindia.com` is Akamai-bot-protected and a JS-rendered SPA.
  Direct `curl`/stateless-fetch of the bare domain returns `403 Access Denied`; `WebFetch` on
  `www.nseindia.com/*` pages times out or SSL-errors. `archives.nseindia.com/content/equity/EQUITY_L.csv`
  and `nsearchives.nseindia.com/content/equity/EQUITY_L.csv` both genuinely 404 — **note the path**:
  `research/56` separately confirmed the correct, LIVE path is
  `archives.nseindia.com/content/equities/EQUITY_L.csv` (plural "equities", not "equity") — a
  simple pluralization mismatch caused this sub-agent's probe to fail; **use the `research/56`-confirmed
  path**, not the 404'd one. Any production pipeline needs a real headless-browser session
  (Playwright/Selenium) with cookie persistence for the JS-rendered pages, not stateless fetch.

**A3. NSE Circulars Archive (`nsearchives.nseindia.com/content/circulars/<CODE><ID>.pdf`) — Grade A, ACHIEVABLE BUT EFFORTFUL**
- Individual circular PDFs confirmed fetchable directly (e.g. voluntary-delisting-notice
  withdrawals). No bulk date-indexed directory exists — `research/57`/this pass's sub-topic B
  separately discovered the real discovery mechanism is `nseindia.com/api/circulars?sub=<keyword>&dept=<code>`
  (session-cookie-gated, but keyword-searchable back to the early 2000s) — **apply that same API
  pattern here** (e.g. `dept=CMPT` or a "delisting" keyword search) rather than guessing circular
  IDs one at a time, which sub-topic A's pass did not discover in time. This is a **cross-reference
  worth actioning**: the F&O sub-topic's discovery of the `/api/circulars` endpoint generalizes to
  delisting circulars too and should collapse much of A3's "effortful" classification.

**A4. SEBI — Grade A for existence, but confirmed NOT a delisted-companies database**
- SEBI's "Report of the Committee on Delisting of Shares" (Kar Committee, 2010,
  `sebi.gov.in/sebi_data/attachdocs/1293169889303.pdf`, fetched and read in full) is a
  policy-framework document — zero company names/dates. SEBI's Delisting of Equity Shares
  Regulations 2021 (as amended Sep-2024) is the legal framework, not a database.
  **No centralized SEBI "list of all delisted companies" was found via any angle searched** —
  matches several secondary sites that all defer to exchange-level search widgets instead.
  This is a genuine negative finding worth recording so it isn't re-searched fruitlessly later.

**A5. Symbol/ISIN rename history — SOLVED (not a gap), per `research/56`**
- `archives.nseindia.com/content/equities/symbolchange.csv` (fetched directly by `research/56`):
  headerless 4-column CSV, `Company Name, Old Symbol, New Symbol, Effective Date`, real confirmed
  rows back to ~2000. Joined against `EQUITY_L.csv` (current ISIN↔symbol), this gives a free,
  first-party, no-auth pipeline to walk any current ISIN's symbol history backward. This sub-topic's
  own pass had flagged "no NSE symbol-rename master found" as a hard blocker — **that is
  superseded by `research/56`'s finding; do not re-treat as a blocker.**
- Caveat carried over from `research/56`: ISIN itself is **not guaranteed constant** across all
  corporate actions (Wikipedia: ISIN ties to the underlying NSIN, which can change) — a simple
  rebrand keeps ISIN constant (what `symbolchange.csv` captures), but a merger/amalgamation
  typically extinguishes the transferor's ISIN. `research/57` confirms **ISIN-extinguishing
  mergers remain the one genuinely hard, unsolved sub-case** (no free bulk source; MCA portal
  403s; NSE per-company announcement PDFs are bot-gated) — smaller in scope than the full
  universe (only companies that actually merged, not all renames), but real.

**A6. GitHub/Kaggle/OSS point-in-time-universe datasets — Grade B**
- `HaloHunter480/Survivorship-Bias-in-Emerging-Market-Small-Cap-Indices` (see A1) — best working
  precedent found, 2016–2025, methodology transparent.
- `Finance-broski/backtest-bias` (GitHub) — `check_survivorship()` bias-detection tool; author
  quantifies **24% of the top-500 Indian stocks as of 2015 are absent from yfinance today**, a
  concrete demonstration of the scale of the survivorship-bias problem this project is solving.
  References a companion "survivorship-free Indian equity dataset" on Kaggle (`financebroski`
  account) — **Kaggle's page is JS-rendered and its actual contents could not be verified this
  session**; a commercial "Bias Check" audit service is advertised at ₹7,500.
- No GitHub repo was found that ships a ready-made, complete NSE point-in-time delisted-universe
  dataset — every lead found is either a narrower proof-of-concept (2016-2025 only) or an
  unverified claim.

**A7. Commercial vendors (Ace Equity, Capitaline, CMIE Prowess, Bloomberg, Refinitiv) — Grade A/B, confirmed NO public pricing except one**
- Cross-referencing `research/56`: **Ace Equity Nxt** (Accord Fintech, successor to the old
  aceanalyser.com "Ace Equity" branding) publishes self-serve pricing directly on its site:
  **₹125,000/yr (~USD 3,500) "onwards," taxes extra** (`aceequitynxt.com/subscribe-now`, Grade A,
  fetched directly by `research/56`). Its public feature page does not explicitly call out a
  dedicated point-in-time/delisted-universe module — "capital structure and shareholding" is the
  closest named feature.
- **CMIE Prowess/ProwessIQ**: confirmed directly this session — the public site states detailed
  content "is available only as a subscription-fee-based service," no price shown anywhere
  public; coverage claims found via secondary institutional-library PDFs (IIMA, RVIM) cite
  "~50,000-108,000+ Indian companies, listed + unlisted + private" — sold primarily to
  universities/corporates, not individual self-serve.
- **Capitaline Plus**: same pattern — "35,000+ Indian listed and unlisted companies," no public
  pricing found; institutional-library-oriented (IIMA reference again).
- **Bloomberg/Refinitiv**: not independently re-verified this session (matches the general
  industry pattern of enterprise-terminal-subscription-only, typically ~$24,000+/yr per seat for
  Bloomberg — an order-of-magnitude figure from general knowledge, **not independently confirmed
  this session**, flag as unverified if cited further).
- **Assessment: none of these are needed.** The free NSE-first-party paths (A1 + A5, backed by
  `research/56`/`57`) already cover the bulk of the reconstruction need at zero cost; a paid
  vendor would only be worth it to resolve the residual merger/ISIN-extinction gap (A5's caveat),
  and even there, pricing wasn't confirmed as covering that specific need.

### Classification summary — Sub-topic A

| Bucket | Item |
|---|---|
| **READILY AVAILABLE** | Bulk bhavcopy tooling (free, Jan/Nov-1994→present); `symbolchange.csv`+`EQUITY_L.csv` rename pipeline (free, `research/56`); working OSS precedent code (`HaloHunter480`) |
| **ACHIEVABLE BUT EFFORTFUL** | Building a suspension-vs-delisting classifier (no source found either confirming or denying whether suspended stocks vanish from bhavcopy the same way delisted ones do — must be tested empirically against known cases, e.g. cross-checking a SEBI trading-restriction order date against bhavcopy); enumerating NSE delisting circulars via the `/api/circulars` pattern (cross-applying sub-topic B's discovery); extending the `HaloHunter480`-style reconstruction from its proven 2016–2025 window back to 1994 |
| **HARD BLOCKER** | Single bulk NSE/SEBI master list of ALL delisted companies with exact dates, back to 1994, in one machine-readable file — not found despite multi-angle search; `delisted.xlsx` is an unverified lead worth a manual-browser follow-up. ISIN-extinguishing merger/amalgamation swap-ratio records (per `research/57`) — genuinely no free bulk source. |

### My assessment: is bhavcopy-presence-since-1994 alone sufficient?

**No — necessary but not sufficient**, confirmed by three concrete, evidence-based Wikipedia
spot-checks this session:
1. **DHFL** — RBI superseded the board 20-Nov-2019, Piramal completed acquisition via insolvency
   (reverse-merger) Sep-2021. No exact NSE delisting date found on Wikipedia — needs an NSE
   circular (now reachable via the `/api/circulars` pattern from B, see A3).
2. **Yes Bank** — **never delisted.** RBI's Mar-2020 moratorium was a 30-day withdrawal cap only;
   the stock traded continuously throughout, completing an FPO Jul-2020. A naive
   "restructuring → assume delisted" heuristic would be **wrong** here — bhavcopy-presence
   correctly shows continuous listing, which is a point *in favor* of the bhavcopy approach for
   this specific case.
3. **Satyam** — the sharpest counter-example: removed from the Nifty *index* Jan-2009, but the
   NSE-listed *symbol* continued trading, was renamed "Mahindra Satyam" Jul-2009 after Tech
   Mahindra's stake purchase, and only legally merged away Jun-2013. A naive symbol-presence check
   would wrongly flag this as a Jan-2009 delisting. **This is exactly the case `research/56`'s
   `symbolchange.csv`+ISIN-join pipeline is built to handle correctly** — track by ISIN across
   renames, not by trading symbol alone.

**Net conclusion:** treat bhavcopy-presence (1994→present) as the backbone signal, joined against
`symbolchange.csv` for rename continuity (already solved), with the suspension-vs-delisting
distinction and the merger/ISIN-extinction subset flagged as the two genuinely open, effortful
items to resolve empirically before this feature can be signed off per Rule F.

---

## B. Historical F&O eligibility snapshots (which stocks had listed derivatives on a given date)

### Ranked sources — this sub-topic is fully solved, no blockers

**B1. NSE historical F&O bhavcopy archive — Grade A (primary), READILY AVAILABLE, PRIMARY METHOD**
- Old format (2-Jul-2001 → 5-Jul-2024):
  `https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{YYYY}/{MON}/fo{DD}{MON}{YYYY}bhav.csv.zip`
  — verified live at multiple points across the full range including the actual first day
  (`fo02JUL2001bhav.csv.zip`, confirmed exactly 31 `OPTSTK` names on day one: ACC, BAJAJAUTO, BHEL,
  BPCL, RELIANCE, SBIN, TISCO, etc.) and the stock-futures launch day
  (`fo09NOV2001bhav.csv.zip`).
- New UDiFF format (8-Jul-2024 → present):
  `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip`
  — clean, documented cutover boundary, both formats verified 200 OK on either side.
- **Mechanism:** filter `INSTRUMENT` ∈ {`FUTSTK`, `OPTSTK`}, take distinct `SYMBOL` = that day's
  exact F&O-eligible universe. Zero interpretation needed — this is empirical ground truth, not a
  reconstruction from rules.
- **Cost:** free, no login; needs a browser-like `User-Agent` header (bare `curl` gets blocked with
  empty/000 responses, but `Mozilla/5.0` UA works reliably — no other anti-bot friction observed
  for this specific archive path, unlike the JS-rendered site pages).
- **This should be the primary build path for sub-topic B — strictly simpler and more reliable
  than any circular-parsing approach.**

**B2. NSE `fo_mktlots.csv` — Grade A, current-state only, cross-check use**
- `https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv` — 217 rows, current F&O underlyings
  + lot sizes. Not versioned/dated by NSE — live-only, not historical.

**B3. NSE Exchange Communication Circulars API — Grade A, secondary "reason" layer**
- `https://nseindia.com/api/circulars?sub=<keyword>&dept=FAO` (dept code `FAO` = Futures &
  Options, discovered from `/api/circulars-departments`). Session-cookie-gated (needs a prior
  request to the circulars page + browser UA + `Referer`), but reliable once primed.
- Verified: `sub=Introduction of Futures&dept=FAO` → **215 circulars**, Nov-2001→present, each an
  addition event. `sub=exclusion&dept=FAO` → matching removal circulars, now issued roughly
  monthly (e.g. "Exclusion of F&O contract on DALBHARAT," Jun-2026; "...SYNGENE," Jan-2026).
- Master eligibility-criteria circular found and read in full: **NSE/FAOP/63682** (30-Aug-2024),
  annexing **SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/116** — the actual current rulebook (see B4).
- **Use case:** enrich each B1-detected addition/removal with a "why" (which circular, what
  changed) — not needed as the primary universe-reconstruction method, since B1 already gives
  ground truth without interpretation. Effort here is real (~200+ individual PDFs to loop through
  the API for) but purely optional polish.

**B4. SEBI eligibility-criteria circular — Grade A, primary, read in full**
- SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/116 (30-Aug-2024). Confirmed exact current criteria: top-500 by
  avg. daily market cap + ADTV; Median Quarter Sigma Order Size ≥ ₹75 lakh; MWPL ≥ ₹1,500 crore;
  Average Daily Delivery Value ≥ ₹35 crore, each on a rolling 6-month basis. Exit triggers after
  missing any criterion for a continuous 3 months (post a 3–6 month gestation period); **1-year
  re-entry lockout** after exclusion. A "Product Success Framework" for single-stock derivatives
  was also introduced in the same circular.
- Prior revisions confirmed to exist (not fixed-schedule): 2004, 2006, 2008/09, 2018, 2024 — via
  circular IDs NSE/faop/5384, 7143, 11448, 12295, 63682. SEBI is the rule-setter; NSE is purely
  operational (publishes the resulting per-stock circulars).
- Standing consolidation: SEBI Master Circular on Stock Exchanges and Clearing Corporations
  (16-Oct-2023), §3.1.2 of Chapter 5.

**B5. F&O "Securities in Ban" list — confirmed DISTINCT, must not be conflated**
- Current: `https://nsearchives.nseindia.com/content/fo/fo_secban.csv`. Historical dated copies
  also exist and are fetchable, e.g.
  `https://nsearchives.nseindia.com/archives/fo/sec_ban/fo_secban_01012020.csv` (verified live).
- This is a **short-term, MWPL-based trading restriction** (triggers at 95% of a stock's
  market-wide position limit, lifts at 80%) applied to stocks that are *already* F&O-eligible. A
  stock can cycle in/out dozens of times a year while remaining permanently F&O-eligible
  throughout. **Conflating ban-list membership with segment-eligibility would corrupt the
  reconstruction** — explicitly flagged so this mistake isn't made during implementation.

**B6. Zerodha Kite Connect instruments dump — Grade A, current-state only**
- `https://api.kite.trade/instruments` — free, no auth, 10.1MB CSV, all live NSE/NFO/BSE/BFO
  instruments. Only useful historically if someone has been archiving daily snapshots (common
  retail-quant practice, but Zerodha itself doesn't serve past days).

**B7. Open-source tooling — Grade B/C, glue only, no pre-built dataset found**
- `swapniljariwala/nsepy`, `jugaad-py/jugaad-data`, `aeron7/nsepython`, `BennyThadikaran/NseIndiaApi`
  — all wrap the same NSE endpoints (including bhavcopy download); none ship a pre-built
  F&O-eligibility-by-date dataset. GitHub search for "NSE FO eligible stocks history" / "nsepy
  fno history" returned **zero repositories** — confirms no ready-made third-party dataset exists;
  must be built from B1.

**B8. Paid vendors (TrueData, Global Datafeeds, Bloomberg, Refinitiv) — unverified, low priority**
- TrueData's `/products` URL 404'd; Global Datafeeds' homepage only advertises generic "long
  histories," no explicit dated F&O-instrument-master product found. Given B1 is free and
  complete, **not worth pursuing further** for this specific need.

### Classification summary — Sub-topic B

| Bucket | Item |
|---|---|
| **READILY AVAILABLE** | Daily F&O bhavcopy archive (B1) — free, gap-free, 2-Jul-2001→present, one URL pattern, primary method, solves the whole sub-topic |
| **READILY AVAILABLE (supporting)** | SEBI eligibility-criteria text (B4); ban-list-vs-eligibility distinction (B5) |
| **ACHIEVABLE BUT EFFORTFUL** | Circular-by-circular "reason code" enrichment (B3) — optional polish only |
| **HARD BLOCKER** | None for the core question. Minor open items: exact paid-vendor pricing (unverified, not needed); the `/api/circulars` date-range query mode (without a keyword) returned empty in testing — keyword-search mode works fine as a substitute |

---

## C. Historical index-constituent history (NIFTY 50 / BANKNIFTY / FINNIFTY / MIDCPNIFTY / NIFTYNXT50)

### Ranked sources

**C1. niftyindices.com official Press Release archive — Grade A (primary, NSE Indices Ltd/IISL), the answer to this whole sub-topic**
- `https://www.niftyindices.com/press-release` — server-rendered raw HTML (confirmed via direct
  `curl`, no JS execution needed to read it), containing **1,445 press-release entries**, of which
  **1,027 are index-change/replacement releases**, spanning **2-Sep-1998 → present**. Each entry:
  exact decision + effective ("w.e.f.") date, downloadable PDF at
  `/Press_Release/ind_prs<DDMMYYYY>[_n].pdf`, company-name + symbol-level inclusion/exclusion
  detail, attributed to the "Index Maintenance Sub-Committee (Equity) of NSE Indices Limited."
- Verified by `pdftotext`-extracting 3 samples spanning eras: `ind_prs28121998.pdf` (CNX Nifty
  Junior, today's NIFTYNXT50), `ind_prs31102000.pdf` (S&P CNX 500), `ind_prs17062026_2.pdf`
  (Jun-2026, a Tata-Group thematic-index replacement — confirms the archive is actively
  maintained through the present).
- **Per-index coverage, all confirmed from the extracted title list:**
  - **NIFTY 50 / NIFTYNXT50 (as "CNX Nifty Junior" historically):** covered from the earliest
    entries (1998), near-complete against Nifty 50's 1996 launch.
  - **BANKNIFTY:** launched as "CNX Bank Index" 15-Sep-2003 — confirmed via two separate
    press-release titles announcing the launch; full reconstitution history since inception is in
    this archive.
  - **MIDCPNIFTY (Nifty Midcap Select):** launched 14-Sep-2021 — confirmed via launch
    press-release title; reconstitutions since then are in the same generic "Replacements in
    indices" releases.
  - **FINNIFTY (Nifty Financial Services):** base index pre-dates F&O; variant launches confirmed
    (25/50 variant May-2020, Ex-Bank variant Feb-2022); reconstitution events live inside the same
    combined multi-index releases — **requires opening each PDF to check which indices it
    touches**, since titles aren't always index-specific.
- **Cost:** free, no login. **Format:** one PDF per event (text-based, `pdftotext`-parseable), not
  a clean bulk CSV.
- **Procurement:** scrape the listing page → regex out all `/Press_Release/ind_prs*.pdf` links +
  dates + titles → bulk-download (~1,000 PDFs) → `pdftotext` each → parse into a structured
  `(index, symbol, action, effective_date)` event log. Format drifts across 28 years, needs
  per-era parsing rules and manual QA, especially pre-2010 — a real one-time engineering task, but
  a fully closed data-availability question.

**C2. NSE F&O circulars — "Change in the Constituents of Indices" — Grade A, cross-check layer**
- Pattern: `nsearchives.nseindia.com/content/circulars/FAOP<number>.pdf` (e.g. FAOP64175,
  FAOP60909, FAOP66817). These restate the niftyindices.com press releases to brokers/members and
  sometimes carry **later amendments** not in the original release — confirmed real example:
  FAOP64175 documents a Sep-2024 Midcap Select change originally announced for 30-Sep-2024 that
  was later postponed to 25-Oct-2024. **Use as a revision-tracker against C1**, not a replacement.

**C3. Index Reconstitution Calendar — not useful for history (noted to avoid wasted future effort)**
- `https://www.niftyindices.com/resources/index-rebalancing-schedule` — confirmed this is a
  **forward-looking** calendar of scheduled review dates only, not a historical-changes archive.

**C4. Historical index price-level data — adjacent, not membership data**
- `https://www.niftyindices.com/reports/historical-data` — confirmed via JS inspection: daily
  index-level (OHLC) downloads back to **1990**, date-range queryable. No constituent/weight data
  — useful elsewhere in the project (index-level replay), not for this sub-topic.

**C5. Third-party circular mirrors — Grade B, supplementary only**
- `exchangecirculars.com` — appeared correctly in DDG search results as a dated NSE circular
  archive entry, but returned 403 on direct fetch this session (retry with different UA needed).
- `rhnvrm/stock-market-circulars` (GitHub + hosted site) — confirmed real via a fetched Dec-2025
  page (Nifty Bank expanding 12→14 constituents, adding Union Bank of India and Yes Bank, w.e.f.
  31-Dec-2025); community project, LLM-assisted extraction over official NSE/BSE/SEBI RSS feeds,
  auto-updated every 3 hours via GitHub Actions. **Historical backfill depth undisclosed** — repo
  file tree couldn't be enumerated this session (GitHub API rate-limited). No bulk export, web UI
  only.

**C6. Pre-built community datasets — Grade B, Nifty 50 ONLY, not the other 4 indices**
- `vishalvx/nifty-indices-datasets` (GitHub, MIT) — Nifty 50 **2008–present**, monthly binary
  in/out indicator (not full weights), plus Nifty Midcap 50/Smallcap 50/Nifty500-Momentum-50 from
  2019/2024. Explicitly built from official media releases + NSE circulars — confirms C1's
  approach is viable. Free.
- Hugging Face `AMP4010/Historical_Nifty_50_Constituent_Weights_20Y` — Nifty 50 **Jan-2008 to
  Aug-2025**, monthly + intra-month reshuffle capture, actual weight percentages,
  corporate-action-adjusted CSV (216 rows × 101 cols, 147KB). **Free for academic/non-commercial
  use under CC BY-NC-SA 4.0** (directly usable for this personal, non-distributed project per the
  project's Rule E license posture); commercial licensing would need contacting the maintainer.
- **Neither covers BANKNIFTY/FINNIFTY/MIDCPNIFTY/NIFTYNXT50** — useful only as a fast-start
  bootstrap/cross-validation set for the Nifty-50 slice while C1 is scraped for the full set.

**C7. niftyhistory.in — Grade B (confirmed real via independent search snippets; direct fetch blocked)**
- Direct `WebFetch` returned 403 both in the original sub-agent pass and in this session's
  follow-up — the site appears to bot-block automated fetches. However, **independently confirmed
  as a real, described resource via DuckDuckGo-indexed snippets in this session's follow-up pass**:
  self-description states *"Download survivorship-bias-free historical constituent lists for
  Nifty 50, Nifty 100, Nifty 200, and Nifty 500. Free CSV data for every rebalancing date since
  [inception]"* and *"Chronological archive of all historical Nifty 50, Nifty 100, Nifty 200, and
  Nifty 500 index rebalancing events since inception."* **Not independently verified by opening
  the actual CSVs** — flagged as a promising Grade-B lead requiring a manual real-browser visit
  before relying on it, and note it does **not** claim BANKNIFTY/FINNIFTY/MIDCPNIFTY/NIFTYNXT50
  coverage (only Nifty 50/100/200/500).

**C8. Wayback Machine spot-checks — Grade A technique, effortful if used as primary method**
- Confirmed working via the Internet Archive's availability API
  (`archive.org/wayback/available?url=...&timestamp=...`): snapshots exist for niftyindices.com
  (Sep-2017) and old nseindia.com historical-index-data pages (Sep-2011). Useful only as a manual
  cross-check against the C1-derived membership list, not as a primary reconstruction method.
  Note: `WebFetch` in this environment explicitly refuses `web.archive.org` URLs directly — use
  the availability API + a different fetch path, or a real browser, if this technique is used.

**C9. Paid vendors — Grade A but cost-prohibitive, confirmed not needed**
- Bloomberg Terminal `MEMB` function has well-documented index-membership-history capability
  (e.g., Harvard Baker Library's Bloomberg guide) — institutional-subscription cost, not
  independently re-priced this session (general industry figure ~$24,000+/yr/seat, **not
  confirmed this session**). Refinitiv/LSEG Eikon has an equivalent documented capability
  (`developers.lseg.com` article on building historical index constituents, not fetched/read this
  pass). **No evidence found of niftyindices.com selling a discrete historical-constituents data
  product separate from the free C1 press-release archive** — the free official channel appears
  to be the de facto distribution path even for institutional users.

**C10. Academic papers — found in this session's follow-up (the original sub-agent pass found zero)**
- "Market Reaction to Index Reconstitutions: Evidence from NSE NIFTY Additions and Deletions"
  (ResearchGate, `researchgate.net/publication/396771284`) — event-study methodology, 92
  addition/deletion events identified across 2010–2024. Focused on price-impact analysis, not a
  reusable point-in-time dataset, but confirms an independently-compiled 2010–2024 event list
  exists in the literature (useful as a cross-check count: ~92 events over 14 years ≈ 6-7/year
  across the indices studied).
- "How Does Inclusion in The Nifty 50 Index Influence Company Stock Performance" (IJAR, PDF) and
  an Indian Energy-Oil-Gas sector reconstitution VAR-analysis paper (IJSSR, PDF) — both
  reconstitution-impact studies, not membership-data sources.
- **Grade B/C** (not independently verified beyond the search snippet + title; would need a full
  fetch/read pass if used for anything beyond a sanity-check event count).

### Classification summary — Sub-topic C

| Bucket | Item |
|---|---|
| **READILY AVAILABLE** | `niftyindices.com/press-release` (C1) — free, official, 1,027 releases, Sep-1998→present, all 5 target indices from each one's real launch date; Hugging Face + GitHub Nifty-50-only pre-parsed datasets (C6) as a fast-start bootstrap |
| **ACHIEVABLE BUT EFFORTFUL** | Scraping + `pdftotext`-parsing ~1,027 PDFs into a clean structured event table (format drift across 28 years, needs per-era rules + manual QA); NSE F&O circulars (C2) and third-party mirrors (C5) as a revision-tracking cross-check layer; niftyhistory.in (C7) needs a manual real-browser confirmation before being trusted as a shortcut |
| **HARD BLOCKER** | None for the core question. Paid vendor pricing (C9) unverified but unnecessary given C1. A single academic-paper search attempt was made in the follow-up (found 3 relevant papers, none a reusable dataset) — not exhaustively ruled out with a full Google Scholar/SSRN pass, but low-priority given C1 fully answers the need |

---

## Cross-cutting synthesis

1. **All three sub-topics resolve to the same underlying pattern:** NSE/NSE-Indices publish the
   ground-truth data free and first-party, but as either (a) a daily bulk file with no
   interpretation needed (bhavcopy — A1/B1, the strongest pattern) or (b) a large set of
   individually-dated PDF documents with no bulk index (circulars/press-releases — A3/C1/C2, the
   "achievable but effortful" pattern). The project should prefer (a)-style sources wherever they
   exist (fully true for B, the F&O case) and budget real one-time scrape-and-parse engineering
   for (b)-style sources (true for A's delisting circulars and C's index press releases).
2. **The single biggest technical obstacle across all three sub-topics is not data availability
   but NSE's site infrastructure**: `nseindia.com`'s main pages are Akamai-bot-protected,
   JS-rendered SPAs that block stateless fetch tools outright (confirmed 403/timeout repeatedly),
   while the `archives.nseindia.com`/`nsearchives.nseindia.com` static-file subdomains and the
   `/api/circulars` endpoint are reliably fetchable with a plain browser-like User-Agent header.
   **Production implementation should always target the `archives`/`nsearchives` static paths and
   the discovered `/api/*` endpoints, never the JS-rendered `www.nseindia.com` pages directly**,
   and should use a real headless-browser session only for the handful of pages that have no
   static-file equivalent (e.g. `delisted.xlsx`'s parent page, if it turns out to need one).
3. **Cross-linking matters**: this pass's sub-topic A initially flagged the symbol/ISIN-rename
   problem as an unsolved hard blocker — it is not; `research/56` (researched the same day, a
   different angle of the same overall universe-registry need) already solved it via
   `symbolchange.csv`. This is a concrete illustration of why `docs/research/` cross-linking
   matters (Rule D/H) — a later pass can supersede an earlier pass's blocker without anyone having
   to re-derive it, as long as both are findable from the index.
4. **The Satyam case (A, §"assessment") is the sharpest concrete argument for tracking universe
   membership by ISIN, not by trading symbol** — a company can be renamed and continue trading for
   years before an eventual merger, and a naive symbol-presence check would misclassify this as an
   early delisting. This should be a explicit design constraint on whatever reconstruction module
   gets built from this research.

## What was NOT covered / needs a follow-up pass

- **`delisted.xlsx`** (A2) — a promising lead, SSL-errored on `www1.nseindia.com` this session;
  needs a manual real-browser retry or a Playwright-based fetch to confirm content/coverage.
- **Suspension-vs-delisting bhavcopy behavior** — no source found either confirming or denying
  whether a trading-suspended (but not delisted) stock disappears from daily bhavcopy the same way
  a delisted one does; must be tested empirically against a known SEBI-suspension case before the
  bhavcopy-presence heuristic can be trusted for this distinction.
- **ISIN-extinguishing merger/amalgamation swap-ratio records** (A5, per `research/57`) — confirmed
  genuinely hard; no free bulk source found; would need either a paid vendor or per-event manual
  sourcing for the (smaller) subset of the universe that actually merged.
- **niftyhistory.in and exchangecirculars.com** (C7, C5) — both bot-blocked to automated fetch
  this session but plausibly real/useful; need a manual real-browser confirmation pass.
- **Exact Bloomberg/Refinitiv India-index-membership pricing** — not independently re-verified
  this session (general industry figures only); low priority since free official paths (C1, B1)
  already fully answer the need.
- **A full Google Scholar/SSRN academic-literature sweep for Nifty reconstitution research** — only
  a single DuckDuckGo-snippet pass was run in the follow-up; not exhaustive, though low-priority
  given C1 already fully solves the data-access question.
