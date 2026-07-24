# 08 — Session / Square-off Management (Layer 8)

**Status:** core built (v1), Rule-F verified. The safety-critical layer:
enforces the no-overnight non-negotiable and the never-a-naked-leg rule.

## Whole-pipeline data flow so far
```
[L1..L6] -> [L7 paper engine / lab]  positions open during a session
                                          │  open position legs
                                          v
[Layer 8: session_management/]
   IntradaySquareOffSchedule
     should_force_square_off_now(at, market_clock)  (default 15:15 IST window
       before the 15:30 close; NseMarketClock is the authority)
        │  when True
        v
   build_square_off_order_intents(open_legs)
     -> exit intents, SAFE-ORDERED: every BUY-to-cover (removes short risk)
        before every SELL-to-close (removes hedge). A credit spread covers
        its short leg before selling its protective hedge — no naked leg,
        not for one tick (research/07 §D.4).
        │
        v
   execute_intraday_square_off(open_legs, broker, config)
     drive-to-flat with RETRIES (never unwind); any leg still open after
     max_attempts -> SquareOffReport.unflattened_legs (CRITICAL, surfaced)
     -> (consumed by the paper loop now, the live loop later)
```

## Files
```
src/nse_algo_trader/session_management/
├── __init__.py
├── intraday_square_off_schedule.py      # WHEN to force square-off
└── intraday_square_off_executor.py      # HOW: safe order + retry-to-flat
tests/test_session_management/test_square_off.py   # 12 tests
```

## Exports
- `IntradaySquareOffSchedule(forced_square_off_time_ist=15:15)` —
  `should_force_square_off_now(at, market_clock)`.
- `OpenPositionLeg(instrument, net_quantity, strategy_tag)`.
- `build_square_off_order_intents(open_legs)` — opposite-side exits,
  BUY-to-cover ordered before SELL-to-close.
- `execute_intraday_square_off(open_legs, broker, config)` ->
  `SquareOffReport(all_positions_flat, leg_outcomes, unflattened_legs)`;
  `SquareOffConfig(max_attempts_per_leg=3)`.

## Verification (Rule F — real data, 2026-07-23)
- 12 tests (209 suite total, green), incl. the PLAN §5 Layer-8 mandate:
  a broker outage right at square-off is RETRIED until flat; a persistent
  failure is reported as unflattened (never silently dropped).
- **Real-data pass:** schedule matched the real NSE calendar (Wed 15:20
  force, Wed 11:00 / Sat no). Over 22 real INFY sessions the engine left
  **0 positions open overnight**. Under an injected broker drop, a real
  credit-spread squared off with the short leg BUY-to-covered FIRST, then
  the hedge sold — never a naked leg — and reached flat after retries.

## Remaining slices
- Wire into a continuous session loop that polls the schedule and pulls
  open legs from the live/paper ledger automatically.
- Live-broker OPEN-state polling: for `KiteBrokerClient`, a submitted
  square-off is OPEN until filled — poll to COMPLETE / re-fire on timeout
  (v1 treats accepted-not-rejected as flattening; paper fills instantly).

## Wired into the live loop (2026-07-24) — Rule G closed
**Correction:** earlier this note said the executor was "consumed by the
paper loop now." That was inaccurate — before 2026-07-24 nothing runnable
called `execute_intraday_square_off`; the replay paper engine did its own
inline single-leg close. Layer 8 is now genuinely wired:
`paper_trading/live_universe_paper_loop.square_off_all_open_positions`
builds an `OpenPositionLeg` per held position and calls
`execute_intraday_square_off` (safe-ordered, retry-to-flat) when the
`IntradaySquareOffSchedule` fires at 15:15 IST during a scan pass.
**Rule-F/unit verified:** `test_live_universe_paper_loop.py::TestForcedSquareOff`
opens a live position then runs a scan pass at 15:20 -> squared_off_at_close,
0 open, ledger flat (no overnight carry, ever). This is the real consumer
that closes the Rule-G orphan.
