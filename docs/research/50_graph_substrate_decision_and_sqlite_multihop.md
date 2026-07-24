# Research/50 — Graph substrate decision + SQLite multi-hop reflection

**Layer 10 memory substrate.** Rule D. Closes the research/43 "Graphiti/Neo4j
swap-up" backlog item with a verified decision, and designs the multi-hop
capability it was a placeholder for — delivered in SQLite.

## 1. Graphiti/Neo4j verdict — DO NOT swap (verified 2026-07-24)
Verified against the live getzep/graphiti repo (github.com/getzep/graphiti,
Apache-2.0, 29.1k★, active):
- Graphiti **builds temporal knowledge graphs from UNSTRUCTURED / semi-structured
  TEXT** (chat, docs) by **LLM entity/relationship extraction** — an **LLM API key
  is mandatory** (OpenAI/Anthropic/Gemini structured output) and a **graph-DB server
  is required** (Neo4j 5.26+/FalkorDB/Neptune; **Kùzu 0.11.2 is deprecated** — the
  embedded option is gone, confirming research/43).
- Our `ExperienceMemory` stores **already-structured typed records**; there is
  nothing to LLM-extract. Feeding structured rows through a text-extraction pipeline
  is an impedance mismatch, and it would add a DB server + paid LLM calls on the VPS
  for **no query a categorical/temporal SQLite query can't serve** at our scale
  (thousands of rows).
- **Decision: REJECT the swap** (over-build, no consumer). This upholds research/43's
  original "SQLite because structured + categorical." Revisit ONLY if a genuine
  semantic-over-text or huge-graph consumer appears. (User chose this path,
  2026-07-24.)

## 2. Deliver the capability, not the infra — SQLite multi-hop
SQLite (3.34 here) supports **window functions (`LAG`)** and **`WITH RECURSIVE`**, so
temporal/multi-hop queries are native — no server, no LLM. The "graph/temporal tier"
Graphiti was a placeholder for is servable in-process.

## 3. What the REAL data supports right now (checked 2026-07-24)
The 213 real experiences span **one regime ("normal")** and 5 mechanisms with
**30–75-trade sequences** each. So regime-transition / cross-regime co-failure
queries have **no regime variation to verify against yet** (premature — queued).
What the sequences DO support is a genuine temporal hop-to-prior-trade:

**Flagship query — outcome-sequence dependence (this slice).**
Per mechanism, `LAG(actual_outcome) OVER (PARTITION BY mechanism_name ORDER BY
occurred_at)` gives each trade's PRIOR outcome. Compare **post-win win-rate vs
post-loss win-rate**. A large gap = the mechanism's wins/losses **cluster** (are not
independent) — which matters because the calibration z-test and veto assume iid
Bernoulli trials; clustered errors make those stats **optimistic** (effective n is
smaller). A real multi-hop signal, verifiable on the real data now.

- `OutcomeSequenceDependence(strategy, mechanism, n, overall_win_rate,
  post_win_win_rate, post_loss_win_rate, dependence_gap, clusters)` where
  `clusters = |dependence_gap| ≥ 0.15` with enough transitions.
- **Consumer (Rule K — decision-adjacent, not decoration):** when a mechanism
  `clusters`, append "errors cluster — iid calibration stats optimistic" to its
  calibration verdict detail (same wiring as the Brier diagnosis) → shown on the
  Assumption-tripwires panel; a reflection insight the antibody's explanation carries.

## 4. Files & wiring
- `ExperienceMemory.outcome_sequence_dependence(minimum_experiments, recency_window)`
  (protocol + sqlite via `LAG`). `OutcomeSequenceDependence` record.
- `evaluate_trading_assumptions` looks up dependence by mechanism and enriches the
  calibration verdict detail.
- No new package/file for the query itself — it is a method on the existing memory
  substrate (Rule G: consumer = the antibody verdict + reflection panel).

## 5. Verify
- Hermetic: a hand-built alternating/streaky sequence → expected post-win vs
  post-loss rates + `clusters` flag; an independent sequence → gap ≈ 0.
- **Rule F (real, now):** run over the real 213 experiences — every mechanism gets a
  finite dependence read; report which cluster.

## 6. Backlog (Rule K — queued, needs data we don't have yet)
- **Regime-transition fragility** + **cross-regime co-failure clusters** — real value
  once the data spans multiple regimes (needs live sessions across ADX regimes).
  Recorded in docs/BACKLOG.md; the LAG/recursive-CTE substrate built here is the
  vehicle.
