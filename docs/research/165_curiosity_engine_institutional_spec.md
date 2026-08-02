# research/165 — Curiosity / Learning-Progress Engine — INSTITUTIONAL SPEC (Trunk XII, Rule-P engine)

**Date:** 2026-07-26 · **Skill:** idea-to-institutional-spec → building-engine-grade-features.
**Grounded in:** `research/164` (intrinsic-motivation math + SOTA, primary sources). **Atlas:** first
breadth build of the ATLAS BREADTH PROGRAM (Trunk XII INTRINSIC MOTIVATION, was 0/11).

## 1. Intent & the decision it changes
The bot's ML win-probability model is trained on thin, undiverse data (≈1 session-day, all "indecisive"
regime). Nothing drives it to GATHER diverse experience. This engine is the organism's "wants to learn"
drive: it scores every (strategy × market-regime) cell by how much LEARNING sampling it would yield, and
steers the **replay curriculum** (which historical session/regime to train on next) toward the highest-
learning cell — replacing the existing raw coverage-deficit heuristic. Decision changed: *what the bot
trains on* (safe — simulation/replay, never live sizing).

## 2. I/O contracts
- **Input:** raw `experience_nodes` rows (DI seam `experience_row_source`): strategy_tag, market_regime,
  win_probability, actual_outcome, brier_contribution, occurred_at (ASC). **Output:** `ExplorationPlan`
  — ranked `CellExplorationPriority` (priority · softmax select_probability · LP · Q_LP · novelty ·
  boredom · competence · trusted/unobserved flags) + `regime_priority: dict[regime→priority]` +
  temperature + is_mature. Consumer: `select_curiosity_driven_replay_session(candidates, regime_priority)`.

## 3. Algorithm (research/164; SOTA analog = Oudeyer-Kaplan IAC / SAGG-RIAC)
Per (strategy × regime) cell, over its time-ordered Brier-error series:
`LP = ⟨err⟩_prior_window − ⟨err⟩_recent_window` (W=MIN_WINDOW=8; untrusted until ≥2W samples). Track
`Q_LP ← Q_LP + α(|LP|−Q_LP)` (α=0.3; |LP| so drift re-triggers interest — SAGG-RIAC). Cold-start /
unobserved cells: count-based novelty `β/√(N+1)` (β=1, exact at N=0 — Bellemare 2016). Boredom
`exp(−κ·bored_windows)` (κ=0.5) retires mastered-stable cells (LP→0). Combine
`priority = (0.7·Q_LP + 0.3·novelty)·boredom`; select via softmax LP-bandit with temperature annealed
`T = max(0.1, 1/(1+trades/500))`. **Rejected (research/164):** empowerment (no real action→future-state
channel in trading), RND (overkill for a few discrete cells), all surveyed OSS libs (none fit discrete
cells) → bespoke is correct.

## 4. Engine-grade acceptance criteria (Rule-P) — all MET
1. **Real algorithm:** LP + non-stationary Q_LP tracker + count-novelty + softmax bandit (not a scalar). ✅
2. **Carried STATE:** per-cell Q_LP + boredom + sample watermark + trade count, persisted (atomic JSON). ✅
3. **Raw-input pipeline:** `experience_nodes` → per-cell Brier-error series (not a precomputed column). ✅
4. **Decision-grade output that changes behavior:** regime_priority steers `select_curiosity_driven_
   replay_session` (what the bot trains on). ✅ (safe pre-earning — simulation, not live sizing).
5. **Tests:** 20 (unit + property/invariant + adversarial + persistence + selector). ✅
6. **Vocabulary:** "engine" justified (real LP/bandit algorithm + carried state). ✅
7. **NUMERIC/behaviour bar:** on real data (340 trades, all "indecisive"), the engine top-ranks the 6
   UNOBSERVED (trending/range_bound × strategy) cells and de-prioritizes the mastered
   opening_range_breakout (n=265) — i.e. it correctly drives toward the diversity the win-prob model
   needs. ✅

## 5. Verification (Rule F/J/K)
- **Real-data pass:** ran on the real 340-trade `experience_nodes` — output inspected (unobserved regimes
  top-ranked, mastered cell demoted, LP=−0.011 on directional_option_orb, temperature 0.595, mature). ✅
- **Hermetic sim (Rule J):** the test suite injects canned rows through the DI seam to exercise LP
  positive/negative, trust gate, boredom, cold-start — the fake lives only under tests/.
- **OPEN BLOCKER (Rule K):** LP is per-cell meaningful only with ≥16 trades/cell across ≥2 time windows;
  with 1 session-day most cells are cold-start-novelty-driven. True LP curves accrue as more trading days
  arrive (same live-accrual shape as win-prob). The acting path (replay steering) works now.

## 6. Decomposition (built) — `intrinsic_motivation/`
`curiosity_experience_reader` (raw → per-cell error series + seen universe) · `learning_progress_estimator`
(LP + Q_LP + boredom, carried state) · `count_based_novelty` (β/√(N+1) + unobserved enumeration) ·
`curiosity_engine` (orchestrator: combine → softmax plan → regime priorities) · `curiosity_engine_store`
(atomic persisted state). Consumer wired in `paper_trading/deficit_driven_replay_session_selector`.

## 7. Branches lit (Trunk XII)
learning-progress reward · competence/certainty drives · uncertainty-targeted active learning ·
boredom signal · diversity/novelty bonus (5 of XII's 11) — as one coherent engine.
