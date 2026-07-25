# research/88 — Slice 5c-i.b: scheduled auto-re-evaluation of champion-challenger

**Date:** 2026-07-25
**Status:** DESIGN + BUILD (this turn). Completes 5c-i's autonomy (research/87 queued item).
**Rule K:** the champion-challenger evaluator + store + live-read exist, but nothing RUNS
the tournament on a schedule — so promotions never happen autonomously. This wires that.

## Design
- **`champion_challenger_reevaluation_scheduler`** (pure): `is_reevaluation_due(
  last_run_date, today) -> bool` (due when never run or the run-date rolled over — i.e. at
  most once per calendar day). Holds `DEFAULT_ORB_CHALLENGER_GRID` — a modest fixed grid of
  `OpeningRangeBreakoutConfig` variants (opening-range minutes × R:R × latest-entry). Kept
  small so the Deflated-Sharpe multiple-testing deflation stays sane.
- **Service `_maybe_reevaluate_champion_challenger(now)`** (best-effort): if due today,
  load the real stored benchmark sessions, run `evaluate_champion_vs_challengers(current
  champion, grid, sessions)`; if a challenger is PROMOTED, `save_champion` + refresh the
  live `_champion_orb_config_cache` (so the loop immediately trades the new config) + log;
  set last-run = today. Below a minimum session count it just marks the day done. Wrapped
  so a failure never disturbs the loop.
- **Wiring (Rule G):** called once per pass inside `_run_forever` (after the memory drain,
  before publish); the scheduler makes it actually execute ~once/day. In-memory last-run
  date → re-runs once per process start (harmless: idempotent, promotes only through the
  conservative gate).

## Real-data verification (Rule F)
On a constructed service (real store), call `_maybe_reevaluate_champion_challenger` twice
same-day: first runs the tournament over the 23 real sessions and (thin evidence) keeps the
champion; second is a no-op (scheduler gate). Confirms it runs on real data, is idempotent,
and leaves the champion store consistent.

## Queued (Rule K)
- Options/credit-spread configs in the grid (needs option-chain replay) — still open.
- Per-market-regime champion (a champion PER regime, chosen with 5b's regime tag) — a
  natural future extension once regime variety accrues.

## Files
- `src/nse_algo_trader/paper_trading/champion_challenger_reevaluation_scheduler.py`
- edits to `dashboard/live_paper_trading_service.py` (trigger + wiring + DI seams)
- `tests/test_paper_trading/test_champion_challenger_reevaluation_scheduler.py`
- `scripts/verify_champion_challenger_autoreeval_realdata.py`

## Rule check
- **Rule G/K:** the tournament now RUNS autonomously and updates the live champion — 5c-i's
  autonomy is closed; remaining grid extensions are queued.
- **Rule F/J:** hermetic scheduler + promotion tests; a real-data idempotent re-eval pass.
- **Rule I/C:** reuses the 5c-i evaluator + store; self-describing names.
- **Rule A:** one slice (the scheduler + wiring).
