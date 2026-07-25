# research/87 — Slice 5c-i: champion-challenger over ORB configs (ADVANCED tier §53)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD (this turn). Second ADVANCED-tier piece (after 5a/5b).
**PLAN ref:** research/62 §4 slice 5 ("parallel multi-day → champion-challenger");
Layer-7 promotion gates (Deflated Sharpe / CPCV) are the significance machinery to reuse.

## Idea
Instead of one fixed strategy configuration forever, evaluate the incumbent **champion**
config against **challenger** configs over a shared set of real replay sessions, and
promote a challenger only if it beats the champion under a **multiple-testing-aware
significance gate** (so we never promote on noise / overfitting). The curriculum (5a)
supplies regime-diverse sessions to evaluate over.

## Sourcing verdict (Rule I — reuse, don't reinvent)
Both halves already exist in the repo:
- `strategy_engine.opening_range_breakout_strategy.detect_opening_range_breakout` +
  `OpeningRangeBreakoutConfig` — the strategy + its tunable knobs (opening-range minutes,
  target R:R, latest entry).
- `paper_trading.strategy_promotion_gate.evaluate_strategy_for_promotion` — Deflated-Sharpe
  gate (`number_of_strategy_trials` = configs tried, `sharpe_std_across_trials` = the
  multiple-testing penalty). This IS the champion-challenger significance test.
BUILD only the thin glue: a per-session ORB backtester + a scorecard + the tournament.

## Design — 5c-i (this slice)
1. **`replay_session_orb_backtester`** (pure): `backtest_orb_session_return(session_bars,
   instrument, config) -> float | None`. Detect the ORB signal on one session's REAL bars;
   if none → None (no trade that session). Else simulate deterministically: after the
   trigger bar, walk bars — LONG wins if `high ≥ target`, loses if `low ≤ stop` (stop
   checked first within a bar = conservative); SHORT mirrored; neither hit → exit at the
   session's last close. Return the signed realized return fraction.
2. **`champion_challenger_orb_evaluator`** (pure): `ConfigurationScorecard`
   (per_session_returns, sessions_traded, hit_rate, total_return, sharpe via the gate's
   `compute_sharpe_ratio`); `score_orb_configuration(config, sessions)`; and
   `evaluate_champion_vs_challengers(champion_config, challenger_configs, sessions) ->
   ChampionChallengerDecision` — score all, take the highest-Sharpe config, and run the
   Deflated-Sharpe gate on it with `number_of_strategy_trials = N configs` and
   `sharpe_std_across_trials = std(all config sharpes)`. Promote a challenger ONLY if it is
   the winner AND the gate says PROMOTE; otherwise keep the champion.
3. **`champion_configuration_store`** (json file): persist the current champion
   `OpeningRangeBreakoutConfig` so a promotion survives restarts.
4. **Wiring (Rule G, live purpose-consumer):** the service reads the champion config from
   the store (`_champion_orb_config`, fallback = default) and passes it as
   `run_live_universe_scan_pass(strategy_config=…)`. So a promoted config actually drives
   live/replay ORB decisions — not display-only.

## Real-data verification (Rule F)
Over the 22 real stored INFY sessions: score the champion (default config) vs a few
challengers (varied opening-range minutes / R:R), print each scorecard, and show the gate's
decision. Expected on THIN evidence (few ORB triggers across 22 sessions): the conservative
Deflated-Sharpe gate KEEPS the champion (min-trades / DSR not met) — verifying the
overfitting-safety property on real data. Promotions become possible as the 5a curriculum
replays more sessions and trade count accrues.

## What this slice does NOT do (queued — Rule K)
- **Autonomous periodic re-evaluation in the loop** (run the tournament every N sessions and
  auto-update the champion store) — this slice provides the evaluator + store + live
  consumption of the champion; the scheduled re-eval trigger is queued.
- **Credit-spread / options configs** in the tournament (needs option-chain replay data) —
  ORB (cash) only for now.
- Broader ADVANCED items (OFI/VPIN depth features, queue/impact fills) — later slices.

## Files
- `src/nse_algo_trader/paper_trading/replay_session_orb_backtester.py`
- `src/nse_algo_trader/paper_trading/champion_challenger_orb_evaluator.py`
- `src/nse_algo_trader/paper_trading/champion_configuration_store.py`
- edits to `dashboard/live_paper_trading_service.py` (read champion → pass to the scan pass)
- `tests/test_paper_trading/test_replay_session_orb_backtester.py`
- `tests/test_paper_trading/test_champion_challenger_orb_evaluator.py`
- `scripts/verify_champion_challenger_realdata.py`

## Rule check
- **Rule I/C:** reuses the ORB strategy + Deflated-Sharpe gate; self-describing names.
- **Rule F/J:** hermetic tests for backtester + evaluator + store; a real-data tournament
  over 22 real sessions (conservative-keep property verified).
- **Rule G/K:** champion config is consumed by the live scan pass (not display-only); the
  scheduled auto-re-eval trigger is queued in BACKLOG.
- **Rule A:** one slice (evaluator + store + live consumption); auto-re-eval + options
  configs are separate.
