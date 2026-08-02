# B18 steps 4–5 — arm-selection posterior store + adaptive selector: design

Implements SPEC §4. **Sourcing pass already run and recorded** in
`b18_index_options_ensemble_research_2026-07-27.md` §6 (INTEGRATE: PyBandits / river / vowpalwabbit;
13 libraries REJECTED with per-candidate reasons). This design follows that pass's own conclusion:

> No library ships the composite (hierarchical shrinkage + discounting + forced floor +
> delayed-reward async updates). Use a posterior core and write the wrapper in-repo.

**Why not just import PyBandits here:** the four safeguards are the engine. A stock Beta/Gaussian TS
posterior is ~20 lines of conjugate arithmetic; the value is entirely in the shrinkage, the time
decay, the burn-in cap and the permanent floor — none of which PyBandits provides, and all of which
would have to wrap it anyway. Adding the dependency would buy the easy 20 lines and still leave the
hard part. Recorded as a deliberate, reasoned decision, not an un-searched one.

## The problem the design must survive

Edge is **5–20% of per-trade noise SD** at **~2.5–7.5 closed trades/day/arm**, while regimes turn
over in **days to ~2 weeks**. Plain TS needs ~390 trades/arm for a 10-point gap (~4 months) and
~4,360 for a 3-point gap (~3.5 years). So the selector must be built to be *honest about not
knowing*, for a long time, without either freezing or chasing noise.

## Two modules

### `paper_trading/arm_selection_posterior_store.py`
Per-cell sufficient statistics, where a **cell = (arm, index, regime bucket)**.

- Tracks discounted `effective_sample_count`, `reward_sum`, `reward_square_sum` — enough for a
  Gaussian posterior without storing every trade.
- **Time-based exponential decay**, not per-observation: `decay = 0.5 ** (days_elapsed /
  half_life_days)`, applied when a cell is touched. Per-observation decay would forget faster in
  busy weeks and slower in quiet ones — the opposite of what "forget stale regimes" means. Default
  half-life **21 trading days** (~1 month), giving the 4–8 week effective memory the research
  recommends.
- SQLite-persisted, so a restart does not erase weeks of accrued evidence (the system restarts often).
- A **pending table** for delayed rewards: `(trade_id, arm, cell, opened_at)` written on open,
  resolved on close. Per Joulani et al. (ICML 2013) delay costs only *additive* regret and needs no
  synchronisation — so selection is NEVER blocked on open trades.

### `paper_trading/adaptive_arm_selector.py`
The composite policy over those statistics.

1. **Hierarchical empirical-Bayes shrinkage**, two levels:
   `shrunk = (n_eff·cell_mean + k·parent_mean) / (n_eff + k)`, where the parent is the arm's
   cross-context mean, itself shrunk toward the grand mean. A new cell therefore inherits real
   information instead of a flat prior — this is what moves per-cell sample needs from *years* to
   *weeks*.
2. **Thompson sampling** from `Normal(shrunk_mean, sigma / sqrt(n_eff + k))`, sigma pooled across
   cells while a cell is thin. Randomness is injected (`random.Random`) so tests are deterministic.
3. **Burn-in cap** — while any arm in this context has `n_eff < 15`, selection is uniform among the
   under-burn-in arms. This *forces* the thin arms to fill rather than letting an early lucky arm
   monopolise.
4. **Permanent ε-floor (12%)**, never phased out — a temporarily-losing arm is never starved of the
   data needed to prove whether it was bad or unlucky.

**Reward** is the CVaR-adjusted, cost-net P&L (SPEC §3): `realized_pnl − total_fees`, penalised by
the cell's downside dispersion so one rare large loss on a premium-selling arm is not averaged away.

## Acceptance criteria

1. `effective_sample_count` decays with elapsed TIME, not observation count; a cell untouched for
   one half-life has ~half its former weight.
2. Statistics survive a restart (SQLite round-trip).
3. Shrinkage strictly reduces total squared error vs raw per-cell means on synthetic cells with
   known truth — the James-Stein claim **tested, not asserted**.
4. A brand-new cell inherits the parent mean, never a flat/zero prior.
5. Burn-in: with any arm under 15 effective samples, no arm exceeds a near-uniform share.
6. ε-floor: over a long run every arm receives ≥ ~ε/K of selections in every context, forever —
   including an arm that always loses.
7. **Convergence:** on a synthetic stream with a genuinely better arm, the selector concentrates on
   it within a stated number of trades.
8. **Non-convergence (the overfitting test):** on a stream with NO true edge, the selector does NOT
   concentrate — allocation stays near uniform. This is the test that matters most; a selector that
   passes 7 but fails 8 is a noise-chaser.
9. Delayed rewards: selection never blocks on open trades; a reward applied late lands on the
   correct cell.
10. Every selection is auditable: posterior mean, variance, effective sample count, and whether it
    was forced exploration.

## Verification

Property/statistical tests for all ten, with an injected RNG for determinism.
**Rule J** applies throughout — this is pure decision logic over injected reward streams, so it is
fully verifiable without the market. ⛔ **The Rule-F pass (real closed trades feeding real
posteriors) remains an OPEN BLOCKER** until B18 is integrated at the entry sites AND enough index
trades exist — which itself waits on B16's real-data deploy.

## Explicitly NOT in this slice (Rule K)

Entry-site integration (SPEC step 6), the `arm_selector` dashboard surface (step 7), the arms
themselves (step 2), and the liquidity guard (step 3). This slice is the selector and its memory —
an orphan until step 6, with that consumer named here.
