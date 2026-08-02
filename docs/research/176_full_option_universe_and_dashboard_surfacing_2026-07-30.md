# 176 — Full option universe (all contracts, every index + full stock breadth) + option-segment dashboard surfacing

**Date:** 2026-07-30
**Operator ask (verbatim):** "option index and option stocks are not opening check i need full
univers in option stocks and all contracts in options every index."
**Clarified (forced MCQ, 2026-07-30):**
- *Symptom* = **BOTH** — the engine barely trades options AND the dashboard does not surface the
  option universe. Fix trading visibility + add full-universe visibility.
- *Breadth* = **ALL** — the engine should scan/trade **every strike × every expiry** for all 5
  index underlyings **and** all ~208 stock-option underlyings (~28,545 contracts), not the current
  ATM±3 nearest-expiry ladder.

---

## 1. Diagnosis (what is actually happening — grounded, not guessed)

### 1a. Live universe numbers (rebuilt against the live Kite NFO master, 2026-07-30)
- Raw NFO rows: **29,182**.
- Classified INDEX option contracts: **4,538** across **5** underlyings
  (NIFTY 18 expiries/124 strikes/1558 contracts · BANKNIFTY 6/171/924 · FINNIFTY 3/103/432 ·
  MIDCPNIFTY 3/148/720 · NIFTYNXT50 3/193/904).
- Classified STOCK option contracts: **24,007** across **208** underlyings.
- **Full option universe = ~28,545 contracts.**

### 1b. Why the tradable universe is narrow
`universe_registry/live_tradable_universe.py::select_near_expiry_option_ladder` keeps, per
underlying: **its own nearest expiry only, ATM ± 3 strikes** (~14 contracts). It also **drops any
underlying whose live spot price is missing**. Net: the engine sees ~3k near-ATM contracts, never
the far strikes / later expiries. This is the deliberate "38k is too many to price every scan"
tradeoff (B9). The operator now wants the full breadth.

### 1c. Why the option SEGMENT BOARDS read empty ("not opening")
The service surfaces open option positions via `_option_spread_views`, which covers ONLY
`state.open_option_spreads` (credit spreads) and `state.open_directional_options`. The **0-DTE
engine** (B32, `paper_trading/zero_dte_expiry_day_live_path.py`) — the one option engine that
actually opens positions (44 real 0-DTE positions on 2026-07-28) — writes to
`state.open_zero_dte_positions` / `state.closed_zero_dte_positions`, and **nothing surfaces those**
into open-position views, closed trades, or `_segment_boards`. So even on a day options DO trade,
the Index/Stock Options tiles show `open_count=0`, `realised_fees=0` (index=₹0 EVER confirms zero
index-option closes ever reached the segment-tagged close path). This is **B32 remaining item (8)**.

### 1d. Why so few option trades at all (context; NOT fully in scope of this slice)
Operator directive 2026-07-28 (BACKLOG B32): the directional arm is effectively **ORB-gated**
(fires only on `detect_opening_range_breakout`); the credit-spread arm has been **dark ~60 sessions**
on IV-rank abstain; `entries_skipped_for_unmeasured_regime_count` abstains when ADX is unwarmed.
Widening the universe increases *opportunity surface* (esp. more expiries → more 0-DTE/near-dated
candidates) but does not by itself rewrite the entry gates — that is the separate A3 strategy slice.
This is surfaced (Rule K), not silently claimed fixed.

---

## 2. Engine scope (Rule P) — this is a universe/visibility engine change, not a scalar

- **Algorithm/state:** a full-universe option-instrument assembler with per-underlying ATM anchoring
  and expiry/strike indexing; carried state = the full `TradableUniverse.option_ladder_instruments`
  (now the complete contract set) + a per-underlying spot map; the look-scheduler
  (`select_option_underlyings_due_for_look`, least-recently-looked) already exists and now spans the
  full breadth.
- **Raw input pipeline:** Kite NFO instrument master → `build_phase1_instrument_universe` (already
  classifies ALL rows) → NEW full-universe selection (keep every strike × every expiry) → spot LTP
  for ATM anchoring (indices via index-quote symbols, stocks via `NSE:<sym>`).
- **Decision-grade output that changes behavior:** the option credit-spread / directional / 0-DTE
  passes now see the entire contract set per underlying → ATM discovery, IV, leg selection, and
  0-DTE routing operate over all strikes/expiries instead of a 7-strike window; the operator can see
  every option position and the full-universe coverage on the dashboard.
- **SOTA analog:** an exchange-complete option chain the strategy layer selects within (à la an
  OMS/'"whole book" universe) rather than a pre-pruned watchlist.

### What a thin version would omit (and we will NOT)
Pricing feasibility at full breadth; per-underlying (not global) expiry handling; surfacing 0-DTE +
directional + spread positions uniformly with correct index/stock segment tags; a coverage panel that
proves the full universe is loaded; real-data verification against the live master.

---

## 3. Build plan (slices, each verified before the next — Rule A/F)

**Slice A — Full option universe.** Add `select_full_option_universe` (all strikes × all expiries,
all underlyings) in `live_tradable_universe.py`; switch `assemble_tradable_universe` /
`fetch_live_tradable_universe` to it (keep ATM spot map for the strategy, but never prune contracts).
Keep the near-expiry ladder helper available for anything that explicitly wants the front band. Tests:
count invariants (all contracts retained, per-underlying expiry/strike coverage), no-spot underlying
still retained. Rule-F: rebuild against live master, assert ~28.5k contracts, 5 idx + 208 stk.

**Slice B — Option positions on the dashboard (fix "not opening").** Add `_zero_dte_views` and fold
0-DTE open positions into `_option_spread_views` (index/stock segment tag via `_INDEX_UNDERLYINGS`);
route 0-DTE closes into `_recent_closed_trades`/segment fees. So `_segment_boards` counts real option
positions. Tests: a state with open + closed 0-DTE positions yields non-zero index/stock board counts
and fees. Rule-F: live pass shows 0-DTE positions on the boards.

**Slice C — Full-universe coverage panel (Rule N).** A dashboard panel: per index + a stock bucket,
show contracts / distinct strikes / distinct expiries in the tradable universe and how many are being
looked at, so the operator SEES the full universe is loaded. Wire into snapshot + render.

**Feasibility note (Rule K):** pricing is per-examined-underlying (`latest_price_by_token(underlying
options)`), not a global 28.5k sweep, so full breadth is affordable at the current look budget
(~25 looks/pass × ~134 avg contracts ≈ ~3.3k priced/pass ≈ ~9 ltp batches). Memory: ~28.5k light
`Instrument` dataclasses — fine. The ONLY thing that grows unboundedly is per-underlying pricing for
mega-underlyings (NIFTY 1558 contracts = 4 batches when examined) — acceptable, logged.

## 3a. Sourcing gate (Rule I / building-features-from-ideas → sourcing-oss-parts)

Decomposed parts and the sourcing decision — **RESOLVED BY REUSE (strongest outcome, no vendor):**
- **NFO instrument-master ingest + classification** → already in repo:
  `universe_registry/kite_instrument_master_loader.py::build_phase1_instrument_universe` classifies
  EVERY NFO CE/PE row into `Instrument`s (index vs stock via `NSE_INDEX_OPTION_UNDERLYING_SYMBOLS`).
  No library needed; the full universe already flows out of this — the pruning is downstream.
- **Option-chain data source** → `kiteconnect` (already the project broker SDK, pinned) supplies the
  full master via `instruments("NFO")`. Evaluated alternatives and **rejected** (surface for
  double-check, Rule O.1): `nsepython` / `jugaad-data` / `nsetools` (PyPI) — they scrape the NSE
  option-chain site (fragile, rate-limited, no token/lot-size authority) and would DUPLICATE the
  authoritative Kite master already in use; `py_vollib` / `QuantLib` — pricing libs, irrelevant to
  *universe assembly* (and IV/greeks are already covered in-repo per B32).
- **Chain assembly / strike-expiry indexing** → plain selection over the classified list; no
  maintained standalone library does exactly "keep the full NFO chain, ATM-anchor per underlying"
  that isn't heavier than a ~40-LOC pure function. Build in repo, full-depth, tested.
- **Web-search burn avoided** deliberately: the only candidate class (NSE scrapers) is strictly worse
  than the authoritative Kite master already integrated. If the operator later wants a *broker-independent*
  chain source, revisit `nsepython` then (logged, not silently skipped).

## 4. Open blockers / not-in-scope (Rule K)
- Entry-gate firing (ORB-gating, IV-rank dark) is the A3 strategy slice, not this one — surfaced.
- Index-option closes reaching the segment-tagged close path with fees must be verified on a live
  index-option trade day (market-gated Rule-F accrual).
