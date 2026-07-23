# 14 — Trade Log Data Schema: Every Column, Segment by Segment

You asked for a browser dashboard where every open/closed trade carries
all the data related to it — not just entry/exit price — so the AI can
later mine patterns in winning vs. losing trades, and you specifically
flagged that options and NSE cash each have their own unique data (Greeks/
decay for options, different context for cash). This file is the full
column-by-column schema, split cleanly by what's shared, what's
cash-only, and what's options-only.

**Status: research + design only. Nothing implemented.** This is the
schema Layer 6 (Broker Integration & OMS) and Layer 7 (Backtesting &
Paper Trading) will actually write rows against, and what Layer 10's
pattern-mining features (`research/06` #2, `research/09` category F) read
from — getting it right before any trade-logging code is written matters
more than for most schemas, since retrofitting missing columns means the
AI can never mine patterns from trades taken before the column existed.

## What's actually available from Kite Connect (verified against Kite's own docs)

Corrects an earlier assumption in this project's research: Kite Connect's
**historical candle API does support open interest** via an `oi=1`
parameter, returning `(timestamp, open, high, low, close, volume, oi)` —
the "no historical OI" finding in `research/13` was based on older forum
threads and should be treated as superseded by this direct docs check.
Confirmed still genuinely unavailable from any Kite endpoint: **delivery
%, IV, Greeks, historical India VIX series, sector/index membership** —
these still need NSE bhavcopy or a self-maintained feed.

Real Kite field names (`kite.trade/docs`, 2026-07-23):
- **Orders**: `order_id, exchange_order_id, tradingsymbol, exchange, transaction_type, order_type, product, price, trigger_price, quantity, average_price, filled_quantity, order_timestamp, exchange_timestamp, tag`
- **Trades**: `trade_id, order_id, tradingsymbol, average_price, quantity, fill_timestamp`
- **Positions**: `quantity, average_price, close_price, last_price, pnl, m2m, unrealised, realised, buy_price, sell_price`
- **Quotes**: adds `oi, oi_day_high, oi_day_low`, 5-level depth, and
  (flagged, not re-verified this pass) likely `upper_circuit_limit`/
  `lower_circuit_limit` — confirm exact field name before schema lock.

## What professional trade journals capture beyond price/qty

Real, shipped products, not invented: **Tradervue** (official API docs)
logs `position_mfe`/`position_mae` (Maximum Favorable/Adverse Excursion)
and `best_exit_pl` — how much better the exit *could* have been. **Edgewonk**
adds R-multiple and per-setup win-rate/expectancy. **TraderSync** ships
*two separate tag taxonomies* — setup tags and mistake tags — plus
commission/fee tracking. **TradesViz** adds psychological tags (FOMO,
REVENGE, HESITATION, OVERSIZE) and two MFE/MAE variants (theoretical
excursion vs. running max/min P&L, which matters for short-duration
scalp-style trades). None of this is unique to this project — it's
standard practice in serious trade journaling, just not usually combined
with an algo system's own signal/strategy metadata.

## Consolidated schema — shared across every trade (cash + options)

| Field | Source | Availability |
|---|---|---|
| `order_id`, `trade_id`, `exchange_order_id` | Kite orders/trades | Direct |
| `tradingsymbol`, `exchange`, `instrument_token` | Kite | Direct |
| `transaction_type`, `product`, `order_type`, `quantity` | Kite | Direct |
| `entry_price`, `exit_price` | Kite trades (`average_price`) | Direct |
| `order_timestamp`, `exchange_timestamp`, `fill_timestamp` | Kite | Direct |
| `holding_duration` | exit_ts − entry_ts | Computable |
| `commission`, `fees`, `taxes` (STT/stamp duty) | Zerodha contract note | Computable in-house |
| `slippage_entry`, `slippage_exit` (vs. signal price) | stored signal price − fill price | Computable |
| `implementation_shortfall_bps` | decision price vs. fill price | Computable |
| `pnl`, `m2m`, `unrealised`, `realised` | Kite positions | Direct |
| `r_multiple` | pnl / initial_risk | Computable |
| `mae`, `mfe`, `price_mae`, `price_mfe` | tick/candle stream during holding | Computable in-house |
| `best_exit_price`, `best_exit_time` | tick stream, post-hoc | Computable |
| `india_vix_entry`, `india_vix_exit` | Kite quote (VIX instrument) | Direct |
| `nifty_trend_entry`, `time_of_day_bucket`, `day_of_week` | derived from OHLC/timestamp | Computable |
| `is_expiry_day`, `event_flag` (results/budget/RBI day) | calendar | External (manual/calendar feed) |
| `setup_tag`, `mistake_tag`, `emotion_tag`, `notes` | journal-style, project UI | In-house |
| `strategy_id`, `confidence_score`, `hypothesis_id` (links to `research/12`'s pipeline), `feature_vector_entry`, `feature_vector_exit` | project pipeline | In-house |

## NSE cash-equity-only columns

| Field | Source | Availability |
|---|---|---|
| `delivery_pct`, `delivery_qty` | NSE bhavcopy delivery report | External (NSE, not Kite) |
| `circuit_limit_pct`, `dist_to_upper_circuit`, `dist_to_lower_circuit` | Kite quote circuit fields (verify exact name) | Direct, pending verification |
| `pct_from_52w_high`, `pct_from_52w_low` | computed from historical candles | Computable |
| `sector`, `market_cap_tier`, `liquidity_tier` | NSE sector/index master | External (NSE) |
| `sector_relative_strength_entry` | sector index return vs. stock return | Computable |

## Options-only columns (your "Greeks/decay" point, specifically)

| Field | Source | Availability |
|---|---|---|
| `strike_price`, `expiry_date`, `option_type` (CE/PE) | Kite instrument master | Direct |
| `days_to_expiry_entry`, `days_to_expiry_exit` | expiry − timestamp | Computable |
| `underlying_price_entry`, `underlying_price_exit` | Kite quote (underlying instrument) | Direct |
| `moneyness_entry`, `moneyness_exit` (ITM/ATM/OTM) | strike vs. underlying | Computable |
| `oi_entry`, `oi_exit`, `oi_day_high`, `oi_day_low`, `oi_change` | Kite historical (`oi=1`) / quote | Direct — corrects `research/13`'s "OI not in historical data" finding |
| `volume_entry` | Kite quote | Direct |
| `iv_entry`, `iv_exit` | back out via Black-76 from LTP, or an external feed (Sensibull/Opstra) | Computable in-house / External |
| `iv_rank_entry`, `iv_percentile_entry` | self-maintained historical IV series | Computable, needs stored history — pick one lookback window (30/52-week/1-year all seen in practice) and document the choice |
| `delta_entry`, `gamma_entry`, `theta_entry`, `vega_entry` and the same four **at exit** | in-house options-pricing model | Computable in-house |
| `theta_decay_realized` (theta_entry × holding_duration vs. actual price change attributable to time decay) | derived from Greeks + holding duration | Computable — this is the specific "decay" data point you flagged |

## What this changes about the plan

- `research/13`'s "Kite Connect has no historical OI" finding is
  **superseded** — OI is available via the `oi=1` historical parameter.
  Delivery %, IV, Greeks, and India VIX history remain genuinely external.
- The `hypothesis_id` and `feature_vector_entry/exit` columns are the
  direct link between this trade log and the hypothesis-validation
  pipeline in `research/12` — every trade a validated (or
  still-`in_validation`) hypothesis produces should be traceable back to
  it, which is also what makes the eventual explainable audit trail
  (`research/06` #28, `research/09` category C) possible without a
  separate retrofit.
- This schema is a design input to Layer 6 (Broker Integration & OMS,
  which writes the row at entry) and Layer 7 (Backtesting & Paper Trading,
  which needs the same columns in simulated fills so paper and live trade
  logs are structurally identical) — not something to build standalone
  before those layers exist.

## Open items flagged, not resolved

- Exact Kite quote field name for circuit limits needs verification
  against current docs before schema lock (flagged, not re-verified this
  pass).
- IV-rank lookback window (30-day/52-week/1-year all seen across sources)
  needs a project decision, not an assumption.
