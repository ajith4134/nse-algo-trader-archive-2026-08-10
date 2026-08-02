# Layer 7.5 Slice 3 — Per-trade pre-mortem (entry-time Monte Carlo via the replay store)

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 7.5 slice 3 (BACKLOG). Read-only
diagnostic; the entry-site decision-consumer (size/defer on CVaR) stays queued.

## 1. Goal (research/95 queued list)
A pre-mortem = before committing, imagine the trade has FAILED and quantify how. At entry-time, run
a MONTE CARLO over REAL historical post-trigger intraday paths (from the replay store) to estimate
the trade's outcome DISTRIBUTION: P(hit target), P(hit stop), P(neither→timeout), expected return,
and the tail (CVaR of the worst 5%). So the bot has a probabilistic pre-mortem, not just a point
thesis, before it acts.

## 2. Why real paths, not a parametric model
Intraday moves are fat-tailed and autocorrelated; a Gaussian MC would understate the tail. Instead
we resample WHOLE real post-trigger close-return sequences from the replay sessions — each is one
faithful path (preserving intraday shape) — and evaluate the current stop/target against each. The
tail (CVaR) then reflects the real historical downside, which is the whole point of a pre-mortem.

## 3. Components (Rule C)
`paper_trading/per_trade_pre_mortem.py` (PURE):
- `extract_post_trigger_return_paths(sessions, config) -> list[list[float]]` — for each real
  session with an ORB signal, the per-bar CLOSE returns AFTER the trigger (one empirical path).
- `PreMortemForecast(trials, probability_target, probability_stop, probability_timeout,
  mean_return, conditional_value_at_risk_5pct, worst_case_return, verdict)`.
- `run_entry_pre_mortem(entry_price, stop_loss_price, target_price, direction, return_paths,
  trials, seed) -> PreMortemForecast` — bootstrap-resample `trials` paths (seeded), walk each
  close-path from `entry_price`, exit at the first stop/target touch (stop checked first —
  conservative, matching the real backtester) else at the path end; aggregate the realized-return
  distribution → probabilities + mean + CVaR-5% (mean of the worst 5%) + worst case + a verdict.
- (Approximation, documented: close-path touches, not intrabar high/low — a distributional
  estimate, not an exact fill model; the real fills use high/low in the backtester.)

## 4. Wiring (Rule G) + cadence
- Service `_maybe_run_pre_mortem(now)` (daily): load the stored sessions, extract the empirical
  paths, run a pre-mortem on a CANONICAL setup at the champion RR (entry 100, 1% risk → stop 99,
  target 100+RR·1) — a config-level pre-mortem stable enough to surface — caching
  `_latest_pre_mortem`. Best-effort.
- Dashboard surface `per_trade_pre_mortem` (Rule N): P(target)/P(stop), mean return, CVaR-5%,
  worst case, verdict.

## 5. Advisory → decision-consumer (QUEUED, Rule K)
Read-only. The consumer that runs the pre-mortem at each ENTRY SITE on the real candidate setup and
sizes-down / defers when the CVaR tail is too deep (calibration-gated, reusing the slice-2c
earn-harness discipline) is the queued follow-up. Precomputing per-mechanism CVaR daily keeps the
hot path fast (like the debate-risk gate).

## 6. Verification
- Hermetic (Rule J): synthetic paths that deterministically hit target / stop / timeout → assert
  the probabilities, mean, CVaR, worst case, and seeded reproducibility; empty-paths guard.
- Real-data (Rule F): over the REAL stored sessions extract paths + run the canonical pre-mortem →
  a real outcome distribution + CVaR. `scripts/verify_per_trade_pre_mortem_realdata.py`.

## 7. Open items (Rule K)
- 🔵 Entry-site decision-consumer: per-mechanism CVaR precomputed daily → size/defer at the 4 entry
  sites, calibration-gated.
- 🔵 Slice 4 — world-model scoreboard (trade-independent forecasts) + profit provenance.
