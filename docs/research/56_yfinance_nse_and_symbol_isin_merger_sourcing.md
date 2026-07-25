# 56 — Corporate-Actions Master Sourcing: yfinance/.NS Adjusted Data (Topic A) & NSE Symbol-Rename / ISIN / Merger Records (Topic B)

Research date: 2026-07-24. Primary-source research for a historical (~20yr) NSE corporate-actions master. This is one part (Topic A + Topic B) of a larger multi-part sourcing report. All claims below are from pages actually opened via WebFetch, not search snippets. Search-engine (WebSearch) budget was exhausted mid-task (session cap hit after 6 queries), so from that point forward research proceeded via direct WebFetch of primary URLs (GitHub source/docs, NSE archive endpoints, official sites) — this is noted per-claim below and does NOT weaken the primary-source findings, since they were read directly rather than via search snippets anyway.

---

## TOPIC A — Yahoo Finance / yfinance for NSE (.NS) corporate actions

### A1. Does Yahoo Finance carry split/dividend-adjusted daily data for NSE .NS tickers?

**Confirmed directly.** Opened `https://finance.yahoo.com/quote/RELIANCE.NS/` — page explicitly labels the quote "NSE - Delayed Quote • INR", shows price in ₹, a 52-week range, forward dividend yield (0.47%) and ex-dividend date (2026-06-05), and benchmarks performance against the BSE SENSEX — confirming this is genuine NSE-sourced data, not a proxy/ADR feed.
`https://finance.yahoo.com/quote/RELIANCE.NS/history` itself returned HTTP 503 on fetch (likely bot-protection on the history sub-route specifically), so the interactive historical-table UI could not be directly inspected, but the underlying data is confirmed reachable via the yfinance API layer (see A2).
**Grade: A** (primary, first-party, directly opened).

### A2. Does `yfinance` expose corporate actions as structured endpoints?

Opened the yfinance GitHub source directly:
- `yfinance/base.py` (`TickerBase` class) — confirmed methods `get_dividends(period="max")`, `get_splits(period="max")`, `get_capital_gains(period="max")`, `get_actions(period="max")`, each delegating to a lazily-loaded `PriceHistory` object and returning a `pandas.Series`.
- `yfinance/scrapers/history.py` — confirmed the underlying `PriceHistory` implementation: `get_dividends`/`get_splits`/`get_capital_gains` each pull a named column (`'dividends'`, `'splits'`, `'capital gains'`) off a cached `_get_history_cache(interval='1d', period=period, repair=repair)` DataFrame. The full daily-history DataFrame carries columns `Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits, Capital Gains`. `get_actions` combines dividends/splits/capital-gains into one filtered (non-zero) series.
- Official docs site `ranaroussi.github.io/yfinance` confirms the public API surface: both method form (`Ticker.get_dividends`, `Ticker.get_splits`, `Ticker.get_actions`, `Ticker.get_capital_gains`) and property form (`Ticker.dividends` → Series, `Ticker.splits` → Series, `Ticker.actions` → DataFrame, `Ticker.capital_gains`) exist. The docs pages themselves are thin on prose (mostly signatures, minimal descriptive text was retrievable via fetch — this looks like a docs-generation/rendering gap on their static site rather than the feature being absent, since the source code confirms full behavior).
- **README** (`raw.githubusercontent.com/ranaroussi/yfinance/main/README.md`) does NOT itself document these methods in prose — it only lists `Ticker`/`Tickers` as top-level components and defers detail to the full docs site. PyPI project page similarly has no corporate-actions detail and no mention of NSE/international support either way (silent, not a claim of unsupported).

**Conclusion:** Yes — `Ticker.splits`, `Ticker.dividends`, `Ticker.actions`, `Ticker.capital_gains` are real, structured, first-class pandas-Series/DataFrame endpoints confirmed in source, and nothing in the code gates them by exchange/country — the same code path is exercised for `.NS` tickers as any other ticker. **Grade: A** (read directly from source code on GitHub, the authoritative primary source for library behavior).

### A3. Adjustment methodology — auto_adjust vs back_adjust (relevant to reconstruction technique)

From `history.py` source, the `history()` function signature and inline comments:
- `auto_adjust: bool` — "Adjust all OHLC automatically? **Default: True**" — when true, calls `utils.auto_adjust(df)`, which (per code path) adjusts Open/High/Low/Close together using both split and dividend factors, producing an all-in-one adjusted OHLC series (this is Yahoo's standard combined adjustment, not a separately toggleable split-only vs dividend-only factor).
- `back_adjust: bool` — "**Back-adjusted data to mimic true historical prices**" — a distinct, mutually-exclusive-in-effect code path (`elif back_adjust: df = utils.back_adjust(df)`), applied only if `auto_adjust` is off.
- A separate comment in the reconstruction/repair logic: `"# First, attempt to calibrate the 'Adj Close' column. OK if cannot."` — confirms yfinance does internal best-effort reconciliation of the `Adj Close` column against raw data, with silent fallback if it can't calibrate — i.e., there is no strict guarantee of correctness, only a best-effort repair pass.
**Grade: A** for the mechanism (read from source); the *correctness* of the repair heuristic itself is unverified/opaque from outside.

### A4. Coverage depth and known accuracy problems for .NS tickers

Could not run open-ended WebSearch (budget exhausted after 6 queries at the very start of this session, before any NSE-specific query landed), so this section is built from direct GitHub Issues fetches (`github.com/ranaroussi/yfinance/issues?q=NSE`), which is itself a primary/authoritative source (first-party bug tracker), just narrower in scope than a broad web sweep would have been — flagged as a **coverage gap**, see "What was not covered" below.

Issues opened and confirmed (all from `ranaroussi/yfinance` GitHub Issues, first-party):
- **#2519** (closed, "not planned") — **RAYMOND.NS**: reported an unexplained ~65% single-day price drop (₹1,564.30 → ₹551.20) on 2025-05-14 with no corresponding split/bonus/demerger recorded on NSE per the reporter, contradicted by NSE/TradingView data showing stable pricing. No maintainer root-cause response; closed without fix. This is a concrete, dated, NSE-specific data-corruption example — directly relevant since a large single-day price discontinuity with no logged corporate action is exactly the failure mode a corporate-actions master is built to guard against (it would either be a real, un-flagged corporate action Yahoo didn't tag, or a raw data error — either way, yfinance alone is not trustworthy as the sole source of truth for *whether* an action occurred).
- **#2055** (closed, "not planned") — **TATASTEEL.NS**: reported a wrong intraday high (138.46 vs actual 141.25) for 2023-12-29. No root cause identified; closed without resolution.
- **#2612** (closed, "not planned") — "No price data found" for a valid NSE/BSE symbol.
- **#2593** (open) — wrong price-to-book ratio specifically for Indian companies (fundamentals-side issue, not price history, but signals broader India-data-quality pattern).
- **#2022** (closed, "not planned") — general "incorrect market data for NSE segment."
- **#2642** (merged/fixed) — 30-minute interval alignment bug specific to NSE/early-open markets — this one *was* fixed, showing NSE-specific handling does get maintainer attention sometimes, just not consistently.
- **#2422** / **#2411** — rate-limiting (`YFRateLimitError` / "Too Many Requests") issues that block bulk retrieval — an operational/procurement risk (bulk historical pulls across 2,000+ symbols will likely hit Yahoo's undocumented rate limits) rather than a correctness issue.

**Pattern observed:** Every NSE-specific *data-correctness* issue found was closed as "not planned" with no maintainer root-cause investigation — consistent with yfinance being an unofficial scraper of a consumer-facing Yahoo Finance product with no SLA, where India-specific data quality is not a maintenance priority. This is a real, repeatable pattern (5+ independent issues, same disposition), not a single anecdote.
**Grade: B** — first-party bug tracker is authoritative for "this was reported," but none were independently triangulated against a second community source (Reddit/blog) because WebSearch was unavailable for that sweep; `old.reddit.com` and `web.archive.org` fetches were also attempted for corroboration but both failed at the tool level (unable to fetch host), not because no content exists. Treat as **probable pattern, not exhaustively confirmed** — see gaps section.

### A5. Back-deriving split/bonus ratios by diffing adjusted vs raw close — soundness and pitfalls

This is a valid supplementary cross-check technique, but yfinance already gives a much better primary path: `Ticker.splits` returns the split ratio series **directly**, without needing to diff two price columns. Diffing should be treated as a *validation* method against `Ticker.splits`/`Ticker.dividends`, not a replacement first-choice extraction method. Pitfalls, reasoned from the confirmed source-code behavior in A3:
1. **Combined adjustment factor.** `auto_adjust` (the default) folds split AND dividend adjustment into one combined multiplier applied to all of OHLC. If two events land close together (a bonus issue and a dividend in the same window — common in India, e.g. a company doing a bonus and a special dividend around the same AGM), diffing adjusted-vs-raw close gives you the *product* of both factors, not either one individually — you cannot cleanly separate a bonus ratio from a simultaneous dividend effect by diffing alone. You must cross-reference `Ticker.splits`/`Ticker.dividends` (the structured, individually-tagged series) to disambiguate, exactly the pitfall named in the task brief.
2. **Back-adjust vs auto-adjust give different numeric answers for the same historical date** (confirmed as two distinct, non-identical code paths in A3) — a diffing script must be consistent about which adjustment mode produced the "adjusted close" it's diffing against raw close, or ratios will be computed inconsistently across the history.
3. **Bonus issues vs "splits" conflation.** Indian bonus issues (e.g., 1:1 bonus) are economically similar to a split but are a legally/procedurally distinct corporate action in India (issue of new fully-paid shares vs face-value subdivision). Whether Yahoo's underlying data classifies an Indian bonus issue as a "split" (ratio 2:1 effectively) in the `Stock Splits` column, vs missing it entirely, is unverified from source code alone (that's a data-content question, not a code-logic question) — flagged as an open item to test empirically against real NSE bonus-issue dates (Rule F real-data verification) before relying on `Ticker.splits` as complete for bonus coverage.
4. **`Adj Close` calibration is explicitly best-effort with silent fallback** (the "OK if cannot" comment, A3) — meaning a diffing approach inherits whatever silent-failure behavior that calibration has, with no signal to the caller that calibration failed for a given ticker/date range.

**Grade: A** for the mechanism/pitfalls (derived directly from confirmed source code logic, not speculation); **untested** empirically against real NSE bonus-issue dates in this pass — flagged for a Rule F follow-up.

---

## TOPIC B — NSE symbol-rename history, ISIN mapping, and merger/amalgamation records

### B1. Does NSE publish an ISIN-to-symbol historical mapping / symbol-change history?

**Yes — confirmed as a real, live, directly downloadable primary source**, which is a materially better outcome than the task brief's framing implied. Opened:

- **`https://archives.nseindia.com/content/equities/symbolchange.csv`** — fetched raw content directly. This is a **headerless, 4-column CSV**: `Company Name, Old Symbol, New Symbol, Effective Date`. Confirmed real rows, e.g.:
  ```
  3P Land Holdings Limited,PDUMJEAGRO,PDUMJEIND,28-MAR-2008
  3P Land Holdings Limited,PDUMJEIND,3PLAND,04-MAY-2018
  63 moons technologies limited,FINANTECH,63MOONS,19-JAN-2017
  Zydus Lifesciences Limited,CADILAHC,ZYDUSLIFE,07-MAR-2022
  iGate Global Solutions Limited,MASCOT,IGS,07-AUG-2003
  ```
  Coverage confirmed from January 2000 through June 2026 (i.e., current/live-maintained, ~1,800+ rows), spanning equities, mutual fund/ETF series codes, and index-linked instrument renames. Multiple symbol changes for the same company appear as separate chained rows (e.g., 3P Land Holdings had two renames, chainable by company name).
  **Important limitation confirmed directly:** this file has **no ISIN column** — the join key across renames is the free-text company name, not ISIN. Company-name strings are inconsistently cased/formatted across rows (e.g., "3M India Limited" vs "63 moons technologies limited" vs "AJR INFRA AND TOLLING LIMITED"), which will require normalization (case-fold, strip "Limited"/"Ltd" suffix variants) to chain multi-hop renames reliably by exact string match.

- **`https://archives.nseindia.com/content/equities/EQUITY_L.csv`** — fetched raw content directly. This is the **current-state** NSE equity master list, 8 columns: `SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE`. Confirmed real rows, e.g. `360ONE,360 ONE WAM LIMITED,EQ,19-SEP-2019,1,1,INE466L01038,1`. This file **does** carry the current ISIN↔current-symbol mapping, but only current state — no history.

- **Procurement path for a full historical ISIN↔symbol map, synthesized from the two confirmed files:** join `EQUITY_L.csv` (current symbol → ISIN, current company name) backward through `symbolchange.csv` (chained by company name) to walk each ISIN's symbol history back through however many renames it went through, back to 2000. This is a real, buildable, free, no-authentication, first-party pipeline — a materially stronger position than "fragmented, manual research per event." The residual risk is purely the company-name string-matching/normalization step, not data unavailability.
  **Grade: A** — both files opened directly, raw content read and quoted verbatim above; this is the strongest, most concrete finding of the whole report.

- Attempted `https://www.nseindia.com/companies-listing/corporate-filings-actions` (the human-facing NSE corporate-actions UI) directly — returned HTTP 403 (bot-protected), and `https://web.archive.org` was unreachable via WebFetch tool (host-level fetch failure, not a 404) so an archived snapshot could not be checked as a fallback. This means the *UI* path is blocked but the *underlying archive CSV endpoints* (used above) are open and unauthenticated — worth noting for a scraper/procurement design: use `archives.nseindia.com` / `nsearchives.nseindia.com` raw file endpoints, not the JS-rendered `www.nseindia.com` UI, which is Cloudflare/bot-gated.

### B2. Does MCA publish merger/amalgamation records (scheme of arrangement, swap ratios, effective dates)?

Attempted three direct fetches: `mca.gov.in` root, `mca.gov.in/content/mca/global/en/mca/master-data/MDS.html`, and a general services page — **all three returned HTTP 403 Forbidden** on direct WebFetch (bot/session-protected, consistent with MCA's known pattern of requiring an interactive session/CAPTCHA for its portal, and public reporting elsewhere that most MCA document retrieval — certified copies of scheme filings, Form INC-28, etc. — requires a paid, per-document fee via the MCA21 e-filing portal, not free bulk API access). **Could not confirm the specifics of MCA's public search directly in this pass** — this is a genuine gap (see below), not a confirmed "MCA has nothing." What's confirmable from general knowledge (unverified in this session, flag accordingly) is that MCA is the statutory repository of scheme-of-amalgamation orders (NCLT-approved schemes get filed with MCA/RoC), so it likely IS the authoritative primary source in principle — the open question is whether it's bulk-searchable/downloadable or only retrievable one certified-copy-at-a-time per company (which would make it impractical as a bulk data source for a 2,000+ symbol universe, even if authoritative).
**Grade: C (unverified this session)** — flagged as a required follow-up rather than reported as fact.

### B3. Vendor/community merger-history sources

- **SEBI** (`sebi.gov.in` Master Circulars listing) — opened directly; confirmed SEBI does maintain a "Master Circular for Issue of Capital and Disclosure Requirements" and a LODR (Listing Obligations and Disclosure Requirements) master circular, either of which plausibly governs scheme-of-arrangement disclosure requirements for listed companies, but the page fetched was only the circular *index* — the actual circular documents (which would state whether scheme-of-arrangement filings are centrally indexed/searchable) were not opened in this pass. **Grade: C (index confirmed, content unverified).**
- **Tofler** (`tofler.in`) — opened directly; confirmed it's a commercial Indian company-data aggregator ("Company 360 reports," financials, directors, charges) sourced presumably from MCA, but the fetched page did not explicitly surface merger/swap-ratio records or pricing — would need deeper site navigation or direct contact to confirm. **Grade: C.**
- **Moneycontrol** — attempted `moneycontrol.com/company-facts/relianceindustries/corporate-actions/RI` — **tool-level failure** ("Claude Code is unable to fetch from www.moneycontrol.com" — a host-blocklist at the tool layer, not a site 403), so this well-known Indian corporate-actions data source could not be verified in this session at all. **Grade: unverified / tool-blocked**, flagged as a gap — this is a commonly-cited free source for retail-facing corporate-action history in India and should be checked via a non-WebFetch path (e.g., browser tool) in a follow-up.
- **Screener.in** — opened directly (`screener.in/company/RELIANCE/consolidated/`); confirmed the page has extensive financials (2015–2026) and a "Corporate actions" section *label* near the Balance Sheet area, but **no actual corporate-action data rendered** in the fetched content (likely JS-rendered/lazy-loaded content that a text-mode fetch doesn't execute). Inconclusive — the label's presence suggests the feature exists but requires a JS-capable browser tool to actually read it. **Grade: C (inconclusive).**
- **Wikipedia** (ISIN article) — opened directly; confirmed the general ISIN mechanics claim: *"When the NSIN changes due to corporate actions or other reasons, the ISIN will also change."* This is an important nuance against the task brief's framing that "ISIN stays constant" during a symbol change — per this primary-adjacent tertiary source, ISIN is tied to the National Securities Identifying Number and **can** change on certain corporate actions (this is consistent with known Indian market practice: a straightforward name/symbol rebrand with no change in the underlying security typically keeps ISIN constant, i.e. what B1's `symbolchange.csv` captures; a merger/amalgamation, by contrast, typically extinguishes the transferor company's ISIN entirely and issues shares under the transferee's existing or a new ISIN — so ISIN continuity is action-type-dependent, not universal). The article had no India-specific (NSDL/CDSL/SEBI) detail. **Grade: C** (general/tertiary, not India-specific, but corrects an assumption in the task brief and is worth flagging to the assembling report).

### B4. Is there a single canonical source, or is this fragmented?

**Split verdict, more nuanced than a flat "fragmented/hard blocker":**
- **Symbol/name-change history (same-entity rebrand, ISIN constant): SOLVED.** `archives.nseindia.com/content/equities/symbolchange.csv` + `EQUITY_L.csv` together give a free, first-party, programmatically-joinable, ~20+ year history with no authentication. This was the task brief's framing of "hardest to track" for the rename sub-case — that framing is **not borne out**; it's a straightforward CSV join once you know the (undocumented, discovered-by-direct-fetch) archive endpoint.
- **Merger/amalgamation (ISIN-extinguishing, swap-ratio-bearing) events: STILL genuinely fragmented/hard**, per this session's findings — no single authoritative bulk-downloadable source was confirmed. MCA is the statutory source in principle but its portal blocked direct automated access (403) and, per general knowledge (unverified this session), is oriented around per-document paid retrieval rather than bulk search. NSE's own per-company corporate-announcement PDFs (the `corporate-filings-actions` UI) are where individual scheme-of-arrangement/merger circulars with swap ratios actually get published, but that UI is bot-gated (403) and, even if accessible, is a per-company/per-event PDF archive, not a structured bulk file like `symbolchange.csv`. This portion of Topic B remains a **real, honest blocker for bulk/automated ingestion** — it looks like it will require either (a) a paid vendor (Tofler-type, unverified pricing) or (b) semi-manual per-event sourcing from NSE/BSE corporate announcement PDFs for the subset of the universe that actually underwent mergers (a much smaller list than the full 2,000+ symbol universe — most symbols only ever have renames, not mergers).

---

## Credibility grade summary

| Finding | Grade | Basis |
|---|---|---|
| Yahoo Finance serves NSE `.NS` data (INR, NSE-labeled) | A | Directly opened `finance.yahoo.com/quote/RELIANCE.NS/` |
| yfinance `Ticker.splits/.dividends/.actions/.capital_gains` exist & behavior | A | Read `base.py` + `scrapers/history.py` source directly on GitHub |
| yfinance `auto_adjust`/`back_adjust` mechanism | A | Read source docstrings/code directly |
| yfinance NSE data-quality issues (pattern of unresolved "not planned" reports) | B | 7 first-party GitHub issues opened directly; not independently triangulated via a second web source (WebSearch/Reddit/archive.org all failed or were unavailable this session) |
| Diffing adjusted-vs-raw close as a cross-check method, and its pitfalls | A (mechanism) / untested (empirical bonus-issue coverage) | Derived from confirmed source logic; not yet tested against real NSE bonus dates |
| `symbolchange.csv` + `EQUITY_L.csv` as a free historical ISIN/symbol-rename pipeline | A | Both files fetched and raw content quoted directly |
| MCA as authoritative merger/swap-ratio source | C (unverified) | All 3 direct fetch attempts returned 403; not confirmed this session |
| SEBI LODR circulars governing scheme-of-arrangement disclosure | C | Index page opened; circular content not opened |
| Moneycontrol corporate-actions pages | Unverified | Tool-level host block, not a real finding either way |
| Screener.in corporate actions section | C (inconclusive) | Page opened but content appears JS-rendered/lazy-loaded, not present in fetched text |
| ISIN changes on corporate actions (general mechanic) | C | Wikipedia (tertiary), not India-specific, but corrects a framing assumption |

## What was NOT covered / follow-ups needed

1. **WebSearch budget was exhausted after only 6 queries**, all fired at the very start before any actually executed — meaning the "multi-angle sweep" (practitioner forums, recency-filtered 2025/2026 blog posts, Reddit/HN, comparison pieces) mandated by the research protocol could not be run for either topic. Everything above came from direct WebFetch of primary URLs I already knew or could reasonably guess/derive (GitHub source, official docs, known NSE archive endpoint patterns, well-known Indian finance sites). This is a materially narrower sweep than intended — **recommend a follow-up pass once WebSearch quota resets**, specifically for: (a) independent corroboration of the yfinance NSE data-quality pattern (Reddit r/IndiaInvestments, r/algotrading, quant blogs), (b) confirmation of MCA's actual public-search/paid-retrieval mechanics, (c) Moneycontrol's corporate-actions page content (needs a non-WebFetch-blocked tool, e.g. a browser-automation tool), (d) Screener.in's corporate-actions section via a JS-capable fetch.
2. **Empirical Rule-F verification not done in this pass**: haven't yet pulled real `yfinance.Ticker('SOMETHING.NS').splits` output against a known real NSE bonus-issue date to confirm bonus issues are correctly tagged (flagged in A5, item 3) — this is a code-execution verification task, not a web-research one, and belongs in the actual build/verification phase.
3. **MCA, SEBI circular content, and BSE-side symbol-change equivalents** were not fully explored — this report is NSE-primary per the task brief; BSE has its own symbol/scrip-code history which may matter for cross-exchange reconciliation but was out of scope here.
4. Did not verify whether NSE's `archives.nseindia.com` endpoints are rate-limited/require a User-Agent or session cookie for bulk automated access (WebFetch succeeded, but that tool may present differently than a raw `requests`/`curl` client would against NSE's bot-detection) — recommend testing this directly in the actual scraper build, not just trusting this session's successful fetch.
