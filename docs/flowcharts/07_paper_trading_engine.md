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

## §9 Prediction-labeled trade-tables lab (added 2026-07-23)
The EPISTEMICS trunk's first ignition (PLAN §9). Every paper trade
declares an immutable prediction BEFORE it opens; reality grades it.
```
src/nse_algo_trader/paper_trading/prediction_lab/
├── prediction_record.py                        # immutable TradePredictionRecord (+enums)
├── adx_confidence_prediction.py                # ADX -> win-prob -> table + mechanism
├── prediction_outcome_grading.py               # grade vs realized P&L; Brier
├── prediction_table_scoreboard.py              # per-table hit-rate/win-rate/Brier
└── opening_range_breakout_prediction_lab.py    # wires lab onto the paper engine
tests/test_paper_trading/test_prediction_lab.py # 13 tests
```
- `TradePredictionRecord` (immutable): predicted_outcome, win_probability,
  assigned_table (CONFIDENT_WIN / CONFIDENT_LOSS / UNCERTAIN),
  expected_reward_multiple, named reasons, mechanism_name,
  predicted_exit_cause, kill_criteria, calendar_context. Post-init
  enforces label↔outcome consistency (CONFIDENT_LOSS must predict LOSS).
- v1 confidence = logistic of ADX around the 20/25 regime band:
  trending→CONFIDENT_WIN (trend-continuation), range-bound→CONFIDENT_LOSS
  (deliberate loss, mechanism = false-breakout-into-chop), mid→UNCERTAIN.
- `grade_prediction` — a CONFIDENT_LOSS prediction is CORRECT when the
  trade actually loses; Brier scores calibration separately.
- `run_orb_prediction_lab_over_replay` — the batch driver; the runtime
  consumer wiring strategy→engine→prediction→grading→scoreboard. Named
  future consumer of the continuous paper loop + Layer 9 dashboard.

### The lab caught a real bug on its first run (Rule F working)
First real run: ALL 17 trades landed in CONFIDENT_LOSS with mean
predicted win-prob 0.03 yet 82% actually won (Brier 0.798). Cause:
intraday ADX at an early breakout bar is un-warmed (needs ~2*period
bars). **Fix:** compute ADX over the CONTINUOUS multi-session stream and
read it at the breakout (warmed, no lookahead) — `run_orb_prediction_lab_
over_replay`. This is the self-correcting loop working on day one.

### Rule F verification (real data, after the fix)
22 real INFY sessions: CONFIDENT_WIN 12 trades, predicted 0.91 / actual
0.92 win (Brier 0.087 — well-calibrated); CONFIDENT_LOSS 4 trades,
predicted 0.29 / actual 0.50 win (Brier 0.290); UNCERTAIN 1. Core check
CONFIDENT_WIN > CONFIDENT_LOSS win-rate = True.
**HONEST CAVEATS:** (1) tiny n (17, one symbol, one month) — a
directional signal, NOT statistical proof; (2) the CONFIDENT_LOSS
table's 50% actual win-rate means the "false breakout in low ADX"
mechanism only half-held here — a real finding to investigate, not
hidden; (3) no slippage/costs, no DSR/CPCV gate yet. The win-side
confidence is well-calibrated; the loss-side mechanism needs work.

## Realistic fill slippage/spread model (added 2026-07-23, PLAN §1.2)
The gap every existing paper engine leaves unmodeled.
```
src/nse_algo_trader/paper_trading/fill_slippage_model.py
tests/test_paper_trading/test_fill_slippage_model.py   # 8 tests
```
- `estimate_slipped_fill_price(order_intent, reference_price, config)` —
  taker pays: buys fill above / sells below by a half-spread. Cash ~3 bps;
  options ~50 bps near-ATM, PLUS +10% of premium for cheap (<=Rs.10)
  far-OTM strikes (a Rs.2 option → ~10.5% half-spread), floored at half a
  tick, never below one tick.
- `make_slippage_fill_adjuster(config)` — wires the model into
  `SimulatedBrokerClient.fill_price_adjuster` (the reserved hook). This is
  the concrete consumer that makes paper fills stop being frictionless.
- **Rule F (real data):** ran the §9 lab over 22 real INFY sessions with
  vs without slippage — frictionless Rs.79,111 → with 3bps/side slippage
  Rs.72,274 (cost Rs.6,837 over 17 cash trades); CONFIDENT_WIN calibration
  unchanged (Brier 0.087). Honest cost of trading now modeled; option
  slippage will bite far harder once the credit-spread paper path exists.
