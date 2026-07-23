# 19 — Cash-Intraday Scanner, Backtest & Data Projects: What to Borrow

Companion to `research/16`-`18`. Covers cash-equity intraday
infrastructure — scanners, indicator libraries, backtesting engines, and
NSE-specific data tooling — excluding backtrader, vn.py, NautilusTrader,
QuantConnect LEAN, Freqtrade, and Jesse, which are already researched in
`research/02`. Every project verified via direct README fetch, GitHub
metadata as of 2026-07-23.

**Status: research only. Nothing borrowed or implemented yet.**

## Projects found

| Project | Stars | License | Last push | What it is |
|---|---|---|---|---|
| [pkjmesra/PKScreener](https://github.com/pkjmesra/PKScreener) | 373 | MIT | 2026-07-23 | (also in `research/16`) NSE scanner, 40+ scans incl. VCP/Ichimoku/Aroon |
| [deshwalmahesh/NSE-Stock-Scanner](https://github.com/deshwalmahesh/NSE-Stock-Scanner) | 323 | none asserted | 2025-03-28 | (also in `research/16`) |
| [BennyThadikaran/stock-pattern](https://github.com/BennyThadikaran/stock-pattern) | 398 | GPL-3.0 | active | CLI chart-pattern scanner (H&S, triangles, double top/bottom, VCP, harmonic BAT) |
| [BennyThadikaran/NseIndiaApi](https://github.com/BennyThadikaran/NseIndiaApi) | 153 | GPL-3.0 | 2026-07-21 | Unofficial NSE API wrapper: bhavcopy incl. delivery %, corporate actions, option chain, quotes, advance/decline |
| [BennyThadikaran/eod2](https://github.com/BennyThadikaran/eod2) | 159 | GPL-3.0 | 2026-07-12 | Automated EOD downloader for 2,000+ NSE stocks since 1995, split/bonus-adjusted, holiday-aware incremental sync, breadth module |
| [jugaad-py/jugaad-data](https://github.com/jugaad-py/jugaad-data) | 542 | custom ("LICENSE.YOLO.md") | active | Bhavcopy + historical/live NSE data + RBI rates, targets NSE's newer site |
| [xgboosted/pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic) | 398 | MIT | 2026-06-24 (v0.6.52) | 224 indicators + 62 candlestick patterns as a pandas `.ta` accessor, numba/TA-Lib acceleration |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | 8,400 | Apache-2.0 + Commons Clause | 2026-07-05 (v1.1.0) | Numba/Rust vectorized backtesting, thousands of parameter combos simultaneously |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | 8,700 | AGPL-3.0 | active | Simple event-driven single-strategy backtester, Bokeh plots |
| [stefan-jansen/zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded) | 1,800 | Apache-2.0 | 2025-07-23 (stale releases) | Quantopian-legacy event-driven backtester, factor/pipeline API |

## Puzzle pieces worth borrowing, and how to upgrade each

- **stock-pattern's standalone, dependency-light pattern-detection
  algorithms** (decoupled from any broker/data source). **Upgrade**:
  rewrite to run incrementally on a rolling window per new bar instead of
  rescanning full history each run — needed for true intraday pattern
  alerts. GPL-3.0 — fine if this project stays internal, a blocker if
  ever distributed permissively.
- **NseIndiaApi is the single most complete client for exactly the three
  NSE data needs this project's own research already flagged as gaps**
  (`research/13`, `14`): bhavcopy, delivery %, corporate actions —
  correctly the `research/13`/`14` "Kite doesn't provide this" list.
  **Upgrade**: add exponential-backoff retry + response-schema validation
  (NSE silently changes JSON shapes) and a persistent on-disk/Redis cache
  with TTL keyed by trading-day.
- **eod2's incremental-sync + holiday-calendar + split/bonus-adjustment
  logic** — the hardest part of an NSE data pipeline to get right,
  already solved. **Upgrade**: swap flat CSVs for a columnar store
  (Parquet/DuckDB) with schema versioning and checksum/row-count
  validation per file to catch NSE format drift automatically.
- **jugaad-data's live-quote (NSELive) client** — a second data-source
  implementation to cross-validate against NseIndiaApi. **Upgrade**: fork
  the bhavcopy layer only (no corporate-action/delivery-% support noted)
  and pair with NseIndiaApi for the gaps. Its unusual "LICENSE.YOLO.md"
  needs the actual terms read before vendoring, not assumed permissive.
- **pandas-ta-classic — the single biggest still-fully-open indicator
  library** (224 indicators, MIT, community continuation after the
  original went commercial in 2025). Directly shortcuts most of
  `research/07` §A's indicator menu. **Upgrade**: it's batch/pandas-only —
  wrap the numba-accelerated kernels for O(1) incremental updates per new
  tick/bar (ring-buffer state) instead of recomputing the full series each
  time, needed for live scanning at intraday frequency.
- **vectorbt's numba/Rust vectorized simulation core** — the most
  architecturally advanced project in this list. **Upgrade**: its
  vectorized model assumes offline historical arrays — adapt the
  signal/portfolio-simulation core to consume streaming intraday bars in
  fixed-size rolling windows for near-real-time re-evaluation. Note the
  Commons Clause restricts reselling it as a service (fine for internal
  use).
- **backtesting.py** — good for rapid single-strategy prototyping, but its
  **AGPL-3.0** license is a real constraint if this bot is ever offered
  as a hosted service (network-use triggers source disclosure) — use only
  for quick iteration, not as the production intraday engine.
- **zipline-reloaded's factor/pipeline API** — strong for cross-sectional
  factor research across the whole NSE universe. **Upgrade**: use the
  pipeline API purely as inspiration for a factor layer feeding the
  scanner (Layer 3), not as the execution engine — its release cadence
  has gone stale even though issues are still triaged.

## Found, wasn't asked (flagged explicitly)

- **PKScreener ships a Telegram alert bot and an "AI Nifty direction"
  predictor** — neither requested, both reusable delivery/signal patterns
  (the Telegram pattern cross-references `research/16`'s finding of the
  same mechanic in two other projects).
- **eod2's market-breadth/PE-alert module** (advance/decline line,
  52-week highs, Nifty PE alerts) is a genuinely useful macro-regime
  filter for gating intraday strategies, not part of the original brief.

## Ranked — most worth reading actual source code from next

1. **BennyThadikaran/NseIndiaApi** — it's the exact data contract
   (bhavcopy + delivery % + corporate actions) `research/13`/`14` already
   flagged as needed; read the session/cookie and endpoint-mapping code
   before building or hardening this project's own client.
2. **BennyThadikaran/eod2** — read the incremental-sync, holiday-calendar,
   and split/bonus-adjustment logic; the hardest-won code in this list.
3. **polakowo/vectorbt** — read the numba/Rust simulation core for real
   speed in Python for intraday backtesting/scanning.
4. **xgboosted/pandas-ta-classic** — read individual indicator
   implementations to see which are already numba-vectorized vs.
   loop-based, as the basis for an incremental/streaming indicator engine.
5. **pkjmesra/PKScreener** — read the scanner/pipe config engine as a
   working precedent for a config-driven, Chartink-like screening DSL.

See `research/20` for the consolidated action plan across all
borrowable-project research (`research/15`-`19`).
