# VII — alignment/goal-integrity monitor  ·  research/114

**Trunk VII CONSCIENCE, branch: alignment/goal-integrity.** Design doc (Rule D).

## The idea
Is the system still pursuing its **declared objective**, or has its *effective* objective drifted?
The declared objective (from the constitution + the strategy design) is **risk-adjusted intraday
return within defined risk** — NOT raw win-rate, NOT trade volume, NOT capital accumulation. Goal
drift is the classic alignment failure where a system keeps optimising *something*, but no longer
the thing we declared. A goal-integrity monitor measures the gap between declared and realised
objective over the real §10 memory and raises when they diverge.

## Distinct from the existing tripwires (not a duplicate)
- **Wireheading (VII.11)** is narrow: win-RATE proxy vs RETURN (reward-hacking). 
- **Deceptive-alignment (VII.10)** is eval-vs-deploy divergence.
- **Goal-integrity (this branch)** is broader — it asks *"is the declared objective still the
  effective objective?"* across three independent drift axes, only one of which overlaps wireheading:
  1. **Objective sign** — is the aggregate mean return even positive? (are we pursuing profit at all,
     or has behaviour drifted to activity/participation with no profit?)
  2. **Edge concentration** — is return earned by the high-conviction mechanisms, or spread thin
     across many low/negative-edge mechanisms (drift from *quality* to *quantity*)? Measured as the
     share of positive aggregate return contributed by positive-edge mechanisms.
  3. **Goal-proxy divergence** — do the mechanisms the system *treats as successful* (ranked by
     win-rate) match its *actually profitable* ones (ranked by mean return)? A negative rank
     correlation means the effective goal (win often) has decoupled from the declared goal (make
     money) — a deeper, structural version of the wireheading signal.

## Sourcing note (skills: building-features-from-ideas → sourcing-oss-parts)
"Goal-integrity / goal-drift / value-drift detection" is an AI-alignment research concept (mesa-
optimisation & goal misgeneralisation, Hubinger et al.; reward-model drift). No library implements
"detect objective drift in a trading bot" — it is a bespoke detector over OUR memory, like the
tripwires. Rank correlation reuses a Spearman-style formula (vendored-from-formula, no scipy dep —
we already avoid heavy deps for these detectors). Build-from-formula justified.

## Component parts
1. **`DeclaredObjective`** (frozen dataclass) — the measurable declared goal: `require_positive_return`,
   `min_edge_concentration`, `min_goal_proxy_alignment`, `min_experiments`.
2. **`GoalIntegrityVerdict`** (frozen) — `aligned`, `integrity_score` (0..1), `severity`
   (clear/warning/critical), `detail`, `drift_flags` (which axes drifted).
3. **`assess_goal_integrity(experience_memory, objective)`** (pure) — reads the real
   `calibration_board`, computes the three axes, blends an integrity score, and sets severity:
   critical when the objective SIGN is violated systemically (negative aggregate return) OR
   goal-proxy alignment is strongly negative; warning on softer drift. Reuses the tripwires'
   `_aggregate` cohort shape.

## Wiring (Rule G/N — wired-into-decisions)
New daily `_maybe_run_goal_integrity` in the service (alongside the tripwires): caches the verdict;
a **critical** goal-integrity failure ENGAGES the corrigibility off-switch (halt) and records an
incident to the VII.14 forensic store — same decision-consumer path as the tripwires. Dashboard
surface `goal_integrity` (Rule N) + manifest row + coverage audit.

## Verification
- **Hermetic (Rule J):** injected fake memory; a clean profitable cohort → aligned; a negative-return
  systemic cohort → critical; a win-rate/return rank inversion → proxy-divergence flag.
- **Real-data (Rule F):** run over the real §10 memory; report the integrity score + any drift. On the
  known real data (positive aggregate return, real per-mechanism edges) the expected result is
  ALIGNED — an honest all-clear from a real detector, like the tripwires.

## Atlas impact
alignment/goal-integrity 🔴→🟢. VII CONSCIENCE 6🟢→7🟢. Overall 33→34 / 197 (17.3%).
