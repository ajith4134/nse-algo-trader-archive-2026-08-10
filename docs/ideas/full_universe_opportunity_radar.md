# Full-universe opportunity radar (watch everything, fire on any perfect setup)

**Seed (user's words):** *"instead of filtering and choosing the best stocks to trade in intraday cash
and options, I need the AI to keep an eye on the FULL universe in both segments and find situations/
conditions where ANY trade in the universe has the perfect condition to place and exit a profit trade —
however small it may be — a constant lookout on the full universe."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring (5 research agents running) · relates to [idea #1](main_ai_brain_all_strategies.md)

---

## 1. The bigger picture (expand-idea)

Stripped down, this is an **opportunity RADAR / attention layer** — a continuous streaming scanner over
the ENTIRE cash + options universe that fires the instant *any* instrument meets a pre-defined
high-probability enter+exit condition. The shift is **opportunity-driven (event-triggered), not
watchlist-driven (pre-selected).** Category one level up = **market-wide setup / anomaly detection**;
one level down = the individual trigger conditions (VWAP-extreme, volume-surge, IV-anomaly…).

**Crucially, this is NOT a competitor to idea #1's brain — it's the PERCEPTION layer that feeds it.**
```
[FULL-UNIVERSE RADAR (this idea)] → candidate opportunities → [BRAIN/router (idea #1)] → risk gate → exec
```
The radar finds *where* something is happening anywhere in the universe; the brain decides *whether/
how* to act given regime + capital.

## 2. The three walls this idea slams into (design around them or it fails)

**"Watch everything, take any small profit" hits three hard walls. Each is a required sub-engine:**

### Wall 1 — COST (the killer of "however small")
"However small a profit" collides head-on with the SEBI finding (idea #1): **57% of retail losses are
transaction costs.** A tiny target often **net-loses** after STT + brokerage + GST + stamp + exchange +
slippage. → **Every opportunity passes a NET-of-cost expected-value gate: fire ONLY if E[profit] >
round-trip cost + slippage + a margin.** "Small profit" is allowed only when it clears the cost floor.
[→ RESEARCH agent-4: exact round-trip bps + break-even move.]

### Wall 2 — FALSE DISCOVERY (scanning everything = finding noise)
Scanning 2000+ stocks × tens of thousands of option contracts × many conditions × continuously = a
**massive multiple-testing problem**. You WILL find "perfect setups" by pure chance. → **FDR control
(Benjamini-Hochberg/Yekutieli) + per-signal-type hit-rate tracking + require a MECHANISM, not just a
correlation.** A fired signal is a *hypothesis*, confirmed by historical hit-rate before it sizes real
capital. [→ RESEARCH agent-3.]

### Wall 3 — THROUGHPUT (real-time over the whole universe)
2000+ cash + full option chains live within Kite limits (quote 1/s, historical 3/s) = a **streaming/
incremental** problem, not batch polling. → **WebSocket tick ingest → per-instrument rolling state →
incremental condition eval (river/online)**, with a liquid-subset pre-filter to keep the option
universe tractable. [→ RESEARCH agent-1.]

### (+ Wall 4 — SELECTION) when many fire at once
Finite capital/margin + order-rate limits + correlation risk → **rank & pick** (net-EV × confidence ×
executability, portfolio-aware, knapsack/CVXPY, bandit across signal types). [→ RESEARCH agent-5.]

## 3. Architecture (the radar)
```
ingest (Kite WebSocket, batched)                         [agent-1]
  → per-instrument streaming state (rolling windows, incremental indicators)
  → CONDITION/ANOMALY eval (setup library + z-score/EWMA outliers)   [agent-2]
  → NET-EV gate (E[profit] > round-trip cost+slippage)  [agent-4]  ← Wall 1
  → FDR / hit-rate gate (is this real or noise?)         [agent-3]  ← Wall 2
  → PRIORITIZE & select (capital/margin/correlation)     [agent-5]  ← Wall 4
  → hand to BRAIN (idea #1) → risk gate → execution
  → track realized hit-rate per signal type → feeds the gate (learning loop)
```

## 4. The setup/condition library (what "perfect condition" means)
Compute continuously per instrument; each is a *candidate*, gated by Walls 1–2:
- **Cash:** VWAP-extreme reversion · relative-volume surge · opening-range break · momentum ignition ·
  gap scan · consolidation breakout · order-flow imbalance · RSI/BB extreme. [→ agent-2]
- **Options:** unusual options activity (vol/OI spike) · IV-rank/percentile extreme · IV-vs-realized gap ·
  skew dislocation · PCR extreme · cheap gamma pre-event · mispriced strike. [→ agent-2]
- **Framing:** treat "opportunity" as a **statistical anomaly** (robust z-score/EWMA on price/volume/
  spread/IV) — online anomaly detection (river HalfSpaceTrees). Entry+exit = small target + stop +
  time-exit; win-rate vs reward-risk of small-target scalping. [→ agent-2]

## 5. Base → Advanced → Ultra
- **Base ✅:** stream the LIQUID subset (top ~200–500 cash + ATM-weekly NIFTY options), 2–3 setup
  conditions, net-EV gate + hit-rate tracking, fire → brain. A real radar on a tractable universe.
- **Advanced 🚀:** full 2000+ cash + full option chains, anomaly-detection setups, FDR control, portfolio-
  aware knapsack selection, bandit across signal types.
- **Ultra 🌌:** self-calibrating conditions (the radar learns which setups pay in which regime via the
  ledger), microstructure/order-flow triggers, cross-instrument (lead-lag, options→cash) signals.

## 6. Open questions (to finalize)
1. Universe scope at launch — liquid subset first (recommend) or literally all 2000+ / all contracts?
2. Segments — cash + options together, or cash radar first?
3. Minimum edge threshold — how far above the cost floor must E[profit] be to fire?
4. Does the radar AUTO-execute (within idea-#1's hard limits) or only surface candidates to the brain?

## 7. Research findings (folding in from 5 agents)

### 7-selection. Prioritizing when many fire at once (agent-5 / Wall-4) ✅
Selection = **resource-constrained combinatorial optimization under uncertainty**, 4 stacked
constraints: **capital · margin (SPAN nonlinear — hedged combos cost less) · order-rate (Kite 10/s,
400/min, 5000/day) · correlation** (40 sector names gapping = 1 bet taken 40×). The concrete pipeline:
1. **Score each fired signal:** `EV_net/margin × hit-rate(signal-TYPE) × reward:risk × liquidity −
   correlation-penalty`. EV is net of full costs; hit-rate tracked per signal-type (feeds the bandit).
2. **De-noise + cluster:** RMT / **Marchenko-Pastur** denoise the candidate correlation matrix → **HRP**
   cluster → cap picks per cluster (kills redundant same-bet).
3. **Select:** **CVXPY mixed-integer knapsack/QP** — maximize Σscore·x − λ·xᵀΣx s.t. capital + margin +
   per-cluster + per-sector caps. Greedy value-density fallback when the burst must fire inside the
   order-rate window. **PyPortfolioOpt DiscreteAllocation** → integer lots.
4. **Execute:** **priority queue** (M/M/1/K) — best-first through Kite's rate limit; every signal carries
   a **decay TTL** (per-type half-life) → **DROP stale signals, don't queue-and-wait** (alpha decays in
   minutes). Sizing = **fractional Kelly** (multi-bet Kelly picks *and* sizes simultaneous bets).
5. **Learn:** realized outcomes → **Thompson / contextual bandit** reweights signal-type priors.
   Academic frame = **Bandits-with-Knapsacks** (arXiv 1305.2545) — arms consume a capital budget.
- **OSS:** CVXPY · PyPortfolioOpt · **riskfolio-lib** (HRP + cardinality/sector caps) · contextualbandits
  (LinUCB/Thompson + off-policy eval) · Vowpal Wabbit. (⚠️ agent hit search-quota → theory/OSS solid,
  live NSE specifics thinner; SPAN calc page 429'd — re-verify margin mechanics.)

### 7-architecture. Real-time full-universe scan (agent-1 / Wall-3) ✅
**Hard ceiling (Kite, official docs):** **3,000 instruments/WebSocket connection · 3 connections/key =
9,000 instruments/key.** 2,000 cash stocks fit in ONE connection (trivial bandwidth). **The option
chain is what blows it** (tens of thousands of contracts) → **(a) pre-filter to liquid near-ATM strikes
before subscribing, and/or (b) multi-key sharding** (N keys × 9,000). REST polling can't be the feed
(quote 1/s × 500/call → ~4s to cycle 2,000 stocks).
- **Pipeline:** WebSocket ingest → fan-out bus (Redis/ZeroMQ/Kafka) → **per-symbol incremental state
  (O(1)/tick — never recompute from history)** → condition eval (event-driven per-tick, OR columnar
  micro-batch via **Polars/DuckDB** for cross-sectional screens) → signal.
- **OSS:** `streaming-indicators` (O(1) SMA/EMA/RSI/ATR/VWAP/SuperTrend classes) · `river` (online ML/
  anomaly) · `faust-streaming` (durable, Kafka) · **OpenAlgo** (ZeroMQ normalized-tick bus, 35 brokers —
  closest NSE reference arch) · **NSE-Stock-Scanner** (325★, 1800 stocks, Kite) · NautilusTrader (arch
  reference). ⚠️ agent hit search-quota; exact live option-contract count unverified (pull from Kite
  `/instruments` daily dump — authoritative).
- **→ confirms base-tier: liquid subset FIRST (top ~200–500 cash + ATM-weekly NIFTY), scale via sharding.**

### 7-cost. Small-profit vs NSE cost economics (agent-4 / Wall-1) ✅ — the decisive constraint
**Round-trip cost:** cash intraday **~6–11 bps** (small tickets worse; ~6bps floor) · options **~25–65
bps** on premium (cheap OTM worst — **STT 0.15%-sell = 15bps alone from Apr-2026**). **Break-even move:
cash ≥0.06–0.11% · options ≥0.27–0.65%.** → a 1–2 tick scalp is **usually BELOW break-even = guaranteed
net loser.** SEBI: **80% of high-frequency (500+ trades/yr) traders net-negative** — turnover multiplies
the fixed-cost drag, never averages edge out. "Any profit however small" is empirically a trap.
- **When tiny edges survive (the only ways):** **maker/limit orders that EARN the spread** (flips the
  single largest cost from debit to credit) · most-liquid names only (spread ≈1 tick) · **netting**
  (fewer, larger round-trips — the OPPOSITE of high-frequency). True HFT/market-making closed to a cloud
  VM (colocation/latency moat + adverse selection).
- **→ THE GATE (reshapes the seed):** per-trade **net-EV gate** — fire only if
  `edge_bps > (cost_bps + live_spread_bps + slippage_bps) × 1.5–2×`, with **instrument+size-aware cost**
  (NOT a constant), **live** spread from the book, and a **per-segment min-edge floor** (~6–8bps large
  cash, ~10–11 small cash, **~25–30bps options**). **Prefer maker orders.** Track realized-vs-modeled
  slippage → throttle any segment that drifts negative. This IS Wall-1, quantified.

### 7-fdr. False discovery at universe scale (agent-3 / Wall-2) ✅
**The math:** FWER = 1−(1−α)^m → near-certainty fast. A **2,000-ticker × 5-condition × 3-window scan =
30,000 tests → ~1,500 false "opportunities" from pure NOISE.** (STW-1999: 7,846 rules, apparent edge
vanished OOS.) Scanning everything guarantees false hits — must be controlled, not trusted.
- **Control method:** **Benjamini-Yekutieli (BY) FDR** = the right default (handles arbitrary dependence
  — scanner signals ARE correlated; ~7.5× stricter than BH at m=1000). Storey q-value adds power.
  **Bonferroni is wrong** (controls FWER / zero-tolerance, kills all signal). 
- **Effective-trials DSR** (Bailey-LdP): `N̂ = ρ̂ + (1−ρ̂)·M` — 20,000 correlated backtests at ρ=0.9 →
  **~2,000 effective trials**. Gate capital on **DSR ≥ 0.95, PBO < 50%** (CSCV).
- **Guardrails:** log EVERY trial (not just winners) · **track each signal-TYPE as ONE ongoing trial
  series** (a hit is not independent proof) · walk-forward re-confirm (not one holdout) · **mechanism-
  motivated signals get a LOWER hurdle than pure pattern-matches** (Harvey-Liu-Zhu) · bound the search
  (1/e optimal-stopping). → the radar treats each fired signal as a HYPOTHESIS, promoted only by tracked
  hit-rate + FDR survival, never traded on first sighting.

### 7-setups. Setup/opportunity detection (agent-2) ✅
**Setup library (candidates, all gated):** _Cash (10):_ ORB (OR + vol≥1.5×) · VWAP ±2σ reversion (skip if
ADX>25) · RVOL surge (3–10×) · gap-and-go / gap-fade · momentum ignition · volume z-score anomaly ·
order-flow imbalance · RS/RW leaders · NR7/BB-squeeze breakout · Connors-RSI(2) mean-reversion.
_Options (7):_ unusual options activity (vol/OI) · IV-rank extreme · **IV−RV spread (VRP)** · skew
dislocation · PCR extreme · sweep/block (ISO) · ~~cheap gamma pre-event~~.
- **Streaming anomaly stack:** robust **z-score (median/MAD) + EWMA** first-pass per-tick O(1) → **CUSUM**
  changepoint → **Robust Random Cut Forest** second-pass only on tripped symbols (bounds compute).
  river `HalfSpaceTrees` weak on clustered anomalies.
- **Scalp def:** seconds–minutes hold; 2R or ATR-scaled target; **4–8 min time-stop** (Carver's decay
  window). ⚠️ cost-modeled R:R collapses toward ~1:1 → breakeven win-rate ~50%+.
- **🔴 DECISIVE evidence (matches cost agent):** small-target scalping does NOT reliably survive costs at
  retail scale — **Carver** (ex-AHL): pre-cost Sharpe 28.8 → post-cost collapse → "didn't work"; Brazil
  97% lose; Taiwan negative every year; ESMA 74–89% lose. Order-flow imbalance **65% concurrent but ~3%
  predictive R²**; cheap-gamma-pre-event **contradicted** (straddles −8%/event — options overprice moves).
  → **the radar is a TRIAGE/candidate-surfacing engine, NOT a guaranteed-edge scalper.**

---
**ALL 5 RESEARCH AGENTS COMPLETE.** → §8.

## 8. Finalized decision (synthesis of all 5 agents)

**The valid core survives; the "any profit however small" premise does NOT.** The radar is a genuinely
valuable **full-universe perception/triage layer** — but every agent independently killed naive
small-target scalping. So the seed is **reshaped, not rejected:**

**What we ARE building — an OPPORTUNITY RADAR that feeds the brain (idea #1), NOT a blind scalper:**
1. **Streaming full-universe scanner** over the LIQUID subset first (Kite ceiling = 9,000 instr/key →
   top ~200–500 cash + ATM-weekly NIFTY options; scale via multi-key sharding). Incremental O(1)
   per-symbol state + anomaly stack (robust-z/MAD + EWMA + CUSUM → RRCF second-pass).
2. **A setup/condition library** (10 cash + 7 options triggers) — each a **candidate hypothesis**, never
   an auto-trade.
3. **The 4 mandatory gates** every candidate must clear, in order:
   - **Wall-1 NET-EV gate:** fire only if `edge_bps > (cost + live-spread + slippage) × 1.5–2×`, per-
     segment floor (~6–8 large cash, ~10–11 small cash, **~25–30 options**). **Prefer maker/limit orders
     that EARN the spread** — the single highest-leverage lever (flips the biggest cost to a credit).
   - **Wall-2 FDR gate:** Benjamini-Yekutieli + effective-trials DSR≥0.95/PBO<50%; **track each signal-
     TYPE as one ongoing trial series**; mechanism-backed signals get a lower hurdle. A fired signal is a
     hypothesis promoted by tracked hit-rate, never traded on first sighting.
   - **Wall-3 throughput:** streaming + liquid pre-filter + sharding (built into #1).
   - **Wall-4 selection:** RMT-denoise → HRP-cluster → CVXPY knapsack (capital+margin+cluster caps) →
     priority queue with decay-TTL through Kite's 10/s·400/min → Thompson bandit reweights signal-types.
4. **Output = candidates to the BRAIN (idea #1)** which decides act/size given regime + the validated
   engine library. The radar surfaces *where*; the brain + risk gate decide *whether/how*.

**The honest headline (Rule O — surface it):** the evidence (Carver, SEBI 80% HF-losers, Brazil/Taiwan)
says a retail cloud-VM **cannot** win by "taking any tiny profit across the universe" — that premise is
a documented loser. The radar's value is **finding + routing genuine, cost-clearing, validated
opportunities to the engine library**, with maker-order spread-capture as the only durable small-edge
lever. Built this way it's a real perception engine; built as the literal seed it repeats the 91–93%
loss statistic.

**Prerequisites (shared with idea #1):** L1 cost engine (the net-EV gate lives here) · L2 validation
(FDR/DSR) · the brain/router · risk gate. OSS: streaming-indicators · river · Polars/DuckDB · OpenAlgo
(tick bus) · CVXPY/riskfolio-lib/PyPortfolioOpt · contextualbandits · statsmodels.

**🟢 LOCKED (user, 2026-08-02):** radar **surfaces gated candidates → idea #1's brain decides** act/size
(perception layer, not a standalone scalper; auto-exec only through the brain's hard limits). Scope =
**liquid subset first** (top ~200–500 cash + ATM-weekly NIFTY options, one WebSocket connection), scale
to full universe via **multi-key sharding** once proven. Built after/with idea #1's brain (it feeds it).
Prereqs shared with idea #1 (L1 cost engine = the net-EV gate · L2 validation = FDR/DSR · brain · risk
gate). Tracked in docs/BACKLOG.
