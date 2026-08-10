# 164 — L1 NSE Transaction-Cost Engine + Pre-Trade Cost Gate (institutional spec)

**Date:** 2026-08-03 · **Redesign slice:** L1 (build order #1 in `REDESIGN_v1_nse_institutional.md`)
**Skill:** building-engine-grade-features (Rule P) · **Status:** SPEC → building
**North-star:** *"Every signal gated on round-trip breakeven … venue/segment/cost selection outranks any
execution tweak. Nothing is real without it."* (redesign §3 L1). This is the **reality filter** — the
biggest missing piece — that makes every downstream P&L honest.

## 1. Why this is an ENGINE, not a fee calculator (depth justification)

A thin diagnostic version would be a ~60-line function: `charges = turnover * rate` per component, summed.
That is a **monitor**, not an engine. This engine is decision-grade because it adds the four things the
diagnostic omits (per research/155's depth-gap list):

- **Carried, calibrated STATE (slippage model).** Statutory charges are a deterministic formula, but the
  *dominant* real cost on NSE intraday is **slippage** (spread + impact), which is NOT a constant — it must
  be **fitted from real quotes/fills per segment and liquidity bucket** and **evolve as fills accrue**
  (Rule Q maturity ladder: half-spread prior → empirical quantile → impact-aware). A fee calculator has no
  state; this engine persists and updates a slippage model.
- **Real input pipeline from RAW sources.** Consumes the real Kite quote (bid/ask/tick/lot/LTP), the real
  option premium + lot size, and real historical fills — not a hand-typed turnover number.
- **Decision-grade output that CHANGES behavior.** Emits a hard **pre-trade cost gate**: a signal's
  expected edge (from the strategy) must exceed round-trip cost + a safety margin, or it is **vetoed or
  resized**. This is wired into the entry path at every site — it changes which trades happen. Without the
  gate this is just a label.
- **Point-in-time correctness.** The statutory schedule is **effective-dated** (STT/stamp/exchange rates
  have all been revised), so a backtest on 2024 data uses 2024 rates, not today's — killing a subtle
  look-ahead-in-costs leak that a naive calculator introduces.

**SOTA analog:** NautilusTrader's `FeeModel` + `FillModel`/slippage, and the crypto-bot blueprint's
"cost engine gating every signal." Institutional systems never let a signal reach sizing without clearing
modelled round-trip cost.

## 2. Segments covered (Rule L — all three equally)

1. **Equity intraday** (NSE cash, MIS) · 2. **Equity delivery** (CNC — for completeness/holding edge cases)
3. **Index options** (NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY/NIFTYNXT50) · 4. **Stock options** (~210 underlyings)
Futures are out of phase-1 scope (schedule includes their rates as data, gate not wired).

## 3. Cost components (exact formulas — RATES populated from verified research, doc/research agent 2026-08-03)

Round-trip cost = Σ over both legs (buy, sell) of:
1. **STT/CTT** — segment-specific leg + base (equity intraday: sell-side on turnover; delivery: both sides;
   options: sell-side on **premium**; option **exercise**: on intrinsic — a distinct nuance). *(exact % ← research)*
2. **Exchange transaction charge (NSE)** — % of turnover (cash) / % of premium (options). *(← research, per-segment)*
3. **SEBI turnover fee** — ₹ per crore of turnover. *(← research)*
4. **Stamp duty** — buy-side only, % per segment (2020 uniform regime). *(← research)*
5. **GST** — 18% on (brokerage + exchange txn + SEBI fee). *(base confirmed ← research)*
6. **Brokerage** — broker-configurable; default **Zerodha** model (delivery ₹0; intraday/F&O `min(0.03%·turnover, ₹20)` per order). Pluggable per-broker.
7. **DP charges** — delivery sells only (₹/scrip/day) — modelled for delivery.

All rates live in an **effective-dated schedule** (`ScheduleVersion(effective_from, source_url, rates)`),
sourced with provenance — NOT inline literals (self-describing + auditable). Statutory rates are external
facts (not tunable params), so they are config-with-provenance; the ONE data-derived, self-calibrating
piece is the slippage model (§4).

## 4. Slippage model (the carried state — the engine's core)

`SlippageCalibrationModel` — per (segment, liquidity_bucket) estimate of round-trip slippage in bps.
- **Liquidity bucket** = data-derived from ADV / spread / price (percentile buckets over the real universe,
  never hardcoded thresholds — Rule "no hardcoded values").
- **Maturity ladder (Rule Q):**
  - *gathering* (few fills): prior = **half-spread** from the real quote (bid/ask) + a conservative impact
    term (square-root/Almgren-Chriss style on order-size/ADV).
  - *earned* (enough fills in a bucket): empirical **fill-vs-mid slippage** quantile (e.g. p75) replaces the
    prior via shrinkage (hierarchical pooling toward the segment mean for thin buckets).
- **State store:** persisted params per bucket (SQLite), `have N / need M` surfaced; arms automatically as
  fills accrue, no code change.
- Input: real quotes (spread, tick) + real fills (entry/exit vs mid). Provides slippage bps to the engine.

## 5. Modules (decomposed, self-describing names)

```
src/nse_algo_trader/cost_engine/
  nse_statutory_cost_schedule.py     # effective-dated STT/exchange/SEBI/stamp/GST rates + provenance; per-segment lookup
  broker_brokerage_models.py          # pluggable brokerage (ZerodhaBrokerageModel default); per-order min(%,cap)
  nse_transaction_cost_engine.py      # CORE: round-trip cost per leg+component → RoundTripCost(bps, ₹, breakdown)
  slippage_calibration_model.py       # STATE: per-(segment,bucket) slippage; maturity ladder; fitted from fills
  liquidity_bucketer.py               # data-derived ADV/spread/price percentile buckets (no magic thresholds)
  slippage_model_store.py             # SQLite persistence of calibrated params + accrual counts
  pre_trade_cost_gate.py              # DECISION: expected-edge vs round-trip-cost → PASS / RESIZE / VETO
  cost_engine_dashboard_surface.py    # Rule N surface (breakeven bps per segment, slippage maturity, veto counts)
```

## 6. Decision integration (Rule G — wired, no orphan)

The `PreTradeCostGate` sits in the entry path: strategy emits a signal with an **expected edge** (target−entry
in bps, already computed by strategy_engine); the gate computes round-trip cost bps for that instrument/size
and returns:
- **PASS** if `expected_edge_bps ≥ roundtrip_cost_bps + margin`;
- **RESIZE** if a smaller size clears (impact scales with size) — return the max viable size;
- **VETO** otherwise, with the reason + the shortfall bps (logged, surfaced).
Wired at the same entry sites the existing risk gate uses (cash ORB entry, option entry). Runs BEFORE sizing.
No signal reaches capital without clearing modelled cost (redesign promotion rule).

## 7. Verification plan

- **Unit (Rule O):** each fee component vs KNOWN reference values from the Zerodha/official brokerage
  calculator for concrete trades (e.g. a ₹1L intraday equity round-trip; a NIFTY option 50-lot) — exact ₹.
- **Property/invariant:** round-trip ≥ one-way; monotonic non-decreasing in qty & price; all components ≥ 0;
  breakeven bps > 0; delivery brokerage = 0 (Zerodha); GST base excludes STT/stamp.
- **Adversarial:** qty=0, penny stock (₹1), huge order vs ADV (impact dominates), missing quote (fallback to
  prior), an effective-date boundary (rate change day picks the right schedule).
- **Rule J hermetic:** slippage model fitted on injected real-shaped fills behind a DI seam.
- **Rule F real-data:** run the engine on the REAL live universe (2,400 cash + option chains) — inspect
  breakeven bps per segment by eye; confirm the gate vetoes sub-cost signals on the real feed. Wire the
  veto counts onto the dashboard.

## 8. Open decisions / blockers (Rule K)
- Exact statutory rates: pending the research agent's verified figures (effective-dated, with source URLs).
- Real-fill slippage accrual is market-gated → the model ships complete with the half-spread+impact prior
  ACTIVE; empirical arming is the one permissible live-accrual blocker (logged), function never reduced.

## 9. Sourcing (Rule O.1) — COMPLETED (research agent, 2026-08-03)

**Key finding — this is SALVAGE, not greenfield.** A cost model already exists:
`paper_trading/indian_trading_cost_model.py` (+ design doc `b28_...md` + tests). L1 therefore =
(a) HARDEN it to verified rates + effective-dating, and (b) BUILD the missing pre-trade GATE (the model
today is a post-hoc paper-P&L cost calc, consumed by `live_universe_paper_loop.py` +
`option_credit_spread_live_path.py` — NOT a pre-trade decision gate). Existing slippage:
`fill_slippage_model.py` (half-spread) + `market_impact_fill_model.py` (size impact) — reuse for the gate's
slippage bps.

**Verified current rates (primary sources; effective dates):**

| Segment | STT | NSE exch txn | SEBI | GST base | Stamp (buy) | Brokerage (Zerodha) |
|---|---|---|---|---|---|---|
| Equity intraday | 0.025% sell | **0.00307%** both | 0.0001% | 18%×(brk+exch+SEBI) | 0.003% | min(0.03%,₹20)/order |
| Equity delivery | 0.1% both | 0.00307% both | 0.0001% | same | 0.015% | ₹0 (+DP ₹15.34/scrip/day sell) |
| Index/stock options | **0.15% sell on premium** (↑ from 0.10%, eff 1-Apr-2026) | **0.03553% premium** each side | 0.0001% | same | 0.003% premium | flat ₹20/order |
| Futures (context) | 0.05% sell (↑ Apr-2026) | 0.00183% | 0.0001% | same | 0.002% | ₹20 |

Primary NSE circular **NSE/FA/73061** (27-Feb-2026, eff 1-Mar-2026, PDF text fetched): cash **₹307/cr**,
options **₹3,553/cr** premium, futures **₹183/cr**, each side (txn+IPFT combined; total outflow unchanged).
Options exercise STT = 0.15% on **intrinsic** (buyer) — the Sept-2019 rule, not full notional. GST excludes
STT & stamp. STT sell-leg only; stamp buy-leg only.

**CONFIRMED LIVE BUG:** `indian_trading_cost_model.py:68` cash `exchange_transaction_charge_rate=0.0000297`
→ verified **0.0000307** (0.00307%, NSE/FA/73061). ~3.4% understatement on that fee line. FIX. (Options
rate 0.0003553 confirmed correct; options STT 0.0015 confirmed correct.)

**OSS triage — ALL REJECTED (keep the in-repo cited-constant approach):**
| Candidate | Verdict | Evidence tier |
|---|---|---|
| PyPI `zerodha-brokerage-calculator` (repo pushed 2026-07-21) | REJECT — options STT hardcoded 0.05% (3 hikes stale), futures STT 0.01% | tier-2 (read `calculator.py` source) |
| `tahseenjamal/zerodha_brokerage_calculator` (2026-04-13) | REJECT — identical stale `STT_FACTOR['options']=0.0005` | tier-2 (source read) |
| `Pkaran01/BrokerageCalculator` (2021) | REJECT — 5y stale, spans 3 rate revisions | tier-1 (staleness) |
| NautilusTrader `FillModel`/`FeeModel` | not vendored — probabilistic-tick slippage, would need a bespoke NSE %-tiered FeeModel anyway; reuse repo's own | tier-1 (I/O shape) |
| vectorbt fees/slippage | not vendored — constant-fraction only, no impact curve | tier-1 |
| Almgren-Chriss impls | port the formula (already in `market_impact_fill_model.py`), don't depend — all are stale notebooks | tier-1 |

Rationale: every OSS calculator carried ≥1 materially stale statutory constant (source-verified) — exactly
the "silently stale rate" failure the repo's own b28 doc predicted. Bespoke-in-repo is the correct, deeper
choice. No vendor.

## 10. Revised build order (salvage)
1. Fix the confirmed rate bug + cash-intraday brokerage `min(0.03%,₹20)` in the existing model (+ tests).
2. Add the effective-dated schedule (point-in-time rates; pre-Apr-2026 options STT 0.10%) with provenance.
3. Build `pre_trade_cost_gate.py` (statutory + slippage → breakeven bps → PASS/RESIZE/VETO vs expected edge)
   with carried veto-stats state; wire AFTER `pre_trade_risk_gate` sizing in the entry path.
4. Dashboard surface + SYSTEM_MAP + tests (unit vs known ₹ + property + adversarial + real-data).
