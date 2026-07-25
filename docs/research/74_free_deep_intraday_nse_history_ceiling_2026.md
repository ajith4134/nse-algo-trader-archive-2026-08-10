# Research/74 — The Realistic FREE Ceiling for Deep Intraday NSE History (1-min / 1-sec, cash + F&O + OI)

**Rule I acquisition research (Rule D: saved to file).** Skill used: `deep-research`
(4 parallel angle-sweeps + source triangulation). Direct follow-up/closure to two
open items from `54_nse_microstructure_data_sourcing.md` (2026-07-24): B6 (ICICI
Breeze 1-second archive depth, "open — verify") and the general "free datasets are
mostly 1-min, spotty" note. This pass ran 4 independent research agents, each doing
live WebSearch → WebFetch (not memory), across: (1) broker free/free-tier APIs,
(2) Kaggle/GitHub/HuggingFace open datasets, (3) non-broker data vendors, (4) quant
forums + NSE's own academic/research-data policy. Full per-agent evidence with every
URL/quote lives in the companion files listed at the bottom; this file is the
cross-angle synthesis and ranked verdict.

Research date: 2026-07-25. Hard filter applied throughout: no credential sharing,
no paywall/auth bypass, no ToS-violating scraping, no piracy — anything of that
kind that surfaced in a search was noted as "found, excluded" and not detailed.

---

## 0. Bottom line

There is **no free source of true multi-year 1-minute (let alone 1-second) NSE
history that is simultaneously: broad-universe, includes F&O options with OI,
and independently verified.** The realistic free ceiling splits by what you need:

| Need | Realistic free ceiling | Best source |
|---|---|---|
| Cash equities, 1-minute, broad universe (2,500+ symbols), OHLCV | **~4 years (2022–2026), rolling** | HuggingFace `xxparthparekhxx/indian-stock-market-minute-data` (MIT, unverified provenance) — see caveat §2.1 |
| Cash equities, 1-minute, single symbol (Nifty50 index only) | **~11 years (2015–2026)** | Kaggle `debashis74017/nifty-50-minute-data` |
| Cash + F&O (index), 1-minute-equivalent via **live broker API**, OI included | **~9 years (since Jul 2017)** | Fyers History API (`oi_flag=1`), 100-day pagination, free Standard tier |
| Cash + F&O, **1-second**, OI included | **~3 years documented; a ~10-year community claim for index F&O exists but is UNVERIFIED** | ICICI Breeze `get_historical_data_v2` — see conflict in §1 |
| Options-with-OI, intraday, bulk pre-built dataset | **Not found. Zero credible free bulk minute-level options archive exists.** | n/a — must self-accumulate or use EOD-only free F&O datasets |
| True 10-year+ 1-minute archive, any asset class, free, verified | **Not found** | n/a |

The honest ceiling for a project wanting **verified, broad-universe, multi-year,
free 1-minute NSE history including F&O+OI is roughly 3–4 years**, achieved only
by combining a broker API (Fyers/Dhan/ICICI, each free) with self-accumulation
going forward, plus one of the Kaggle/HuggingFace dumps to backfill the recent
past. Anything deeper than ~4 years, free, at 1-minute or finer, with broad
symbol coverage, does not currently exist as a single legitimate source — it
would have to be assembled from fragments (see §5).

---

## 1. Broker free/free-tier historical APIs — the deepest single legitimate lever

Full detail + every doc URL/quote: `docs/research/73_broker_api_intraday_historical_data_limits_2026.md`.

| Broker | 1-min max/request | Total free archive depth | 1-sec? | F&O + OI | Cost |
|---|---|---|---|---|---|
| **Fyers** | 100 days/request | **since Jul 2017 (~9 yrs)** | rolling last 30 trading days only | yes, `oi_flag=1` | Free (Standard) |
| **Dhan** | 90 days/request | **~5 years total** | no | yes, embedded OI | Free |
| **ICICI Breeze** | undocumented row cap (~1000/request) | **~3 years documented (ICICI's own FAQ)** | **yes — the only free broker with 1-second** | yes to 1-min; 1-sec OI population unconfirmed | Free |
| Angel One SmartAPI | 30 days/request (the oft-quoted "2000 days" is for *daily* candles, not 1-min) | unclear beyond 30-day chunks; no expired-contract F&O history | no | via separate `getOIData` call; no expired contracts | Free |
| Upstox v3 | 1 month/request | archive starts Jan 2022 (~4 yrs); expired F&O gated behind paid "Upstox Plus" | no | yes for live contracts only | Free |
| Zerodha Kite Connect | 60 days/request | multi-year but **no expired-contract F&O data** | no | yes, live contracts only | **Not free** — ₹500/month (cut from ₹2000 in May 2025) |
| Finvasia Shoonya | undocumented (docs unreachable) | unknown | unknown | claimed yes | claimed free, unconfirmed |
| Alice Blue ANT | ~2 years cash | F&O = current expiry only | no | unconfirmed | unconfirmed |

**Key correction vs. the brief's assumption:** Kite is *not actually free* any
more (₹500/mo since a 2025 pricing change) — it's a paid API, just cheap. Among
the genuinely free options, **Fyers currently has the deepest documented
same-mechanism archive (since Jul 2017) that includes F&O + OI**, ahead of
ICICI Breeze's 1-minute data. Breeze's unique edge is being the *only* free
broker offering **1-second** granularity at all — nothing else here goes finer
than 1-minute.

**Unresolved conflict — ICICI Breeze depth:** ICICI's own FAQ states minute/second
history is available for **~3 years**. Independently, a Nov 2024 TradingQnA
thread (`tradingqna.com/t/which-is-the-best-source-for-options-historical-data/176182`)
claims users have pulled **minute-level OHLCV+OI for Nifty/BankNifty going back
"10 years"** via Breeze. These are not reconcilable from documentation alone —
the FAQ is the primary source (Grade A) and should be treated as the operative
limit until someone empirically probes `get_historical_data_v2` against a
pre-2023 date range and confirms non-empty results (tracked as an open item,
§6). Do not plan around the 10-year claim without that empirical check.

---

## 2. Free open datasets (Kaggle / GitHub / HuggingFace / Zenodo)

Full detail + every dataset URL: findings captured in the agent transcript for
this pass (not yet split into its own numbered file — folded in here to avoid a
second 71/72-range collision, since another concurrent session in this project
used 71 and 72 today for unrelated corporate-actions/order-book research).

### 2.1 Best broad-universe cash-equity find
**HuggingFace — `xxparthparekhxx/indian-stock-market-minute-data`**
(https://huggingface.co/datasets/xxparthparekhxx/indian-stock-market-minute-data)
— 2,500+ NSE stocks/indices, 1-minute OHLCV+OI, **2022–2026** (~4 years), daily
candles back to 2000, ~715M rows, Parquet, MIT license, actively updated
(682 downloads/month as of this check). **Caveat: the dataset card does not
disclose data provenance** (which broker/vendor feed it was built from) — MIT
license covers the *packaging*, not necessarily a demonstrated right to
redistribute NSE's underlying market data. Treat as a strong practical resource,
not a legally bulletproof one; do not resell it or claim it as verified-licensed
NSE data without independently confirming provenance.

### 2.2 Best single-symbol long-history find
**Kaggle — `debashis74017/nifty-50-minute-data`** — Nifty 50 **index only** (no
constituent stocks, no options), 2015–2026 (~11 years), 908,897 rows,
weekly-updated. Needs a free Kaggle account. No explicit license stated
(Kaggle default terms apply).

Related sibling from the same uploader,
`debashis74017/stock-market-data-nifty-50-stocks-1-min-data`, was only
independently verified at the **5-minute** granularity: 100 Nifty-100 stocks +
indices, Jan 2015–Feb 2022, ~33GB. Its 1-minute / Nifty-500 claim (referenced
in dataset title/forum posts) could not be confirmed past the title — treat as
medium-confidence, not verified.

A third candidate, `nishanthsalian/indian-stock-index-1minute-data-2008-2020`,
claims the **longest span found (2008–2020, 12 years)** but is index-only
(Nifty + BankNifty) and the page was reCAPTCHA-gated during verification —
title/snippet confidence only, and it appears abandoned (no updates since 2020).

### 2.3 Best GitHub stock-universe find
**GitHub — `ShabbirHasan1/NSE-Data`** (github.com/ShabbirHasan1/NSE-Data,
GPL-3.0) — Nifty50 + Next-100 mid-caps + 9–12 indices, 1-minute CSVs,
**Jan 2017–Dec 2020** (frozen archive; the repo also has an ongoing daily
collector built on the Alice Blue API, i.e. this is a real example of the
"self-accumulate going forward" pattern rather than a bulk historical pull).

### 2.4 Options-with-OI, intraday, bulk dataset
**Not found.** Every Kaggle/GitHub F&O dataset checked
(`akshaypawar7/nsecombine`, `kaalicharan9080/nse-future-and-options-data`,
`sunnysai12345/nse-future-and-options-dataset-3m`,
`tanay001/nseindia-futures-options-daily`,
`sajal101agrawal/nse-options-last-5-years`) turned out to be **daily
bhavcopy-derived EOD snapshots** (one row per contract per day, with strike/
expiry/OI) — none are intraday/minute-granular. A Kaggle forum post titled
"Introducing NSE Future and Options 1-Minute Data" could not be verified past
its title (JS-blocked). **This is the single hardest gap: no legitimate free
bulk source of intraday options OI exists.**

### 2.5 Academic repositories (Zenodo/OSF)
Only daily-granularity equity datasets found (e.g., a 20-year daily-price
dataset sourced from Yahoo Finance for the top 50 Indian companies). No open
academic minute-level NSE repository was found.

### 2.6 Access libraries vs. bulk archives — a distinction to keep straight
`nsepy`, `jugaad-data`, and `openchart` (github.com/marketcalls/openchart,
actively maintained, hits NSE's own charting/`chart-database` API for 1m/5m/
15m/30m) are **on-demand access tools**, not pre-built bulk archives — they let
you *pull* history live, subject to whatever depth NSE's own undocumented
charting endpoint allows (unverified — an open GitHub issue on `openchart`,
#4, is unanswered on exactly this question). `nsepy` is further limited to
daily bhavcopy and unmaintained since NSE changed its site; it has no working
minute endpoint.

---

## 3. Non-broker data vendors — free tiers, checked and ruled out

Full detail: agent transcript for this pass. Every well-known name was checked
by reading current pricing/docs pages directly (not memory):

| Vendor | NSE intraday on free tier? |
|---|---|
| Yahoo Finance / yfinance | **Yes, but only a rolling ~7–30 day window for 1-min** (~60 days for coarser intraday) — a live snapshot tool, not a historical archive. `.NS` suffix works; no NSE F&O/options chain data. |
| stooq.com | India coverage exists but intraday granularity unconfirmed (bot-walled); treat as **daily-only** until proven otherwise. |
| Alpha Vantage | Free-tier `TIME_SERIES_INTRADAY` is documented against US tickers only; no NSE support evidenced. |
| Twelve Data | India (XNSE) is explicitly flagged **"Delay: EOD"** even on paid plans. No intraday at any tier. |
| EODHD | Free tier = EOD only, 20 calls/day. Minute data requires the paid "All World Extended" plan (€29.99/mo). |
| Marketstack | Free tier = EOD only, 1 year history. No intraday on any tier for international markets. |
| Polygon.io / Tiingo / Financial Modeling Prep / firstratedata.com | **No NSE/India coverage found** — all are US/global-futures-centric; firstratedata's own roadmap only *targets* Asian-market expansion from mid-2024, with zero India symbols in its catalog as checked. |
| NSE itself (nseindia.com / archives.nseindia.com) | Free downloads are **bhavcopy (EOD), circuit-limit files, delivery-position files — all end-of-day.** No retroactively-downloadable intraday time series exists on NSE's own public site. Pre-open data is a single snapshot, not a series. |

**Verdict for this angle: none of the non-broker vendors provide meaningful
free NSE intraday history beyond Yahoo's rolling ~1-month window.** This
category is a dead end for depth; it's only useful for very recent, very
short-window data.

---

## 4. Forums, GitHub discussions, and NSE's own academic/research policy

Full detail + URLs read: agent transcript for this pass.

- **Community consensus** (TradingQnA, Reddit, GitHub issues): genuinely free
  1-minute NSE data tops out around **3–4 years via community-assembled
  archives**, or **60 days via official broker UI downloads (Zerodha)**.
  Nobody surfaced a single bulk free source of 5–10+ years of 1-minute data —
  a direct GitHub ask for exactly that went unanswered by a maintainer, which
  is itself a data point.
- **StockMojo.in** — a free browsable archive of *expired* NSE option-chain
  history (OI, IV, premium, price) across several years for Nifty/BankNifty/
  FinNifty/major F&O stocks. Not a bulk API/download, but a legitimate free
  way to retrieve OI history that brokers normally purge — useful for manual/
  scripted retrieval, not for building a bulk archive quickly.
- **NSE's own Data Usage and Data Sharing Policy** (issued 3 Oct 2024,
  nsearchives.nseindia.com) formally defines a **"Non-Commercial User"** class
  (academic institutions, researchers, students, not-for-profits) under the
  **NSE Research Initiative 2.0**. It states tick-by-tick order/trade data
  exists for **2019–2020 (cash)** and **2022 (cash+F&O)**, accessible via a
  **Data Seeking Request Form** routed through NSE's Economic Policy Research
  Department (nseri@nse.co.in), with possible fee waivers for non-commercial
  users. The form is addressed generically to "Researchers" — technically
  open to an independent applicant, not gated to university affiliation on
  its face — but approval is discretionary and institutional proposals are
  clearly favored in practice. This is the **only channel found anywhere in
  this research that could plausibly grant free access to genuine tick-level
  (finer than 1-second) NSE history**, and it is also the **only channel that
  requires an application/approval step rather than instant access.**
- Telegram/Discord: no legitimate public bulk-data-sharing community was
  found; nothing requiring exclusion-on-legitimacy-grounds was encountered
  either (i.e., no piracy group surfaced in these particular searches).

---

## 5. Ranked list — best free legitimate path per use case

1. **Deepest, free, includes F&O+OI, verified: Fyers API** (since Jul 2017,
   ~9 years) — via 100-day paginated pulls. Best default for a live-plus-backfill
   pipeline.
2. **Finest granularity, free, verified depth: ICICI Breeze 1-second** (~3
   years documented) — best for near-tick fidelity over a shorter recent
   window; do not plan on the unverified "10 years" community claim.
3. **Broadest symbol universe, free, pre-built, no API calls needed:
   HuggingFace `xxparthparekhxx/indian-stock-market-minute-data`** (2,500+
   symbols, 2022–2026, cash+index, OI column, no options) — fastest way to
   backfill 1-minute cash history without touching any broker's rate limits;
   provenance caveat applies (§2.1).
4. **Longest single-symbol span, free: Kaggle `nishanthsalian/...2008-2020`**
   (index-only, unverified beyond title, likely abandoned) — worth a manual
   download-and-inspect pass but not a foundation to build on blind.
5. **Only route to genuine tick-level (sub-1-second) history: NSE Research
   Initiative 2.0 application** — worth filing given the low cost of applying,
   but not a dependable near-term source; treat as a long-lead, uncertain-yield
   application, not a plan input.
6. **Everything else (non-broker vendors, NSE's own public site, Alpha
   Vantage/Twelve Data/EODHD/Marketstack free tiers): ruled out** for anything
   beyond a rolling ~1-month window.

**Recommended combined build path for the project:** run Fyers (or Dhan) as
the primary free broker backfill for cash+F&O+OI going back to their real
archive start, layer ICICI Breeze 1-second on top for the last ~3 years where
finer granularity matters, use the HuggingFace dataset as a fast bulk seed for
broad-universe cash 1-minute history 2022+, and self-accumulate 1-minute (or
finer, via the project's own broker connections) going forward from today so
depth only grows from here — this mirrors the exact pattern GitHub's
`ShabbirHasan1/NSE-Data` used successfully. This is consistent with, and
extends, the Tier-1/Tier-2 build path already recommended in
`docs/research/54_nse_microstructure_data_sourcing.md` §6.

---

## 6. Open items (Rule K — tracked, not silently dropped)

Broker-specific open items (Shoonya, Alice Blue/Motilal Oswal/IIFL, Kite rate
limits, Upstox Plus pricing, Breeze 1-sec OI population) are already tracked
in `docs/BACKLOG.md` under "Broker historical-data API limits research
(research/73)". Added below, new items surfaced by this pass:

- 🔴 **ICICI Breeze 3-year vs. "10-year" claim conflict (§1)** — needs an
  empirical probe of `get_historical_data_v2` against a pre-2023 date range
  for a Nifty/BankNifty option contract to see whether it returns real data
  or an empty response.
- 🔴 **HuggingFace `xxparthparekhxx/indian-stock-market-minute-data`
  provenance** — the dataset card doesn't disclose its source feed; before
  relying on it as a production seed, spot-check a sample of rows against a
  known-good source (e.g., NSE bhavcopy close vs. the dataset's last 1-min
  bar of the day) to sanity-check accuracy, and do not represent it externally
  as licensed NSE data.
- 🔴 **`openchart`'s real depth against NSE's `chart-database` endpoint** —
  unanswered upstream (GitHub issue #4); worth an empirical test since it's
  actively maintained and free.
- 🔴 **NSE Research Initiative 2.0 application** — not yet filed; low cost to
  file, uncertain/slow yield. Track as a long-lead item, not a blocker to
  current work.

## What this pass did NOT cover
- Did not empirically test any API against real credentials (verification
  gate / Rule F real-data sign-off is a separate step, not part of this
  research pass).
- Did not exhaustively check every regional/smaller Indian broker beyond the
  ones named in the brief plus Finvasia/Alice Blue/Motilal Oswal/5paisa/IIFL.
- Did not investigate BSE-specific free intraday sources (brief was NSE-only).
- Did not pursue any Telegram/Discord group that appeared to involve
  redistributing paid-vendor data without a license — none were found in this
  particular pass's searches, but the possibility of such groups existing
  elsewhere is not disproven, only not investigated (per the hard exclusion
  filter).

## Companion files (this pass)
- `docs/research/73_broker_api_intraday_historical_data_limits_2026.md` — full
  broker-by-broker evidence with every doc quote and URL.
- `docs/research/54_nse_microstructure_data_sourcing.md` (2026-07-24) — prior
  pass this one closes an open item from (B6).
- `docs/research/59_deep_history_price_and_universe_sourcing.md` (2026-07-24)
  — the NSE-official *paid* Data & Analytics historical products (bhavcopy/
  order-trade data), for context on what the *paid* ceiling looks like above
  this free-ceiling research.
