# 13 — NSE Intraday Scanner/Filter Taxonomy (Full Category, Not Just Your Two Examples)

You named 52-week high/low breakout and upper-circuit proximity, then
flagged there are "lots more types of filters" you hadn't mentioned. This
is the full taxonomy — an `expand-idea` pass over real, verified NSE
scanner/filter categories, checked against what actual Indian screener
tools (Chartink, TradingView India, Sensibull) ship, not assumed.

**Status: research only. Nothing implemented.** Extends `research/07` §A
(indicators) with the *filter/scanner* framing specifically, since a
"filter" in this context is usually a rule applied over indicators/raw
data to select a stock list, not a new indicator on its own.

## Bottom line

Nearly all of this taxonomy is real and shipping in production Indian
tools today. Evidence quality varies sharply: **exchange-mechanics
filters are objectively verifiable market-structure facts** (Grade A/B —
F&O ban list, OI buildup matrix, bulk/block deals), while **pattern
filters are popular but empirically thin** (Grade B/C — NR7, round
numbers, golden cross). Critical project-specific finding: **Kite
Connect's historical API has no historical OI field and no delivery %
field at all** — both would need separate ingestion from NSE's public
bhavcopy/report pages, not the Kite API this project is built on.

## 1. Price-level filters (your two examples live here)

52-week/all-time high-low, previous-day-high/low breakout, gap up/down,
support/resistance breakout, upper/lower circuit proximity — Grade B,
standard and universally implemented (Chartink's Min/Max-over-252-days
functions). Gap-fill statistics (81.5% of up-gaps, 60.2% of down-gaps
close by session end) come from a **DJIA case study, not NSE-specific** —
flagged as a literature gap, not a confirmed NSE number. Round-number
levels are Grade C — contested even in the academic literature (real
effect in FX per Osler 2005, "no clear pattern" in broader equities).

## 2. Volume-based filters

- **Unusual volume spike** (vs. N-day average) — Grade B, universal.
- **Delivery % spike** — Grade B, real and commonly used. NSE/BSE publish
  a daily "Security-wise Delivery Position" file; delivery% = delivered
  qty / traded qty, rising delivery% read as non-intraday accumulation
  (bullish conviction signal). **Not available via Kite Connect** —
  requires scraping NSE's daily report separately.
- **Bulk deal / block deal disclosures** — Grade A, regulatory fact.
  Bulk deal = single trade ≥0.5% of listed equity, same-day disclosure,
  quantity only. Block deal = ≥₹10 cr or ≥5 lakh shares, traded in a
  separate window (8:45-9:00 AM / 2:05-2:20 PM), disclosed by 9:45 AM
  with price revealed. Published at
  nseindia.com/report-detail/display-bulk-and-block-deals — not
  confirmed available via Kite Connect.

## 3. F&O-native mechanisms (real exchange rules, not folklore)

- **OI + Price buildup 2×2 matrix** — Grade A, standard,
  exchange-agnostic: ↑Price+↑OI = **Long Buildup**, ↓Price+↑OI = **Short
  Buildup**, ↑Price+↓OI = **Short Covering**, ↓Price+↓OI = **Long
  Unwinding**. Triangulated identically across 4 independent sources.
- **F&O ban list / Market Wide Position Limit (MWPL)** — Grade A/B. A
  stock enters ban when aggregate F&O open interest crosses **95% of
  MWPL** (only unwinding allowed, no fresh positions); exits at **80% or
  below**; NSE also issues an **early-warning alert at 60%** — a third
  threshold most retail explainers omit entirely. "Entering ban" often
  reads as forced-unwind risk (can squeeze intraday shorts); "exiting
  ban" signals fresh position-taking can resume. Daily ban-list circular
  released after 6 PM.

## 4. Relative-strength / comparative filters

Stock-vs-sector/NIFTY relative strength and sector rotation are real and
widely used, specifically via **Relative Rotation Graphs (RRG)** —
adapted from Julius de Kempenaer's methodology, plotting RS-Ratio vs.
RS-Momentum across 4 quadrants (Leading/Weakening/Lagging/Improving)
against NIFTY50/BankNifty/sector benchmarks. Offered by multiple India
tools and at least one open-source GitHub implementation. **Found this,
wasn't asked for by name** — it's the specific methodology behind generic
"sector rotation" filter requests.

## 5. Technical/pattern-based scanner filters

MA crossovers (golden/death cross, 20/50/200 DMA) — Grade B, real but
modest documented edge (~1.5%/3mo per Ned Davis Research), heavily
whipsaw-prone in sideways markets, better as a trend filter than an entry
trigger. NR7/inside-day compression and Bollinger Band squeeze — Grade C,
popular on Indian screeners but thin rigorous evidence, practitioner-level
only.

## 6. Options-specific filters

Unusual options volume/OI at specific strikes (possible informed
positioning), IV spike/IV-percentile scanners, and Max Pain are all real
and shipped as India-specific products (Sensibull's screener bundles IV
percentile, PCR, OI accumulation, and Max Pain in one tool) — Grade B.
PCR extreme readings are Grade C — a widely-used contrarian heuristic
(>1.3 read bullish-contrarian, <0.7 bearish-contrarian) explicitly flagged
by sources themselves as subjective/context-dependent. **Max Pain found
this, wasn't asked for** as a distinct named filter.

## 7. Corporate-action / event-driven filters

**Index reconstitution** (NIFTY 50 add/remove, semi-annual March/September
rebalancing) — Grade A/B, academic literature finds 2-4% abnormal returns
for additions pre-effective-date, reversing within 60 days; a concrete
2025 example drew ₹3,128cr/₹6,525cr passive inflows on two additions.
Upcoming-results-date proximity and ex-dividend/bonus/split dates — Grade
B, mechanically simple, widely published on corporate-action calendars.

## 8. What real Indian scanner tools actually ship (verified directly)

**Chartink** (fetched its own scanner-user-guide directly, Grade A
primary confirmation): OHLCV, SMA/EMA/WMA/TMA, RSI/MACD/ADX, ATR/Bollinger,
Parabolic SAR/Supertrend, VWAP/MFI, Ichimoku, gap up/down, crossovers,
52-week/lifetime highs, Min/Max functions, plus separate fundamental
filters. **TradingView India**: Security Info / Market Data (incl. gap,
beta) / Technicals (crossovers, oscillators, volatility bands, candlestick
patterns) / Financials. **Screener.in**: fundamentals-first (ROE, ROCE,
D/E, promoter holding) — confirmed the wrong tool for this project's
intraday use case, better suited to fundamental screens.

## 9. Found this, wasn't asked (flagged explicitly)

- Relative Rotation Graphs (RRG) as the named sector-rotation methodology.
- Max Pain as a distinct, separately-named options filter.
- NSE's 60%-of-MWPL early-warning alert — a third threshold beyond the
  95%/80% ban/unban pair that most explainers skip.
- Compound filters combining categories (e.g. "high delivery % + near
  52-week high," common on Chartink) — filters are routinely stacked, not
  used one at a time.

## Data-access note for this project (Kite Connect / Zerodha)

- OHLCV historical — available via Kite Connect historical API.
- **Open Interest** — live quotes only, **not in historical candle data**;
  must be polled and stored intraday by this project's own system.
- **Delivery %** — not available via Kite Connect at all; requires
  scraping NSE's daily bhavcopy/security-wise-delivery report.
- **Bulk/block deals** — not confirmed available via Kite Connect;
  published as public NSE reports, would need separate ingestion.
- **MWPL/ban list** — published as an NSE circular/CSV daily after 6 PM,
  not a Kite Connect field.

This means Layer 2 (Market Data) needs an explicit design decision: which
of these NSE-native data sources get ingested beyond what Kite Connect
provides, since several of the most exchange-authentic filters (OI
buildup, ban list, delivery %, bulk deals) require it.

## What this means for the plan

Extends `research/07` §A (indicators) with the filter/scanner framing.
Every filter here — including the exchange-mechanics ones with solid
evidence grades — still routes through the hypothesis validation pipeline
in `research/12` before being trusted as a strategy trigger, since "this
is a real exchange mechanism" and "this mechanism predicts profitable
trades" are different claims requiring separate verification.
