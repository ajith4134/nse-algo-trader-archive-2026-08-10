# Research/55 — Replay / RL / LOB technique + OSS parts to vendor

**Sourcing-oss-parts pass (Rule I: reuse before build).** For each buildable PIECE of the
24/7 market-open simulation (idea map in `research/53`), this maps the best existing
open-source implementations, reads their README/docs, and assesses maturity, fit, and
how to vendor-and-adapt. **License is NOT a filter** (personal, non-distributed use) —
but source availability and copyleft-if-ever-distributed are noted where relevant.
Skill: `deep-research` (six parallel multi-angle sweeps, one per piece; sources
triangulated across GitHub API + PyPI + docs + papers, fetched 2026-07-24).

Companion to `research/53` (idea map, incl. §8 project-specific additions:
prequential replay, provenance watermark, leakage firewall, surprise-gated time
dilation, sleep-consolidation memory, temporal self-play, deficit curriculum,
sim-reality-gap KPI).

Verdict legend: **BORROW** (vendor code ~as-is behind an interface) · **ADAPT** (lift
specific files/algorithms, reshape to our seam) · **REFERENCE-ONLY** (study the design
or formula, don't vendor) · **SKIP**.

Existing seams these plug into: `MarketClockGatedDataSourceRouter` (live↔replay flip),
the §9 experiment lab, the log/quadratic/Brier proper-scoring + auto-recalibration
consumer, the antibody, the information-diet ledger, the opponent ledger, and the
CPCV/Deflated-Sharpe overfitting gate.

---

## Piece 1 — Event-driven tick + order-book replay engine (stream tick+depth "as if live")

**What we need:** an engine whose *own* design treats backtest and live as two
implementations of ONE strategy-facing interface, so our replayed NSE tick+depth stream
enters through the same seam the live feed uses — matching our router.

### Top candidates
1. **NautilusTrader** — *ADAPT (primary engine/interface backbone).* Rust-core,
   Python-API, deterministic event-driven platform spanning research→backtest→live with
   **no code changes between them** — its DataClient/ExecutionClient adapter model *is*
   the "live and replay behind one seam" pattern. Accepts **L2 (MBP) and L3 (MBO)** as
   deltas or snapshots at nanosecond resolution; with a book present, fills walk the
   actual book across levels; configurable fill models (`prob_fill_on_limit` +
   `prob_slippage`, `BestPriceFillModel`, `TwoTier/ThreeTierFillModel` via
   `get_orderbook_for_fill_simulation()`); per-venue latency modeling.
   **Maturity:** ~25k★, v1.230.0 (Jun 29 2026), ~fortnightly releases, very active,
   LGPL-3.0, Python 3.12–3.14.
   **Gap vs hftbacktest:** fills are probabilistic/synthetic-book, NOT literal FIFO
   price-time queue position.
   **Seam:** write one NSE adapter emitting `OrderBookDeltas`/`QuoteTick`/`TradeTick`;
   live pulls from the NSE feed, replay pushes the recorded stream into `BacktestEngine`
   as the identical message types. Maps directly onto the router's live↔replay flip.
   Refs: [repo](https://github.com/nautechsystems/nautilus_trader) ·
   [backtesting docs](https://nautilustrader.io/docs/latest/concepts/backtesting/) ·
   [overview](https://nautilustrader.io/docs/latest/concepts/overview/) ·
   [PyPI](https://pypi.org/project/nautilus_trader/)

2. **hftbacktest** — *ADAPT for fill-realism core; REFERENCE-ONLY for its live side.*
   HFT/MM backtester built around **queue position** and feed/order latency from full
   L2/L3 tick data. Simulates your **exact FIFO queue position** at each price level
   (orders ahead/behind you; 1st vs 50th = 100% vs 10% fill in fast markets); ships
   probabilistic queue models + an L3 MBO FIFO model + custom latency models.
   **Maturity:** ~4.3k★, MIT, v2.4.x (last push 2025-12-23), active; Numba-Python +
   faster Rust path. **Live side is Rust-only, crypto-only (Binance/Bybit)** — not for
   NSE equities; our own live feed owns that.
   **Seam:** convert NSE tick+depth into its numpy structured-array event stream; vendor
   its queue+latency engine as the truthful matching layer behind the replay branch
   (NSE is price-time priority, so its FIFO model is directly valid).
   Refs: [repo](https://github.com/nkaz001/hftbacktest) ·
   [queue.rs](https://github.com/nkaz001/hftbacktest/blob/master/hftbacktest/src/backtest/models/queue.rs) ·
   [docs](https://hftbacktest.readthedocs.io/)

3. **QuantConnect LEAN** — *REFERENCE-ONLY.* Genuine live↔backtest parity ("streams data
   in fast-forward"), large/active, but C#-core makes a Python-native NSE stack sit
   awkwardly at the engine boundary and fills are simpler than hftbacktest. Good parity
   *pattern*, poor vendor target. [repo](https://github.com/quantconnect/lean)

### Skip
- **vnpy** (~28k★, active but China-gateway-centric; CTA backtester lacks FIFO
  queue/latency realism), **Backtrader** (~15k★ but LTS/maintenance since 2023, no
  order-book/queue modeling), **zipline-reloaded** (bars only, no L2), **backtesting.py**
  (OHLC only), **mbt-gym** (model-simulated LOB, not replay — filed under Piece 4/5).

**Verdict:** Nautilus as the interface/orchestration backbone; port hftbacktest's queue+
latency model as a custom Nautilus fill model (or run it as the simulator behind the
replay branch) when tick-perfect fills matter.
Sources: [2026 engine comparison](https://bullalert.ai/blog/best-python-backtest-engines-2026/) ·
[autotradelab comparison](https://autotradelab.com/blog/backtrader-vs-nautilusttrader-vs-vectorbt-vs-zipline-reloaded)

---

## Piece 2 — LOB reconstruction + microstructure feature libraries

**NSE reality that shapes this:** NSE broker/exchange depth is **market-by-price L2
(MBP-5, or 20-level), snapshot+incremental — NOT MBO/L3 with per-order IDs.** So
Nasdaq-ITCH/LOBSTER message parsers are schema-reference-only; what we need is an
exchange-agnostic sorted L2/L3 book + snapshot+delta maintenance.

### 2a. LOB reconstruction
1. **hftbacktest** — *BORROW (primary).* Reconstructs a full tick-level book from **both
   L2 MBP and L3 MBO** + trades; L3 gives explicit queue position. MIT, 4,306★, v2.4.4
   (2025-12-10), active. **Input seam:** numpy structured array (8 fields: `ev`,
   `exch_ts`, `local_ts`, `px`, `qty`, `order_id`, `ival`, `faval`); ships
   `validate/correct_event_order()`. **Output:** `depth()` → best bid/ask + arrays;
   `orders()` → resting orders w/ queue position. One NSE MBP-5/20 → structured-array
   adapter needed. [repo](https://github.com/nkaz001/hftbacktest) ·
   [data schema](https://hftbacktest.readthedocs.io/en/latest/data.html)
2. **bmoscon/orderbook** — *BORROW/adapt (leanest container).* Fast L2/L3 sorted book in
   C-for-Python; assign bids/asks dicts, query by level index, checksum. 317★, GPL-3.0,
   active (2025-11-03). It's a container, not a feed maintainer, and L2 mode exposes no
   per-order FIFO. [repo](https://github.com/bmoscon/orderbook)
3. **bmoscon/cryptofeed** — *ADAPT the maintenance pattern (pin a copy).* Its book layer
   implements exactly the maintenance an NSE replay/live book needs: snapshot bootstrap →
   delta apply, **sequence-gap detection + resync, crossed-book `cross_check`, checksum**.
   Copy the pattern, not the venue code. 2,874★, **ARCHIVED 2026-07-07 (read-only)**.
   [repo](https://github.com/bmoscon/cryptofeed) ·
   [book validation](https://github.com/bmoscon/cryptofeed/blob/master/docs/book_validation.md)
- **Reference:** ABIDES `order_book.py`/`PriceLevel` (real FIFO price-level book + L3
  ITCH snapshot API; original ships a `MarketReplayAgent`) — design reference for L3
  queue semantics; JPMC copy archived 2025-06-02. Nautilus order-book (full L1/L2/L3 from
  deltas, production-grade, heavier). **Skip:** mbt_gym (model sim, no ingestion), LOBSTER
  tooling (ITCH schema ≠ NSE), DeepLOB data-prep repos (ML preprocessing, license-encumbered).

### 2b. Microstructure features (no single library covers the set — assemble)
| Metric | Best source | Signal | Verdict |
|---|---|---|---|
| Kyle's λ, spread, PIN, Amihud | **frds** ([repo](https://github.com/mgao6767/frds), [λ docs](https://frds.io/measures/kyle_lambda/)) | 107★, MIT, Sep 2025, `pip install frds`, numpy→scalar | **BORROW** (only clean importable lib) |
| Trade sign (tick/LR/CLNV/EMO/quote) | **tclf** ([repo](https://github.com/KarelZe/tclf)) | 21★, BSD-3, **2026-07-22 (most active in this report)**, sklearn API | **BORROW** |
| BVC | **jktis** ([repo](https://github.com/jktis/Trade-Classification-Algorithms)) / **tr8dr HawkesBVC** ([repo](https://github.com/tr8dr/tseries-patterns)) | 167★ MIT / 291★ MIT | **BORROW/adapt** (tclf lacks BVC) |
| Microprice (Stoikov) | **sstoikov/microprice** ([repo](https://github.com/sstoikov/microprice)) | 471★, no license, notebook — wrap for streaming | **ADAPT** (canonical) |
| VPIN | **jheusser/vpin** ([repo](https://github.com/jheusser/vpin)) | 117★, no license, Py2 script | **ADAPT** (no maintained option exists) |
| OFI / multi-level OFI | **nicolezattarin/LOB-feature-analysis** ([repo](https://github.com/nicolezattarin/LOB-feature-analysis)) | 275★, Apache-2.0, 2022 — lift formulas, drop bundled `.so` | **ADAPT math** |
| Bars (tick/volume/dollar/imbalance) | **mlfinpy** ([repo](https://github.com/baobach/mlfinpy)) | 79★, MIT | Borrow (no microstructure) |
| VPIN/Kyle/Roll/Corwin-Schultz (algorithms) | **mlfinlab** | 4,881★, **All-Rights-Reserved / non-commercial since June 2021** | **REFERENCE-ONLY** (closed) |

**Correction of a common belief:** mlfinlab was *never* MIT/BSD — always All-Rights-
Reserved, explicitly Non-Commercial from June 2021 (its `microstructural_features` module
has VPIN/Kyle/Roll/entropy but NO OFI/microprice/Lee-Ready/BVC anyway). Reimplement from
de Prado AFML ch.19 (public math). arbitragelab has zero microstructure — skip.

**Verdict:** hftbacktest (reconstruction) + assembled `frds` + `tclf` + `jktis`/`tr8dr` +
adapted `microprice`/`vpin`/`nicolezattarin` OFI (microstructure features).

---

## Piece 3 — Market-impact + queue-aware fill models

**No single OSS does both** (queue fills AND price impact) — vendor from two sources.

### 3a. Queue-position fills
- **hftbacktest — BORROW/port.** The reference queue-model implementation. Each model
  implements a `QueueModel` trait: `new_order()` (initial position = size ahead),
  `trade()` (advance front by traded qty), `depth()` (adjust on cancels), `is_filled()`.
  Models: **RiskAverseQueueModel** (pessimistic, advance only on trades — keep as a
  Rule-F lower bound), **ProbQueueModel<P>** (probabilistically attributes cancels to
  front vs back), closures **PowerProbQueueFunc** `f(x)=x^n` (Identity/Square/Power),
  **LogProbQueueFunc**, and **L3FIFOQueueModel** (exact if MBO available). Each is ~50
  lines of Python to reimplement; partial fills fall out naturally.
  [queue.rs](https://github.com/nkaz001/hftbacktest/blob/master/hftbacktest/src/backtest/models/queue.rs) ·
  [prob-queue docs](https://hftbacktest.readthedocs.io/en/latest/tutorials/Probability%20Queue%20Models.html)
- **Nautilus `FillModel`** — *REFERENCE* for the plug-in seam (`get_orderbook_for_fill_simulation()`);
  its own queue model is coarser (open issue #2194 acknowledges hftbacktest is richer).

### 3b. Price impact (temporary / permanent / square-root / propagator)
- **mbt_gym `price_impact_models.py` — BORROW/adapt.** Self-contained (NumPy-only), BSD-3.
  Abstract `PriceImpactModel(get_impact, max_speed)` with **TemporaryPowerPriceImpact**,
  **TemporaryAndPermanentPriceImpact**, and **Transient/propagator** variants
  (Obizhaeva-Wang-style, resilience-decayed). Companion `fill_probability_models.py`
  (exponential/triangular/power fill-vs-depth) complements hftbacktest's queue fills.
  [impact file](https://raw.githubusercontent.com/JJJerome/mbt_gym/main/mbt_gym/stochastic_processes/price_impact_models.py)
- **MACE (FinRL-Meta extension, arXiv 2603.29086) — REFERENCE + borrow the closures.**
  Pluggable impact behind one interface: **square-root `I(Q)=Y·σ·√(Q/V)`**,
  Almgren-Chriss decomposition, Obizhaeva-Wang, 10bps baseline; permanent impact with
  exponential decay (half-life default). Take the formulas + "pluggable cost model applied
  inside `step()`" pattern; don't pull in FinRL-Meta.
  [arXiv](https://arxiv.org/abs/2603.29086)
- **LEAN `MarketImpactSlippageModel`** (REFERENCE — worked Almgren-2005 formula, C#);
  **felixpatzelt/priceprop** (REFERENCE — linear propagator/TIM kernel math, MIT, stale
  2018) if you want true transient impact beyond mbt_gym's resilience decay;
  standalone Almgren-Chriss repos and ABIDES emergent impact = REFERENCE/skip for
  open-loop replay.

**Verdict/plan:** define two interfaces — `QueueModel` (from hftbacktest) and
`ImpactModel` (from mbt_gym) — wire both at the single `order_submit → fill_decision`
point (Nautilus `get_orderbook_for_fill_simulation` template); add a `SqrtLawImpact`
closure from MACE; calibrate `Y`/`κ`/resilience on real NSE tick data.

---

## Piece 4 — RL market environments (Gymnasium API)

**Finding:** only **two** projects give LOB-microstructure state + order-level actions;
the rest are OHLC-bar buy/sell/hold. **Recommendation: build a thin custom
`gymnasium.Env` and borrow schemas** rather than adopt any wholesale.

| Criterion | **ABIDES-gym** | **AlphaTrade / JAX-LOB** | **mbt-gym** | gym-trading-env | gym-anytrading | FinRL-Meta | TensorTrade |
|---|---|---|---|---|---|---|---|
| State = LOB microstructure? | **Yes** (imbalance5, spread, impact, mid-returns) | **Yes** (full multi-level from real msgs) | Partial (model state) | No (OHLC) | No | No | No native LOB |
| Action = order-level? | Partial ({MKT, LMT@touch, hold}) | **Yes** (place/cancel limit, market) | Yes (quote offsets) | No (position wt) | No ({buy,sell}) | No (weights) | Configurable, not LOB |
| Data model | **simulated** ABM (not replay) | **real LOBSTER replay** | **synthetic** stochastic | your bars | your bars | bars | price feed |
| Stars / API | ~173, old Gym, **archived 2025-06-02** | ~134, Gymnax(JAX) | ~176, pre-Gymnasium | ~496, **Gymnasium** ✅ active | ~2.4k, Gymnasium, inactive | ~1.9k, old Gym | old Gym (#460 open) |
| Verdict | **REFERENCE/adapt** (state+reward schema) | **ADAPT/reference** (closest action model + LOB matching) | REFERENCE (MM/exec math) | ADAPT (Gymnasium skeleton) | Skip | Skip | Skip |

- **ABIDES-gym** execution env exposes a genuinely microstructural 9-feature state
  (`holdingsPct, timePct, differencePct, imbalance5, imbalanceAll, priceImpact, spread,
  directionFeature, R^k`) + implementation-shortfall reward — **borrow the observation
  schema + reward** (computable from our replayed NSE depth). Archived → design reference.
  [repo](https://github.com/jpmorganchase/abides-jpmc-public) · [paper](https://arxiv.org/abs/2110.14771)
- **AlphaTrade/JAX-LOB** is the only open project with real-book replay + place/cancel
  limit actions; its `jaxob` order book is the best reference to **adapt the order-level
  action model + LOB matching**; JAX design is the migration target for GPU-parallel
  training across 2,000+ NSE symbols. [repo](https://github.com/KangOxford/AlphaTrade) ·
  [paper](https://arxiv.org/abs/2308.13289)
- **mbt-gym** = math reference for MM/execution action+reward (inventory-penalized PnL,
  quote offsets). **gym-trading-env** = Gymnasium boilerplate reference.

**Integration seam to implement:** `reset()` seeks the NSE replay iterator to an episode
start; `step(action)` decodes place/cancel/market → advances the tick/depth replay →
runs the Piece-3 fill model against replayed book updates → recomputes the ABIDES-style
feature vector as obs → returns inventory-penalized shortfall as reward. The one
non-trivial piece is the fill/matching model against non-reactive replayed data —
AlphaTrade's `jaxob` + our Piece-3 queue model cover it.

---

## Piece 5 — Agent-based simulators + generative "days that never happened"

### 5a. Agent-based market simulators (reactive tapes)
1. **DeepMarket + TRADES — BORROW (top pick; unifies ABM + generative).** Python framework
   that **extends ABIDES** so background agents are trained deep generative models
   (diffusion + CGAN). Generates order-level LOB dynamics **conditioned on market state
   AND the trading agent's actions** (so the tape reacts to our orders) and explicitly
   supports **counterfactual "what-if"/stress scenarios** — precisely "days that never
   happened." 108★, MIT, active 2025; ships pretrained TRADES+CGAN checkpoints, training,
   eval metrics, a 265k-row synthetic dataset.
   [repo](https://github.com/LeonardoBerti00/DeepMarket) · [TRADES paper](https://arxiv.org/pdf/2502.07071)
2. **pymarketsim — ADAPT (lean pure-Python ABM).** 4-heap price-time engine + agent zoo +
   swappable mean-reverting fundamentals + **vectorized Gym wrappers**. 22★, MIT, active,
   Python 3.10+, pip-installable. Cleaner/hackable alternative to the heavy JPMC fork.
   [repo](https://github.com/dipplestix/pymarketsim)
3. **ABIDES upstream — REFERENCE/base-to-fork** (foundational, but **archived 2025-06-02**;
   rely on the DeepMarket fork). **MAXE** (C++/pybind, pro-rata matching ideas) =
   reference-only. **JAX-LOB/AlphaTrade/JaxMARL-HFT** = reference now, adapt later for GPU
   scale. **Simudyne** (closed) / LLM-agent toy sims = skip.
   [ABIDES](https://github.com/jpmorganchase/abides-jpmc-public)

### 5b. Generative / world-model generators
- **TRADES (via DeepMarket) — BORROW (top generative pick).** Transformer denoising
  diffusion, market-state+action-conditioned, counterfactual-capable, evaluated on
  stylized facts. Sibling papers (DiffLOB, DiffVolume, "Painting the market") = technique
  reference. [paper](https://arxiv.org/pdf/2502.07071)
- **tick (X-DataInitiative) — ADAPT (cheap Hawkes order flow).** Most mature point-process
  lib (self/cross-exciting Hawkes). 548★, BSD-3. Fit a multivariate Hawkes to NSE
  event timestamps, simulate new event times, feed a matching engine → synthetic day;
  lightweight vs training diffusion. [repo](https://github.com/X-DataInitiative/tick).
  **mpoints** (state-dependent Hawkes) = reference/adapt.
- **LOB-Bench — BORROW (validation gate).** Scores generative LOB models vs real data
  (spread, book volumes, imbalance, inter-arrival, impact, trained discriminator). This
  is the **Rule-F instrument** every synthetic NSE day must pass before it's trusted.
  [repo](https://github.com/peernagy/lob_bench) · [paper](https://arxiv.org/pdf/2502.09172)
- **DreamerV3 — ADAPT (advanced/world-model track).** Learns a latent world model and
  trains the policy inside imagined rollouts; accepts custom Gym envs → wrap the sim,
  "dream" synthetic NSE days. 3.6k★, MIT, active. [repo](https://github.com/danijar/dreamerv3)
- **REFERENCE-ONLY:** Stock-GAN (no maintained code — DeepMarket's CGAN supersedes it),
  QuantGAN/Fin-GAN/TimeGAN (return-series only, not reactive LOB), rough_bergomi/QuantLib
  Heston (continuous vol paths — only as a driving process for options vol regimes, not
  the market itself). **DeepLOB is a predictor, not a generator — don't use here.**

**Verdict:** vendor DeepMarket+TRADES (ABM + generative + counterfactual) and LOB-Bench
(mandatory validation); adapt pymarketsim + tick as a lighter fallback generator;
DreamerV3 for the world-model track. **All generative models are NASDAQ/LOBSTER-trained —
none NSE-native — so Rule I: source NSE order-level tick data and retrain/recalibrate.**

---

## Piece 6 — Anti-overfitting + prequential evaluation tooling

We already own a CPCV/DSR gate; the genuinely missing brick is **PBO (CSCV)** and a
**streaming predict-then-see** scorer.

### 6a. Overfitting statistics
| Library | Method(s) | License | Signal | Verdict |
|---|---|---|---|---|
| **purgedcv** (eslazarev) | CPCV, purged/group K-fold, walk-fwd, embargo, **PBO, DSR, PSR, MinTRL** | MIT, PyPI | ~19★, ~354 tests / 98% cov, `mypy --strict`, active | **BORROW (PBO); reference CPCV/DSR** |
| **pypbo** (esvhd) | **PBO/CSCV**, PSR, DSR, MinTRL, MinBTL | AGPL-3.0 | ~136★ (most-starred), lightly maintained | **ADAPT / PBO cross-check** |
| **rubenbriones/PSR** | PSR, **DSR**, expected-max-SR | unstated | ~129★, example-grade | **REFERENCE** (line-by-line DSR check) |
| **jsharpe** (tschm) | PSR, MinTRL, **FDR/FWER multiple-testing** (Bonferroni/Holm/BH), autocorr fix | MIT, PyPI | ~21★, very active | **BORROW multiple-testing utils** |
| **skfolio** | CPCV, WalkForward, randomized CV (portfolio layer) | BSD-3 | mature, active | REFERENCE/adjacency (no DSR/PBO) |
| **timeseriescv** | CombPurgedKFoldCV | open | stale since 2018, buggy | **SKIP** (superseded by purgedcv) |
| **mlfinlab** / jmrichardson fork | CPCV (no PBO) | all-rights-reserved / fork dead (1 commit) | — | **SKIP** (algo reference only) |
| quantstats/pyfolio/empyrical | standard perf metrics | open | mature | SKIP for overfitting stats |

- **purgedcv** ([repo](https://github.com/eslazarev/purged-cross-validation)) is the only
  actively-maintained OSS bundling CPCV + purged/embargoed CV + PBO/DSR/PSR in one typed,
  tested library — the natural home to standardize on. Cross-check its PBO numerics
  against **pypbo** ([repo](https://github.com/esvhd/pypbo)) and the R **mrbcuda/pbo**
  (CRAN) as a language-independent oracle; primary paper: Bailey/Borwein/López de Prado
  [CSCV/PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
- **mlfinlab is closed/commercial** (relicensed all-rights-reserved; fork dead) — and
  never implemented PBO/CSCV even when open. Reference-only.

### 6b. Prequential / predict-then-see streaming scorer
- **River — BORROW.** The de-facto online-ML lib. `evaluate.progressive_val_score(...)` =
  interleaved **predict-then-observe** over a stream with a `delay` param for late labels;
  ships proper scores **Log-Loss and Brier**, wrappable in `metrics.Rolling` /
  `metrics.TimeRolling` for rolling prequential scoring + drift detection. BSD-3, very
  mature/active. Feed the brain's per-step probabilistic forecast → cumulative/rolling
  proper score out — the exact substrate for §8.1 prequential replay. No other lib is
  competitive here. [progressive-val docs](https://riverml.xyz/latest/api/evaluate/progressive-val-score/)

**Verdict:** purgedcv (PBO, with pypbo + R `pbo` as oracles) + jsharpe (FDR/FWER) + River
(prequential Log-Loss/Brier streaming).

---

## Maturity / credibility note

- **A-grade, primary-source-verified (GitHub API + PyPI + docs/papers, 2026-07-24):**
  Nautilus/hftbacktest maturity + L2/L3 handling; hftbacktest queue models and mbt_gym
  impact files (source read directly); mlfinlab closed-source status (H&T's own license +
  issue #496); River as the mature prequential option (official docs); ABIDES-gym archived
  2025-06-02; cryptofeed archived 2026-07-07; frds/tclf feature coverage.
- **B-grade / probable:** purgedcv's PBO+DSR presence (README/paper, code not executed —
  cross-check numerically before trusting the gate); AlphaTrade internal reward details
  (inferred from paper + file listing, not line-level read); MACE impact code is new
  (2026) and lightly reviewed.
- **Cross-triangulated formulas:** square-root law (Bouchaud + recent empirical arXiv),
  Almgren-2005 impact (LEAN model + paper).
- **Weighting note:** this is a niche academic field — star counts are modest; **archive
  status + paper provenance + test/CI evidence matter more than stars** (e.g. purgedcv's
  98% coverage weighted over its ~19★; popularity ≠ maintenance).

---

## Gaps / open items (surface every sign-off — Rule K)

1. **No NSE-native LOB-reconstruction repo exists publicly.** Every reconstruction engine
   and every generative model is NASDAQ/LOBSTER/crypto-trained. **Rule I:** we must source
   NSE order-level (ideally L3, else MBP-5/20) tick+depth history and write the NSE→
   structured-array adapter ourselves; generative models must be retrained/recalibrated on
   NSE data and pass LOB-Bench before trust. → BACKLOG task.
2. **Fidelity ceiling = data.** NSE public feeds are L2 MBP (no per-order IDs), so
   hftbacktest's *exact* L3 FIFO queue is unavailable; we're limited to its **probabilistic**
   queue models unless an MBO source is acquired. Decide fidelity target (Q7.1 in `research/53`).
3. **Numeric equivalence not yet verified** for purgedcv DSR vs our existing gate, and for
   its PBO vs pypbo/R — run the oracle cross-check before wiring (Rule F).
4. **No runtime benchmark** of book containers / feature libs on the 2,000+ symbol universe
   (Rule F throughput test on real NSE depth is the sign-off gate).
5. **Adjacent multiple-testing methods not swept:** White's Reality Check / Hansen's SPA
   would complement jsharpe's FDR/FWER — flagged as a possible follow-up sweep.
6. **DeepMarket/DreamerV3 compute cost** (diffusion retraining, world-model training) not
   scoped against our overnight budget (Q7.4 always-on vs nightly batch).

---

## The BASE shortlist — minimum parts for faithful replay + prequential scoring + safety

Per `research/53` §8, **BASE must deliver 8.3 (leakage firewall) → 8.2 (provenance) →
8.1 (prequential), on data we already have,** on top of the existing router. The minimum
OSS set to stand that up:

| # | Part to vendor | Verdict | Plugs into (seam) | §8 idea it enables |
|---|---|---|---|---|
| B1 | **NautilusTrader** — engine/interface backbone (or a thin custom event loop mirroring its DataClient/FillModel seams) | ADAPT | The router's live↔replay flip; one NSE `OrderBookDeltas/QuoteTick/TradeTick` adapter fed live *and* from recorded stream | Structural **leakage firewall (8.3)** — replay pushes the SAME message types through the SAME interface, so nothing future-stamped can leak |
| B2 | **hftbacktest** book reconstruction + `RiskAverseQueueModel`/`ProbQueueModel` (ported to Python) | ADAPT/port | Behind the replay branch as the matching layer; `order_submit→fill_decision` | Faithful fills without a reactive market; the pessimistic model = a Rule-F lower bound |
| B3 | **frds + tclf + adapted OFI/microprice/VPIN** (`nicolezattarin`/`sstoikov`/`jheusser`) | BORROW/adapt | Feature-computation step over the reconstructed book → the state the brain sees | Real microstructure state feeding §9 lab + calibration; enables **surprise-gated dilation (8.4)** later (VPIN/OFI drive the clock) |
| B4 | **River** (`progressive_val_score` + Log-Loss/Brier + Rolling/TimeRolling) | BORROW | The existing log/quadratic/Brier scorer + auto-recalibration consumer (tasks #25–27) | **Prequential replay (8.1)** — every replayed step becomes a graded predict-then-see exam |
| B5 | **purgedcv** (PBO) + verify against **pypbo** | BORROW | The existing CPCV/DSR promotion gate | Extends the overfitting gate with PBO for the promotion discipline (guards caveat #1) |
| B6 | *(build, not vendor)* provenance-tag + trust-weight wrapper on every stored experience; strict causal gate in the Rule-J DI seam | BUILD | The antibody + information-diet ledger (task #30); Layer-10 memory writes | **Provenance watermark (8.2)** + enforcement of **leakage firewall (8.3)** — sim can never override live evidence |

**Why this set:** B1 makes replay *causally honest* by construction (8.3); B6 makes it
*provenance-safe* before any sim writes to memory (8.2); B4 turns every idle hour into
graded learning (8.1) — the three §8 BASE must-haves — while B2+B3 give faithful fills and
real microstructure state on data we already have, and B5 hardens the promotion gate.
Everything above BASE (Piece 4 RL gym, Piece 5 DeepMarket/TRADES/DreamerV3, Piece 3 impact
model, deficit curriculum, temporal self-play, sleep consolidation) layers on **after**,
gated by NSE data acquisition (gap #1) and the fidelity decision (gap #2).

**Deliberately deferred to ADVANCED/ULTRA:** Piece-3 impact models (8.4 needs closed-loop),
AlphaTrade/ABIDES-gym RL env (Piece 4), DeepMarket+TRADES+LOB-Bench generative days and
DreamerV3 world model (Piece 5, 8.5/8.8) — each recorded in BACKLOG with its gating data
dependency so nothing is silently dropped (Rule K).
