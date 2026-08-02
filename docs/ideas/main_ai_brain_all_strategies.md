# Main AI brain + all strategies (cash + options, all regimes)

**Seed (user's words):** *"main ai brain and all the strategies on intraday cash trading full universe
and options both index full universe and all contracts (near/OTM/ATM/ITM) and all option stocks full
universe, all the indicators, all candle chart patterns … how money can be made in volatile regime,
bull, bearish and even in flat markets."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring (6 research agents running; findings fold in below)

---

## 1. The bigger picture (expand-idea) — what this idea REALLY is

Stripped of examples, the seed is **not** "a strategy" or "a list of indicators." It is:

> **A regime-adaptive strategy ROUTER (the "brain") sitting on top of a LIBRARY of validated strategy
> engines that together span cash + options, so that for whatever regime the market is in right now,
> the right engine is deployed at the right size.**

The category one level UP = **meta-strategy / strategy-of-strategies allocation**. One level DOWN =
the individual engines (ORB, VWAP-reversion, iron-condor, long-straddle…). **The user's real intent
lives at the top: the brain that picks.**

**The load-bearing reframe (what makes or breaks this):** the edge is NOT in *owning* all indicators
and all patterns. Owning 200 indicators + 60 candle patterns is the exact trap that sinks retail
systems — the data-snooping problem (Sullivan-Timmermann-White: 7,846 rules on 100y of Dow, the best
fails out-of-sample once corrected for search size). **The edge is in three things:**
1. **Regime detection** — correctly reading volatile / bull / bear / flat (and the transitions).
2. **Matching** — deploying the engine whose Greeks/edge PAYS in that regime.
3. **Ruthless validation** — every indicator/pattern/engine must survive the search-integrity gate
   (Deflated Sharpe, purged CV) before it routes capital. Most won't. That is correct, not failure.

So "all indicators / all patterns" = build the full COMPUTE library (cheap, via TA-Lib/pandas-ta), then
let validation KEEP the few that survive. Breadth of *candidates*, ruthlessness of *promotion*.

## 2. The regime axis — how money is made in each (the heart of the ask)

| Regime | What it looks like | What PAYS (why) | Engines |
|---|---|---|---|
| **Bull trend** | higher highs, ADX↑, price>VWAP | **momentum / breakout / long delta** — trend persistence | ORB-long, momentum, bull-call-spread, long call |
| **Bear trend** | lower lows, ADX↑ down | **short momentum / long puts / defined-risk bear** — downside + rising vol | breakdown-short, bear-put-spread, long put |
| **Volatile / expansion** | wide range, IV↑, ATR↑, gaps | **long gamma / long vol / breakout** — big moves + vega | long straddle/strangle, breakout, long gamma |
| **Flat / range / low-vol** | tight range, IV↓, ADX↓ | **mean-reversion + THETA selling** — nothing moves, time decays | iron condor, short strangle, VWAP-reversion, credit spreads |

This 4-row map is the **spine of the brain**: detect the row → deploy that row's engines. [Regime
detection methods + evidence → RESEARCH agent-1, folding in.]

## 3. The strategy-engine library (full universe)

### 3a. Cash intraday (full 2000+ NSE universe)
ORB + variants · VWAP reversion · VWAP trend/pullback · momentum/relative-strength · gap fade/go ·
range/pivot breakout · mean-reversion (overextension) · pairs/stat-arb (cointegrated) · event-driven.
Universe scanning: liquidity/turnover filter · **exclude circuit-band / ASM-GSM / F&O-ban** · rank
setups · respect Kite rate limits + MIS square-off + STT/cost. [→ RESEARCH agent-6.]

### 3b. Options (index NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY + stock options, all contracts)
Directional (long call/put, covered call, protective put) · verticals (bull-call, bear-put, bull-put,
bear-call) · long-vol (straddle, strangle) · short-vol/theta (short straddle/strangle, **iron condor,
iron butterfly**, credit spreads) · time/skew (calendar, diagonal, ratio, backspread, butterfly).
Contract ladder: ATM/ITM/OTM moneyness changes Δ/Γ/Θ — pick by the engine's Greek intent + liquidity
(OI/bid-ask; NSE liquidity concentrates in ATM weekly index). Needs a **Greeks + IV-surface engine**
(a second risk vocabulary — a short-vol book tiny by notional can be catastrophic by vega). NSE:
weekly-expiry dynamics, physical settlement of stock F&O, SPAN margin. [→ RESEARCH agent-2.]

### 3c. Signal inputs — candidates, not gospel
- **Indicators** (compute-all via TA-Lib/pandas-ta, then prune): trend (EMA/MACD/ADX/Supertrend),
  momentum (RSI/Stoch/CCI), volatility (BB/ATR/Keltner/India-VIX), volume/flow (VWAP/OBV/MFI/CMF),
  breadth (A/D). Prune redundant (don't stack 10 momentum oscillators). [→ RESEARCH agent-4.]
- **Candle + chart patterns** (encode via TA-Lib candlestick fns): single/dual/triple candles;
  H&S/double-top/triangles/flags/wedges. **Efficacy caveat: most fail OOS once corrected** — gate
  every pattern through search-integrity before it trades. [→ RESEARCH agent-3.]

## 4. The AI brain (the router) — architecture

```
market → REGIME CLASSIFIER → STRATEGY ROUTER → engine library → RISK GATE → execution
             (agent-1)         (bandit/meta)      (§3)          (Rule P)      (Kite)
                    ↘ experiment ledger + meta-model (learns which engine pays in which regime) ↙
```
- **Regime classifier:** ADX/VIX/HMM/Markov-switching ensemble → current regime + confidence.
- **Router:** discounted/contextual **bandit** (Thompson) or **meta-model over the ledger** picks the
  engine + size for the regime. NOT a chat-committee — evidence: naive multi-agent LLM committees
  UNDERPERFORM budget-matched; durable pattern = model output behind a HARD deterministic gate. [→ agent-5.]
- **Memory:** episodic (trade ledger) · semantic (market knowledge) · reflective (consolidation).
- **Hard rule:** no engine routes capital until it survives validation (Deflated Sharpe + purged CV),
  and nothing bypasses the risk gate.

## 5. Base → Advanced → Ultra

- **Base ✅:** regime classifier (4 states) + ONE engine per regime (e.g. ORB bull, bear-put bear,
  long-straddle volatile, iron-condor flat) + bandit router + risk gate + validation. A real
  regime-adaptive desk, small.
- **Advanced 🚀:** full engine library (cash + all option structures), Greeks/IV-surface engine,
  indicator+pattern candidate library behind the validation gate, meta-model over the ledger, full
  universe scanning.
- **Ultra 🌌:** the self-learning brain — reflective memory, champion/challenger auto-reevaluation,
  regime-transition anticipation, cross-engine netting, contextual bandits conditioned on microstructure.

## 6. Open questions (to finalize)
1. First regime+engine pair to build? (recommend: **flat→iron-condor/theta** OR **bull→ORB** — both
   have the clearest edge and data.)
2. Cash-first or options-first for engine #1?
3. How many regimes at launch — the clean 4, or finer?
4. Autonomy: brain auto-routes, or proposes and you approve?

## 7. Research findings (folding in from 6 agents)

### 7a. Regime detection + regime→strategy map (agent-1) ✅
**Regimes = 2 axes:** direction (trend-up / trend-down / range) × volatility (compressed / normal /
expanding). Academic: Hamilton-1989 (2-state) → 3/4-state (bull, bull-correction, bear-rally, bear —
direct bull↔bear jumps rare).
- **Detection methods (ALL lagging):** ADX/DMI (trend strength, >50% false crossovers), Choppiness
  Index, ATR/BBW (vol, leading for expansion but non-directional), Kaufman Efficiency Ratio, Hurst
  (window-sensitive), **HMM/Markov-switching**, CUSUM/BOCPD/PELT change-points, HAR-RV (vol forecast).
  → **Combine a trend-gauge (ADX/CHOP/ER) + a vol-gauge (ATR/BBW/India-VIX); require multi-bar
  persistence (3–5) before switching.**
- **⚠️ HMM look-ahead TRAP:** use **filtered** P(state|data≤t) (causal, valid) — NEVER **smoothed**
  P(state|all data) which leaks the future and inflates the backtest. Build-critical.
- **⚠️ India VIX:** coincident/reactive not leading; **VIX futures discontinued 2017 → no tradeable
  term structure** — synthesize regime vol-signal from weekly-vs-monthly NIFTY option IV skew.
- **Regime→strategy payoff (matches §2 spine):** trend → momentum/breakout + directional options;
  range/low-vol → mean-reversion + **premium-selling (harvests the variance risk premium: IV>realized
  on average)**; high-vol/expansion → long straddle/strangle/gamma; bear → protective puts/defensive.
- **🔴 THE decisive honest finding:** component strategies are well-evidenced, but **that mechanically
  SWITCHING by detected regime BEATS a static diversified blend — net of whipsaw + transaction cost —
  is NOT proven; it's an open question.** Whipsaw at transitions is the dominant cost; a lagging HMM
  filter once missed a full year of recovery. → **Design consequence: prefer SOFT regime-WEIGHTING
  (blend engine exposures by regime probability) over hard on/off switching; make switching
  cost-aware; and treat "the router adds value" as a hypothesis the validation gate must prove on NSE
  data, not an assumption.** SOTA analog: Hamilton-1989 + QuantStart `hmmlearn` GaussianHMM gating
  example (honest about its re-entry lag) + Ang-Bekaert regime allocation.

### 7c. Candle + chart patterns (agent-3) ✅
**Verdict: mostly NOISE out-of-sample.** Rigorous bootstrap/data-snooping-corrected studies reject
predictive edge for candlesticks in US/Japan equities (Marshall-Young-Rose 2006; Marshall-Young-Cahan
2008; Horton 2009). Chart patterns weak/mixed: Lo-Mamaysky-Wang 2000 find *some* statistical info in
H&S/double-bottom but NOT proven tradable after costs; H&S profitable in FX (Osler-Chang) but not US
equities. Sullivan-Timmermann-White 1999 (7,846 rules) + Aronson 2006: **no robust edge survives once
search-size corrected.** Bulkowski's base rates are non-peer-reviewed + his own failure rates ~doubled
1990s→2000s (alpha decay). Caginalp-Laurent 1998 is the lone big positive, unreplicated/no costs.
→ **Design consequence:** encode ALL patterns cheaply (TA-Lib 61 `CDL*` fns / pandas-ta-classic 62+),
treat each as a **hypothesis behind the search-integrity gate** (bootstrap-vs-random-walk null · CPCV ·
Deflated Sharpe · White Reality Check / Hansen SPA · costs). Pattern edge, if any, concentrates in
less-efficient markets — must be *proven on NSE data*, never assumed. Full citations in the run notes.

### 7f. NSE intraday cash strategies (agent-6) ✅
**THE central fact — costs, not strategy, decide outcomes:** SEBI FY23 study (~7M traders): **~70%
of intraday cash traders LOSE; loss-makers spend 57% of their losses on transaction costs** (vs 19%
for winners). F&O worse: 93% lose (FY22–24, >₹1.8L cr). → **The L1 cost engine gating every signal is
the single highest-leverage build — a small edge is eaten alive without it.**
- **Strategy families ✓** (each mapped to regime): ORB · VWAP-reversion (flat) · VWAP trend-pullback
  (trend) · momentum/relative-strength (bull) · gap fade(>8%,low-vol)/go(vol 140%+) · breakout
  (prior-day H/L, CPR pivots) · pairs/stat-arb (regime-agnostic, cointegration + Kalman hedge) ·
  event-driven. Regime map matches our §2 spine.
- **Universe scanning (2000+ → ~150–500 tradeable):** liquidity/turnover filter (ADV, order ≤1–2% ADV)
  · **daily exclusions: ASM/GSM (no intraday), F&O-ban (OI>95% MWPL), circuit-band/T2T (intraday
  disallowed)** · sector-heatmap → relative-strength rank. **Kite limits force a WebSocket-tick
  architecture** (quote 1/s, historical 3/s, orders 10/s, 400/min) — cannot REST-poll the universe.
- **NSE microstructure:** T+1 doesn't affect intraday (MIS squared off ~15:10–15:25) · STT 0.025%
  sell-side · ₹40–120/trade all-in · circuit = liquidity trap (stops can fail).
- **OSS:** data `jugaad-data`/`nsepython` · platform **OpenAlgo** (33 brokers, stat-arb course) ·
  backtest backtrader/**vectorbt**/zipline. Full citations in run notes.

### 7e. The AI brain / regime→strategy router (agent-5 + SOTA analog) ✅
**Architecture template = RegimeFolio (arXiv 2025):** three stages — (i) **VIX-based regime classifier**
→ (ii) **regime-conditional model bank** (per-regime ensembles) → (iii) **dynamic allocator**
(mean-variance w/ shrinkage). **India VIX maps directly onto its front door** for NSE. Theory anchor:
**Ang & Bekaert 2002** (2-state Markov regime switching → rotate allocation), the canonical precedent.
- **Router mechanisms** (pick per regime + size): discounted/contextual **bandit** (Thompson) · **meta-
  labeling** (López de Prado — secondary model decides whether to ACT on a primary signal = functionally
  a strategy selector) · meta-model over the experiment ledger · HMM/GMM regime states.
- **Reusable OSS:** structural-break detectors (SADF/CUSUM/Chow) + meta-labeling in **mlfinlab**;
  HMM via `hmmlearn`/`pomegranate`/statsmodels Markov-switching; online learning `river`; bandits
  `mabwiser`. ⚠️ **mlfinlab public repo is partly STUB code** (bodies `pass`, real behind paywall) —
  verify/reimplement, don't blindly depend (matches crypto-bot's finding; use `fracdiff` BSD-3 etc.).
- **The hard rule (evidence-backed):** NOT a chat-committee — naive multi-agent LLM committees
  underperform budget-matched; the durable pattern is model output behind a **hard deterministic
  evaluator** (FunSearch/AlphaEvolve). Brain = disciplined router + validation gate, never a vote-wrapper.
- **Router of choice = non-stationary bandit** (discounted / sliding-window Thompson): the ONLY family
  where *forgetting stale edge* is first-class (down-weights a strategy that stopped working) — exactly
  what markets need. 6 families exist (HMM-switching · mixture-of-experts · **bandits** · meta-labeling ·
  stacking-over-ledger · hierarchical-RL). **Qlib** = the only real OSS reference (Nested Decision
  Execution + **DDG-DA** drift adaptation, AAAI'22: Sharpe 2.41 vs 1.51 baseline). No other OSS strategy-
  router exists. OSS libs: **mabwiser** (Fidelity contextual bandits) · `river` (online ML) · statsmodels
  `regime_switching` · pomegranate/hmmlearn (HMM). Counter-evidence: Berkeley MAST (41–86% committee
  fail), Cognition "Don't Build Multi-Agents", DeepMind self-correction degrades. Memory = episodic
  (ledger) + semantic (what-worked-when) + reflective (consolidation) + **bandit posteriors that decay**.

### 7d. Technical indicators (agent-4) ✅
**Same lesson as patterns — zoo = trap.** Hundreds exist across 5 families (trend/momentum/volatility/
volume/breadth), but most **correlate >0.8–0.9** (RSI/Stoch/CCI/ROC/%b are all "price velocity") → "10
momentum oscillators ≈ 1 effective trial." STW-1999 + Deflated-Sharpe: mining the best-of-N is
data-snooping; edge evaporates OOS. → **Use a small DECORRELATED set (2–4 across DIFFERENT families):
one trend + one volume/flow + one volatility filter beats three momentum oscillators.**
- **Selection method (the antidote):** correlation-prune (drop |ρ|>0.8 clusters) → feature-importance
  (MI/RFE/random-forest) → **effective-trials** DSR (cluster correlated variants; don't count 10 as 10)
  → **walk-forward** validation.
- **OSS:** **TA-Lib** (BSD-2, 150+ fns + 60 candle recognizers, actively maintained) = primary engine;
  **pandas-ta-classic** (community fork, original pandas-ta going paid/archived Jul-2026) = pure-Python
  fallback; finta/tulipy legacy/vendor-only. India VIX = the volatility/regime input.

### 7b. Options strategy taxonomy (agent-2) ✅
**Full taxonomy done** (Greeks/max-P&L table in run notes): directional · verticals · long-vol
(straddle/strangle/gamma) · short-vol/theta (short strangle, **iron condor**, iron butterfly, credit
spreads) · time/skew (calendar/diagonal/ratio/backspread/butterfly/broken-wing). Each = a
view×Greeks signature.
- **Why premium-selling pays in flat/low-vol:** the **variance risk premium** (IV > realized on
  average) — the most durable options edge — BUT short-gamma = **fat-tail blowup** on gaps.
- **Contract selection:** Δ/Γ/Θ peak ATM + intensify near expiry; sellers use ~0.25–0.35Δ OTM (~70%
  win); liquidity concentrates at ATM nearest-**weekly**. Needs a real **Greeks + IV-surface engine**
  (skew: NIFTY reverse-skew near-constant; term structure; portfolio vega/gamma ≠ notional; GEX/pinning).
- **⚠️ NSE現 CURRENT facts (verify before sizing):** SEBI Oct-2024 → **one weekly index per exchange:
  NSE = NIFTY weekly ONLY; BANKNIFTY/FINNIFTY/MIDCPNIFTY = MONTHLY-only.** NIFTY weekly moved Thu→
  **TUESDAY (Sept 2025).** Stock F&O **100% physically settled** (Oct 2019). Shorts carry SPAN+Exposure
  margin + **2% expiry-day ELM**; Peak-Margin (2021) killed leverage. **STT options-sell → 0.15% from
  Apr 2026** + auto-exercise STT trap on ITM. → these reshape which contracts/structures are viable.
- **🔴 Empirical:** SEBI FY22–25: **91–93% of F&O traders LOSE; options (not futures) drive the losses**
  (individuals net-PROFITABLE in futures, deeply negative in options). Premium-selling backtests ~68–70%
  win (vendor-grade) but **no rupee-quantified tail-loss data** for blowup days (Aug-2024 VIX +60%) — gap.
  → **defined-risk (iron condor) over naked; the cost + risk gate are survival, not optional.**

---
**ALL 6 RESEARCH AGENTS COMPLETE.** Cross-cutting verdict → §8.

## 8. Finalized decision (synthesis of all 6 agents)

**The idea survives, but reshaped by evidence.** Six independent research passes converge on ONE
conclusion: **the edge is not breadth — it's cost-discipline + regime-matching + ruthless validation.**

**What we ARE building:**
1. **A regime-aware SOFT-WEIGHTING router (the brain)** — NOT a hard switch (whipsaw is the dominant
   cost; switching-beats-blend is unproven) and NOT an LLM committee (committees fail 41–86%). It reads
   regime by **probability** (trend-gauge ADX/CHOP/ER + vol-gauge ATR/BBW/**India-VIX**, HMM **filtered**
   only) and **blends engine exposures by regime confidence**, allocated by a **non-stationary bandit**
   (discounted Thompson — forgets stale edge), gated behind a **hard deterministic validator**.
2. **An engine LIBRARY**, each engine decision-grade (Rule P), one per regime archetype:
   - flat/low-vol → **defined-risk premium-selling (iron condor / short strangle) on NIFTY weekly**
     [variance-risk-premium; NSE liquidity is exactly here].
   - trend → intraday cash momentum/ORB + directional verticals.
   - volatile/expansion → long straddle/strangle / long gamma.
   - bear → protective puts / defensive.
3. **Signal candidates, not gospel** — compute ALL indicators (TA-Lib) + ALL candle/chart patterns,
   then **the validation gate keeps the few that survive** (correlation-prune → feature-importance →
   Deflated-Sharpe on *effective* trials → walk-forward). Assume ~95% are noise.
4. **The two survival engines under everything:** the **L1 NSE cost engine** (SEBI: 57% of retail
   losses = costs; STT-sell 0.15% Apr-2026; auto-exercise trap) gating every signal, and the **risk
   gate** (defined-risk only; short-gamma tail control). Without these the whole thing is a noise
   generator that pays fees to lose (the exact retail-loss statistic).

**Prerequisites (from the redesign atlas):** L0 truth · **L1 cost engine** · **L2 validation
(Deflated Sharpe + CPCV + trial registry)** · **Greeks/IV-surface engine (L6)** for any options engine.
None optional. OSS to integrate: TA-Lib · pandas-ta-classic · statsmodels regime_switching ·
hmmlearn/pomegranate · mabwiser (bandit) · `fracdiff` · (Qlib DDG-DA as router reference; NOT mlfinlab
public — partly stubbed).

**🟢 LOCKED (user, revised 2026-08-02): scope = ALL market regimes from the START, not flat-first.**
(Supersedes the earlier "engine #1 = flat premium-seller only" lock.) This aligns with **Rule L** (cover
the full space equally, never a narrow slice) + **Rule Q** (build the FULLEST function; gate only
ACTIVATION). The committed target from day one = the **full regime-weighted brain + an engine per regime**:
| Regime | Engine (cash + options, both segments) |
|---|---|
| **Bull-trend** | momentum / ORB (cash) · bull-call-spread / long-CE (options) |
| **Bear-trend** | breakdown-short (cash) · bear-put-spread / long-PE (options) |
| **Volatile / expansion** | long straddle / strangle / long-gamma |
| **Flat / low-vol** | iron-condor / short-strangle premium-seller · VWAP-reversion |
Autonomy = **auto within hard limits** (defined-risk; max-loss/vega/gamma caps; expiry-day ELM aware).

**⚠️ Honest engineering caveat I owe you (Rule A/F/P):** "all regimes from the start" = all are in SCOPE
and the **brain is designed for all four from day one** — NONE is deferred out of scope. But you physically
cannot build + REAL-DATA-verify four deep engines *simultaneously* (Rule A = verify one engine before
advancing; Rule F = real-data pass each; Rule P = whole engine at once). So they **come online
one-verified-at-a-time via the Rule-Q maturity ladder**: the brain routes among whatever engines are ARMED,
and a not-yet-armed regime just means the brain stays flat/abstains for that regime — **automatic, no code
change when it arms.** "All from the start" governs the *design + commitment*; the *arming* is sequenced.

**Shared prerequisites — built ONCE, serve EVERY regime (Rule G, no per-engine duplication):**
1. **L1 NSE cost engine** (net-EV gate — survival) · 2. **L2 validation** (Deflated Sharpe + CPCV + trial
registry) · 3. **Greeks/IV-surface engine** (extend existing black_scholes IV) · 4. **options + cash risk
gate** (defined-risk, vega/gamma/max-loss caps) · 5. **regime classifier + non-stationary-bandit router**
(the brain, §7a/§7e) · 6. the **directional bots** (idea #4) feeding the router.

**Then the four regime engines arm in whatever order clears the real-data gate first** (each: detector→
constructor→entry/exit→sizing→auto-executor, verified on REAL data). Highest-conviction to arm first stays
**flat/low-vol premium-seller** (clearest VRP edge, NSE liquidity) — but that's now an *ordering* call, not
a scope cut; bull/bear/volatile engines are committed, not "later vision."

Next pipeline step: **institutional SPEC** (idea-to-institutional-spec) covering the full four-regime brain
+ shared prereqs → building-engine-grade-features. Prereqs + arming order tracked in docs/BACKLOG.
