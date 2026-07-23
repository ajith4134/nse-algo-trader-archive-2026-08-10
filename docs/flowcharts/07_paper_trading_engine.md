# 07 — Backtesting & Paper Trading (Layer 7)

**Status:** IN PROGRESS. Foundation built — the MarketClock-gated
DataSourceRouter (24/7 replay↔live, PLAN §1.4) — tested + Rule-F
real-data verified. Remaining Layer 7 scope listed at the bottom.

## Why this layer is special
Per the AI integration map, **Layer 7 is where 5 trunks first ignite**:
EPISTEMICS (the calibration lab), PREDICTIVE CORE (replay = proto world-
model), MEMORY (PredictionRecords = proto episodic memory), CONSCIENCE
(Referee + Constitutional Core), plus CURIOSITY/SELF seeds. It is also
an **always-on service** (never stops, even after live trading starts),
not just a pre-live gate.

## Whole-pipeline data flow so far
```
[L1 Universe]->[L2 Market Data + SQLite store]->[L3 Indicators]->[L4 Signals]->[L5 Risk]->[L6 OMS]
                          │ real stored bars
                          v
[Layer 7: paper_trading/]  — FOUNDATION (built)
   NseMarketClock  (the only authority on "is NSE open?": 09:15-15:30 IST,
     Mon-Fri, minus injected real holidays)
        │  is_market_open(at)
        v
   MarketClockGatedDataSourceRouter
     current_data_mode(at) -> REPLAY | LIVE
     next_bars(at) -> one interface; consumers never learn the source
        ├─ closed (or no live source yet) -> HistoricalBarReplaySource
        │     .stream_bars(loop_forever) — real stored bars in time order,
        │     loops so the learning loop never idles
        └─ open + live source -> live feed (KiteTicker; wired when a real
              open session + Layer 6 auth exist — Rule F blocker)
        │
        v
   (next: paper engine consumes next_bars(); prediction-labeled tables
    lab (§9) + slippage model build on top)
```

## Files (this slice)
```
src/nse_algo_trader/paper_trading/
├── __init__.py
├── nse_market_clock.py                        # NseMarketClock
├── historical_bar_replay_source.py            # HistoricalBarReplaySource
└── market_clock_gated_data_source_router.py   # router + DataSourceMode
tests/test_paper_trading/test_market_clock_and_router.py   # 13 tests
```

## Exports
- `NseMarketClock(trading_holiday_dates)` — `is_trading_day`,
  `is_market_open(at)`, `next_session_open(at)`, `next_session_close(at)`;
  naive datetimes treated as IST. Holidays injected (real NSE list loaded
  from data per Rule F; wiring the live holiday feed is a TODO).
- `HistoricalBarReplaySource(store, tokens, interval, from?, to?)` —
  `load_chronological_bars()`, `stream_bars(loop_forever, on_bar_emitted)`;
  merges multiple instruments into one time-ordered stream.
- `MarketClockGatedDataSourceRouter(clock, replay, live_bar_source=None)`
  — `DataSourceMode` REPLAY/LIVE, `current_data_mode(at)`, `next_bars(at)`.

## Verification (Rule F — real data, 2026-07-23)
- 13 unit tests (160 suite total, green).
- **Real-data pass:** MarketClock matched the real NSE calendar (Wed
  2026-07-22 open 09:15-15:30, Sat/Sun closed, next-open from Fri = Mon
  09:15). Replay source streamed the **real 1,650 stored INFY 5-min
  bars** (2026-06-22..07-22) in verified chronological order; router
  correctly served REPLAY while NSE is closed and yielded the real first
  bar (close 1066.2 @ 09:15).

## Remaining Layer 7 scope (next slices)
1. **Paper engine** consuming `next_bars()` — drives L4 signals through
   L5 risk into the L6 `SimulatedBrokerClient`, tracking a paper ledger.
2. **Prediction-labeled trade tables lab (PLAN §9/§10, queue items 1-6):**
   CONFIDENT-WIN / CONFIDENT-LOSS / UNCERTAIN tables, immutable
   PredictionRecord (outcome, win-prob, expected R, reasons, mechanism,
   kill-criteria), calendar partition key, per-table scoreboard
   (hit-rate + Brier), Referee v0.
3. **Realistic options slippage/spread model** (PLAN §1.2) via the
   `SimulatedBrokerClient.fill_price_adjuster` hook.
4. **Live-feed handoff** verified during a real open session (Rule F
   blocker until market hours + KiteTicker auth).
5. **Deflated-Sharpe / CPCV promotion gate** (PLAN §5) for strategies.

## Paper engine slice (loop-closing, added 2026-07-23)
```
src/nse_algo_trader/paper_trading/
├── paper_trading_ledger.py                     # PaperTradingLedger (avg-cost P&L)
└── opening_range_breakout_paper_engine.py      # the L4->L5->L6->ledger loop
tests/test_paper_trading/test_paper_ledger_and_engine.py   # 9 tests
```
- `PaperTradingLedger(starting_virtual_cash)` — `record_fill`,
  `net_quantity`, `is_flat`, `unrealized_pnl`, `total_pnl`; average-cost
  realized P&L; purely virtual money.
- `run_opening_range_breakout_paper_session(session_bars, instrument,
  simulated_broker, risk_budget, ledger)` -> `PaperSessionResult`
  (outcome NO_SIGNAL/RISK_REJECTED/EXITED_TARGET/EXITED_STOP/
  SQUARED_OFF_AT_CLOSE). Enters at the breakout close, manages intraday
  stop/target, hard square-off at session end (no overnight).
- `group_bars_into_sessions(bars)` — splits the replay stream by date.
- **This closes the Rule-G loop**: it is the runtime consumer that wires
  Layer 4 (signal) -> Layer 5 (risk gate) -> Layer 6
  (SimulatedBrokerClient) -> the ledger, driven by Layer 7's replayed
  real bars. L4/L5/L6 are no longer "awaiting consumer."

### Rule F verification (real data, 2026-07-23)
Ran the engine over the router's REPLAY of the real 1,650 INFY 5-min
bars (22 real sessions): 17 paper trades (14 up / 3 down), 2 hit target,
15 squared off at close, 5 no-signal; ledger flat at every session end
(no overnight); realized P&L tracked end-to-end.
**HONESTY CAVEAT (not a validated edge):** the raw month P&L is
one-symbol, one-month, with NO slippage/costs modeled and NO
walk-forward / Deflated-Sharpe / CPCV gate (PLAN §5) — those gates are
later Layer 7 slices. What is verified here is that the PIPELINE runs
correctly on real data, not that ORB is profitable. No strategy touches
live capital before clearing the promotion ladder.

### Cash-side ORB path scope
This slice is the directional cash ORB path. The credit-spread paper
path needs intraday option bars (store holds EOD bhavcopy only) — a
later slice. The prediction-labeled tables lab (PLAN §9) attaches on top
of this engine next.
