# 04 — Strategy / Signal Engine (Layer 4)

**Status:** v1 built and unit-tested; dry-run verified on real data.
**Full statistical validation (backtest -> walk-forward -> Deflated
Sharpe + CPCV gate per PLAN §5) deliberately awaits Layer 7** — nothing
here is a proven edge yet; parameters are starting points for tuning.

## Whole-pipeline data flow so far

```
[L1 Universe] -> [L2 Market Data] -> [L3 Indicators]
                                          |
                                          v
[Layer 4: strategy_engine/]
   ADX (L3) -> session_strategy_regime_gate
       classify_adx_market_regime(adx) -> MarketRegime
         TRENDING (>=25) / RANGE_BOUND (<=20) / INDECISIVE (between, or ADX=None)
       choose_v1_session_strategy(adx) -> V1SessionStrategyChoice
         TRENDING -> OPENING_RANGE_BREAKOUT
         RANGE_BOUND -> CREDIT_SPREAD
         INDECISIVE -> STAND_ASIDE (never trade blind)
       |                                    |
       v                                    v
   opening_range_breakout_strategy      credit_spread_leg_selector
     detect_opening_range_breakout(       select_credit_spread_legs(
       session_bars, instrument, cfg)       option_instruments, underlying,
     -> OpeningRangeBreakoutSignal|None     spot, atm_iv (L3), bias, date, cfg)
                                          -> CreditSpreadSignal | None
                    |                       |
                    v                       v
        (nothing consumes signals yet — Layer 5 Risk validates them,
         Layer 6 OMS executes them, Layer 7 backtests them)
```

## Files belonging to this layer

```
src/nse_algo_trader/strategy_engine/
├── __init__.py                          # public surface re-exports
├── strategy_signal_types.py             # signal data model (see below)
├── opening_range_breakout_strategy.py   # directional v1 strategy
├── session_strategy_regime_gate.py      # ADX -> regime -> strategy choice
└── credit_spread_leg_selector.py        # income v1 strategy leg picker

src/nse_algo_trader/indicators/black_scholes_implied_volatility.py
└── (+ compute_black_scholes_delta — added for strike selection)

tests/test_strategy_engine/              # 17 tests
├── test_opening_range_breakout_strategy.py
└── test_regime_gate_and_credit_spread_selector.py
```

## Data model (`strategy_signal_types.py`)
- `SignalDirection` LONG/SHORT; `OptionLegAction` BUY/SELL;
  `CreditSpreadBias` BULLISH_SELL_PUT_SPREAD / BEARISH_SELL_CALL_SPREAD.
- `OpeningRangeBreakoutSignal` — instrument, direction, triggered_at,
  breakout_close_price (entry ref), opening_range_high/low,
  stop_loss_price (opposite range bound), target_price, strategy_tag.
- `OptionLegIntent` — concrete Instrument + action + lots.
- `CreditSpreadSignal` — underlying, bias, short_leg + hedge_leg in ONE
  object (PLAN §1.3 atomicity), short_leg_estimated_delta;
  `__post_init__` enforces short=SELL, hedge=BUY, equal lots.

## Strategy rules (v1 defaults, all tunable via config dataclasses)
- **ORB** (`OpeningRangeBreakoutConfig`): range = first 15 min; trigger =
  first bar CLOSE beyond range (wicks don't count); stop = opposite
  bound; target = entry ± 2.0 × risk; one signal/session; no entries
  after 14:30 IST.
- **Regime gate** (`AdxRegimeGateConfig`): trending >= 25, range <= 20,
  else stand aside. ADX=None (warmup) -> stand aside.
- **Credit spread** (`CreditSpreadSelectionConfig`): nearest expiry with
  >= 1 calendar day left; short leg = OTM strike with |BS delta| closest
  to 0.25 (vol input = day's ATM IV — skew deliberately ignored in v1,
  documented limitation); hedge = 2 ladder steps further OTM; returns
  None rather than ever constructing a naked short (ladder too short,
  no OTM strikes, unknown underlying).

## How it was verified (2026-07-23)
- 17 unit tests (105 suite total, green): wick-vs-close triggering, first-
  signal-only, entry cutoff, custom range windows, threshold boundaries,
  delta-optimality of the chosen strike (checked against every other
  strike), expiry-day skip, too-short-ladder -> None, signal invariants.
- **Real-data dry-run** over the 22 stored INFY sessions: 12 ORB days
  (8 signals, entries 09:30-14:05, stops/targets coherent), 6 credit-
  spread days, 4 stand-aside. Real NIFTY chain (2026-07-22): bull put
  SELL 23750 / BUY 23650 @ delta 0.24, credit ~Rs.1,665/lot vs max loss
  ~Rs.5,835/lot; bear call SELL 24300 / BUY 24400 mirrored above spot
  [spot 23996, ATM IV 12.6%].

## Known limitations / explicitly deferred
- No skew model: every strike priced at ATM IV for delta selection.
- ORB is signal-only — trade management (trailing, partial exits) is
  Layer 6/7 territory; regime gate is EOD/last-value ADX in the dry-run,
  live wiring will use rolling intraday ADX.
- Statistical edge validation (DSR + CPCV) gated on Layer 7 existing —
  no strategy touches live capital before passing it (PLAN §5).

## Full-universe hardening (2026-07-23, user directive — PLAN §8a.14)

Added `option_moneyness_classifier.py`:
- `OptionMoneyness(str, Enum)` — ATM / ITM / OTM.
- `infer_strike_ladder_step(sorted_unique_strikes)` — smallest adjacent
  gap; NEVER hardcoded (real steps found in the live universe range from
  ~0.2 to 500 rupees across 18 distinct values).
- `classify_option_moneyness(strike, spot, right, ladder_step)` — ATM
  within half a step of spot, else ITM/OTM by payoff side.

**Breadth verification (2026-07-22 data, all option underlyings):**
215/215 ATM IVs recovered, 215/215 PCRs computed, 215/215 valid
credit spreads selected — spot-checked across wildly different chains
(YESBANK spot 23/step 1, TATASTEEL 186/2.5, MIDCPNIFTY 14626/25,
PAGEIND 39820/250). No symbol-specific code anywhere.

**Cash-side breadth note for Layer 7:** the 2,000+ stock intraday scan
will ride the live tick stream / batched quote API (Kite historical is
rate-limited ~3 req/s — per-symbol bar polling across the full universe
is not viable intraday; bars get built from ticks instead).
