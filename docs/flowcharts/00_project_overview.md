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
| 5 | Risk Management | not started — must model per-combination option margin + undefined-risk-leg detection, `../PLAN.md` §4 | — |
| 6 | Broker Integration & Order Execution (OMS) | not started — architecture decided: in-house `BrokerClient` protocol (paper/live parity), multi-leg orders as one atomic unit, `../PLAN.md` §1 | — |
| 7 | Backtesting & Paper Trading | not started — must include realistic options slippage/spread modeling, `../PLAN.md` §1.2 | — |
| 8 | Session / Square-off Management | not started — square-off ordering must never leave a naked multi-leg position open, `../PLAN.md` §4 | — |
| 9 | Dashboard, Monitoring, Logging & Alerting | not started — scope defined in `../PLAN.md` §2 | — |
| 10 | Memory & Reflection (Plan 2 — case-based memory, council-of-models, Deflated-Sharpe/CPCV promotion gate, adversarial-validation trip wire, explainable memory) | not started; **upgraded recommendation** — build on a temporal knowledge graph (Graphiti-style) from day one, not a plain vector store, per `../research/06_self_learning_ai_feature_taxonomy.md` | — |
| 11 | Strategic LLM / Autonomous Research Agent layer (Plan 3 — deferred: role-divided LLM strategist, debate-as-risk-check, synthetic stress rehearsal, meta-strategy allocator, graph-grounded debate, causal analysis, federated cross-strategy learning) | deferred until Layer 10 is live and validated | — |

Each layer's file (once it exists) documents, cumulatively:
1. A data-flow diagram from the pipeline's start through that layer.
2. Every function name and every import the layer introduces.
3. The exact type/shape of every piece of data the layer exports.
4. The full list of files belonging to that layer.

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
   -> (nothing consumes signals yet — Layer 5 Risk will validate them)
```

Full detail: `01_universe_instrument_registry.md`,
`02_market_data_sourcing.md`, `03_indicator_engineering.md`,
`04_strategy_signal_engine.md`.
