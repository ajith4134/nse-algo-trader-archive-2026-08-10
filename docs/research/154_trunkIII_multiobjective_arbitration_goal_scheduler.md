# research/154 — Trunk III WILL · multi-objective arbitration + goal-priority scheduler

**Slice:** the first slice of the ABSENT trunk III WILL (drives/goals/decision; 0🟢 3🟡 9🔴). Gives the
system a VOLITION organ: when objectives conflict (return vs risk vs confidence), ARBITRATE them, and
SCHEDULE which mechanisms/goals to pursue first. **Consumes the XIV explicit utility** (research/153) as
one objective — so this also gives XIV a real consumer (partially clears task #8). Cross-trunk wiring.

Moves: **multi-objective arbitration 🔴→🟢** · **goal-priority scheduler 🔴→🟢**.

## Sourcing (Rule I) — bespoke (pymoo is the wrong shape)
Real WebSearch (2026-07-26): **pymoo** (evolutionary multi-objective *optimization* framework — Problems,
algorithms, populations) + **objective-weights-mcda** — REJECTED: heavy, built to OPTIMIZE a continuous
problem; we RANK a small finite set (5 mechanisms) across a few objectives. **pareto.py** (pure-Python
nondominated sort) is the right PRIMITIVE but ~a few lines → implement bespoke (no new dep). Weighted
arbitration reuses the XIV `evaluate_utility`. Sources logged in BACKLOG.

## Real data (Rule F) — 5 real mechanisms
`experience_nodes` grouped by `mechanism_name` gives a real per-mechanism return series each:
false-breakout (n=198, −0.40%) · long-ATM-ORB (n=69, −2.58%) · post-breakout-trend (n=40, −0.76%) ·
indeterminate (n=27, 0.00%) · credit-spread (n=6, **+8.79%**). A real objective-conflict: credit-spread
wins on RETURN but is thin on CONFIDENCE (n=6) — exactly what arbitration must resolve.

## STEP 1 — Target
- `will/multi_objective_arbitration.py` (PURE): each mechanism → an `ObjectiveProfile`
  (utility [XIV], mean_return, −risk, confidence[∝√n]); `arbitrate(profiles, weights) ->
  ArbitrationResult` = the Pareto non-dominated set + a weighted arbitration score + ranking + the
  conflicts (who's dominated by whom).
- `will/goal_priority_scheduler.py` (PURE): `schedule_goals(arbitration, max_concurrent) -> GoalSchedule`
  — priority-ordered mechanisms to pursue (top-K by arbitration score, non-dominated first), the rest deferred.
- **Success test (Rule F):** over the 5 real mechanisms, the Pareto front + weighted ranking are honest
  (credit-spread high on return but confidence-penalised; false-breakout low), and the schedule prioritises the winner(s).

## STEP 2 — Build / wiring
- New `will/` package (Trunk III): the two PURE modules + `ObjectiveWeights` (default: utility &
  confidence weighted, so the arbitration doesn't chase a thin high-return sample).
- Service: `_maybe_run_will_arbitration` reads per-mechanism returns from experience_memory → each
  mechanism's utility via XIV `evaluate_utility` → arbitrate + schedule; `objective_arbitration` +
  `goal_schedule` surfaces. **Consumes axiology (XIV) → clears part of task #8.**
- **Named future consumer (Rule K):** the entry loop prioritises which mechanism's candidates to open
  first when capital/concurrency-constrained, per the schedule. Read-only board until then.

## STEP 3 — Verify
- Hermetic (Rule J): crafted profiles → correct Pareto front (a dominated mechanism excluded), weighted
  ranking respects weights, schedule respects max_concurrent + non-dominated-first.
- Real-data (Rule F): the real 5-mechanism arbitration + schedule; the credit-spread confidence-conflict
  resolved honestly.

## Rule K — after this slice (III WILL remaining)
opportunity-cost accounting · patience scoreboard · commitment/consistency guard · homeostatic drive
stack · goal formation · utility handoff · no-orphan-goals. The scheduler's loop-consumer (prioritise
entries) is QUEUED.
