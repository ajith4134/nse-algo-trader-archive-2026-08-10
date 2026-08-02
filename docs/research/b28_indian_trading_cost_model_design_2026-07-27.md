# B28 — the real Indian round-trip cost model (design + sourcing pass, 2026-07-27)

Operator request: *"add the total broker fees column for each segment type and total fees on closed
trades."* This is also a **hard dependency of B18**, whose acceptance bar is "positive net expectancy
per trade AFTER realistic costs" — an expectancy computed gross of these fees is fiction.

## Sourcing pass (Rule I — this is the ACTUAL search, not a from-memory note)

A live web research pass was run on 2026-07-27 across four independent angles (cost stack ·
regulatory/lot-size/expiry · microstructure/slippage · expiry-day settlement), fetching primary and
broker pages rather than search snippets. Lot sizes and the STT-on-exercise mechanics were derived
twice independently and agree.

**No OSS library was integrated for this.** Searched for an Indian brokerage/STT cost library; the
cost stack is a handful of jurisdiction-specific percentages that change by Finance Act and by
exchange circular. A third-party package would be a *staleness liability* — the failure mode here is
silently using last year's rates, which is exactly what a pinned dependency causes. Verdict:
**implement in-repo from cited primary rates, with the source and effective-date recorded next to
every constant** so staleness is auditable. This is a REJECT-with-reason, not a skipped search.

## What the research CORRECTED — three traps we would otherwise have shipped

**1 · The "STT on exercise = full notional" folklore is SIX YEARS STALE and must NOT be encoded.**
SEBI/CBDT moved STT-on-exercise from full contract value to **intrinsic value only** in September
2019. As of **1 April 2026** (Finance Act 2026), STT on sold options and on exercised options are
**both 0.15%**. Worked check — 24000CE bought ₹150, settles 24200 (intrinsic 200), lot 65:

| path | STT |
|---|---|
| squared off near intrinsic | 0.15% × 200×65 = **₹19.50** |
| left to auto-exercise (current rule) | 0.15% × 200×65 = **₹19.50** — identical |
| the *pre-2019* full-notional rule | 0.15% × 24200×65 = ₹2,359.50 — **121× higher** |

Encoding that 121× penalty would have made the engine irrationally terrified of holding to expiry.

**2 · NIFTY expiry is TUESDAY, and only NIFTY still has weekly options.**
NSE moved expiry Thu→Mon (Apr 2025) then Mon→Tue (Sep 2025). SEBI's Oct-2024 framework allows **one
weekly-expiry index per exchange**, so BANKNIFTY / FINNIFTY / MIDCPNIFTY weeklies were discontinued
20 Nov 2024 — all four non-NIFTY indices are **monthly-only (last Tuesday)**.
**This makes backlog B9 worse than logged:** the single global `nearest_expiry_date` will, outside
monthly-expiry week, resolve to a NIFTY weekly and drop **all ~210 stock options AND the other four
indices** from the ladder. B9 must select expiry per underlying.

**3 · SL-M orders are BANNED on NSE options (since 27 Sep 2021).**
Only SL-limit exists, so a triggered stop can fail to fill. Modelling exits as "market order +
slippage%" is unrealistic. (The repo's `broker_oms` already maps SL-M-for-options → buffered
SL-limit, so the execution layer is right; the *fill model* still assumes certainty — logged as B29.)

## The cost stack (each constant carries its source + effective date in code)

| Component | Rate | Base | Side |
|---|---|---|---|
| Zerodha brokerage | ₹20 flat per executed order | — | both legs |
| STT — squared off | **0.15%** | premium turnover | **sell leg only** |
| STT — exercised/ITM expiry | **0.15%** | **intrinsic value** (NOT notional) | buyer, on exercise |
| NSE exchange transaction charge | **0.03553%** | premium turnover | both legs |
| SEBI turnover fee | 0.0001% (₹10/crore) | premium turnover | both legs |
| GST | 18% | **only** (brokerage + SEBI fee + exchange charge) — NOT on STT, NOT on stamp | both legs |
| Stamp duty | 0.003% (₹300/crore) | premium turnover | **buy leg only** |

Worked example — NIFTY, lot 65, buy ₹150 → sell ₹170: brokerage ₹40 · STT ₹16.58 · exchange ₹7.39 ·
SEBI ₹0.02 · GST ₹8.53 · stamp ₹0.29 = **₹72.81 round trip** on ₹9,750 notional ≈ **0.75% of
turnover**. That is the per-trade hurdle before any slippage.

**Cash equity intraday** uses a different stack (STT 0.025% on the sell side of intraday delivery-less
trades, different exchange charge) — modelled separately, never by reusing the option rates.

## Current lot sizes (Jan 2026 series) — already correct in-repo

NIFTY **65** · BANKNIFTY **30** · FINNIFTY **60** · MIDCPNIFTY **120** · NIFTYNXT50 **25**.
Verified against the live Kite instrument dump earlier today (NIFTY 65, BANKNIFTY 30, FINNIFTY 60
observed) — the repo reads lot size from the broker per instrument rather than hardcoding, so it is
already current and stays current. No change needed.

## Design

New module `paper_trading/indian_trading_cost_model.py`:
- `NSE_OPTION_COST_RATES` / `NSE_CASH_INTRADAY_COST_RATES` — frozen rate tables, each field carrying
  its rate, source and effective date, so a stale rate is visible rather than buried.
- `estimate_round_trip_cost(...) -> TradeCostBreakdown` with per-component rupee fields, not just a
  total — an aggregate that cannot be decomposed cannot be audited.
- Segment-aware: `nse_index_options` / `nse_stock_options` / `nse_cash_equity`.
- Pure, no I/O.

Wiring: cost computed at close, stored on `ClosedPaperTrade` and in the experience memory (so
expectancy is computable net), surfaced as a fees column per segment board and a total on the
closed-trades panel, per the operator's request.

## Acceptance criteria

1. The worked NIFTY example reproduces **₹72.81 ± ₹0.05**.
2. STT applies to the **sell leg only** for options, on premium turnover.
3. GST base **excludes** STT and stamp duty (a model taxing the whole stack overstates cost).
4. Stamp duty applies to the **buy leg only**.
5. Exercised-ITM cost uses **intrinsic value**, never full notional (the 121× trap).
6. Cash equity uses its own rate table, never the option rates.
7. Costs are always ≥ 0 and monotone in turnover.
8. Every rate constant carries a source + effective date in code.
9. Rule-F: fees appear per segment and as a total on the live dashboard.

## Explicitly NOT settled (Rule K — carried as open blockers, not silently treated as fact)

- **Primary gazette text for the 0.15%/0.15% STT rates was NOT opened.** Rests on two convergent
  secondary sources (Zerodha's live charges page + a taxguru clause summary). **Verify before this
  gates real capital.**
- **The NSE circular for the 0.03553% exchange charge could not be fetched** (NSE PDF timeouts);
  rests on Zerodha's billing page alone.
- Any Zerodha exercise/settlement handling fee beyond STT — not found; assumed ₹0.
- Zerodha's specific ITM auto-square-off cutoff time before expiry — not found; deliberately NOT
  hardcoded.
- Slippage: no official NSE spread dataset exists. Practitioner estimate ~0.5–1.0% of premium for
  NIFTY/BANKNIFTY ATM, materially wider for FINNIFTY and wider again for MIDCPNIFTY/NIFTYNXT50/OTM.
  Treated as a separate, clearly-labelled assumption — **not** folded into the cost model as if it
  were a known rate.
