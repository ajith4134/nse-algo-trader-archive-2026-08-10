# research/153 — Trunk XIV AXIOLOGY · explicit utility function + value-drift detection

**Slice:** the first slice of the ABSENT trunk XIV AXIOLOGY (values & practical wisdom; 0🟢 4🟡 8🔴).
Makes the system's OBJECTIVE explicit (it was implicit in `risk_management`) and detects when realized
behaviour drifts from stated values. Fresh trunk after 10 news slices (Rule M anti-tunnel zoom-out).

Moves: **explicit utility function 🟡→🟢** · **value-drift detection 🔴→🟢**.

## Sourcing (Rule I) — build bespoke (portfolio-opt libs are the wrong shape)
Real WebSearch (2026-07-26): **Riskfolio-Lib / skfolio / PyPortfolioOpt** are portfolio-ALLOCATION
optimizers — they solve for asset WEIGHTS that maximize a utility given a returns matrix + a convex
solver. Our need is the opposite: a **scalar utility that SCORES our realized trading outcomes** against
explicit named values (return / risk / drawdown / tail), and a drift monitor — no allocation, no solver.
→ REJECTED as heavy + wrong-shape; the underlying risk measures (mean, volatility, max-drawdown, CVaR-5%)
are standard formulas → **bespoke** stdlib/`scipy` (already a dep; `world_model_scoreboard`/`per_trade_
pre_mortem` already compute CVaR-style measures in-house). Sources logged in BACKLOG.

## Real data (Rule F) — 340 real trades
`experience_memory.sqlite3::experience_nodes` (340 rows) carries `realized_return_fraction`,
`realized_pnl`, `session_date`, `mechanism_name`, `market_regime` — a real realized-return series to
score the utility over and to run drift detection on. (Sample realized_pnl: −626, −879, −957 … real.)

## STEP 1 — Target
- `axiology/explicit_utility_function.py` (PURE): `evaluate_utility(returns, weights) -> UtilityScore`
  — a scalar U with an EXPLICIT, named decomposition:
  `U = w_return·mean − w_risk·volatility − w_drawdown·max_drawdown − w_tail·CVaR5`.
  The `ValueWeights` ARE the system's stated values (previously implicit) — inspectable + adjustable.
- `axiology/value_drift_monitor.py` (PURE): split the return series into an earlier BASELINE window and
  a RECENT window; flag **value drift** when a recent risk component (volatility / drawdown / CVaR)
  exceeds the baseline by a threshold — i.e. the system is taking more risk than its values sanction.
- **Success test (Rule F):** over the real 340 trades, the utility decomposes into named value terms and
  the drift monitor produces an honest verdict (drift / stable) on the real recent-vs-baseline split.

## STEP 2 — Build / wiring
- New `axiology/` package (Trunk XIV): the two PURE modules + `ValueWeights` (default weights encoding
  the project's stated values: capital-preservation-leaning — risk/drawdown/tail weighted).
- Service: `_maybe_run_axiology` cadence reads the realized-return series from the experience memory →
  `explicit_utility` + `value_drift` reports cached; `explicit_utility` + `value_drift` dashboard surfaces.
- **Named future consumers (Rule K):** the explicit utility → the meta-strategy allocator can optimize
  IT (making values drive allocation); value-drift → a value-alignment caution (defer/trim when the
  system drifts from its risk values, like a CONSCIENCE tripwire). Read-only boards until then.

## STEP 3 — Verify
- Hermetic (Rule J): crafted return series → correct utility decomposition + sign; a high-risk recent
  window → drift flagged; a stable series → no drift.
- Real-data (Rule F): compute over the real 340 experience_nodes → real utility decomposition + an
  honest drift verdict.

## Rule K — after this slice (XIV remaining)
value-uncertainty · preference learning (learn the weights from outcomes) · practical wisdom · moral/
regulatory reasoner · assistance-game alignment · corrigibility-as-value · fairness-to-future-self.
Consumers (allocator optimizes utility; value-drift → alignment gate) are QUEUED.
