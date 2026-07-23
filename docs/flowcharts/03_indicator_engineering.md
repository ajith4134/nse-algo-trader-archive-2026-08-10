# 03 — Indicator / Feature Engineering (Layer 3)

**Status:** v1 set COMPLETE — price-series six (EMA, RSI, ATR, ADX,
Supertrend, session VWAP) plus options-derived (Black-Scholes IV, ATM-IV
snapshots, IV Rank, PCR-OI), all built, tested, verified on real data.
Awaiting user sign-off before Layer 4.

## Whole-pipeline data flow so far

```
[Layer 1: Universe Registry] -> list[Instrument]
        |
        v
[Layer 2: Market Data] -> list[PriceBar]  (live Kite fetch or SQLite store)
        |
        v
[Layer 3: indicators/]  every function: list[PriceBar] -> per-bar series
   compute_exponential_moving_average(bars, period) -> list[float | None]
   compute_relative_strength_index(bars, period=14) -> list[float | None]
   compute_true_range_series(bars)                  -> list[float]
   compute_average_true_range(bars, period=14)      -> list[float | None]
   compute_average_directional_index(bars, period=14) -> AdxSeries
       (.adx / .plus_directional_indicator / .minus_directional_indicator)
   compute_supertrend(bars, atr_period=10, band_multiplier=3.0)
       -> SupertrendSeries (.supertrend_line, .trend_direction +1/-1)
   compute_session_anchored_vwap(bars)              -> list[float | None]
        |
        v
   (nothing consumes these yet — Layer 4 Strategy Engine will)
```

All outputs align 1:1 with the input bars; None = warmup. ADX is the
v1 trend-vs-range regime gate (research/28): >~25 -> directional
strategy allowed; low -> credit-spread regime.

## Files belonging to this layer

```
src/nse_algo_trader/indicators/
├── __init__.py                      # public surface re-exports
├── exponential_moving_average.py    # stdlib only
├── relative_strength_index.py       # stdlib only (Wilder RMA)
├── average_true_range.py            # TR + Wilder ATR
├── average_directional_index.py     # imports average_true_range
├── supertrend_indicator.py          # imports average_true_range
└── session_anchored_vwap.py         # per-session-date anchor

tests/test_indicators/test_price_series_indicators.py  # 12 hand-computed tests
```

## Conventions (chosen deliberately, documented for cross-checking)
- EMA: alpha=2/(period+1), SMA seed (pandas-ta/TradingView standard).
- RSI/ATR/ADX: Wilder smoothing (alpha=1/period); classic seeds
  (mean/sum of first `period` values). ADX first value at 2*period-1.
- Supertrend: **TradingView/Pine convention** — direction decided
  against the *current* ratcheted band (pandas-ta uses the previous
  bar's band; see verification note below). ATR period 10, mult 3.0
  defaults (common Indian-retail parameterization).
- VWAP: typical price (H+L+C)/3, anchored per calendar session date.

## How it was verified (PLAN §5: reference cross-check on real data)
2026-07-23, against pandas-ta-classic 0.6.52 (dev dependency) on 1,650
real INFY 5-min bars (2026-06-22..07-22, fetched live, persisted to the
store), comparing the last 800 points (seed decay excluded):
- EMA / RSI / ATR / ADX / +DI / -DI / session-VWAP: max |diff| between
  3.6e-15 and 4.3e-14 — **identical to floating-point precision**.
- Supertrend: 785/800 directions identical; all 15 mismatches within 7
  bars of a trend flip — the documented current-band vs previous-band
  convention difference, not a math error. Line values where the
  convention histories realign match; TradingView semantics kept since
  that is what Indian retail tooling (incl. Zerodha's charts) displays.
- 12 unit tests with hand-computed expectations (70 total suite, green).

## Known limitations / explicitly deferred
- IV Rank + PCR (options-derived, the rest of the v1 set) — next
  feature in this layer: PCR from stored F&O bhavcopy OI; IV via
  Black-Scholes inversion of stored option settlement prices.
- Batch (full-series) computation only — O(1) incremental per-new-bar
  updates (research/19's streaming upgrade) deferred until the live
  scanning loop actually exists to need it.
- India VIX ingestion (would shortcut IV-regime gating) not wired.

## Options-derived additions (2026-07-23, completing the v1 list)

```
src/nse_algo_trader/indicators/
├── black_scholes_implied_volatility.py   # BS price + bisection IV inversion
├── end_of_day_atm_implied_volatility.py  # bhavcopy rows -> ATM IV snapshot
├── implied_volatility_rank.py            # IV history -> 0-100 rank
└── put_call_ratio.py                     # bhavcopy rows -> PCR-OI

src/nse_algo_trader/market_data/
└── fo_bhavcopy_backfill_job.py           # historical FO bhavcopy -> store
    (+ store methods has_fo_bhavcopy_for_date / list_stored_fo_bhavcopy_trade_dates)

tests/test_indicators/test_options_derived_indicators.py  # 18 tests
```

- `compute_black_scholes_option_price(underlying, strike, tte_years,
  vol, OptionRightForPricing, rate=0.065)` — European BS; intrinsic at
  tte<=0. `compute_implied_volatility(...)` — bisection in [0.001, 5.0],
  None outside no-arbitrage bounds. Stdlib math only.
- `compute_end_of_day_atm_implied_volatility(rows, underlying, rate)` ->
  `AtmImpliedVolatilitySnapshot` (nearest future expiry, nearest strike,
  CE/PE IVs from settlement prices, `.atm_implied_volatility` average).
- `compute_implied_volatility_rank(current, history)` — standard
  100*(cur-min)/(max-min), clamped, None on thin/flat history.
- `compute_put_call_open_interest_ratio(rows, underlying)` ->
  `PutCallOpenInterestRatio` (all-expiry PE/CE OI sums, `.ratio` None on
  zero call OI). Options rows only — futures never counted.
- Backfill: 31 additional real FO bhavcopy days downloaded (store now
  holds 2026-06-08..07-22, 32 trade dates, ~1.3M contract rows).

### Verification (2026-07-23)
- BS priced against Hull textbook values (S=42,K=40,r=10%,σ=20%,T=0.5:
  C=4.76/P=0.81) — matches to the penny; IV round-trips recover σ to
  1e-4 across CE/PE × {12%, 35%, 80%}.
- Real-data sanity over all 32 stored days, 32/32 ATM IVs recovered per
  underlying: NIFTY IV 9.0-20.2% (latest 12.6%, IV Rank 32.1) with
  visible put skew (PE 14.1% vs CE 11.1%); BANKNIFTY 10.9-20.5%;
  RELIANCE 15.9-27.5% — index < bank-index < single-stock ordering as
  expected. PCR-OI: NIFTY 0.72-1.43, RELIANCE 0.52-0.71 — textbook
  ranges. 18 new tests (88 total, green).
