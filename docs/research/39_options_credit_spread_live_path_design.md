# 39 — Options Credit-Spread Live Path: Design (2026-07-24)

## Why
The layer cross-verification (2026-07-24, market open) confirmed the entire
options path is built-but-ORPHANED (Rule G): L3 IV→IV-Rank→PCR pipeline,
L4 `select_credit_spread_legs` + the ADX regime gate
(`choose_v1_session_strategy`), and L6 `atomic_multi_leg_executor` +
`build_order_intents_for_credit_spread` have zero non-test callers. The
live loop trades only cash ORB unconditionally. This wires the options path
into the running live paper loop, un-orphaning all three.

## Routing (faithful to L4 doc)
`choose_v1_session_strategy(adx)` per underlying:
- ADX ≥ 25 (TRENDING) → ORB (the cash path already covers directional).
- ADX ≤ 20 (RANGE_BOUND) → **credit spread** (this path).
- between → STAND ASIDE.
Credit spreads are the range-bound play: sell premium with a defined-risk
hedge. Bias from the underlying's intraday drift: mild-up → BULL_PUT
(sell put spread), mild-down → BEAR_CALL (sell call spread).

## Per-underlying pipeline (215 underlyings: 5 index + 210 stock)
1. Resolve the underlying's SPOT instrument for bars/ADX: stock → its cash
   equity; index → a bar-fetch carrier Instrument built from the NSE
   INDICES master token (NIFTY→256265, BANKNIFTY→260105, FINNIFTY→257801,
   NIFTYNXT50→270857, MIDCPNIFTY→288009).
2. `recent_intraday_bars(spot)` → ADX (warmed over the multi-day window).
   Gate: only RANGE_BOUND underlyings proceed.
3. ATM IV via L3 `compute_implied_volatility` (BS inversion) on a real ATM
   option LTP → un-orphans the IV pipeline.
4. `select_credit_spread_legs(ladder, underlying, spot, atm_iv, bias, date)`
   → `CreditSpreadSignal` (short leg + defined-risk hedge).
5. `evaluate_credit_spread_signal(signal, risk_budget)` → defined-risk-only
   gate (L5). Rejected (undefined/naked/insufficient) → skip.
6. Open via `build_order_intents_for_credit_spread` +
   `execute_multi_leg_order_atomically` (hedge BUY first) on the sim broker
   with real leg LTPs → un-orphans the atomic executor. Record net credit.

## Open-position model
`OpenOptionSpreadPosition` (2 legs): underlying, bias, short/hedge
Instruments, lots, lot_size, entry net credit, opened_at, strategy_tag,
assigned_table. Tracked in `LiveUniversePaperState.open_option_spreads`
keyed by underlying (one spread per underlying at a time).

Mark/unrealized each pass from both legs' live LTP: a credit spread profits
as net premium decays — `unrealized = (entry_net_credit − current_net_premium)
× lots × lot_size`. Exit: capture-target (e.g. 50% of credit) or stop
(net premium ~2× credit), else hold to 15:15.

## Square-off (L8, already multi-leg-safe)
At 15:15 build an `OpenPositionLeg` per spread leg and call
`execute_intraday_square_off` — BUY-to-cover the short before selling the
hedge, never a naked leg. Same path the cash positions use.

## Dashboard
Spreads surface as open positions (underlying + bias, net credit, live
mark, unrealized P&L) alongside cash, grouped by their §9 table.

## Scope of v1 (honest)
- Opens real defined-risk spreads on live data, atomic, safe square-off.
- Bias = intraday drift sign; managed exit = target/stop on net premium +
  15:15 flatten.
- §9 prediction grading for spreads (a spread-specific PredictionRecord)
  is a follow-up; v1 assigns a table by regime confidence for display.
- One spread per underlying per session (no laddering multiple spreads).
