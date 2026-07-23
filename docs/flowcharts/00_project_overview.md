# 00 — Project Overview & Layer Roadmap

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
| 7 | Backtesting & Paper Trading | not started — realistic options slippage (`../PLAN.md` §1.2), MarketClock/DataSourceRouter 24/7 replay (§1.4), **and the Prediction-Labeled Trade Tables lab (§9) + institution concepts (§10): WIN / deliberate-LOSS / UNCERTAIN tables, immutable PredictionRecords with kill-criteria + mechanism fields, calendar partition keys, Referee audits — the paper engine is an experiment allocator, not one portfolio** | — |
| 8 | Session / Square-off Management | not started — square-off ordering must never leave a naked multi-leg position open, `../PLAN.md` §4 | — |
| 9 | Dashboard, Monitoring, Logging & Alerting | not started — scope in `../PLAN.md` §2 **plus the lab/institution surfaces (§9/§10): live view of all prediction tables (WIN/LOSS/UNCERTAIN/control arms), calibration scoreboards + reliability curves, Skill-vs-Luck verdict feed, loss-epidemiology outbreak panel, world-model scoreboard, reason ledger, assumption-registry tripwire status, Referee audit alerts, profit-provenance breakdown** | — |
| 10 | Memory & Reflection (Plan 2 — case-based memory, council-of-models, Deflated-Sharpe/CPCV promotion gate, adversarial-validation trip wire, explainable memory; **primary training signal = prediction-error streams from the §9 trade-tables lab: reason ledger, reflection diffs, adversarial arm, double-sided hypothesis tests; plus §10 institution features in order: assumption registry, opponent ledger (participant-wise OI), information diet, epidemiology->antibody automation**) | not started; **upgraded recommendation** — build on a temporal knowledge graph (Graphiti-style) from day one, not a plain vector store, per `../research/06_self_learning_ai_feature_taxonomy.md` | — |
| 11 | Strategic LLM / Autonomous Research Agent layer (Plan 3 — deferred: role-divided LLM strategist, debate-as-risk-check, synthetic stress rehearsal, meta-strategy allocator, graph-grounded debate, causal analysis, federated cross-strategy learning; **+ parked §10 items re-evaluated here: prediction-market council weighting, information-diet-directed research targeting**) | deferred until Layer 10 is live and validated | — |

Each layer's file (once it exists) documents, cumulatively:
1. A data-flow diagram from the pipeline's start through that layer.
2. Every function name and every import the layer introduces.
3. The exact type/shape of every piece of data the layer exports.
4. The full list of files belonging to that layer.


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
