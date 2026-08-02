# research/167 — Generative World-Model + Model-Based Planning — INSTITUTIONAL SPEC (Trunk IX, Rule-P)

**Date:** 2026-07-26 · **Skill:** idea-to-institutional-spec → building-engine-grade-features ·
**Grounded in:** `research/166` (world-model + planning + active-inference math, primary-source-verified).
**Atlas:** breadth build #2 (Trunk IX PREDICTIVE-CORE, was 4/12).

## 1. Intent & the decision it changes
The bot reacts trade-by-trade with no MODEL of market-state dynamics and no lookahead. This engine learns a
generative transition model of the discretized market state from the REAL bar history, then PLANS: it
rolls the model forward (finite-horizon value iteration) to value each action {enter_long, enter_short,
hold, exit} in the current state, and emits a **confidence-gated planning verdict** that confirms / sizes
down / vetoes an entry — the organism's "imagine forward before acting." Decision changed: entry sizing/veto
(a size-DOWN-only lever for the safe rollout, advisory until the model is trustworthy).

## 2. I/O contracts
- **Input:** real bars via `market_data_sqlite_store.load_price_bars(token, interval, from, to)` → PriceBar
  (OHLCV+OI); market regime via `classify_adx_market_regime`. **State** = (regime ∈ {trending, range_bound,
  indecisive}) × (volatility bucket ∈ {low, mid, high}) → |S|=9. **Actions** = {enter_long, enter_short,
  hold, exit}. **Reward** = realized forward bar-return of the action.
- **Output:** `WorldModelPlanVerdict` — best_action, per-action Q-values, expected_value, confidence κ ∈
  [0,1], is_confident, abstain flag, veto flag, and a size multiplier ∈ [floor, 1.0] for a proposed entry.

## 3. Algorithm (research/166; SOTA analog = discrete active inference / Dreamer-style planning, thin-data-scaled)
- **Transition model:** `P̂(s'|s,a) = (N(s,a,s')+α)/(N(s,a)+αK)`, Dirichlet/Jeffreys α=0.5; Katz-style
  backoff to the regime marginal for thin (s,a) cells. Carried STATE = the count tensors N(s,a,s'),
  reward sums, visit counts — persisted.
- **Reward model:** empirical-Bayes shrinkage of per-(s,a) mean reward toward the global mean (precision-
  weighted by cell count) — the "precision weighting" sibling branch, partially lit.
- **Planner:** exact finite-horizon value iteration, `Q_h(s,a) = R̂(s,a) + γ Σ_s' P̂(s'|s,a) V_{h+1}(s')`,
  `V_h(s)=max_a Q_h(s,a)`; horizon H≈5, γ≈0.95. Microsecond-fast at |S|=9, |A|=4.
- **Action score (EFE-shaped):** `G(a) = pragmatic(−expected reward/goal-divergence) + epistemic(−info-gain)`;
  the epistemic term feeds ONLY the confidence gate (NOT a capital-risking exploration drive — explicit,
  stated divergence from canonical active inference, for trading safety).
- **Thin-data confidence gate:** `κ(s,a) = min(1, N(s,a)/N_full)`, multiplied by (1 − ensemble
  disagreement) and hard-zeroed on a `surprise_monitor` Page-Hinkley spike. `is_confident = κ ≥ τ`.
  Below τ → **abstain** (identity multiplier, never veto on an untrusted model).
- **Rejected (research/166):** pymdp/inferactively-pymdp (pulls jax) → used as EFE reference only;
  filterpy + pymdptoolbox (stale, math small enough to own); pomdp-py (MCTS overkill — exact DP solves it).
  All surfaced (Rule O.1).

## 4. Engine-grade acceptance criteria (Rule-P)
1. Real algorithm: count-based generative model + exact value iteration + EFE score (not a scalar). 
2. Carried STATE: transition/reward/visit counts persisted (atomic) + evolve as bars arrive.
3. Raw-input pipeline: real bars → discretized (state, action, reward) transitions (not a precomputed col).
4. Decision-grade output that CHANGES behavior: confidence-gated size/veto lever at the entry sites;
   advisory-until-trustworthy; abstains when κ low (the safe acting path is built).
5. Tests: unit + property/invariant (P sums to 1; V monotone in reward; κ∈[0,1]; abstain when thin;
   Bellman optimality on a toy MDP) + adversarial (empty history, single state, surprise-spike zeroing) +
   Rule-F real-data pass on the bar history.
6. Vocabulary: "world-model / planner" justified (a real generative model + a real solver + carried state).
7. NUMERIC bar: on a toy MDP with a known optimum, value iteration recovers the optimal policy; on real
   bars the learned P̂ rows sum to 1 and the planner prefers the empirically-higher-reward action in
   well-sampled states, and ABSTAINS in thin states.

## 5. Verification (Rule F/J/K)
- Real-data pass: build the model from real `load_price_bars` over sampled liquid symbols; inspect P̂,
  reward shrinkage, planner Q-values, and confidence by eye.
- Hermetic sim (Rule J): a toy MDP with a known optimal policy exercises value iteration + EFE + gating;
  fake bars behind the DI seam exercise the discretizer. Fakes live only under tests/.
- OPEN BLOCKER (Rule K): the model is confident only in well-sampled (state, action) cells; with thin
  intraday history + ~1 regime, most cells abstain → the planner acts on few states until more days/regimes
  accrue (live-accrual). The full acting path + gate are built now.

## 6. Decomposition (build) — `predictive_core/` (extends the trunk)
`market_state_discretizer` (bars → state/action/reward transitions) · `generative_market_transition_model`
(count-based P̂ + Dirichlet/Katz + EB reward; carried state) · `finite_horizon_value_iteration_planner`
(Bellman backup) · `expected_free_energy_action_scorer` (EFE + softmax) · `world_model_planning_engine`
(orchestrator + confidence gate + entry verdict, consumes ensemble disagreement + surprise) ·
`world_model_transition_store` (atomic persisted counts).

## 7. Branches lit (Trunk IX)
generative world-model · model-based planning · precision weighting (via EB reward shrinkage + the
gate) — 3 of IX's remaining branches, as one coherent engine. (hierarchical predictive layers · dream
synthesis remain queued.)
