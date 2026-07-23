# 03 — Indicator / Feature Engineering (Layer 3)

**Status:** price-series v1 set (EMA, RSI, ATR, ADX, Supertrend, session
VWAP) built, tested, reference-verified on real data. Options-derived
pair (IV Rank, PCR) not started yet. Awaiting user sign-off on this
feature-set.

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
