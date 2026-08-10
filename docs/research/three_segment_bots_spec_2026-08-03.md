# SPEC — Three Segment-Specialist AI Bots + Portfolio Supervisor (NSE)

**Rev:** 2026-08-03 · **Status:** SPEC (pre-build) · **Owner rule set:** P (engine-grade), O
(production-grade), D (persist), F/J (real-data verify), G (no orphans), K (no silent skips), L (full
universe), M/N (altitude + dashboard).

This spec is the contract the build + review are graded against. It is produced by
`idea-to-institutional-spec` and hands off to `building-engine-grade-features`.

---

## 0. Intent & the decision it changes

Today ONE strategy engine (`strategy_engine`: ORB + mean-reversion + credit-spread + 0DTE) trades every
segment off one shared brain. Replace it with **three independent segment-specialist AI bots inside the
one system, each a full trade brain**, coordinated by **one portfolio supervisor**:

| Bot | Segment (FULL universe — Rule L) | Algo class fit to its microstructure |
|-----|----------------------------------|--------------------------------------|
| **CASH bot** | Full NSE cash, intraday (~2000 stocks, cross-sectional) | Cross-sectional ranking (GBDT/factor stack) + microstructure OFI |
| **INDEX-OPT bot** | Full index-option universe (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50; weeklies + 0DTE) | Vol-regime (GARCH/HAR/HMM) + IV-vs-RV premium + term-structure/skew + 0DTE gamma/theta |
| **STOCK-OPT bot** | Full stock-option (F&O) universe (~180+ underlyings) | IV-rank premium selling + earnings/event vol-crush + skew/risk-reversal + option-flow |

**The decision each bot changes:** which instruments in ITS segment to enter/size/exit each cycle, from
ITS own signals. **The decision the supervisor changes:** how much capital each bot gets, and whether a
correlated cross-bot exposure is netted/capped before it reaches the book.

**Why a thin version fails the intent:** three `if`-gated parameter presets over one shared ORB engine is
NOT three bots — it has one brain, one feature space, one learning loop. The intent is three *independent
cognitions* that each specialise, self-learn, and are individually promotable/fireable on evidence.

**User decisions locked (interview 2026-08-03):**
- Architecture: **each bot fully independent — own data + own ingestion end-to-end (choice B)**, own
  strategies, own online-research loop, own features/models, own risk sizing, own execution policy, own
  self-learning loop + track record + retrain cadence. Max isolation.
- Shared ONLY: the broker/execution seam (`broker_oms`), the organism cognition (ONE `conscience` / ONE
  `memory_reflection` / ONE `will` govern all three), and the supervisor.
- Supervisor: allocates capital across the 3 sleeves, enforces ONE portfolio risk budget, arbitrates
  conflicts via **net exposure + risk-budget cap**.
- Bot relationship: **cooperative pod, one P&L, but bots compete for capital** (performance/competency-
  weighted allocation — champion-challenger flavour, reuses `capital_allocation` + `society`).

**Choice-B risk (surfaced, user overrode):** the user's own crypto Feature-Catalogue (03b) flags fully
independent ingestion as a known failure mode — *"three ingestion paths means three bots disagreeing about
the price."* Mitigation that does NOT violate B: a **price-reconciliation cross-check at the supervisor's
netting boundary only** (bots stay end-to-end independent; the supervisor sanity-checks the price each bot
reports for a shared underlying before netting, and raises a divergence alarm). This is the single
concession; it adds a guard, it does not share ingestion.

---

## 1. Design rules PORTED from the user's crypto Feature-Catalogue §03b (proven blueprint)

These are hard-won multi-bot rules from the user's own reference system; they are acceptance-bearing here:

1. **Portfolio netting layer above the brains** (their #1 most-forgotten). Two bots on opposite sides of
   one underlying must not pay fees both ways. → Supervisor `NetExposureNettingLayer`.
2. **Joint Trial Registry across all three bots.** 3 searches ≈ 3× trials; false-discovery / DSR
   correction MUST use the *joint* trial count, not per-bot. Per-bot registries silently restore
   overfitting. → one shared `JointTrialRegistry` (extends existing Trial Registry / holdout custodian).
3. **Attribution split (per-bot alpha).** Three bots share one P&L; without a signal/timing/exit
   attribution split no bot can be improved or fired on evidence. → `PerBotAlphaAttribution`.
4. **Per-bot feature namespace + registry entry + retrain cadence + competency level + independent
   promotion.** A bot at competency 2 gets no capital while its sibling is at 5. → reuse
   `StrategyFamilyPromotionRegistry` pattern, one registry entry per bot.
5. **Objective = expectancy + tail capture, never win-rate.** Hard risk stop overrides a bot absolutely
   (risk gate owns the stop; the bot's mandate is an objective, not a veto).
6. **Arbiter owns trade selection** — the ONE place a trade is chosen or refused (the supervisor's arbiter,
   over the joint distribution of the three bots' proposals).
7. **Signal expiry bound on waiting** — a bot's "not yet" without a deadline is a silent rejection; expired
   = abandoned + logged.

---

## 2. I/O contracts (the seams the build + tests bind to)

### 2.1 Per-bot contract (identical shape, 3 implementations)
Each bot is a `SegmentBot` exposing:
- **Inputs (own, end-to-end — choice B):** its own data adapter pulling ITS segment's raw feed
  (`market_data` adapters are *instantiated per bot*, not shared), its own online-research loop
  (`news_sentiment` + web research scoped to its segment), point-in-time correct (Rule F / bitemporal).
- **State (carried):** own feature store namespace, own fitted model(s), own posterior/track-record store,
  own retrain-cadence clock, own competency level.
- **Output:** `list[TradeProposal]` — `{underlying, segment, side, structure, size_hint, conviction∈[0,1],
  calibrated_prob, expected_expectancy, loss_tail_estimate, signal_expiry_ts, feature_provenance}`.
  **A bot PROPOSES only — it never places an order** (mirrors 03b BULL/BEAR "proposes only").

### 2.2 Supervisor contract
- **Inputs:** the 3 bots' `TradeProposal` streams + each bot's competency + track record; live portfolio
  state (`paper_trading` ledger); risk budget config.
- **Core:** (a) **capital allocator** over 3 sleeves (competency/performance-weighted, `capital_allocation`
  optimizer + Ledoit-Wolf covariance); (b) **net-exposure netting layer** (aggregate correlated exposure
  per underlying/factor, cap by risk budget); (c) **arbiter** (accept/refuse/resize each proposal over the
  joint distribution); (d) **price-reconciliation cross-check** (choice-B guard).
- **Output:** `list[ArbitratedOrder]` → the existing execution path (`broker_oms` / paper live path). ONE
  portfolio risk budget enforced (`risk_management` pre-trade gate stays the absolute stop — Rule from
  03b: hard stop overrides bots).

### 2.3 Organism cognition (shared, one instance)
`conscience` (safety veto), `memory_reflection` (shared episodic memory), `will` (mandate/goals) wrap the
supervisor — one mind, three specialist hands. Bots' self-learning is local; the organism's learning is
global and observes all three.

---

## 3. Algorithm/model + named SOTA analog per bot (grounded — research briefs persisted alongside)

| Bot | Real method | Named SOTA analog (the bar) | Heavyweight lib to integrate |
|-----|-------------|-----------------------------|------------------------------|
| CASH | Cross-sectional GBDT ranker on a factor+microstructure stack; portfolio construction cost-aware | **Microsoft Qlib** (Alpha158/360 + LightGBM + cost-aware backtest) | `pyqlib`, `lightgbm`, `alphalens-reloaded`, `cvxportfolio` |
| INDEX-OPT | Vol-regime (GARCH/HAR + HMM) → IV-vs-RV premium harvest + term-structure/skew + 0DTE gamma/theta structures, delta-hedged | **`arch`** (GARCH/HAR) + **`py_vollib`** (IV/greeks) + **`optopsy`** (structure backtest) | `arch`, `py_vollib(_vectorized)`, `statsmodels` Markov-switching (regime, `hmmlearn` fallback), `optopsy` |
| STOCK-OPT | Per-name IV-rank/percentile premium selling + earnings/event vol-crush gating + 25Δ risk-reversal skew + option-flow (vol/OI) | **tastytrade IVR methodology** + **Optopsy** + in-house SVI/SSVI surface | `py_vollib_vectorized`, in-house SVI fitter (`scipy.optimize`), `jugaad-data`/`nsepython` (NSE F&O), in-house NSE corporate-event scraper (Rule I) |
| SUPERVISOR | Competency/perf-weighted sleeve allocation (risk-parity/ERC + Bayesian shrinkage + bandit) under CVaR/risk-budget; net-exposure arbitration | **PyPortfolioOpt / Riskfolio-Lib** (convex, ERC, Black-Litterman, CVaR) on `cvxpy` | `cvxpy`, `riskfolio-lib`/`pyportfolioopt`, EG/Hedge bandit (vendor from `universal-portfolios` or hand-roll ~10 lines), `pymc`/`numpyro` for Bayesian sleeve Sharpe |

**Surfaced OSS rejections (Rule O.1 — user double-check):** `mlfinlab` (paywalled enterprise license — reimplement fractional-diff/meta-labelling from AFML instead) · `hmmlearn` (stale since Oct-2024 — prefer `statsmodels` Markov-switching, vendor hmmlearn only if needed) · SVI/SSVI pip packages (none production-grade — build in-house) · NSE option-flow / corporate-event calendar (no free OSS for NSE — build scrapers, Rule I) · `riskparityportfolio` + `universal-portfolios` (maintenance unverified — vendor-and-adapt, don't take as live deps).

---

## 4. Engine-grade ACCEPTANCE CRITERIA (pass/fail gates — Rule P)

Per bot AND supervisor, ALL must pass:

**Structural (Rule P):**
- [ ] Real algorithm/model/solver (not a scalar diagnostic): CASH = fitted GBDT ranker; INDEX-OPT = fitted
      GARCH/HMM + IV engine; STOCK-OPT = per-name IV surface + event model; SUPERVISOR = convex allocator.
- [ ] Carried state + store: each bot has its own persisted feature store + model + track-record store.
- [ ] Raw-input pipeline: each bot ingests real NSE data end-to-end (choice B), point-in-time correct.
- [ ] Decision-grade output that changes behaviour: proposals actually drive orders through the arbiter →
      execution (Rule G — NOT display-only).
- [ ] Correct vocabulary; self-describing names (Rule C).

**Numeric bars (grounded in research §3):**
- [ ] CASH: rank-IC (Spearman) > 0 and IC-IR stable out-of-sample on real NSE cross-section; cost-adjusted
      Sharpe reported with **Deflated Sharpe / PBO** using the JOINT trial count; turnover netted against
      the real Indian cost model (`paper_trading/indian_trading_cost_model`).
- [ ] INDEX-OPT: IV-vs-RV premium capture measured on REAL NSE option chains (not blog numbers — Rule F);
      delta-neutrality error + vega error bounded; 0DTE intraday-resolution risk snapshot (not EOD greeks).
- [ ] STOCK-OPT: per-name IV-rank reliability curve (realised win-rate vs IVR bucket) on real NSE data;
      event-hit-rate (implied vs realised move) per name; vega/gamma limits enforced.
- [ ] SUPERVISOR: portfolio Sharpe > capital-weighted avg of the 3 sleeve Sharpes (the whole justification
      for a supervisor); diversification ratio tracked; risk-budget adherence; allocation turnover in the
      ~9–19% sane band; netting demonstrably removes double-fee opposite-side exposure.

**Tests (Rule P):** unit + property/invariant (e.g. netting never increases gross risk; signal-expiry
always abandons; hard-stop always overrides) + adversarial (bot disagreeing price → reconciliation alarm;
overfit trial → joint-registry DSR rejects) + the Rule-F real-data pass.

---

## 5. Verification plan (Rule F / J)

- **Real-data pass (Rule F):** run each bot on real NSE historical + live-replay data across the FULL
  universe (Rule L — all ~2000 stocks / all index underlyings / all ~180+ F&O names), via the existing
  `historical_bar_replay_source` + `live_universe_paper_loop`. Metrics in §4 computed on real data.
- **Market-gated items (Rule J):** live intraday 0DTE behaviour + live cross-bot netting on a correlated
  move are market-gated → verify via **hermetic sim harness** (injected fake feed behind the DI seam,
  never leaking to prod) AND leave the real-data live pass as a named OPEN BLOCKER in `docs/BACKLOG.md`.
- **Machine done-rule:** `scripts/verification_cockpit.py` per bot + supervisor.

---

## 6. Depth justification (what a thin version would OMIT — Rule P)

A thin "3 presets over ORB" version omits: independent feature stores, real per-segment models
(GBDT/GARCH/IV-surface), per-bot self-learning + retrain cadence, competency-based promotion, the joint
trial registry (→ silent overfitting), per-bot alpha attribution (→ can't fire a bot on evidence), the
net-exposure netting layer (→ pays double fees), the CVaR-constrained sleeve allocator, and the 0DTE
intraday risk resolution. Each omission is a real function loss, so the LOC is justified by function, not
padding.

---

## 7. Decomposition (modules `building-engine-grade-features` will build)

New package `segment_bots/` (+ supervisor), roughly:
- `segment_bots/segment_bot_protocol.py` — `SegmentBot`, `TradeProposal` types (self-describing).
- `segment_bots/cash_intraday_bot/` — data adapter · factor+OFI features · GBDT ranker · portfolio
  construction · self-learn loop.
- `segment_bots/index_option_bot/` — chain adapter · GARCH/HMM regime · IV/greeks engine · structure
  selector (0DTE/term/skew) · delta-hedge scheduler · self-learn loop.
- `segment_bots/stock_option_bot/` — F&O chain adapter · per-name IV-surface (SVI) · IV-rank + event
  model · skew/flow signals · corporate-event scraper (Rule I) · self-learn loop.
- `portfolio_supervisor/` — capital allocator (on `capital_allocation`) · net-exposure netting layer ·
  arbiter (on `society` consensus/governance) · price-reconciliation guard · one portfolio risk budget.
- `research_shared/` — `JointTrialRegistry`, `PerBotAlphaAttribution` (shared across bots).

**Build order:** deterministic per-bot fallback first (generates the dataset the learned bot trains on —
the 03b "ordering is forced" rule) → then the learned engine per bot → then supervisor → then wire to loop.

---

## 8. Dashboard surface + wiring (Rule G + N)

- **Wiring (Rule G):** proposals → arbiter → `ArbitratedOrder` → existing execution/paper path in
  `dashboard/live_paper_trading_service.py` / `paper_trading/live_universe_paper_loop.py`. The supervisor
  REPLACES the current single-engine dispatch (behaviour-changing, not additive display).
- **Dashboard (Rule N):** new "THREE BOTS" board — per-bot competency, capital sleeve %, live P&L +
  per-bot alpha attribution, netting actions, joint-trial-registry DSR status. Screenshot-confirm each
  slice (dataviz skill for the board).

---

## 8b. ADVANCED COMPLETENESS ADDITIONS (2026-08-03 — make the design more complete & advanced)

Beyond the base 3-bots+supervisor, these lift it to an institutional multi-strat pod. Each is engine-grade
(Rule P), reuses an existing trunk where one exists, and is wired (Rule G):

**Per-bot cognition upgrades (all 3 bots):**
1. **Online learning + drift adaptation** — `river` ADWIN/DDM per bot: each bot detects ITS own concept
   drift and adapts between retrains (not just a periodic rebuild). Reuses the surprise/Page-Hinkley monitor.
2. **Mandatory calibration layer** — Platt/isotonic per bot so `conviction`/`calibrated_prob` are real
   probabilities before they drive sizing (GBDT/NN are overconfident). Feeds the existing proper-scoring gate.
3. **Meta-labeling (AFML triple-barrier)** at the arbiter — the *selection* model that decides trade/skip on
   top of each bot's side model (crypto §03b rule 6: selection lives in ONE place).
4. **Per-bot explainability (SHAP)** — every proposal carries a feature-attribution trail (evidence, Rule O).
5. **Competency maturity ladder (Rule Q)** — each bot self-activates capital as its own track record accrues;
   full algorithm always built, only ACTIVATION gated. Supervisor learns which bot to trust.
6. **RANDOM-CONTROL + SHADOW-REJECTED arms per bot** — skill-vs-luck attribution per bot via the existing
   `control_arm_comparison` + `skill_vs_luck_court`, so each bot is promoted/fired on evidence, not P&L noise.
7. **Shadow-before-swap** model updates — a challenger model shadows on delayed labels before it can swap in.

**Supervisor upgrades:**
8. **Regime-conditioned allocation** — allocate per detected market regime (existing regime classifier),
   not one global weight; a bot strong in trend gets more in trend, less in chop.
9. **Cross-bot crowding / correlation monitor** — Millennium-style: detect when the 3 bots pile into the same
   factor/underlying BEFORE the correlated drawdown (the netting layer's early-warning sibling).
10. **CVaR/tail-budget allocation** — supervisor optimises under a portfolio CVaR constraint (`cvxpy`), not
    just variance — options gamma/gap tail is the binding risk. Reuses `capital_allocation` objective programs.
11. **Bandit meta-selector** (EG/Hedge) as the online, model-free fallback allocator when the covariance
    estimate is untrustworthy (non-stationary regimes) — provable regret vs best fixed mix.

**New cross-bot desk (genuinely advanced — bridges bots 2 & 3):**
12. **Dispersion overlay** — sell index-option vol / buy single-stock-option vol (or reverse) to harvest the
    implied-correlation risk premium (index IV > weighted constituent IV). A supervisor-level overlay that
    only exists BECAUSE INDEX-OPT and STOCK-OPT coexist — the whole is more than the parts. Gated on NSE
    single-name option liquidity (Rule I: build the liquidity-tier scanner it needs).

**Safety/governance (reused, wired over all 3 bots):**
13. Existing `conscience`/`corrigibility_switch`/`constitutional_referee` gate ALL three bots' orders; the
    supervisor's hard risk stop overrides any bot absolutely (crypto §03b rule 5). One conscience, three hands.
14. **Per-bot dashboard board** (Rule N) — competency, sleeve %, live alpha attribution (signal/timing/exit),
    drift state, crowding heat, dispersion P&L.

These additions are logged as build slices; the base 4 engines (bots + supervisor) build first, upgrades layer on.

## 9. Open blockers / deferrals (Rule K — mirrored to docs/BACKLOG.md)

- ⛔ Real-data live pass for 0DTE intraday + live cross-bot netting — market-gated (Rule J sim first).
- 🔴 NSE corporate-event calendar scraper + NSE option-flow signal — no OSS, build (Rule I).
- 🔴 In-house SVI/SSVI surface fitter — no production OSS.
- 🟡 Confirm Kite/data completeness for full 180+ F&O underlying option history.
