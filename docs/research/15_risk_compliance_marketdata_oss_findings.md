# Open-Source Sweep: Risk Management, Compliance/Audit-Trail, Market-Data Infra

Supplementary pass covering three layers the prior research rounds (bots, Greeks engines,
autonomous agents, scanners/backtesters) did not focus on. Every project below was verified via
the GitHub REST API (stars/license/last-push, 2026-07-23) and a direct README fetch — nothing
listed from search snippets alone.

## Area 1 — Portfolio Risk Management / Construction

| Project | URL | Stars | License | Last push |
|---|---|---|---|---|
| PyPortfolioOpt | https://github.com/PyPortfolio/PyPortfolioOpt | 5,882 | MIT | 2026-07-07 |
| Riskfolio-Lib | https://github.com/dcajasn/Riskfolio-Lib | 4,382 | BSD-3 | 2026-06-22 |
| pyfolio | https://github.com/quantopian/pyfolio | 6,373 | Apache-2.0 | 2023-12-23 (stale) |
| fortitudo.tech | https://github.com/fortitudo-tech/fortitudo.tech | 302 | GPL-3.0 | 2026-07-09 |
| pyhrp | https://github.com/tschm/pyhrp | 55 | MIT | 2026-07-22 |
| ibaris/VaR | https://github.com/ibaris/VaR | 33 | none asserted | 2025-09-08 |

**Borrowable pieces:**
- **PyPortfolioOpt** — working efficient frontier (max-Sharpe/min-vol/target-return), Black-Litterman,
  HRP, mean-semivariance & CVaR optimization, covariance shrinkage (Ledoit-Wolf), and a
  **discrete allocation** step that converts continuous weights into actual buyable share/lot
  quantities with L2 regularization. This last piece maps directly onto NSE lot-size constraints.
- **Riskfolio-Lib** — the deepest catalogue: 26+ convex risk measures (CVaR, EVaR, CDaR, Ulcer
  Index, Tail Gini), **logarithmic mean-risk (Kelly criterion) optimization**, Risk Parity + HRP +
  Nested Clustered Optimization, and per-asset/per-factor risk-contribution decomposition. Built on
  CVXPY so it can plug in MOSEK/GUROBI for large constrained problems.
- **pyfolio** — tear-sheet generation (drawdown, rolling Sharpe, factor exposure) — useful as a
  reporting template even though the repo itself is stale (no commits since 2019, only community
  forks are alive; do not depend on it long-term).
- **fortitudo.tech** — Entropy Pooling (blending subjective views/stress scenarios into the return
  distribution) + CVaR optimization + Fully Flexible Resampling — a from-scratch, non-Quantopian
  implementation of the same Meucci-style methodology used at institutional risk desks.
- **pyhrp** — a minimal, dedicated HRP implementation (scipy hierarchical clustering →
  recursive bisection), plus Schur-complement risk allocation. Good as a readable reference
  distinct from PyPortfolioOpt's more opinionated version.
- **ibaris/VaR** — a working multi-method VaR/CVaR engine: historical, parametric (fitted
  distributions), Monte Carlo, **parametric-GARCH**, plus CDaR and PELVE, with a built-in
  `backtest()`/`evaluate()` harness (Kupiec-style exception counting).

**Upgrade path to "ultra advanced" for this project:**
Combine Riskfolio-Lib's risk-measure catalogue + Kelly-criterion optimizer as the core allocator,
feed it PyPortfolioOpt's discrete-allocation step to respect NSE lot sizes, and layer ibaris/VaR's
multi-method VaR/CVaR engine as an intraday **pre-trade risk gate** (reject/size-down any order
that would push portfolio VaR past a limit). Extend VaR to options books specifically:
Greeks-scaled parametric VaR (delta-gamma-vega approximation) plus historical simulation replaying
realized NSE intraday moves, since these libraries are equity-return-only out of the box. Add a
Kelly-fraction cap (e.g., half-Kelly) tied to live win-rate/payoff-ratio estimates from the trade
log (see doc 14), recomputed per strategy per session rather than statically.

## Area 2 — Compliance / Immutable Audit-Trail Logging

| Project | URL | Stars | License | Last push |
|---|---|---|---|---|
| immudb | https://github.com/codenotary/immudb | 9,002 | Apache-2.0-family (NOASSERTION on GH) | 2026-07-22 |
| django-auditlog | https://github.com/jazzband/django-auditlog | 1,376 | MIT | 2026-07-20 |
| Chronicle Queue | https://github.com/OpenHFT/Chronicle-Queue | 3,782 | Apache-2.0 | 2026-07-22 |

**Borrowable pieces:**
- **immudb** — a genuine tamper-proof database: append-only ledger backed by a **cryptographic
  Merkle-tree commit log**, zero-trust client-side verification (clients don't have to trust the
  server), SQL/KV/document access, and ~1.2-1.8M writes/sec on modest hardware. This is a real
  "puzzle piece," not a toy — it's the closest open-source analogue to what SEBI's white-box audit
  trail requirement actually needs: an immutable, independently-verifiable ledger of every order/
  signal/modification.
- **django-auditlog** — a working, mature "who changed what, when" model-level audit log (actor +
  timestamp + JSON diff) for any Django-backed dashboard/admin. It is **not** cryptographically
  tamper-evident by design (its own README does not claim integrity guarantees) — useful only as
  the ORM-level change-capture layer, not as the compliance ledger itself.
- **Chronicle Queue** (flagged as new, see below) — persisted, memory-mapped, broker-less message
  log with microsecond write latency and no backpressure on producers; multiple independent
  "tailers" can replay the full ordered history without consuming it — a strong pattern for
  deterministic audit replay and state reconstruction.

**Upgrade path:** Use immudb as the backing store for the Algo-ID-tagged audit ledger: every order,
modification, cancellation, and risk-check decision gets written as an immudb entry with a
cryptographic proof; run django-auditlog (or a custom equivalent) at the ORM layer purely to
capture human/admin config changes (strategy param edits, kill-switch toggles), then **also** pipe
those into immudb so config changes are equally tamper-evident. Add: SEBI Algo-ID as a mandatory
indexed field on every entry, dual timestamping (exchange-received time + local system time) to
support latency audits, and a periodic external anchoring step (e.g., publishing a daily Merkle
root hash to a public timestamping service) so even a compromised server can't rewrite history
retroactively — mirroring what Certificate-Transparency-style logs (Google's Trillian design) do.

## Area 3 — Real-Time Market-Data Streaming Infrastructure

| Project | URL | Stars | License | Last push |
|---|---|---|---|---|
| QuestDB | https://github.com/questdb/questdb | 17,195 | Apache-2.0 | 2026-07-23 |
| VeighNa (vn.py) | https://github.com/vnpy/vnpy | 43,759 | MIT | 2026-05-17 |
| Chronicle Queue | https://github.com/OpenHFT/Chronicle-Queue | 3,782 | Apache-2.0 | 2026-07-22 |

All the "kafka + tick data" GitHub projects surfaced by search are small student/portfolio demos
(0-16 stars, largely abandoned) — none had README substance worth borrowing as a piece; they were
fetched and rejected rather than omitted from search.

**Borrowable pieces:**
- **QuestDB** — a real, production-grade time-series database purpose-built for tick/trade/order-book
  data: columnar storage, SIMD-accelerated ingestion (millions of rows/sec), and **native
  time-series SQL** (ASOF JOIN, SAMPLE BY, LATEST ON) — exactly the query primitives needed for
  joining option-chain snapshots to underlying ticks. Integrates directly with Kafka/Redpanda/Flink.
- **VeighNa (vnpy)** — flagged explicitly as **new, not covered by prior passes** (those focused on
  NSE-specific bots; vnpy is CTP/China-market-native but architecturally generic). Its
  **RiskManager module** enforces order-flow-rate limits, order-quantity caps, active-order caps,
  and cancellation-count limits — i.e., a working pre-trade risk-control frontend, a different
  puzzle piece from portfolio VaR. Its event-driven engine + market-data gateway abstraction is a
  clean reference for a broker-agnostic tick ingestion layer.
- **Chronicle Queue** (Java, HFT-grade) — real production pattern for persisted, replayable,
  backpressure-free tick ingestion (cited handling CME OPRA's ~10M events/minute). Not Python and
  not directly embeddable, but the **design pattern** (memory-mapped append-only file, multiple
  independent tailers, no producer slowdown) is the right target architecture for a Python
  ingestion layer (e.g., replicate via mmap-backed ring buffer or use it as a sidecar via a thin
  IPC bridge) rather than routing every Zerodha WebSocket tick through Kafka with its ack-based
  backpressure.

**Upgrade path:** Terminate Zerodha Kite Connect's WebSocket ticks into a Chronicle-Queue-style
append-only persisted buffer (or a Python equivalent) to decouple ingestion from downstream
consumers (Greeks engine, scanners, risk engine) with zero producer backpressure, then fan out into
QuestDB for time-series storage/backfill and into the immudb-backed audit ledger for anything
that becomes an order. This closes the loop: tick arrives → persisted losslessly → replayable for
compliance/backtesting → feeds both the live strategy engines and the immutable audit trail with a
single source of truth.

## New ideas flagged ("found this, wasn't asked")
1. **vnpy's pre-trade RiskManager** (order-flow-rate/cancel-count limiting) is a distinct risk
   layer from portfolio VaR — an exchange-facing throttle, not a portfolio-construction tool.
2. **immudb** as a ready-made tamper-evident ledger is a much stronger starting point than writing
   a bespoke hash-chain logger from scratch.
3. **Chronicle Queue's architecture** (no-backpressure, replay-first persisted log) is a better
   mental model for tick ingestion + audit replay than a generic Kafka pipeline, which is what
   every other search result defaulted to.

## Ranked shortlist — read source code from next
1. **Riskfolio-Lib** (dcajasn/Riskfolio-Lib) — richest risk-measure/Kelly/HRP implementation; read
   the `Portfolio` class and CVaR/EVaR constraint-building code.
2. **immudb** (codenotary/immudb) — read the Merkle-tree commit-log and verification client code;
   this is the actual compliance-ledger candidate.
3. **PyPortfolioOpt** (PyPortfolio/PyPortfolioOpt) — read `discrete_allocation.py` for the
   lot-size-aware allocation logic to adapt to NSE lot sizes.
4. **vnpy** (vnpy/vnpy) — read the `RiskManager` app and `EventEngine` core for the pre-trade
   throttle and gateway abstraction pattern.
5. **ibaris/VaR** — small enough to read in full; adapt its GARCH/backtest harness for an
   options-aware intraday VaR gate.
