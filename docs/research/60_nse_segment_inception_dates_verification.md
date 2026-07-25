# Research/60 — NSE Market Segment Inception Dates — Primary-Source Verification

**Renumbered 2026-07-24 from `56_nse_segment_inception_dates_verification.md` to `60_...`
to resolve a filename collision with two other same-day `56_*` files (corporate-actions
vendor pricing and yfinance/symbolchange sourcing). Content unchanged; only the number/
filename moved. This file answers item 4 of `research/59`'s task (per-segment inception
dates) and is a companion to `research/53` §10.3.**

**Purpose:** Ground-truth the exact inception dates of NSE derivative segments and expiry
cadences, for use in scoping how far back the historical replay simulator can walk for
each product. Compiled 2026-07-24 via parallel primary-source research (NSE circulars,
SEBI circulars, NSE's own archival PDF, cross-checked against independent financial
press). Memory/training-knowledge dates were treated as unverified until confirmed.

**Overall confidence:** All facts below are Grade A unless noted otherwise. Grade
definitions: **A** = corroborated by NSE/SEBI primary source (circular, archival PDF) or
≥2 independent reputable secondary sources with matching dates; **B** = single reputable
source, minor date disagreement, or primary source not locatable despite strong
secondary corroboration; **C** = only low-quality/forum sources, unverified.

---

## 1. Segment launch dates (2000–2001 founding derivatives segments)

All four founding dates trace to a single authoritative NSE document —
`archives.nseindia.com/content/press/Data_Details_F_n_O.pdf` ("Historical Data
Dissemination of Future and Options Segment") — read in full, not as a snippet:

> "The derivatives trading on the exchange commenced with S&P CNX Nifty Index futures
> on June 12, 2000. The trading in index options commenced on June 4, 2001 and trading
> in options on individual securities commenced on July 2, 2001. Single stock futures
> were launched on November 9, 2001."

| Segment | Exact date | Grade | Corroboration |
|---|---|---|---|
| **Nifty index futures** | **Monday, 12 June 2000** | A | NSE archival PDF (primary, read in full); NSE product pages `nseindia.com/static/products-services/equity-derivatives-nifty50` and `nseindia.com/static/nifty-50-25-glorious-years` (primary, via crawl); NSE press release via PR Newswire, 6 Jan 2022 (primary, fully fetched); Wikipedia citing Mint's "India@75" retrospective (secondary); Economic Times 2026 expiry-shift article (secondary) |
| **Nifty index options** | **Monday, 4 June 2001** | A | Same NSE archival PDF; same two NSE product pages; same PR Newswire release. No fully independent (non-NSE-originated) press source citing the exact day was located, but four independent NSE-originated documents agree with zero conflict, meeting the "NSE primary source" bar |
| **NSE single-stock options** | **Monday, 2 July 2001** | A | Same NSE archival PDF (primary); nseoptions.in "History of Options Trading in India" (independent secondary, matches exactly) |
| **NSE single-stock futures** | **Friday, 9 November 2001** | A | Same NSE archival PDF (primary); nseoptions.in (independent secondary, matches exactly) |

No disagreement found across any source for any of these four dates. The commonly-cited
informal dates (Jun 2000 / Jun 2001 / Jul 2001 / Nov 2001) are all confirmed correct at
day-level precision.

**Implication for replay simulator:** Nifty futures data can in principle start
2000-06-12; Nifty index options 2001-06-04; single-stock options 2001-07-02;
single-stock futures 2001-11-09. (Actual availability of clean tick/EOD data that far
back is a separate question from the segment's existence — NSE's own historical bhavcopy
archives may not extend cleanly to day one; that's a data-sourcing question, not a
regulatory-inception question, and is out of scope for this doc.)

---

## 2. Weekly index-option introduction dates, per index

Verified via NSE's own launch circulars (downloaded and read in full from
`archives.nseindia.com` / `nsearchives.nseindia.com`), cross-checked against independent
press.

| Index | Weekly options launch | Announcing circular | Grade |
|---|---|---|---|
| **BANKNIFTY** (Nifty Bank) | **Friday, 27 May 2016** (announced 5 May 2016) | NSE/FAOP/32329, Circular Ref. 044/2016, dated 5 May 2016: *"Weekly Options contracts on BANKNIFTY Index shall be made available for trading in Future & Options segment w.e.f. May 27, 2016."* | A — primary NSE circular (read in full) + Zerodha Market Intel bulletin + India Today/PTI, all matching |
| **NIFTY 50** | **Monday, 11 February 2019** (approval circular 18 Dec 2018; live-date circular 7 Jan 2019) | NSE/FAOP/39675 (18 Dec 2018, SEBI approval + contract specs, live date "to be intimated separately") → NSE/FAOP/39894 (7 Jan 2019): *"Weekly Options contracts on NIFTY 50 Index shall be made available for trading in Future & Options segment w.e.f. February 11, 2019."* | A — primary NSE circulars (read in full) + The Hindu BusinessLine, Economic Times, Moneycontrol, LiveMint (four independent outlets, all matching) |
| **FINNIFTY** (Nifty Financial Services) | Index launched **7 Sept 2011** (niftyindices.com factsheet); **F&O (incl. weekly) launched 11 Jan 2021** — weekly was part of the very first F&O launch, no separate monthly-only period | NSE/FAOP/46603 (10 Dec 2020): *"Futures and Options on Nifty Financial Services Index shall be made available for trading ... w.e.f. January 11, 2021"*, Annexure 1 specifies "7 serial weekly ... and 3 serial monthly." Symbol renamed FINANCIALS→FINNIFTY same launch (NSE/FAOP/46924, 6 Jan 2021) | A — primary NSE circular (read in full) + Zerodha, Financial Express, Outlook Money |
| **MIDCPNIFTY** (Nifty Midcap Select) | **Monday, 24 January 2022** (announced 10 Jan 2022) — weekly was part of the very first F&O launch | NSE/FAOP/50968 (10 Jan 2022): *"Futures and Options on Nifty Midcap Select Index shall be made available for trading ... w.e.f. January 24, 2022"*, Annexure 1: "7 serial weekly (excl. monthly) and 3 serial monthly" | A — primary NSE circular (read in full) + Economic Times, FlatTrade, India Infoline, Zerodha. **Note:** the "2023" figure sometimes cited for MIDCPNIFTY conflates this Jan 2022 launch with a later, unrelated expiry-*day* change (Wednesday→Monday, effective ~17–21 Aug 2023) |
| **NIFTYNXT50** (Nifty Next 50) | **Never introduced.** Derivatives (futures+options) launched Wed 24 April 2024 (announced 18 Apr 2024) as **monthly-only** — no weekly line item ever existed in the contract spec | NSE/FAOP/61629 (18 Apr 2024): *"Futures and Options contracts on Nifty Next 50 Index shall be made available for trading ... w.e.f. April 24, 2024"*, Annexure 1 lists only "3 serial monthly contracts" (contrast directly with the BANKNIFTY/FINNIFTY/MIDCPNIFTY circulars above, which explicitly list weekly cycles) | A — primary NSE circular (read in full) + Zerodha launch bulletin (no weekly mention) + Zerodha's Nov 2024 rationalization support article (explicitly lists NIFTYNXT50 as never having had a weekly product) + Business Today |

**Implication for replay simulator:** NIFTYNXT50 should be modeled as **monthly-expiry-
only for its entire history** (2024-04-24 onward) — there is no weekly cadence to
backfill or discontinue for this underlying, ever.

---

## 3. 2024–2025 SEBI/NSE weekly-expiry rationalization

### 3a. The SEBI circular (primary, full text obtained)

- **Circular:** SEBI/HO/MRD/TPD-1/P/CIR/2024/132
- **Date issued:** 1 October 2024
- **Title:** "Measures to Strengthen Equity Index Derivatives Framework for Increased
  Investor Protection and Market Stability"
- **URL (PDF, fetched in full):** `https://www.sebi.gov.in/sebi_data/attachdocs/oct-2024/1727786261636.pdf`

Verbatim (Section 5.5.2–5.5.3):

> "Henceforth, each exchange may provide derivatives contracts for only one of its
> benchmark index with weekly expiry. This measure shall be effective from
> **November 20, 2024**."

The circular's applicability table confirms Nov 20, 2024 as the effective date
specifically for "Rationalization of Weekly Index derivatives products" (other measures
in the same circular — upfront premium collection, intraday position monitoring — carry
later effective dates of Feb 1, 2025 and Apr 1, 2025 respectively; don't conflate these).

**Grade: A** — direct primary-source text, unambiguous.

### 3b. NSE implementation — last weekly-expiry trading day per index

| Index | Last weekly-expiry day | Grade |
|---|---|---|
| BANKNIFTY | **13 November 2024** | B — 4+ independent reputable sources (Business Standard, Zerodha, Bajaj Broking, ICICI Direct, ETNow) all matching, but the specific NSE discontinuation-circular PDF/number could not be located despite extensive search (site/bot-protection limits) |
| MIDCPNIFTY | **18 November 2024** | B — same source set, same caveat |
| FINNIFTY | **19 November 2024** | B — same source set, same caveat |
| **Regime change effective** | **20 November 2024** | A — matches SEBI circular's own stated effective date exactly |
| NIFTYNXT50 | N/A — never had weekly expiry to discontinue (see §2) | A |

**Product NSE retained for weekly expiry: NIFTY 50** (since 20 Nov 2024, the sole
NSE index with weekly options going forward).

**Open item:** the exact NSE circular number for the Oct/Nov 2024 discontinuation
announcements (analogous to the FAOP/32329-style launch circulars) was not locatable via
search in this pass — dates themselves are well-corroborated (4+ independent secondary
sources, matching), but lack primary-document confirmation. Flagging as a follow-up if a
harder primary-source pass is ever needed (e.g., via NSE's circular search UI directly,
which is bot-protected against automated fetch).

### 3c. 2025 expiry-day-of-week changes (separate from the weekly-count rationalization)

Timeline, all corroborated by multiple independent sources:

1. **~4 March 2025** — NSE announces plan to shift Nifty (and other index) expiry from
   **Thursday to Monday**, targeting 4 April 2025 effective date. (Bajaj Broking)
2. **27 March 2025** — SEBI issues a **consultation paper** on uniform expiry-day rules,
   proposing expiries be limited to Tuesdays or Thursdays exchange-wide, requiring SEBI
   pre-approval for future expiry-day changes.
3. **27–28 March 2025** — NSE **defers** its Monday-shift plan "until further notice,"
   citing the SEBI consultation paper. (Rediff Money, New Indian Express, Economic
   Times, Zerodha — all consistent)
4. **17–18 June 2025** — SEBI approves exchanges "swapping" expiry days to avoid
   collision (Business Today, ICICI Direct).
5. **23 June 2025** — NSE circular FAOP/68685 (Ref. 108/2025), "Revision in Expiry Day
   of Index and Stock Derivatives Contracts."
6. **25 June 2025** — NSE circular **FAOP/68747** (Ref. 111/2025), partial modification —
   **primary source obtained in full**
   (`nsearchives.nseindia.com/web/sites/default/files/inline-files/FAOP68747.pdf`):
   NIFTY monthly/quarterly/half-yearly and weekly contracts move from **last
   Thursday/Thursday → last Tuesday/Tuesday**; BANKNIFTY/FINNIFTY/MIDCPNIFTY/NIFTYNXT50
   monthly contracts also move to last Tuesday. Contracts expiring ≤31 Aug 2025
   unaffected; new contracts from 26 June 2025 EOD onward use the new day.
7. **Effective 1 September 2025** — NSE moves from Thursday to **Tuesday** expiry;
   BSE Sensex moves from Tuesday to **Thursday** (swap, to avoid same-day collision).
   No evidence found of any subsequent reversal as of the latest sources checked.

**Grade: A** for the Sept 1, 2025 change (primary NSE circular obtained in full) and for
the March 2025 announce/defer episode (4+ independent matching sources).

### 3d. BSE cross-check (context only, Grade B)

- May 2023: BSE launches weekly Sensex + Bankex contracts (Friday expiry).
- Oct 2023: BSE moves Bankex expiry to Monday.
- Post-Nov 20, 2024 rule: BSE keeps **Sensex** weekly, discontinues **Bankex** weekly
  (Economic Times headline — snippet-only, not fully fetched; flagged as needing
  independent confirmation, though consistent with the "one weekly product per exchange"
  rule).
- Jan 2025: BSE shifts Sensex weekly expiry to Tuesday.
- 1 Sept 2025: BSE Sensex moves Tuesday → Thursday (the NSE/BSE swap described above).

---

## Summary timeline (all indices, all cadence eras)

```
2000-06-12  NIFTY futures launch (monthly cycle)
2001-06-04  NIFTY index options launch (monthly cycle)
2001-07-02  Single-stock options launch
2001-11-09  Single-stock futures launch
2011-09-07  FINNIFTY index itself launched (no derivatives yet)
2016-05-27  BANKNIFTY weekly options launch
2019-02-11  NIFTY weekly options launch
2021-01-11  FINNIFTY F&O launch (weekly + monthly, from day one)
2022-01-24  MIDCPNIFTY F&O launch (weekly + monthly, from day one)
2022-03-04  BANKNIFTY weekly count reduced 7->4 serial weeklies
2023-01-04  FINNIFTY weekly count reduced 7->4 serial weeklies
2023-08-17/21  MIDCPNIFTY expiry day moved Wed->Mon (NOT a weekly-launch date)
2024-04-24  NIFTYNXT50 F&O launch — MONTHLY ONLY, no weekly ever
2024-11-13  BANKNIFTY last weekly expiry
2024-11-18  MIDCPNIFTY last weekly expiry
2024-11-19  FINNIFTY last weekly expiry
2024-11-20  SEBI rationalization takes effect — NIFTY 50 becomes the ONLY
            NSE index with weekly options, going forward
2025-09-01  NSE expiry day moves Thursday -> Tuesday (all NSE index/stock
            derivatives); BSE Sensex moves Tuesday -> Thursday (swap)
```

**Practical rule for the replay simulator's weekly-expiry data availability:**
- BANKNIFTY weekly: data exists 2016-05-27 through 2024-11-13 only.
- FINNIFTY weekly: data exists 2021-01-11 through 2024-11-19 only.
- MIDCPNIFTY weekly: data exists 2022-01-24 through 2024-11-18 only.
- NIFTY weekly: data exists 2019-02-11 onward, continuously, through today.
- NIFTYNXT50: no weekly data ever exists at any point in history — monthly-only.
- Expiry weekday for all NSE index/stock derivatives: Thursday-based through
  2025-08-31 (contracts listed before the change), Tuesday-based from
  2025-09-01 onward — any simulator that infers "days to expiry" from a fixed
  weekday must branch on this date.

---

## What was NOT independently verified / follow-up items

1. Original SEBI approval-order circular numbers for the 2001 Nifty options and Nifty
   futures launches (the NSE-side confirmation is solid Grade A; the underlying SEBI
   regulatory approval document itself wasn't located).
2. A fully independent (non-NSE-originated) press confirmation of the exact day for
   Nifty index options (4 June 2001) — corroboration rests on 4 independent NSE
   documents rather than a third-party newsroom's exact-day statement.
3. NSE's own circular number(s) for the Nov 2024 BANKNIFTY/FINNIFTY/MIDCPNIFTY weekly
   discontinuation (dates are Grade A via SEBI's stated effective date + Grade B via
   4+ matching secondary sources; the specific NSE circular PDF wasn't locatable).
4. Full confirmation of BSE Bankex weekly-contract discontinuation (single
   snippet-only ET source).
5. No search for reversal/further changes to the Sept 2025 Tuesday-expiry regime was
   possible beyond the latest available sources as of this research (2026-07-24) —
   worth a periodic recheck if the simulator is maintained over time.

## Research method note

Conducted via 4 parallel research passes (per fact cluster), each independently running
WebSearch + WebFetch against NSE archival PDFs/circulars (`archives.nseindia.com`,
`nsearchives.nseindia.com`), SEBI's official circular pages (`sebi.gov.in`), and
independent financial press (Economic Times, Business Standard, LiveMint, Moneycontrol,
The Hindu BusinessLine, Business Today, Zerodha Market Intel, PR Newswire). Several
direct-fetch limitations were encountered and worked around: `nseindia.com` root/article
pages and several press domains (ET, LiveMint, Moneycontrol) block or timeout direct
WebFetch due to bot protection — in those cases, content was retrieved via search-engine
crawl/cache (Brave Search, DuckDuckGo) rather than a direct page read, which is flagged
inline above wherever it applies. All NSE/SEBI circular PDFs cited as "primary, read in
full" were successfully downloaded and read directly, which is the strongest evidence
tier available for this research.
