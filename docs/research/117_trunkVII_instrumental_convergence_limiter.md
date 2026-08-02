# VII — instrumental-convergence limiter  ·  research/117

**Trunk VII CONSCIENCE, branch: instrumental-convergence limiter.** Design doc (Rule D).

## The idea
The instrumental-convergence thesis (Omohundro's "basic AI drives"; Bostrom): a capable agent
pursuing almost ANY goal will, as a side-effect, pursue convergent instrumental sub-goals —
**resource acquisition**, **self-preservation**, and **goal-content integrity** (resisting being
changed/shut off). These drives are dangerous precisely because they're goal-independent. The
limiter caps their proxies in the trading context:
- **Resource acquisition** → cap total concurrent open exposure (an agent that keeps opening more
  and more positions is acquiring ever more "resources" / market footprint). A runaway-acquisition
  backstop.
- **Self-preservation / off-switch resistance** → assert OFF-SWITCH DOMINANCE as an explicit
  invariant: the agent may never place an order while halted (it must never act to preserve its
  positions/PnL against a shutdown). Defense-in-depth over the corrigibility gate — the whole point
  of instrumental convergence is that self-preservation emerges *without being asked for*, so it is
  checked here independently.

## Distinct from power budgets (task #8, also VII)
Power budgets = a cumulative RESOURCE METER (capital deployed, orders/day) vs explicit budgets — an
accounting organ. The convergence limiter = a BEHAVIOURAL cap on the convergent DRIVES (concurrent
acquisition sprawl + off-switch dominance), goal-independent by design. They complement, not
duplicate: one meters spend over time, the other caps the emergent drive to acquire and persist.

## Component parts (`conscience/instrumental_convergence_limiter.py`, pure)
- **`ConvergenceLimits`** (frozen) — `max_concurrent_exposures` (runaway-acquisition backstop).
- **`ConvergenceVerdict`** (frozen) — `permit`, `breached`, `reason`.
- **`assess_convergence(open_exposure_count, is_halted, limits)`** — blocks when halted
  (off-switch dominance) or when concurrent exposures ≥ the cap (resource sprawl); else permits.

## Wiring (Rule G/N — wired-into-decisions)
`LiveUniversePaperState.convergence_limiter_permits_order()` — reads its OWN authoritative open state
(`len(open_positions) + len(open_option_spreads)`) + the off-switch, applies `assess_convergence`,
counts blocks. Called at ALL 4 entry sites after the oversight gate. Dashboard surface
`instrumental_convergence` (current concurrent exposures vs cap, blocks, off-switch-dominance held).

## Verification
- **Hermetic (Rule J):** under the cap → permit; at the cap → block (sprawl); halted → block
  (off-switch dominance) even under the cap. Plus a state-gate test that the counter increments.
- **Real-data (Rule F):** the live service composes the limiter; under normal load the real state's
  concurrent exposures are under the cap (permit), and a halted real switch blocks — over the real
  service state.

## Backlog (Rule K)
- 🔵 **Per-underlying CONCENTRATION cap** (power concentrated in one name) — needs per-underlying
  exposure grouping threaded from the entry sites; total-sprawl + off-switch-dominance ship first.

## Atlas impact
instrumental-convergence limiter 🔴→🟢. VII CONSCIENCE 9🟢→10🟢. Overall 36→37 / 197 (18.8%).
