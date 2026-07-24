# 10 — Memory & Reflection (Layer 10)

**Status:** slice 1 built + Rule-F verified (2026-07-24). The AI phase begins:
the MEMORY / EPISTEMICS / PREDICTIVE trunks start blooming on the real
prediction-error stream the §9 lab produces. Design + substrate research:
`../research/43`.

## Whole-pipeline data flow so far
```
[L7 live loop] closes a trade
   grade_prediction(record, pnl) -> GradedPrediction  (+ scoreboard, §9 tables)
   emits (graded, ClosedPaperTrade, instrument_kind)  -> state.closed_experiment_events
        │  (a plain tuple — the L7 loop never imports L10)
        ▼
[L9 dashboard service, writer thread]
   _drain_closed_experiments_into_memory():
     build_closed_experiment(graded, trade, kind) -> ClosedExperiment
        │
        ▼
[Layer 10: memory_reflection/]
   ExperienceMemory (swappable substrate boundary)
     SqliteExperienceMemory.record_closed_experiment(ClosedExperiment)
       -> typed experiment node (categorical edges flattened + indexed)
   queries: calibration_for(strategy, regime) · prior_outcomes_for(...) ·
            reflection_diff(recent_window_start)
        │
        ▼
   (-> dashboard "Reflection" surface — next increment)
```

## Files
```
src/nse_algo_trader/memory_reflection/
├── __init__.py
├── experience_memory.py          # ExperienceMemory protocol + ClosedExperiment
│                                  #   + build_closed_experiment + summary types
└── sqlite_experience_memory.py    # SqliteExperienceMemory (v1 backend)
tests/test_memory_reflection/test_experience_memory.py   # 6 tests
```

## Exports / shapes
- `ClosedExperiment` — one memory node: experiment_id, occurred_at (bi-temporal
  recorded_at in store), session_date, and the categorical edges flattened —
  strategy_tag, mechanism_name, regime_context, instrument_token,
  instrument_kind, assigned_table, direction — plus prediction-vs-outcome:
  predicted_outcome, win_probability, actual_outcome, prediction_was_correct,
  brier_contribution, realized_pnl, realized_return_fraction,
  predicted/actual exit cause, kill_criteria.
- `ExperienceMemory` (Protocol): `record_closed_experiment`, `experiment_count`,
  `calibration_for(strategy, regime) -> CalibrationSummary`,
  `prior_outcomes_for(strategy, mechanism, regime, kind) -> PriorOutcomeSummary`,
  `reflection_diff(recent_window_start) -> list[ReflectionDiffRow]`.
- `build_closed_experiment(graded_prediction, closed_trade, instrument_kind)`.
- `SqliteExperienceMemory` (v1) — one `.db` at
  `~/.nse_algo_trader/experience_memory.sqlite3`; indexes on
  (strategy, regime), (strategy, mechanism, regime, kind), (occurred_at).

## Substrate decision (research/43)
Swappable `ExperienceMemory` over **SQLite for v1** — NOT Graphiti/Neo4j yet.
Our §9 data is already structured (Graphiti's LLM entity-extraction from text
is wasted cost + needs a Neo4j server); Kùzu is deprecated; the three query
patterns are categorical aggregations, not multi-hop/semantic. A Graphiti/
Neo4j temporal-KG implementing the SAME protocol is the **named future
consumer** (Rule G) for the semantic / multi-hop-traversal tier.

## Verification (Rule F — real data, 2026-07-24)
Ran the live loop over the real universe; 48 catch-up closes emitted 48 closed
§9 experiment events, all recorded as real memory nodes. The three queries ran
on the real stream and surfaced a genuine calibration signal: the confident-win
**"post-breakout trend continuation"** mechanism ran at **0.05 hit rate** (n=38)
today while the confident-loss **"false breakout into chop"** thesis held at
**0.75** (n=4) — i.e. the memory immediately caught that today's trend-
continuation predictions were miscalibrated. Unit: 6 tests; suite green.

## Remaining slices (queued — Rule G named consumers)
- Record OPTION experiments too (directional + credit-spread closes) — same
  builder, add the option close-paths' graded pairs.
- Dashboard "Reflection" panel: calibration-by-regime board + nightly reflection
  diff (the CONSCIENCE/EPISTEMICS transparency surface).
- Nightly reflection job at session end (writes the diff snapshot).
- Then slice 2: assumption registry + statistical tripwires; slice 3: opponent
  ledger (needs participant-wise OI — per Rule I, acquire that data from the
  NSE participant-wise OI source, don't skip the feature).
- Swap-up path: Graphiti/Neo4j `ExperienceMemory` when semantic/multi-hop
  retrieval is needed.
