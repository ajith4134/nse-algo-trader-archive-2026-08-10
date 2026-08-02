# II — correlation/breadth + cross-market context  ·  research/137

**Trunk II SENSES — perception.** Design doc (Rule D). Sourcing: real WebSearch (July 2026).

## Sourcing (real search)
Query: "python library market breadth advance decline line McClellan cross-sectional dispersion".
Findings: market breadth (**Advance-Decline line/ratio**, **McClellan Oscillator**) are well-defined
STANDARD indicators (StockCharts, ThinkorSwim), but **no Python library combines them** — `ta-lib`/
`pandas-ta` are SINGLE-SERIES TA (RSI/MACD over one price stream), not cross-sectional
breadth-across-a-universe. **Verdict: BUILD from formula** (count advancers/decliners, A-D ratio,
cross-sectional return dispersion), referencing the A-D / McClellan standards — bespoke over the
stored cash bhavcopy (`cash_bhavcopy_delivery` has `prev_close` + `close_price` per symbol per date).
[Sources: chartschool.stockcharts.com/table-of-contents/market-indicators · quantifiedstrategies.com/mcclellan-oscillator-and-summation-index]

## The ideas
- **Correlation / breadth** — a market-INTERNALS sense: how broadly is the market moving? Advancers
  vs decliners, A-D ratio, % advancing, and cross-sectional return DISPERSION (are stocks moving
  together — high correlation/low dispersion — or apart). Broad participation vs a narrow move.
- **Cross-market context** — is the aggregate market move CONFIRMED by breadth, or a narrow
  divergence (the headline up but most stocks down = a fragile, few-leaders rally)? The
  breadth-vs-benchmark confirmation read.

## Targets
- `compute_market_breadth(returns) -> MarketBreadthReport` over per-symbol daily returns. Success
  test: a broad-up day (most advancing) → high breadth %, is_broad; a mixed day → narrow.
- `assess_cross_market_context(returns) -> CrossMarketContext` — the median "market" move vs breadth →
  confirmation or divergence.

## Component parts (`market_data/market_breadth.py`)
- `SymbolReturn`(symbol, return_fraction) · `MarketBreadthReport`(total, advancers, decliners,
  breadth_pct, advance_decline_ratio, dispersion, is_broad, summary) · `compute_market_breadth`.
- `CrossMarketContext`(market_return, breadth_pct, confirms, divergence, summary) ·
  `assess_cross_market_context`.
- Store: `MarketDataSqliteStore.cash_bhavcopy_symbol_returns(trade_date, series="EQ")` — per-symbol
  `(close−prev_close)/prev_close` for a date (equities only).

## Wiring (Rule G/N)
Daily `_maybe_run_market_breadth` reads the latest stored bhavcopy → returns → both reports; caches.
Surface `market_breadth` (breadth + cross-market confirmation). READ-ONLY sense (a consumer — breadth
as a regime/risk input — is queued, Rule K).

## Verification
- Hermetic (Rule J): a broad-up return set → high breadth %, is_broad, low dispersion; a split set →
  narrow, high dispersion; a narrow rally (one big up, many small down) → cross-market divergence.
- Real-data (Rule F): over the REAL latest cash bhavcopy (thousands of EQ symbols), report the real
  advance-decline breadth + dispersion + confirmation.

## Backlog (Rule K)
- 🔴 **sentiment/news (II SENSES)** — needs an external news/sentiment SOURCE (Rule I acquisition:
  a news API / feed). Tracked separately; not in this slice.

## Atlas impact
correlation/breadth + cross-market context 🔴→🟢. II SENSES 4🟢→6🟢 (2🔴 left: sentiment/news + …).
Overall built 62→64/197 (32.5%).
