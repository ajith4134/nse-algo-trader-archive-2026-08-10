# 00 — Project Overview & Layer Roadmap

> **START HERE → [`docs/SYSTEM_MAP.md`](../SYSTEM_MAP.md)** — the living,
> code-generated architecture & data-flow map (every feature, its files, and
> the real data-flow edges between and within them). Read it before opening
> any source file; keep it updated on every new file/feature (CLAUDE.md Rule H).

This is the index note. Every layer gets its own numbered file in this
folder (`01_...`, `02_...`, ...). Each one is appended to as the layer
grows — never rewritten from scratch, never deleted. Read this file first,
then the layer file you care about.

Pre-implementation research and architecture decisions (market/regulatory
research, adaptive-learning/memory architecture research, broker/paper-live
framework landscape, self-learning AI feature taxonomy, strategy/indicator/
option taxonomy, AI-beyond-self-learning categories, the consolidated
top-level AI feature atlas, NSE microstructure claims evidence-checked,
time-of-day session behavior, an external-knowledge hypothesis-validation
pipeline, the full NSE scanner/filter taxonomy, the full trade-log data
schema, a 41-project sweep of borrowable open-source "puzzle pieces," a
round-2 self-learning-agent sweep, a final frontier sweep of
self-improving-AI systems beyond MATS — AI Scientist, AlphaEvolve/
OpenEvolve, FunSearch, Eureka, OpenHands, SPIN/self-rewarding models, the
Darwin Gödel Machine, ADAS, SEAL, and Absolute Zero Reasoner — plus
connecting/integration frameworks, automated feature/indicator discovery,
a closing synthesis, continuous/24-7 market-replay-with-seamless-
live-handoff architecture, and the remaining self-learning categories
(meta-/active-/federated-learning, synthetic data, explainability,
cognitive architectures, curriculum learning, novelty detection,
quality-diversity, and a v1-shortlist deep evidence re-check) live in
`../research/00` through `../research/28`.
**19 research passes, 110+ projects README/paper-verified in total.**
The synthesis of all of it — the full feature
menu, the broker-abstraction architecture decision, the dashboard plan,
and the per-layer testing method — lives in `../PLAN.md`. Read that
first**, then the individual research files for backing detail, before
starting Layer 3 onward.

**Later research/design docs (2026-07-24, the live-trading build):**
`../research/37` dashboard Layer-9 plan · `../research/38` live universe
paper-loop build plan · `../research/39` options credit-spread live-path
design · `../research/40` order-types Kite spec + taxonomy (SL/SL-M, the
options-SL-M-blocked gotcha, CO/BO/GTT decisions) · `../research/41` **deep
cross-verification audit of Layers 1–9** (Rule-G orphans found + fixes) ·
`../research/42` raw order-types research notes · `../research/43` **Layer 10
slice 1 — experience-memory substrate** (memory node per closed §9 experiment;
recommend a swappable `ExperienceMemory` over SQLite for v1, defer Graphiti/
Neo4j to the semantic/multi-hop tier) · `../research/44` **memory-substrate OSS
sourcing pass** (sourcing-oss-parts: keep the SQLite build — no OSS does the
whole structured-experience + calibration + tripwire feature; queued borrow:
`python-prediction-scorer` MIT proper scoring rules to enrich grading beyond
Brier) · `../research/45` **Rule J research** (hermetic simulation-harness
verification when real data is unavailable — verified best-practice + the rule,
demonstrated before codifying) · `../research/46` **Layer 10 slice 4 —
shadow-arm recovery design** (recency-window veto so a refuted mechanism can
un-veto once it recovers + 1-in-8 shadow probes to keep evidence flowing; no
permanent lock-out).

## Scope decided so far
- Segments in phase 1: NSE cash intraday, NSE options intraday (index +
  single-stock). Futures, commodities, BSE index options (SENSEX/BANKEX):
  deferred.
- No overnight carry, any segment, ever.
- Language: Python.
- Broker (phase 1): Zerodha Kite Connect — kept behind a swappable
  broker-integration boundary, not hardcoded into strategy/risk/data code.

## Layer roadmap (build order — do not skip ahead)

| # | Layer | Status | Notes file |
|---|-------|--------|------------|
| 1 | Universe & Instrument Registry | **built & signed off** (tests re-verified 2026-07-23, 8/8 passing) | `01_universe_instrument_registry.md` |
| 2 | Market Data (real-time + historical) | **complete for v1, Kite-only per PLAN §8a.13** (2026-07-23): auth automation, historical bars, NSE report ingestion + SQLite store all live-verified; other-broker adapters deferred post-completion; live-tick check pending an open market session | `02_market_data_sourcing.md` |
| 3 | Indicator / Feature Engineering | **v1 complete, awaiting sign-off** (2026-07-23): EMA, RSI, ATR, ADX, Supertrend, VWAP + BS-IV, ATM-IV, IV Rank, PCR — all reference- and real-data-verified | `03_indicator_engineering.md` |
| 4 | Strategy / Signal Engine | **v1 built** (2026-07-23): ORB + ADX regime gate + credit-spread leg selector, unit-tested + real-data dry-run; statistical validation gated on Layer 7 | `04_strategy_signal_engine.md` |
| 5 | Risk Management | **v1 built** (2026-07-23): defined-risk-only gate, undefined-risk detection (incl. adversarial cases), conservative margins, fixed-fractional sizing, ban-list enforcement; 215-underlying sweep verified | `05_risk_management.md` |
| 6 | Broker Integration & OMS | **v1 built** (2026-07-23): BrokerClient protocol + Simulated/Kite twins, atomic multi-leg executor (hedge-first, unwind-on-failure), SEBI rate throttle; parity + one-leg-failure tests green; live read path verified | `06_broker_oms.md` |
| 7 | Backtesting \& Paper Trading | **complete for v1** (2026-07-23): 24/7 router · paper engine · §9 prediction-tables lab · slippage model · Deflated-Sharpe gate · CPCV gate — all Rule-F verified. Only the live-feed handoff remains, blocked on an open market session | `07_paper_trading_engine.md` |
| 8 | Session / Square-off Management | **signed off (v1)** (2026-07-24): square-off schedule + safe-ordered retry-to-flat executor (short covered before hedge sold, never a naked leg); Rule-F verified — 0 positions open across 22 real sessions, survives injected broker outage. **Now WIRED into the live universe loop** (`square_off_all_open_positions` flattens all open paper positions at 15:15) — Rule-G orphan closed 2026-07-24 | `08_session_square_off.md` |
| 9 | Dashboard, Monitoring & Alerting | **signed off (v1)** (2026-07-24): read-model + control config & enforcement + browser dashboard (phone/laptop) + two-way live API + monitoring alerts; **now shows LIVE OPEN positions across the full universe + live §9 tables** via the background `LivePaperTradingService` (was a single-symbol INFY replay). Rule-F verified live 2026-07-24 (45 open positions, universe 9,272). Deferred: push alerts, WebSocket ticks, advanced AI panels | `09_dashboard.md` |
| 10 | Memory & Reflection (Plan 2 — case-based memory, council-of-models, Deflated-Sharpe/CPCV promotion gate, adversarial-validation trip wire, explainable memory; **primary training signal = prediction-error streams from the §9 trade-tables lab: reason ledger, reflection diffs, adversarial arm, double-sided hypothesis tests; plus §10 institution features in order: assumption registry, opponent ledger (participant-wise OI), information diet, epidemiology->antibody automation**) | **slice 1 built + Rule-F verified (2026-07-24)**: swappable `ExperienceMemory` (SQLite v1) — a closed §9 experiment → a memory node; calibration-by-regime / prior-outcomes / reflection-diff queries; wired (loop emits → service records). Substrate research `../research/43`; note `10_memory_reflection.md`. Graphiti/Neo4j temporal-KG = named swap-up for the semantic/multi-hop tier. Next: option experiments, dashboard Reflection panel, then assumption registry | `10_memory_reflection.md` |
| 11 | Strategic LLM / Autonomous Research Agent layer (Plan 3 — deferred: role-divided LLM strategist, debate-as-risk-check, synthetic stress rehearsal, meta-strategy allocator, graph-grounded debate, causal analysis, federated cross-strategy learning; **+ parked §10 items re-evaluated here: prediction-market council weighting, information-diet-directed research targeting**) | deferred until Layer 10 is live and validated | — |

Each layer's file (once it exists) documents, cumulatively:
1. A data-flow diagram from the pipeline's start through that layer.
2. Every function name and every import the layer introduces.
3. The exact type/shape of every piece of data the layer exports.
4. The full list of files belonging to that layer.

**How the 16-trunk AI tree connects to this roadmap:** see
`AI_integration_and_sequencing_map.md` — the tree is built THROUGH these
layers (not after); Layer 7 is where 5 trunks first ignite
(EPISTEMICS/PREDICTIVE-CORE/MEMORY/CONSCIENCE + CURIOSITY/SELF seeds).
**Rule F (CLAUDE.md):** every feature/layer/branch — incl. all 200 AI
branches — is signed off only after verification on the REAL data it
operates on, never fake data.


## Autonomous-intelligence concept map (PLAN §12, research/32)

Breadth-first atlas of ALL 32 main branches of the self-learning
autonomous-AI stem, grouped in 7 trunks — the index that guarantees no
faculty is forgotten when the AI/dashboard phases arrive. Deep
per-branch expansion (sub-branches->twigs) happens later, one branch at
a time, in this order: Constitution+Alignment -> Metacognition ->
Drives -> Ontogeny -> Internet-research -> Tool-use -> rest.

```
MIND     reasoning·learning·memory·METACOGNITION·creativity·foresight·abstraction
SENSES   market·INTERNET-RESEARCH(gated)·anomaly·microstructure·interoception
WILL     DRIVES·planning·autonomy-levels·affect·utility
BODY     actuation·TOOL-USE(gated)·resource-economy·survival·cost-homeostasis
SELF     self-modification(gated)·evolution·ONTOGENY·identity·teachability
SOCIETY  inner-society·external-agents·human-interface·influence(bounded)·teaching-legacy
CONSCIENCE  CONSTITUTION(supreme)·security·law-ethics·off-switch·transparency·ALIGNMENT

  + 7 literature-grounded trunks (PLAN §13, research/33):
VIII  SENTIENCE & GLOBAL WORKSPACE   (Baars/Dehaene/Tononi/Graziano)
IX ⊛  PREDICTIVE CORE / ACTIVE INFERENCE   (Friston)          [meta]
X  ⊛  AUTOPOIESIS / SELF-PRODUCTION   (Maturana & Varela)     [meta]
XI    GENERATIVITY & OPEN-ENDEDNESS   (POET / Clune / Stanley)
XII   INTRINSIC MOTIVATION / CURIOSITY   (Schmidhuber / Oudeyer)
XIII  EPISTEMICS / TRUTH & UNCERTAINTY   (Legg-Hutter / Bayesian)
XIV   AXIOLOGY / VALUES & PRACTICAL WISDOM   (Russell / Gabriel)
  + 2 root-coverage trunks (PLAN §14, research/34 — closed gaps the
    user named as root pillars but were only branches):
XV    MEMORY & KNOWLEDGE BASE   (CMC memory modules / Tulving / graph-memory)
XVI   UNIVERSAL ACCESS & ACQUISITION (gated)  (reach/ingest/integrate ANY
        legit-reachable info+tool+data; technical friction only, never
        auth/law bypass, never market manipulation)
```
16 trunks total. All prior lab/institution/organism concepts
(research/29/30/31) + the research/32 branches map under these — see
research/32 + /33 + /34 coverage checks. Recursive self-improvement =
the EMERGENT loop of SELF x Open-Endedness x Curiosity x Active-
Inference (a product of trunks, not a trunk).

**Depth pass 1 (branches) COMPLETE — PLAN §15/§16, research/35+36:** all
16 trunks now have ~200 branches total (research/35 ~120 + research/36
~80 new, research-grounded), and EVERY branch carries 2-4 seed extension
ideas (research/36). Twig-level depth (below branches, expanding these
extensions into buildable specs) is one-file-per-trunk and PAUSED until
a trunk is picked; order: VII+XIV -> VIII -> XV -> XVI -> IX -> XIII ->
III/XII -> rest.

## AI / dashboard feature implementation queue (from PLAN §9 + §10)

Single ordered list so nothing adopted gets lost. Research each item
right before building it (per Rule D), in this order:

**With Layer 7 base (the lab core):**
1. Prediction-labeled tables: CONFIDENT-WIN / CONFIDENT-LOSS / UNCERTAIN
2. Immutable PredictionRecord (outcome, win-prob, expected R, reasons,
   predicted exit cause, mechanism name, kill criteria)
3. Calendar-condition partition key on every table/ledger
4. Per-table scoreboard: hit rate + Brier score
5. Referee v0: decision-reproduction audits
6. Kill-criteria exit hook (thesis-falsification exits beyond stops)

**Layer 7.5 (after the base runs):**
7. RANDOM-CONTROL + SHADOW-REJECTED arms
8. Skill-vs-Luck Court (verdict pipeline; learning trains on diagonal only)
9. Loss epidemiology (death certificates -> outbreak detection)
10. World-model scoreboard (trade-independent forecasts)
11. Per-trade pre-mortem (entry-time Monte Carlo via replay store)
12. Profit provenance (P&L decomposition vs control arms)
13. Reliability curves per regime/strategy; reason ledger
14. INVERSE-HARVEST arm; promotion/demotion ladder

**Layer 9 (dashboard surfaces for all of the above):**
15. Tables view, calibration boards, verdict feed, epidemiology panel,
    world-model board, reason ledger, assumption tripwires, Referee
    alerts, provenance breakdown (PLAN §2 + §9/§10)

**Layer 10 (memory/reflection fusion):**
16. Memory-graph nodes per closed experiment; nightly reflection diffs
17. Assumption registry + statistical tripwires
18. Opponent ledger (requires participant-wise OI ingestion in Layer 2)
19. Epidemiology -> auto-distilled veto antibodies
20. ADVERSARIAL self-play arm; single-reason interventional trades
21. Double-sided hypothesis pipeline (trade claim AND negation)
22. Information-diet accounting
23. Distributional forecasts + CRPS

**Layer 11 (parked, re-evaluate):**
24. Prediction-market council weighting; information-diet-directed
    autonomous research targeting

**Organism-tree insertions (PLAN §11, research/31) — merged by layer:**
25. L7 base: Constitutional Core scaffold (I1) · state snapshots (E2)
26. L7.5: patience scoreboard (G2) · self-ablation (A3) · competence-
    envelope groundwork (B2) · market-microscope hook (H3) · redundancy
    runbooks (E1)
27. L8: off-switch covenant (I4) · sentinel pair (E3) · chaos drills (E4)
28. L9: vital-signs organ (B1) · transparency organ (I3)
29. L10: homeostatic drive stack (D1-D4) · self-experiment protocol
    (R2a) · metabolic accounting (R2b) · ontogeny ladder (R2c) ·
    novelty governor + self-model (B3/B4) · devil's advocate (F2) ·
    self-scheduling + anniversary reviews (G3/G4) · anomaly telescope
    (H2) · dream synthesis (R2d) · genome split (A2) · niched evolution
    + fossil record (J1/J3)
30. L11: shadow self-rewrite pipeline (A1) · tool foundry / data
    prospecting / knowledge compiler (C1-C3) · apprentice teachability
    (F3) · red-queen sparring (J4) · parked-item re-evaluation

## Whole-system data flow (updated as layers are added)

```
[Layer 1: Universe & Instrument Registry]
   -> produces the Instrument catalogue (cash + index-options + stock-options)
        |
        v
[Layer 2: Market Data]  (complete for v1, Kite-only)
   Broker side (swappable protocols; Kite adapter first):
     HistoricalBarSource -> list[PriceBar]
     LiveTickStreamSource -> MarketTick callbacks
   NSE official-reports side:
     NseReportDownloader + 5 parsers -> delivery %, EOD OI, ban list,
     MWPL utilization, bulk/block deals
        |
        v
[Layer 3: Indicators]  (v1 complete)
   price-series: EMA / RSI / ATR / ADX / Supertrend / session VWAP
     (list[PriceBar] -> 1:1-aligned per-bar series)
   options-derived: BS-IV inversion -> ATM-IV snapshots -> IV Rank;
     PCR-OI (from stored F&O bhavcopy rows, 32 days backfilled)
        |
        v
[Layer 4: Strategy Engine]  (v1 built)
   ADX regime gate -> ORB signal | credit-spread legs | stand aside
   emits OpeningRangeBreakoutSignal / CreditSpreadSignal (atomic legs)
        |
        v
[Layer 5: Risk Management]  (v1 built)
   pre_trade_risk_gate: defined-risk-only + ban-list + fixed-fractional
   sizing -> RiskGateDecision (approved qty | machine-readable reasons)
        |
        v
[Layer 6: Broker OMS]  (v1 built)
   signals+approvals -> OrderIntents (hedge BUY first) ->
   atomic multi-leg executor -> BrokerClient protocol
     paper: SimulatedBrokerClient | live: KiteBrokerClient (MIS, throttled)
   -> (Layer 7 paper engine + Layer 8 square-off will drive this)
```

Full detail: `01_universe_instrument_registry.md`,
`02_market_data_sourcing.md`, `03_indicator_engineering.md`,
`04_strategy_signal_engine.md`, `05_risk_management.md`, `06_broker_oms.md`.
