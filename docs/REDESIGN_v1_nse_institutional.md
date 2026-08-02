# REDESIGN v1 — NSE institutional trading system (harvest of 3 projects)

**Date:** 2026-08-02 · **Status:** PLAN (repo decision deferred, per user) · **Market:** NSE only
**North-star (from the user's own words):** *fewer things, each built deep like a professional coding
team ships it (real logic + real depth, thousands of justified LOC — never thin "simple" code); proven
to make money on real data; one clear dashboard; lean core now, node-network + brain later.*

This is the front-end plan produced via `idea-to-institutional-spec`. It harvests the best of three of
the user's projects and defines the redesigned system + build order. Per-engine institutional specs
(with acceptance criteria + OSS sourcing) are written one at a time before each engine is built.

## 1. The diagnosis (why nse-algo-trader is being redesigned)

Confirmed by the user: (a) **too sprawling** — 197 branches across 16 "AI-organism" trunks
(conscience, will, sentience, society, axiology, epistemics, intrinsic_motivation, autopoiesis);
(b) **no proven money** — breadth over validated edge; (c) **no clear dashboard**; (d) **code too
thin** — many ~60–150-line scalar diagnostics dressed as engines, not decision-grade depth.

**Root cause:** effort went to *breadth of concepts* instead of *depth of a few money-making engines*.
The redesign inverts the axis: **depth-first, money-first, NSE-only, one dashboard.**

## 2. What each project contributes (harvest)

| Source | KEEP / ADOPT | CUT / DEFER |
|---|---|---|
| **nse-algo-trader** (current) | Kite live data + universe registry · broker OMS/sessions/credentials · Black-Scholes IV + option chain · pre-trade **risk gate** · replay backtester · **verification cockpit** (new) · experience memory · VPIN/participant positioning · dashboard shell | **All 8 AI-organism trunks** (conscience/will/sentience/society/axiology/epistemics/intrinsic_motivation/autopoiesis) → deferred to the "node-network + brain later" phase, not deleted |
| **crypto-bot** (blueprint) | The **6-layer discipline** (Truth→Cost→Search-integrity→Ops→Strategy→Portfolio) · **validation-first** (Deflated Sharpe as in-loop fitness, honest **trial registry**, holdout custodian, CPCV, MinBTL, PBO) · **cost engine gating every signal** · mechanism declaration · regime-coverage gate · the **20-most-forgotten** checklist | Crypto venue specifics (funding/Hyperliquid/sops+age) — not NSE |
| **nse-crypto-bot-final** (prior build) | **`cpcv.py`** (Combinatorial Purged CV) + **`backtest.py`** (vectorbt, no-lookahead) → vendor directly · the **node-network + brain** pattern (for the *later* phase) · **real trading truths** (intraday mean-reversion; naive momentum loses ~0.23%/trade) · FastAPI+React+D3 **dashboard** approach | The premature 500-node breadth + Mackey-Glass dev-data path |

## 3. The redesigned architecture — 6 lean NSE layers (build in this order)

Each layer is a precondition for the next (crypto-bot's rule). **NSE SOTA analog for the ML/validation
stack: Microsoft Qlib; for execution discipline: NautilusTrader's shared backtest/live path.**

- **L0 — Truth (NSE).** One point-in-time data path shared by backtest + live: Kite instrument master +
  historical/1s bars, bitemporal (event/ingestion/availability time), snapshot-on-ingest, frozen
  tradable-universe per date. *Kills look-ahead leakage structurally.* (Salvage `market_data` +
  `universe_registry`; add the bitemporal/availability-time guarantee.)
- **L1 — Reality filter (NSE cost engine).** Every signal gated on round-trip breakeven: **STT +
  brokerage + GST + exchange txn + SEBI + stamp duty + slippage**, per segment (equity delivery/intraday,
  F&O). *Venue/segment/cost selection outranks any execution tweak.* (New engine — biggest missing piece.)
- **L2 — Search integrity.** Trial registry (honest cumulative N incl. discarded runs) · holdout
  custodian · **Deflated Sharpe as the in-loop fitness** · CPCV (vendor `cpcv.py`) · MinBTL · PBO ·
  mechanism declaration. *This is what kills overfitting — the thing that sank the prior attempt.*
- **L3 — Ops floor.** Pre-trade risk gate (salvage) hardened · idempotent order IDs · order-intent WAL ·
  state reconciliation from broker truth on restart · rate-limit budgeter · kill switch. *Nothing lives
  before this.*
- **L4 — One strategy family, end-to-end.** Pick **one** NSE edge and take it all the way to small-live
  through the promotion pipeline (research→paper→shadow→reduced-live). Candidate: an intraday
  mean-reversion / ORB family (the prior build's real truth said intraday NSE-adjacent markets mean-revert).
- **L5 — Portfolio + dashboard.** Vol-target sizing + fractional-Kelly ceiling · drawdown ladder ·
  **one clear dashboard** (P&L attribution by cost component, per-strategy health, promotion state,
  the cockpit verdict). *Every engine visible (Rule N).*

**Deferred to "later" (the blend, Q4):** the **node-network of models + learning brain** from
nse-crypto-bot-final — added *only after* L0–L5 make money, so it amplifies a working base instead of
becoming new sprawl.

## 4. Depth bar (the anti-"thin-code" contract)

Every engine is built via `building-engine-grade-features` to Rule P: a real algorithm/model/solver +
carried state + real input pipeline + output that changes a trade decision + full tests (unit +
property + adversarial + **real-data pass**). Integrate heavyweight libs (Qlib, CVXPY, LightGBM,
statsmodels, vectorbt) — never a bespoke lite reimplementation. Size follows real function, not padding.

## 5. Promotion pipeline (money discipline)

`research → paper → shadow → reduced-size live → full live`, gated by: DSR survives the honest trial
count · CPCV path distribution holds · MinBTL satisfied · shadow signal/execution alignment · **regime
coverage** (seen a real drawdown + a vol spike, not elapsed days) · manual go-live button. **No path
from any signal to capital skips the risk gate.**

## 6. Build order (slices, one at a time — Rule A)

1. L1 **NSE cost engine** (highest missing leverage — nothing is real without it).
2. L2 **search-integrity** core (vendor `cpcv.py` + DSR/MinBTL/PBO + trial registry).
3. L0 **bitemporal truth** hardening of the Kite data path.
4. L3 **ops floor** hardening of the risk gate + WAL + reconciliation.
5. L4 **one strategy family** end-to-end to paper+shadow.
6. L5 **one clear dashboard** + portfolio sizing.
7. (later) node-network + brain.

## 7. YOUR NEW IDEAS — to fold in (needs your input)

You said you have *"new ideas and features and trades."* List them and I'll place each into the layers
above (or open a new one) with an institutional spec. Until then this plan covers only the harvest.

## 8. Open decisions
- **Repo:** salvage-in-place vs greenfield — you chose "decide after the plan." Recommendation once you
  react to this: **salvage** (keep L0/L3/dashboard plumbing that already works; delete the 8 organism
  trunks) — least waste, fastest to money.
- **First strategy family (L4):** to be chosen from a short researched menu before L4.
