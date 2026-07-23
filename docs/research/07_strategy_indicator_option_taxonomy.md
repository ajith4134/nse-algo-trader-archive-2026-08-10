# 07 — Strategy, Indicator, and Option Order-Type Taxonomy

Full-category `expand-idea` pass for "all the strategies, all the
indicators, all the types in option trading like placing PE and CE." These
are stable, well-established finance-domain categories (not fast-moving
like frameworks/AI techniques), so this is built from established
quant/derivatives references rather than a fresh web sweep — flagged where
a claim would benefit from verification before being relied on for a real
strategy (e.g. exact SEBI margin treatment).

**Status: research + planning only. Nothing implemented. This is the menu
to choose from — Layer 3 (Indicators) and Layer 4 (Strategy) build only
what gets picked, per Rule A (one layer at a time).**

## Legend
⭐ user named this explicitly (PE/CE) · ✅ common/adjacent · 🚀 advanced ·
🌌 ultra-advanced/frontier

## A. Technical indicators

| Category | Items | Tier |
|---|---|---|
| Trend | SMA, EMA, WMA, VWMA, MACD, ADX/DMI, Parabolic SAR, Aroon | ✅ |
| Trend (advanced) | Ichimoku Cloud, Supertrend, Hull MA, KAMA, TRIX, Vortex Indicator, Linear Regression Channel | 🚀 |
| Momentum | RSI, Stochastic, CCI, Williams %R, ROC/Momentum | ✅ |
| Momentum (advanced) | Stochastic RSI, Awesome Oscillator, TSI, Ultimate Oscillator, Fisher Transform | 🚀 |
| Volatility | Bollinger Bands, ATR, Historical Volatility, Standard Deviation bands | ✅ |
| Volatility (advanced) | Keltner Channel, Donchian Channel, Chaikin Volatility | 🚀 |
| Volume | OBV, VWAP, Anchored VWAP, Money Flow Index, Accumulation/Distribution | ✅ |
| Volume (advanced) | Chaikin Money Flow, Klinger Oscillator, Volume Profile / Market Profile (TPO), Volume Delta / order-flow footprint | 🚀 |
| Market internals/breadth | Advance-Decline line, India VIX, New Highs-New Lows | ✅ |
| Breadth (advanced) | TRIN (Arms Index), McClellan Oscillator | 🚀 |
| Options-specific | Implied Volatility, IV Rank/Percentile, Open Interest, OI change, Put-Call Ratio (PCR), Greeks (Delta/Gamma/Theta/Vega/Rho) | ⭐/✅ — directly needed for PE/CE strategies |
| Options-specific (advanced) | IV Skew, Volatility Smile/Surface, Max Pain, Gamma Exposure (GEX) | 🚀 |
| Pattern-based | Candlestick patterns (engulfing, doji, hammer, etc.), classic chart patterns (H&S, triangles, flags) via algorithmic detection | ✅ |
| Pattern-based (advanced) | Elliott Wave approximation, Harmonic patterns (Gartley, Bat, Butterfly) | 🚀 |
| Statistical/quant | Z-score mean-reversion bands, cointegration/spread indicators (pairs) | 🚀 |
| Statistical (ultra) | Hurst exponent (trend vs. mean-reversion regime classifier), Kalman-filter smoothing, fractal dimension | 🌌 |
| Order-flow/microstructure | Bid-ask imbalance, Level-2 depth analysis, tick-by-tick footprint | 🚀 |
| Microstructure (ultra) | VPIN (volume-synchronized probability of informed trading) | 🌌 |
| Composite/ML-driven | Autoencoder-compressed multi-indicator composite score, HMM regime indicator, wavelet-transform decomposition, ensemble "meta-indicator" | 🌌 |

## B. Trading strategies (equity + index, directional/systematic)

| Category | Items | Tier |
|---|---|---|
| Trend-following | MA crossover, breakout (Donchian/opening-range breakout — ORB is a very common NSE intraday pattern), Supertrend-following, momentum trading | ✅ |
| Mean-reversion | Bollinger Band reversion, RSI overbought/oversold fade, VWAP reversion | ✅ |
| Statistical arbitrage | Pairs trading / cointegration spread trading, index arbitrage, futures-cash basis arbitrage | 🚀 |
| Relative strength | Sector rotation, relative-strength ranking/momentum factor | ✅ |
| Event-driven | Earnings/results-day plays, weekly-expiry-day plays (NIFTY/BANKNIFTY), budget-day/RBI-policy volatility plays, news-momentum | 🚀 |
| Scalping | Tick scalping, spread capture (must stay under the SEBI 10 orders/sec/exchange/client cap — see `CLAUDE.md`) | 🚀 |
| Systematic/quant | Factor-based selection, ML-signal-driven entries, regime-switching meta-strategy that allocates between sub-strategies | 🚀 |
| Portfolio-level | Hierarchical Risk Parity allocation across multiple validated strategies (ties to file 01's Fusion E) | 🌌 |

## C. Option order types and strategies — this is what "PE and CE" generalizes into

The user named the atomic building blocks (buy/sell PE, buy/sell CE).
Every options strategy is a combination of those 4 atomic actions across
strikes/expiries. Full taxonomy:

### Atomic legs (⭐ the user's own examples, made complete)
- **Buy CE** (long call) — bullish, defined risk (premium paid)
- **Sell CE** (short/naked call) — bearish/neutral, **undefined risk** —
  needs explicit risk-layer guardrails before ever being enabled live
- **Buy PE** (long put) — bearish, defined risk
- **Sell PE** (short/naked put) — bullish/neutral, large margin, capped
  but large downside risk

### Two-leg strategies (✅ common)
- **Bull Call Spread** (buy lower-strike CE, sell higher-strike CE) —
  bullish, defined risk/reward
- **Bear Put Spread** (buy higher-strike PE, sell lower-strike PE) —
  bearish, defined risk/reward
- **Bull Put Spread / Bear Call Spread** (credit spreads — sell near
  strike, buy further strike for protection) — income/theta strategies,
  defined risk
- **Long Straddle** (buy CE + buy PE, same strike) — big-move-either-way
  bet, common before events
- **Long Strangle** (buy OTM CE + buy OTM PE) — cheaper than straddle,
  needs a bigger move
- **Covered Call** (long stock/futures + sell CE) — income on an existing
  holding
- **Protective Put / Collar** (long stock/futures + buy PE, optionally +
  sell CE to fund it) — hedging an existing holding

### Multi-leg strategies (🚀 advanced)
- **Short Straddle / Short Strangle** (sell CE + sell PE) — premium
  selling, undefined risk unless hedged — very common on NIFTY/BANKNIFTY
  weekly expiry, and exactly where risk-layer guardrails matter most
- **Iron Condor** (bull put spread + bear call spread combined) — defined
  risk, range-bound premium selling — the standard "safe" version of
  short strangle
- **Iron Butterfly** (short straddle converted to defined risk with wings)
- **Calendar Spread** (same strike, sell near-expiry, buy far-expiry) —
  time-decay/volatility play
- **Diagonal Spread** (different strikes AND different expiries)
- **Ratio Spread** (unequal number of legs, e.g. buy 1 CE, sell 2 further
  CE) — can carry undefined risk on the extra leg
- **Butterfly Spread** (buy-sell-sell-buy across 3 strikes) — defined risk,
  bet on low movement/pinning near a strike
- **Broken-Wing Butterfly / Condor variants** — asymmetric versions tuned
  for a directional skew while keeping defined risk

### Arbitrage/synthetic (🌌 ultra-advanced)
- **Box Spread** (combines a bull call spread + bear put spread at the
  same two strikes) — near risk-free arbitrage when mispriced, thin
  margins, execution-speed sensitive
- **Synthetic Long/Short Futures** (long CE + short PE = synthetic long
  futures, and the reverse) — used for margin/tax/exposure engineering
- **Gamma scalping** (dynamically hedging a long-options position's delta
  with the underlying as it moves) — a market-making-adjacent technique,
  execution-heavy
- **Volatility skew arbitrage** (trading the *shape* of the IV curve
  across strikes, not direction) — needs the IV-skew indicator from
  section A

## D. Mapping strategies to actual order placement (Kite Connect / broker layer)

This is the part that makes "switch paper/live with zero code difference"
real for options specifically — the OMS (Layer 6) needs to treat every
strategy above as one logical unit, not N independent orders:

1. **Single-leg** (buy/sell one CE or PE) → one order, straightforward.
2. **Multi-leg strategies** (spreads, straddles, condors, butterflies) →
   must be placed as a **basket/multi-leg unit** with a shared strategy
   tag, so partial fills, one-leg failures, and square-off are handled
   atomically, not as accidentally-naked legs. Kite Connect's basket-order
   API and order tags are the relevant primitive to build this on (needs
   verification against current Kite Connect docs when Layer 6 is built —
   flagged, not yet confirmed).
3. **Margin treatment differs by combination**: naked short options need
   full SPAN+exposure margin; recognized spreads (e.g. bull put spread,
   iron condor) get margin benefit from the broker/exchange for the
   hedged combination — this affects position sizing and must be modeled
   correctly in Risk Management (Layer 5), not assumed.
4. **Square-off ordering matters**: for multi-leg positions, the
   auto-square-off logic (a non-negotiable per `CLAUDE.md`) must close
   legs in an order that never leaves a naked, undefined-risk leg open
   even for one tick — e.g. close the short leg of a credit spread before
   or simultaneously with the long leg, never after.
5. **Paper vs. live parity for options specifically**: a simulated fill
   engine must model bid-ask spread and slippage realistically for
   options (much wider spreads than cash equity, especially for
   far-OTM/illiquid strikes) — this is exactly the gap OpenAlgo's own docs
   flag as unmodeled (`03_openalgo_deep_dive_verified.md`), so our
   in-house paper engine needs to do this deliberately rather than
   inherit the same blind spot.

## What this implies for the roadmap

Feeds Layer 3 (Indicator/Feature Engineering — pick from section A), Layer
4 (Strategy/Signal Engine — pick from sections B/C), and Layer 6 (Broker
Integration & OMS — section D's multi-leg-as-one-unit requirement is a
design constraint on the OMS itself, not an afterthought). See
`../PLAN.md` for the concrete build order and which items from this menu
are recommended for the first working version vs. deferred.
