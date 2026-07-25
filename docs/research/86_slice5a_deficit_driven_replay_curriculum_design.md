# research/86 — Slice 5a: deficit-driven replay CURRICULUM (ADVANCED tier, task #20-adjacent §53)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD (this turn). First ADVANCED-tier (§53 slice 5) sub-slice.
**PLAN ref:** research/62 §4 slice 5 ("deficit-driven curriculum — unblocks the Layer-10
regime queries"); Layer-10 open blocker "multi-regime queries need regime variety".

## Problem / ground truth (Rule F diagnosis)
Today the market-closed replay always picks **the most recent trading day**
(`_maybe_activate_autonomous_*_replay` → `most_recent_trading_day_on_or_before(yesterday)`).
That never deliberately varies the market REGIME it learns from. Measured reality:
- The real memory (`~/.nse_algo_trader/experience_memory.sqlite3`) has **293 experiences,
  ALL `regime_context="normal"`** — `regime_context` is populated from the *calendar*
  context, which is degenerate (one value). This IS the Layer-10 "single-regime" blocker.
- The **ADX market regime** (trending / range_bound / indecisive) is computed by
  `strategy_engine.session_strategy_regime_gate.classify_adx_market_regime` but is **never
  used to steer which day we replay**.
- The bar store has 22 real single-symbol (INFY) 5-minute sessions (2026-06-22…07-22) +
  the full-universe day — enough real sessions to classify into varied regimes.

**Curriculum idea:** replay the day whose market regime we've learned LEAST about, so the
replay stream becomes regime-diverse instead of "yesterday again." This is the enabling
step for the Layer-10 multi-regime queries (which need regime variety to differentiate).

## Sourcing verdict (Rule I / sourcing step)
Reuse, don't reinvent: the classifier is glue over the EXISTING
`indicators.compute_average_directional_index` + `strategy_engine.classify_adx_market_
regime`. No external curriculum-learning library fits (they target ML training loops, not
market-regime replay day-selection). BUILD thin glue.

## Design — 3 parts + wiring
1. **`historical_session_market_regime_classifier`** (paper_trading, PURE):
   `classify_session_market_regime(session_bars) -> MarketRegime` — compute ADX over the
   session's bars, take the last non-None ADX, classify via the existing gate. Reuses the
   real indicator + gate (Rule C/I). Verifiable on the 22 real INFY sessions.
2. **`replayed_session_regime_ledger`** (paper_trading, SQLite own file):
   `record_replayed_session(session_date, regime)` + `covered_regime_counts() -> {regime:int}`.
   Persists curriculum coverage so successive activations ROTATE regimes (without it, every
   activation would re-pick the same rarest-historical day).
3. **`deficit_driven_replay_session_selector`** (paper_trading, PURE):
   `select_deficit_replay_session(classified_candidates: [(date, MarketRegime)],
   covered_regime_counts) -> date | None` — pick the candidate whose regime has the LOWEST
   covered count (the deficit); tie-break most-recent. None when no candidates.
4. **Wiring (Rule G)** into `LivePaperTradingService._maybe_activate_autonomous_multi_
   broker_replay`: build recent candidate trading days (day-walker), classify each from the
   stored benchmark bars (best-effort; skip days with no stored bars), select the deficit
   day as `session_date`, and after building the config **record it** in the ledger. If no
   day can be classified (no stored bars), fall back to most-recent — no regression. Same
   optional hook offered to the Breeze activation later.

## What this slice does NOT do (queued — Rule K)
- **5b — market-regime TAG on experiences** (so `ExperienceMemory`'s regime-aware queries —
  calibration_by_regime, outcome_sequence_dependence, cross-regime co-failure — get real
  variety, finally unblocking the Layer-10 multi-regime queries end-to-end). The curriculum
  (5a) makes the replay stream regime-diverse; 5b captures that regime onto each experience.
  Tracked in BACKLOG. Until 5b, 5a's payoff is a regime-diverse replay schedule + the
  coverage ledger; the memory-side unblock lands in 5b.
- Deeper ADVANCED items (microstructure OFI/VPIN, queue/impact fills, champion-challenger)
  remain later slices (research/62 §3).

## Files
- `src/nse_algo_trader/paper_trading/historical_session_market_regime_classifier.py`
- `src/nse_algo_trader/paper_trading/replayed_session_regime_ledger.py`
- `src/nse_algo_trader/paper_trading/deficit_driven_replay_session_selector.py`
- edits to `dashboard/live_paper_trading_service.py` (wire the selector + ledger)
- `tests/test_paper_trading/test_historical_session_market_regime_classifier.py`
- `tests/test_paper_trading/test_deficit_driven_replay_session_selector.py`
- `scripts/verify_replay_curriculum_realdata.py` (classify the 22 real INFY sessions;
  assert regime variety + the selector picks a deficit regime)

## Rule check
- **Rule F/J:** hermetic tests for classifier + selector + ledger; a real-data pass over
  the 22 real stored sessions (regime variety observed, deficit pick correct).
- **Rule G/K:** the selector is wired into the loop's replay day-selection (not display-
  only); the experience-tag consumer (5b) is queued in BACKLOG, surfaced at sign-off.
- **Rule I/C:** reuses the real ADX indicator + regime gate; self-describing names.
- **Rule A:** one slice (the curriculum brain + its loop wiring); 5b and deeper ADVANCED
  items are separate.
