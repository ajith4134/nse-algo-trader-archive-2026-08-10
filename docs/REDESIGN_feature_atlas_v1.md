# REDESIGN — full feature/idea atlas for the NSE institutional system (v1)

**Date:** 2026-08-02 · Companion to `REDESIGN_v1_nse_institutional.md`. This is the COMPLETE menu to
**select and prioritize from** before any build — the 3 harvested projects are a *sample*, not the
boundary. Legend: ⭐ already in one of the 3 repos · ✅ common/adjacent, not yet built · 🚀 advanced ·
🌌 ultra/frontier. ⚠️ = NSE-specific fact to verify (SEBI rules/rates/lots change) before it sizes a control.

> NSE reality the crypto repos never modelled: SEBI position limits + **MWPL / F&O ban list**, **ASM/GSM**
> surveillance, **circuit filters / price bands**, weekly index-option **expiry-day** dynamics, **physical
> settlement** of stock F&O, **peak-margin / SPAN+exposure**, T+1 settlement, STT/CTT, corporate actions,
> **FII/DII + participant-wise OI**, SLB, holiday/Muhurat calendar. These are first-class here.

---

## 1. Market data & ingestion
⭐ Kite live ticks + historical bars · ⭐ full option chain · ⭐ 1s bars · ✅ **bitemporal/point-in-time
store** (event/ingestion/availability time) · ✅ frozen tradable-universe per date · ✅ gap detection +
provenance-flagged backfill · ✅ corporate-action adjustment (splits/bonus/dividend/rights) ⚠️ · ✅
**circuit-band / ASM / GSM / F&O-ban state per symbol** ⚠️ · ✅ index constituents + weights (NIFTY/BANKNIFTY/
FINNIFTY/MIDCPNIFTY/sectoral) · 🚀 **participant-wise OI** (FII/DII/client/pro) ⚠️ · 🚀 **FII/DII cash flows**,
bulk/block deals · 🚀 full L2/market-depth (5/20 level) + order-flow tape · 🌌 **tick-level order-book
reconstruction** + microstructure store · 🌌 multi-broker consolidated feed (Kite+Upstox+Angel) with
liquidity-weighted cross-check.

## 2. Feature engineering / signals
⭐ Black-Scholes IV ⭐ VPIN/participant positioning · ✅ realized vol multi-horizon, **HAR-RV** · ✅
depth-weighted order-flow imbalance (never L1) · ✅ triple-barrier labelling + sample-uniqueness · ✅
fractional differentiation (stationarity w/ memory) · ✅ **option-chain features**: PCR, max-pain, IV
skew/term-structure, OI build-up (long/short) · ✅ funding-analog = **cash-futures basis / roll** · 🚀
absorption detection · 🚀 **India VIX** regime features ⚠️ · 🚀 cross-sectional ranking across the F&O
universe · 🚀 expiry-day / day-of-week / event seasonality · 🌌 microprice + Kyle's lambda · 🌌 learned
representations (TS→image→CNN: GAF/MTF) · 🌌 alt-data (news/social/dev-activity) behind a quarantine.

## 3. Models
⭐ (nse-crypto-bot-final node library: GBT, reservoir, Darts N-HiTS/TCN, HMM/GMM, gplearn) · ✅ **mandatory
linear/naive baseline** every model must beat · ✅ **LightGBM primary** (CPU-native) · ✅ meta-labelling
(López de Prado) · ✅ rolling walk-forward retrain · ✅ model registry w/ aliases · 🚀 stacked ensemble ·
🚀 champion/challenger + delayed-label "shadow-before-swap" · 🚀 meta-model over the experiment ledger
(learns which families work in which regime) · 🌌 deep-learning representation front-end feeding a simple
decider · 🌌 conformal prediction for calibrated intervals into sizing.

## 4. Strategy families (the alpha — pick where you compete)
✅ **Intraday mean-reversion / ORB** (prior build's measured NSE-adjacent truth) · ✅ momentum/trend
(swing, latency-insensitive) · ✅ **cash-futures basis / calendar-roll carry** · ✅ **index-option premium
selling** (theta, expiry-day) · ✅ pairs / statistical arbitrage (NSE cointegrated pairs) · 🚀
**event-driven** (earnings, index rebalance, F&O ban entry/exit, corp actions) · 🚀 **variance-risk-premium
harvest** (IV>RV on index options) · 🚀 delta-neutral vol / gamma scalping · 🚀 dispersion (index vs
single-stock vol) · 🚀 sector rotation · 🌌 volatility-surface relative value · 🌌 cross-asset (equity↔
INR/commodity/bond) · ❌ HFT/latency-arb (closed from a retail VM — the prior build proved it).

## 5. Execution
⭐ market/limit orders · ✅ **idempotent client order IDs** · ✅ partial-fill tracking · ✅ signal-expiry /
TIF discipline · ✅ **cost-aware maker/taker + segment routing** · ✅ per-order slippage budget + abort ·
✅ **Kite GTT / basket / cover / bracket orders** · ✅ cross-strategy netting (don't trade against
yourself) · 🚀 impact-aware slicing (only where clip > liquidity) · 🚀 **SPAN+exposure margin-aware
sizing** ⚠️ · 🌌 smart order routing across brokers · 🌌 RL execution agent (dense reward).

## 6. Options & derivatives (F&O — a whole sub-system)
⭐ BS IV · ✅ **full Greeks (Δ Γ ν Θ ρ)** per-position + portfolio-aggregated · ✅ **IV surface fit**
(skew + term structure) · ✅ Greeks-based pre-trade gate (a 2nd risk vocabulary) · ✅ **physical-settlement
handling** for stock F&O ⚠️ · ✅ expiry/pin-risk management · ✅ margin (SPAN) calculator ⚠️ · 🚀 strategy
builder (spreads/straddles/strangles/iron-condor/butterfly/calendar/diagonal) · 🚀 auto delta-hedge
scheduler · 🚀 vega/gamma exposure limits · 🌌 local-vol / SABR / rough-vol surface calibration · 🌌
American-option pricing for stock options (physical, early exercise).

## 7. Risk management
⭐ pre-trade risk gate · ✅ max position/order/rate + price-collar + max-leverage · ✅ **max daily loss +
drawdown kill** · ✅ per-symbol & aggregate exposure, **correlation-aware** limits · ✅ **MWPL / F&O-ban /
position-limit guard** ⚠️ · ✅ liquidation/margin-shortfall monitor · ✅ circuit-limit aware order rejection ·
🚀 graduated **drawdown ladder** (−5/−10/−15%) · 🚀 correlation-breakdown breaker (regime-split) · 🚀
kill-switch as a separate watchdog process + reconciliation on restart · 🌌 CVaR / tail-risk + stress
scenarios (2008/2020/flash-crash replays) · 🌌 real-time portfolio VaR w/ Greeks.

## 8. Portfolio & capital allocation
⭐ capital_allocation module · ✅ **vol-target sizing** primary + **fractional-Kelly ceiling** · ✅
P&L attribution by cost component (edge/fees/slippage/impact) · 🚀 **discounted-bandit allocator**
across strategies · 🚀 capacity tracking per strategy · 🚀 **RMT correlation denoising** (Marchenko-Pastur)
· 🚀 **CVXPY constrained optimizer** (Markowitz/CVaR/cardinality) · 🌌 Bayesian hierarchical alpha
(NumPyro) · 🌌 regime-conditional allocation.

## 9. Validation & research integrity (the money-discipline core)
⭐ experience/experiment memory · ⭐ (vendor) **cpcv.py** + **backtest.py** · ✅ **experiment ledger incl.
abandoned runs** · ✅ **trial registry** (honest cumulative N) · ✅ **holdout custodian** · ✅ purge+embargo
per family · ✅ **Deflated Sharpe as in-loop fitness** · ✅ MinBTL hard gate · 🚀 PBO/CSCV · 🚀 BH-FDR on the
promoted set · 🚀 mechanism-declaration + mechanism-health metric · 🚀 regime-coverage gate (not elapsed
days) · 🌌 bootstrapped max-drawdown distribution for non-arbitrary circuit thresholds · 🌌 Hansen SPA at
the promotion gate.

## 10. Operations & infra
⭐ paper-trading loop · ✅ **order-intent WAL** · ✅ state recovery from broker truth · ✅ **daily Kite
token auto-refresh (TOTP)** ⚠️ · ✅ rate-limit budgeter (Kite limits) · ✅ clock sync + drift alert · ✅
cold-start behaviour · ✅ holiday/Muhurat/session calendar ⚠️ · 🚀 disaster-recovery runbook · 🚀 tiered
alerting (page/notify/log) · 🚀 structured audit log of every decision · 🌌 blue-green deploy + config
versioning/rollback.

## 11. Intelligence / AI / autonomy (the "brain" — DEFERRED to after money)
⭐ (nse-crypto-bot-final brain: node-network + memory + self-coding) · ⭐ (nse-algo-trader organism trunks —
now paused) · 🚀 **node-network of models + learning router** (the blend's phase 2) · 🚀 dual-LLM quarantine
for untrusted content · 🚀 LLM-authored strategy code (sandboxed, gated, never auto-promoted) · 🚀
automated postmortem writer feeding the ledger · 🌌 meta-analysis over the trial registry (self-knowledge)
· 🌌 belief records w/ provenance + half-life · 🌌 the paused organism faculties (conscience/will/axiology…)
re-introduced ONLY as governance overlays with no veto over the risk gate.

## 12. Governance & compliance (SEBI — non-negotiable)
✅ **manual go-live button** · ✅ config versioning + rollback · ✅ **SEBI position-limit / MWPL compliance
checks** ⚠️ · ✅ **STT/CTT/stamp/GST tax-lot record** (exportable) ⚠️ · ✅ per-strategy kill authority ·
🚀 change-log tied to deployments · 🚀 jurisdiction/segment eligibility (what the account may trade) · 🌌
full regulatory audit trail (algo-ID tagging if ever required) ⚠️.

## 13. Dashboard & observability (the "clear dashboard" you're missing)
⭐ dashboard shell · ✅ **one landing view**: live P&L, positions, open risk, promotion state, cockpit
verdict · ✅ P&L attribution by cost component · ✅ per-strategy health board · ✅ fill-quality vs assumed ·
🚀 option Greeks/exposure panel · 🚀 regime + India-VIX panel · 🚀 latency histograms · 🌌 replayable
decision timeline ("why did it trade?") · 🌌 live risk heatmap across the F&O universe.

---

## Combinations (cross-layer fusions worth building as one)
1. **Cost engine (L1) × validation (L9):** Deflated-Sharpe fitness computed **net of the real NSE cost
   model** — so search never promotes edge that fees eat. (Neither repo coupled these.)
2. **Options Greeks (L6) × risk gate (L7) × portfolio (L8):** one risk vocabulary where vega/gamma are
   first-class exposures sized by CVXPY under MWPL limits.
3. **Participant OI + FII/DII flows (L1) × event-driven + VRP (L4):** flow-aware option-selling that
   stands down into F&O-ban / expiry / high-VIX regimes.
4. **Node-network brain (L11) × meta-model over ledger (L9):** the brain learns *which* engines to
   allocate to per regime — but only after L0–L9 make money (your blend).

## The three tiers (of the whole system)
- **Base ✅** — the lean money-first core: L0 truth · **L1 NSE cost engine** · L2 validation (DSR+CPCV+
  trial registry) · L3 ops+risk gate · **one L4 family** to paper/shadow · L5 one dashboard. *A real,
  honest, small NSE trader.*
- **Advanced 🚀** — add the F&O depth (full Greeks + IV surface + option strategies), the bandit
  allocator + CVXPY/RMT portfolio, event-driven + VRP families, mechanism-health + regime-coverage gates,
  flow/participant-OI signals, the richer dashboard.
- **Ultra 🌌** — the node-network + learning brain routing capital across engines; vol-surface RV +
  dispersion; conformal/Bayesian sizing; tick-level microstructure; self-knowledge meta-analysis — the
  autonomous-desk vision, but earned on top of a base that already trades profitably.

## Open questions — pick before we spec anything
1. **Which L4 strategy family goes first?** (intraday mean-reversion/ORB · index-option premium selling ·
   cash-futures basis · event-driven — I can `deep-research` a menu with NSE evidence.)
2. **Cash-equity, F&O, or both** in the first cut? (drives how much of L6 is P0.)
3. **How autonomous** at launch — manual-approve every order, or auto within hard limits?
4. **Which 🌌 items are actually wanted** vs nice-to-have, so we don't rebuild the sprawl.
5. **Your new ideas/trades** — what's not on this map yet?
