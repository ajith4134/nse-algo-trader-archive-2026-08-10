# research/95 — Control arms, slice 1: RANDOM-CONTROL baseline (Layer 7.5 #7)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD. First of the Layer-7.5 advanced-lab tier (control arms →
skill-vs-luck court → per-trade pre-mortem → world-model scoreboard → profit provenance).
User: build all four in order; this is control arms, slice 1 (RANDOM-CONTROL).

## Why
A strategy's positive P&L means nothing without a baseline: is the edge SKILL or LUCK? The
RANDOM-CONTROL arm answers it — run the SAME entry triggers with a RANDOM direction, over the
same real sessions, and compare. If the real strategy's win-rate/return/Sharpe is NOT above
the random-control baseline, the "edge" is noise. (SHADOW-REJECTED — what the gate refused —
is slice 2; skill-vs-luck court is the verdict layer over both.)

## Sourcing
Build-from-scratch (project-specific lab logic over our own ORB backtester — no external lib
fits). Reuses `paper_trading.replay_session_orb_backtester` (real arm) + `strategy_promotion_
gate.compute_sharpe_ratio`. The existing `shadow_probe_counter` is an antibody-RECOVERY probe,
not a control arm — separate concept, not reused.

## Design
1. **`control_arm_backtester`** (paper_trading, PURE): reuse the ORB entry TRIGGER but take a
   RANDOM direction (seeded coin-flip, seed from the session date for reproducibility),
   recompute stop/target symmetrically, simulate the exit exactly like the real backtester.
   `backtest_random_control_session_return(bars, instrument, config, seed) -> float | None`.
   This isolates directional skill: same when-to-enter, random which-way.
2. **`control_arm_comparison`** (paper_trading, PURE): over a set of real sessions, score the
   REAL arm (champion ORB) and the RANDOM-CONTROL arm → per-arm (trades, hit_rate, mean_return,
   total_return, sharpe) + an **edge verdict**: `has_edge = real.sharpe > random.sharpe` AND
   `real.hit_rate > random.hit_rate` (a conservative both-must-agree read; on thin data it just
   reports "gathering"). `compare_control_arms(sessions, champion_config, seed) ->
   ControlArmComparison`.
3. **Surface (Rule G/N):** a feature-registry row "Skill-vs-luck control (RANDOM-CONTROL)"
   showing real-vs-random hit-rate/return + the edge verdict, computed over the stored sessions.

## Real-data verification (Rule F)
Over the 22 real stored sessions: score real ORB vs random-control, print both arms + the
verdict. Assert the comparison runs and both arms produce valid stats in range. (On this data
the real strategy is losing — so the honest expected verdict is "no demonstrated edge vs
random," which is exactly the scientific value of the arm.)

## Queued (Rule K) — the rest of control arms + the 3 following features
- SHADOW-REJECTED arm (what the gate vetoed/deferred would have done) — slice 2.
- Skill-vs-Luck Court (verdict pipeline; learning trains on the skill diagonal only).
- Per-trade pre-mortem (entry-time Monte Carlo via replay store).
- World-model scoreboard (trade-independent forecasts).
- Profit provenance (P&L decomposition vs the control arms).

## Files
- `src/nse_algo_trader/paper_trading/control_arm_backtester.py`
- `src/nse_algo_trader/paper_trading/control_arm_comparison.py`
- feature-surface row + manifest entry
- `tests/test_paper_trading/test_control_arm_comparison.py`
- `scripts/verify_control_arms_realdata.py`

## Rule check
- **Rule F/J:** hermetic (seeded, deterministic) + real-session pass.
- **Rule G/N:** surfaced on the dashboard (real consumer). The learning-consumer (skill-vs-luck
  court feeding what memory trains on) is a queued follow-up.
- **Rule A:** one slice (RANDOM-CONTROL); the other 3 features + shadow-rejected queued.
