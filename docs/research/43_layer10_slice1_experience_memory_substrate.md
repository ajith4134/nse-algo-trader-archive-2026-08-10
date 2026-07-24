# 43 — Layer 10 Slice 1: Experience-Memory Node per Closed §9 Experiment — Substrate Research & Design

Layer 10 (Memory & Reflection) opening slice. Anchored on the first queued
AI item (`00_project_overview.md`): **"memory-graph node per closed
experiment; nightly reflection diffs."** Per the AI-integration map, a branch
is built where its trunk first has real data — and that data **exists now**:
the live loop is producing closed §9 experiments (graded predictions + closed
trades). Rule D persist; Rule F verifiable on the real §9 stream.

## 1. The slice spec (what to store, what to query)

A **closed §9 experiment** = a `GradedPrediction` (its `TradePredictionRecord`
+ `actual_outcome` + `realized_pnl` + `prediction_was_correct` +
`brier_contribution`) joined to its `ClosedPaperTrade` (entry/exit/pnl/outcome/
opened_at/closed_at). All fields are **already structured** — no NLP needed.

**Nodes (typed):**
- `Experiment` — one closed prediction+trade (the episodic unit). Bi-temporal:
  `occurred_at` (session/closed_at) + `recorded_at` (ingest time).
- `Strategy` (`strategy_tag`), `Mechanism` (`mechanism_name`),
  `Regime/Context` (`calendar_context` + ADX regime), `Instrument`
  (`instrument_token` → kind: cash/index-opt/stock-opt), `PredictionTable`
  (confident_win/loss/uncertain).

**Edges (typed):** Experiment `-USES_STRATEGY→` Strategy · `-VIA_MECHANISM→`
Mechanism · `-IN_CONTEXT→` Regime/Context · `-ON_INSTRUMENT→` Instrument ·
`-LABELED→` PredictionTable. Each Experiment carries: predicted win-prob,
predicted vs actual outcome, Brier contribution, realized R, reasons
(`NamedPredictionReason[]`: name/observed/claimed-contribution),
predicted-vs-actual exit cause, kill-criteria.

**The three query patterns this slice MUST serve:**
1. **Nightly reflection diff** — per (strategy × mechanism × regime): how did
   hit-rate / mean-Brier / mean-R move vs the previous night's snapshot? →
   grouped aggregation + snapshot compare.
2. **Calibration-by-regime retrieval** — "for THIS strategy in THIS regime,
   historical hit-rate & Brier?" → filtered aggregation on categorical keys.
3. **Entry-time pre-mortem lookup** — at entry, for a signal's (strategy,
   mechanism, regime, instrument-kind), the prior outcome distribution of
   matching past experiments → filtered retrieval + summary stats.

**Crucial observation:** all three are **categorical filters + aggregations**,
not multi-hop graph traversal and not semantic (embedding) similarity. That
directly determines the substrate.

## 2. Substrate research (verified 2026-07, primary + practitioner sources)

| Candidate | What it is | Fit for this slice | Verdict |
|---|---|---|---|
| **Graphiti** (getzep, Apache-2.0, 20k★) | Temporal KG for agent memory | Needs a **Neo4j 5.26+ / FalkorDB server** + an **LLM call per episode** to extract entities *from text*. Our data is already structured (LLM extraction wasted); can ingest structured JSON but still needs the server. Built for semantic linking of unstructured text — not our need yet. | **Defer** — right shape, wrong time; heavy infra + LLM cost for categorical queries. |
| **Kùzu** (embeddable graph) | "DuckDB for graphs", MIT, pip | **Archived Oct 2025 (Apple acquisition), unmaintained** — Graphiti itself is *deprecating* its Kùzu driver. | **Reject** — dead foundation. |
| **Neo4j / FalkorDB** | Server graph DBs | Great multi-user/multi-hop; a heavy service dependency for a few hundred→thousands of single-node nodes with categorical queries. | **Defer** — swap-up target when multi-hop/scale arrives. |
| **Vector store** (LanceDB / sqlite-vec / Chroma) | Embedding similarity | Our matching is on categorical keys, not fuzzy semantics — vectors add cost with no v1 benefit. | **Defer** — add when semantic ("similar setups") retrieval is needed. |
| **SQLite typed-graph** (nodes/edges as tables + FTS, one `.db`) | Embeddable, zero-config | Serves all three query patterns natively (indexed group-by + filter); zero new service deps; **matches the project's existing `market_data.sqlite3`**; 2026 consensus that SQLite suffices for single-node agent memory. | **✅ Adopt for v1.** |

**2026 practitioner consensus (triangulated):** the field stopped arguing
vector-vs-graph and converged on a **swappable poly-store** — NetworkX/SQLite
in-process for dev, swap to Neo4j/FalkorDB for the *few* entity-heavy multi-hop
queries that justify the schema cost, **without rewriting app code**. Vectors
for semantic entry-point, graph for relational depth, episodic buffer for
recency — added *only when a query needs them*.

## 3. Recommendation

**Build v1 as a light, typed `ExperienceMemory` over SQLite — behind a
swappable interface — NOT Graphiti/Neo4j yet.** This mirrors the project's
own broker/data-source swappable-boundary pattern (CLAUDE.md), keeps the
temporal-KG *shape* the plan wants, and avoids standing up Neo4j + per-write
LLM calls to answer categorical questions over a few hundred nodes.

- **Interface (self-describing, Rule C):** `ExperienceMemory` protocol —
  `record_closed_experiment(graded_prediction, closed_trade)`,
  `calibration_for(strategy, regime)`, `prior_outcomes_for(strategy,
  mechanism, regime, instrument_kind)`, `reflection_diff(since)`. Strategy
  code depends on the protocol, never the backend.
- **v1 backend:** `SqliteExperienceMemory` — typed `experiment_nodes` +
  `experiment_edges` tables (or a denormalized experiment row + edge index),
  bi-temporal columns, indices on (strategy, mechanism, regime,
  instrument_kind, occurred_at). One `.db` file alongside the market store.
- **Swap-up path (documented, not built):** a `GraphitiExperienceMemory` /
  `Neo4jExperienceMemory` implementing the same protocol, adopted when we
  need (a) multi-hop "why did this cluster of losses share a hidden cause"
  traversal or (b) LLM-driven semantic linking of unstructured reason text.
  The interface makes that a backend swap, not a rewrite.

**Why not Graphiti now, explicitly:** (1) our data is structured — Graphiti's
core value (LLM entity extraction from text) is unused; (2) it needs a Neo4j
server — a heavy new dependency; (3) an LLM call per write is real cost/latency
for what indexed SQL answers instantly; (4) its own embeddable driver (Kùzu)
is deprecated. We keep Graphiti as the *named, queued future consumer* (Rule G)
for the semantic/multi-hop tier, adopted via the interface.

## 4. Slice-1 build plan (next, one slice — Rule A)
1. `paper_trading/experience_memory/` — `ExperienceMemory` protocol +
   `SqliteExperienceMemory`; node/edge schema from §1.
2. **Wire into the loop (Rule G):** the live service records each closed
   experiment (cash + option paths) into memory as trades close; the nightly
   reflection diff runs at square-off / session end.
3. **Verify on REAL data (Rule F):** replay/live closed §9 experiments →
   memory populated; the three queries return correct calibration/prior/diff
   over the actual stream (not synthetic).
4. **Surface (Layer 9):** a dashboard "Reflection" panel (calibration-by-regime
   + nightly diff) — the CONSCIENCE/EPISTEMICS transparency surface.
5. Update `docs/SYSTEM_MAP.md` (Rule H) + `10_*` flowchart note (Rule B); sign
   off out loud (Rule A) before slice 2 (assumption registry + tripwires).

## Sources
- A: github.com/getzep/graphiti (Apache-2.0; Neo4j 5.26+/FalkorDB required;
  LLM extraction default; **Kùzu driver deprecated — upstream unmaintained**).
- B: multiple 2026 practitioner surveys — SQLite suffices for single-node
  agent memory; swappable poly-store consensus (vector entry-point + graph
  depth + episodic buffer, added on demand); Kùzu archived Oct 2025 (Apple).
