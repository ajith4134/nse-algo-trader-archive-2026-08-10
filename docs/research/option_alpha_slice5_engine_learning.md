# Slice 5 — Self-learning engine re-weighting (option_alpha)

The ultra-tier: the bot learns WHICH of its own profit-engines actually pay from its realised track record and
re-weights the opportunity scorer toward them — so capital shifts to the engines that work in THIS market.

## The loop
`scorer picks engine → optimizer synthesizes structure → lifecycle closes it → record (engine, won, P&L) →
EnginePerformanceLearner computes each engine's realised edge → weights → scorer re-weights the engine scores`.

## Engines
### A. `EnginePerformanceStore` (carried state)
Each closed pod trade records `(engine, won, realized_pnl)` (engine from the synthesized structure's
provenance). Persisted JSONL. The substrate of the learning.

### B. `EnginePerformanceLearner`
Per engine, from its closed trades: realised **win-rate** and **mean P&L**. Small-N honesty (Rule Q): the
weight is a **Bayesian-shrinkage** blend toward a neutral 1.0 —
`weight = 1 + k·(edge)·(n/(n+n0))`, where `edge = win_rate − base_rate` (or normalized mean-P&L), `n0` the
shrinkage prior. Thin engine → weight ≈ 1.0 (neutral, no premature tilt); a proven engine → weight > 1 (up-
weight), a losing one → weight < 1 (down-weight, floored ≥ a minimum so it still explores). Output:
`{engine: weight}`.

### C. Scorer integration (changes behaviour)
`OptionOpportunityScorer.rank_universe` accepts optional `engine_weights`; each engine score is multiplied by
its weight before the argmax. So the selection itself shifts toward the engines that have paid — the bot
learns its own edge. Weights refresh each cycle from the store (online).

## Depth justification
Real learning from realised outcomes (shrinkage estimator over carried state), closing the loop from decision
→ outcome → re-weighted decision — not a static heuristic. SOTA analog: an online policy-weighting /
contextual-bandit arm-value update (river-style), applied to the engine-selection policy.

## Rule Q / F
Real closed-trade accrual is thin on paper (few option trades close per session) → the learner shrinks to
neutral until trades accrue; the weights arm themselves automatically as the track record grows (no code
change). The full algorithm ships now; the DATA accrual is the one permissible open blocker (Rule K). Verify
hermetically (injected closed-trade history → correct weights) now; the real-data tilt matures live.

## Sourcing (Rule I)
numpy for the shrinkage math (dep present). `river` (already a dep) offers online bandit/metric primitives but
the per-engine shrinkage weight is a few exact lines fitter than wiring a bandit; a full contextual bandit over
(regime × engine) is the queued upgrade. No external OSS to vendor. Logged.

## Backlog (Rule K)
- CVXPY cross-name BOOK optimizer — pick the portfolio of option trades maximizing expected utility subject to
  net-greeks / margin / VaR (the other half of slice 5) — QUEUED as a distinct engine.
- Contextual bandit over (regime × engine) once trade volume supports it.
- Real-data tilt accrual (few paper closes today) — the permissible blocker.
