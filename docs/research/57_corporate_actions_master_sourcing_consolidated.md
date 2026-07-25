# Corporate-Actions Master Sourcing (NSE, ~20yr) — Consolidated Findings

**Date:** 2026-07-24
**Goal:** Source a historical corporate-actions master (splits / bonus / dividends / rights / renames / mergers) for NSE-listed equities going back ~20 years, to align a raw tick-price archive so price *continuity* stays correct across each action while the UNADJUSTED point-in-time print is still preserved.
**Method:** Primary-source web research across 4 parallel agents. WebSearch quota was exhausted early in every agent's run, so findings lean on direct WebFetch / raw-HTTP verification of live endpoints and GitHub source — stronger than search snippets, but with fewer secondary cross-checks (flagged below).
**Companion detail files:** `56_corporate_actions_vendors_ace_capitaline_trendlyne.md`, `56_yfinance_nse_and_symbol_isin_merger_sourcing.md`.

---

## Bottom line

The corporate-actions master is **buildable for free from NSE + BSE first-party endpoints, back to 1995** — this is NOT a hard blocker. Two verified free pipelines cover the bulk of the need:

1. **NSE `corporates-corporateActions` API** — full-universe bulk pull, 1995→present, 41,979 records verified in a single call. (Grade A, verified live.)
2. **NSE `symbolchange.csv` archive + `EQUITY_L.csv`** — free first-party symbol-rename history (Jan 2000→present, ~1,800 rows) joinable to the current ISIN master. Renames are effectively SOLVED, contrary to the initial assumption that they'd be the hardest part. (Grade A, verified live.)

**The ONE genuine hard blocker:** ISIN-extinguishing **mergers/amalgamations** with swap ratios and surviving-entity mapping. No free canonical source found (MCA/Moneycontrol/NSE announcement UIs are bot-gated). This affects only the subset of companies that actually merged/delisted, not the full universe — solvable with a paid vendor or semi-manual per-event sourcing.

**Two engineering tasks, not data-access tasks:** (a) both NSE and BSE return the action as a free-text `subject`/`Purpose` string (e.g. `"Face Value Split... From Rs 10 To Rs 2"`, `"Div 30%/Bonus 1:1"`) — 2,600+ distinct variants on NSE — so a robust regex normalizer for action-type + ratio/amount is required; (b) NSE's endpoint is undocumented/reverse-engineered and needs defensive session-cookie priming at production scale.

---

## The 7-item map

### 1. NSE own corporate-actions data — SOLVED, Grade A (verified live)

- **Endpoint:** `https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY[&symbol=XXX][&fo_sec=true]`
- Backs the public page `https://www.nseindia.com/companies-listing/corporate-filings-actions` (JS SPA calling this same API).
- **Verified:** one call for `01-01-1995`→`31-12-2025` (no symbol filter) returned **41,979 records, ~13MB JSON, HTTP 200, no pagination cap**. Earliest record **04-Jan-1995** (consistent with NSE CM segment launch Nov 1994). 1990/1994 queries returned zero.
- **Fields:** `symbol, isin, comp, series, faceVal, subject (free-text), exDate, recDate, bcStartDate, bcEndDate, ndStartDate, ndEndDate, caBroadcastDate`.
- **Format caveat:** action type + ratio live only in the free-text `subject` — needs a parser (2,600+ distinct subject-prefix variants).
- **Cost:** free, no key, no registration. `robots.txt` allows `/`.
- **Caveats:** undocumented endpoint (could change / add anti-bot tokens); prime a session cookie defensively in production. A RELIANCE per-symbol spot-check showed 0 records for 1996–2003 (possible symbol/ISIN-continuity quirk) — the bulk `index=equities` query (no symbol filter) is the safer path and does cover that era market-wide. Validate per-symbol against the full 2,000+ universe (Rule F) before trusting.

### 2. BSE equivalent — SOLVED as cross-check, Grade A (verified live)

- **Endpoint:** `https://api.bseindia.com/BseIndiaAPI/api/CorpactCSVDownload/w?Fdate=YYYYMMDD&TDate=YYYYMMDD&Scripcode=&Purposecode=&strSearch=S&industry=&status=`
- Blank `Scripcode` → **all scrips bulk CSV** (`Corporate_Actions.csv` attachment). Columns: `Security Code, Security Name, Company Name, Ex Date, Purpose, Record Date, BC Start/End, ND Start/End, Actual Payment Date`.
- **Earliest coverage: ~30-Jun-2000** (1990–1999 queries returned zero rows, despite BSE dating to 1875). `Purpose` field is slightly more structured than NSE's `subject` but still free text.
- **Cost:** free, no key (needs `Origin/Referer: bseindia.com`). Same undocumented-endpoint caveat.
- **Role:** cross-validate/backfill NSE from 2000→present. For 1995–2000, NSE is the only free exchange-native bulk source found.

### 3. SEBI — DEAD END, Grade A (verified negative)

- SEBI hosts **no** corporate-actions database. Its public-filings system is an IPO/public-issue (DRHP/RHP/prospectus) repository (~5,721 records); SCORES is investor-grievance. Under LODR, listed-company corporate-action disclosures are filed with and published by the **exchanges** (NSE/BSE — items 1–2), not duplicated at SEBI. Not a usable procurement path.

### 4. OSS tools (jugaad-data / nsepython / nselib) — nselib WINS, Grade A (source read)

| | jugaad-data | nsepython | nselib |
|---|---|---|---|
| Repo | github.com/jugaad-py/jugaad-data | github.com/aeron7/nsepython | github.com/RuchiTanmay/nselib |
| PyPI latest | 0.33.1 (2026-03-16) | 2.97 (2025-05-26) | 2.5.1 (2026-05-01) |
| Corp-actions fn | **No** — only `corporate_announcements()` (free-text filings, wrong endpoint) | **No** (`dividend_timeline()` is rumored but absent — issue #75) | **Yes — `corporate_actions_for_equity()`** |
| Endpoint hit | `/api/corporate-announcements` | none | `/api/corporates-corporateactions?index=equities&...` (the real one) |
| Last commit | 2026-03-16 | 2026-03-07 | **2026-07-18** (most active) |

- **`nselib.corporate_actions_for_equity(from_date, to_date, period, fno_only)`** is the only library wrapping the correct structured NSE actions API; returns a pandas DataFrame. Accepts arbitrary dd-mm-YYYY range (period shorthand caps at `1Y`, but explicit dates span any range; library imposes no cap/chunking). No built-in price-adjustment (issue #77). Real multi-year depth **not empirically verified** (direct NSE probe timed out on anti-bot session) — test against real universe before trusting.
- **Takeaway:** use `nselib` as the wrapper, or hit the endpoint directly (item 1) with your own session handling. jugaad-data/nsepython do not solve corp-actions.

### 5. Paid vendors — no confirmed affordable API CA master, Grade A/B

- **Bloomberg** — ~$24k–32k/yr/seat, enterprise sales only. Ruled out. (Grade B, triangulated.)
- **Refinitiv/LSEG Workspace** — no public pricing, sales-only. Ruled out. (Grade A on procurement.)
- **Ace Equity Nxt** — the one concrete self-serve price: **₹125,000 (~$3,500)/yr onwards** + tax. CA module not explicitly confirmed on terminal; separate ACE Datafeed lists "Corporate Action – BSE EOD" (no pricing, no event breakdown). (Grade A on price, B on CA granularity.)
- **Capitaline** — no published pricing anywhere; CA coverage never itemized. Genuine gap.
- **CMOTS/Accord** — site is JS SPA (didn't render); reseller docs don't mention CA.
- **Screener.in** — ₹0 / ₹4,999/yr, has a Corporate Actions tab (incl. preferential issues) but **no official API**; unofficial GitHub wrapper doesn't expose it.
- **Tickertape** — ₹2,999–₹4,788/yr, only dividends confirmed, no API.
- **Simply Wall St** — India/NIFTY coverage via S&P Global, but no CA product/API found.
- **Trendlyne** — MOST PROMISING lead but **primary-unverified** (site 405-blocked all fetches). Secondary review (findmymoat.com) reports ₹2,190–₹11,900/yr tiers with explicit "dividends, splits, M&A, board meetings" coverage + Excel/Sheets export. **Grade B — flag for manual human-browser follow-up.**
- **Verdict:** no vendor confirmed from primary source to sell a clean, API-accessible, ~20yr, per-event-typed CA master at individual-affordable price. Closest: Trendlyne (verify) and Ace Equity Nxt (~$3,500/yr, verify CA granularity). Given items 1–2 are free, paid vendors are only worth it for the merger/swap-ratio gap (item 7).

### 6. Yahoo Finance / yfinance reconstruction — works as CROSS-CHECK, Grade A/B

- Confirmed `finance.yahoo.com/quote/RELIANCE.NS` serves genuine NSE INR data ("NSE - Delayed Quote").
- `yfinance` (github.com/ranaroussi/yfinance) exposes **structured** `Ticker.splits`, `.dividends`, `.actions`, `.capital_gains` (real pandas objects, not exchange-gated) — read from `base.py`/`scrapers/history.py`. `auto_adjust` (default, split+div) vs `back_adjust` are distinct code paths.
- **Data-quality risk:** 7 first-party GitHub issues show a repeatable pattern of NSE-specific correctness bugs (e.g. RAYMOND.NS spurious 65% single-day drop) closed "not planned." Indian bonus-issue tagging accuracy unverified. (Grade B — not independently triangulated; Reddit/archive fetches failed.)
- **Diffing adjusted-vs-raw close** is sound only as a *cross-check*, not a primary source: combined split+dividend factors can't be disambiguated without the structured `.splits`/`.dividends` series. Use yfinance's structured actions series directly, and use it to VALIDATE the NSE/BSE master rather than to build it.

### 7. Renames / mergers — renames SOLVED, mergers HARD BLOCKER, Grade A

- **Renames — SOLVED (Grade A, verified live):** `https://archives.nseindia.com/content/equities/symbolchange.csv` — free, unauthenticated, ~1,800 rows, Jan 2000→Jun 2026, columns Company Name / Old Symbol / New Symbol / Date. Join to `EQUITY_L.csv` (current Symbol↔ISIN master) for full historical rename tracking keyed on ISIN. This overturns the assumption that renames are the hardest sub-case.
- **Mergers/amalgamations — HARD BLOCKER (honest gap):** ISIN-extinguishing events with swap ratios + surviving-entity mapping have no free canonical source. MCA portal (403), NSE per-company announcement UI (403, bot-gated), Moneycontrol (blocked), Screener.in CA section (JS-rendered, inconclusive). Requires a paid vendor (see item 5) or semi-manual per-event research. Scope is limited to actually-merged companies, not the full universe.

---

## Recommended build path

1. **Primary pull:** NSE `corporates-corporateActions` API, chunked by year 1995→present (avoid one 13MB monolith); prime session cookies defensively.
2. **Cross-validate/backfill:** BSE `CorpactCSVDownload` all-scrip CSV, 2000→present.
3. **Normalize:** regex parser for free-text `subject`/`Purpose` → {action_type, ratio/amount, face_value_from/to}. This is the real engineering effort.
4. **Renames:** join `symbolchange.csv` + `EQUITY_L.csv` on ISIN for a continuous symbol-history spine.
5. **Validate (Rule F):** cross-check the parsed master against yfinance `.splits`/`.dividends`/`.actions` for the full 2,000+ universe; investigate mismatches. Resolve the RELIANCE-era per-symbol anomaly by keying on ISIN not symbol.
6. **Mergers (BACKLOG):** track swap-ratio/surviving-entity events separately; source from a paid vendor (Trendlyne/Ace — verify first) or manually per event. → add to `docs/BACKLOG.md`.
7. Preserve the UNADJUSTED print always; store adjustment factors alongside so continuity is derived, never destructive.

## Confidence & caveats
- **Solid (A, verified live):** NSE actions API (1995+), BSE CSV (2000+), symbolchange.csv, nselib function/endpoint, SEBI dead-end, yfinance structured actions methods exist.
- **Probable (B):** vendor pricing figures, Trendlyne CA coverage, yfinance NSE data-quality concerns.
- **Uncertain / to verify empirically:** true server-side lookback depth of the NSE endpoint across the full universe; per-symbol vs ISIN anomalies; Trendlyne primary verification; Ace CA granularity.

## Not covered
- NSE/BSE official *paid* institutional bulk archives (free endpoints sufficed).
- Legal/ToS risk of scraping undocumented endpoints at production scale.
- Pre-2000 BSE actions (this API doesn't expose that era).
- Two vendor PDFs (Capitaline brochure, CFA Society Accord doc) unreadable — may hold undisclosed pricing.
