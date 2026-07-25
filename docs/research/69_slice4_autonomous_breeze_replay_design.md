# Research/69 — §53 Slice 4 task #7: autonomous unattended Breeze 1s replay (design)

**Rule D design doc.** P4a-wire made the loop able to run on Breeze 1-second bars
when a `HighFidelityReplayConfig` is injected. Task #6 added the daily session-token
store + the ICICI stock-code resolver. This slice makes the always-on service
**self-activate** 1s replay unattended: on start, if a valid stored Breeze token
exists, build the config itself (rate-limit-aware focus) — else fall back to the
stored-5m replay. No behaviour change until the user has set a token.

## Constraints (Rule I honesty)
- **Rate limit 5000 calls/day.** A 1-second full session ≈ ⌈22500s / (1000×1s)⌉ =
  **23 chunked calls per instrument**, so ≤ ~217 instrument-sessions/day. The focus
  set MUST be capped to the budget — never the full ~2000 universe. This is the
  core new logic (a pure planner), verifiable offline.
- **No headless login.** Autonomy is bounded by the daily manual token (task #6);
  when it expires the service silently reverts to store-5m until refreshed.

## The build
1. `paper_trading/breeze_replay_focus_planner.py` (pure, fully testable):
   - `chunks_per_instrument_for(bar_interval, session_trading_seconds)` = the ≤1000-
     candle windows a session needs.
   - `plan_breeze_replay_focus(candidate_instruments, daily_call_budget,
     bar_interval, session_trading_seconds) -> list[Instrument]` = the budget-capped
     focus (candidates truncated to `budget // chunks_per_instrument`). Logs nothing
     silently — the caller surfaces how many were dropped.
2. Service self-activation (in the `dashboard` feature — already imports
   `broker_sessions`, so NO new graph edge):
   - Constructor DI seams (default real): `breeze_session_token_store`,
     `breeze_historical_source_builder`, `autonomous_breeze_replay_call_budget=5000`.
   - `_maybe_activate_autonomous_breeze_replay()` (called in `start()` only when no
     explicit `high_fidelity_replay` was injected): load a still-valid token → build
     an authenticated Breeze source (client via #6a builder + #6b resolver) → pick
     `session_date` = `HistoricalTradingDayWalker.most_recent_trading_day_on_or_before
     (yesterday)` → `plan_breeze_replay_focus(cash_universe, budget, SECOND_1)` →
     set `self._high_fidelity_replay`. **Best-effort**: any failure (no token, no
     creds, network) leaves it None → the store-5m path (never breaks startup).

## Verification
- **Hermetic (Rule J):** planner budget math (5000/1s → 23 chunks → ≤217 focus;
  small budget → fewer; empty candidates → empty). Service activation with an
  injected fake token store + fake source builder: a valid token activates a
  capped-focus config; no/expired token leaves it None (store path).
- **Real data (Rule F):** store today's real token (#6a CLI), run the activation,
  assert it self-builds a `HighFidelityReplayConfig` whose feed serves real Breeze
  1-second bars for the focus set.

## Backlog (Rule K)
Focus SELECTION is currently "first N of the cash universe (budget-capped)" — a
liquidity/interest-ranked focus (trade the names the loop actually watches) is a
refinement, tracked. P4b (live-depth recorder) remains the other open Slice-4 arm.
