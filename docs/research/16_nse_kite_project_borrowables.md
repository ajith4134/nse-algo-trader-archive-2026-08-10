# 16 — NSE/Kite-Specific Trading Bot Projects: What to Borrow

You asked to find famous/advanced existing projects related to this
project's requirements, read their READMEs, and identify "puzzle piece"
features worth borrowing instead of building from scratch — plus flag
anything genuinely new we hadn't planned for. This file covers NSE- and
Zerodha-Kite-specific bots. Every project below was verified by fetching
its README directly (not from search snippets), with GitHub API metadata
(stars/license/last-push) as of 2026-07-23.

**Status: research only. Nothing borrowed or implemented yet.** Every
license is noted because it determines whether code can be vendored
directly vs. only the idea/pattern reimplemented.

## Projects found

| Project | Stars | License | Last push | What it is |
|---|---|---|---|---|
| [pkjmesra/PKScreener](https://github.com/pkjmesra/PKScreener) | 373 | MIT | 2026-07-23 | NSE breakout/consolidation scanner, 40+ composable "piped" scans, Telegram delivery, backtested scan-performance view |
| [deshwalmahesh/NSE-Stock-Scanner](https://github.com/deshwalmahesh/NSE-Stock-Scanner) | 323 | none asserted | 2025-03-28 | Kite-connected screener/backtester: patterns, RSI/MACD/Stochastic/BB/ATR/ADX, TICK/TRIN breadth, fixed-R:R position sizing |
| [buzzsubash/algo_trading_strategies_india](https://github.com/buzzsubash/algo_trading_strategies_india) | 58 | none asserted | 2026-06-24 | Live index option-selling bot (straddle/strangle), capital-proportional multi-account copy-trading, Kite 2FA auto-login |
| [studiogangster/next-gen-algo-trading-bot](https://github.com/studiogangster/next-gen-algo-trading-bot) | 37 | none asserted | 2026-05-11 | FastAPI + Redis TimeSeries + Ray-cluster engine for Zerodha; parallel per-instrument fetch workers |
| [aaryansinha16/AI-trader](https://github.com/aaryansinha16/AI-trader) | 44 | MIT | 2026-07-09 | NSE index-options system (TrueData, not Kite): XGBoost signals, PCR/OI flow scoring, tabular Q-learning RL exit agent |
| [P0W/trading_with_shoonya](https://github.com/P0W/trading_with_shoonya) | 15 | none asserted | 2026-01-16 | ATM short-straddle → iron-butterfly conversion bot (Shoonya broker), cron-driven expiry deployment |
| [BennyThadikaran/Kite-Trader](https://github.com/BennyThadikaran/Kite-Trader) | 42 | GPL-3.0 | 2024-09-25 (stale) | Unofficial Kite client with rate-throttle wrapper |
| [hemangjoshi37a/hjAlgos](https://github.com/hemangjoshi37a/hjAlgos) | 6 | MIT | 2024-11-08 (stale) | Transformer price-prediction driving Kite auto-trading, Flask+Bokeh dashboard |
| [naveen7v/Bhavcopy](https://github.com/naveen7v/Bhavcopy) | 17 | none asserted | 2021-07-09 (dead) | NSE bhavcopy scraper — broken by NSE site changes per its own README |
| [udhay8005/nifty_bot](https://github.com/udhay8005/nifty_bot) | 1 | none asserted | 2025-12-30 | Small Upstox bot with SQLite crash-recovery + Telegram kill-switch |

## Puzzle pieces worth borrowing, and how to upgrade each

- **PKScreener's composable scanner DSL** ("pipes" chaining 40+ filter
  criteria) is the closest thing here to a Chartink-style query layer for
  `research/13`'s filter taxonomy. **Upgrade**: it's INI/CLI-driven and
  single-process — rebuild as a real parsed expression language (AST)
  compiled to pandas/polars masks, and run against a live tick cache
  rather than only EOD snapshots.
- **NSE-Stock-Scanner's TICK/TRIN market-breadth indicator** and
  **risk-budget position-sizing function** — rare, most repos skip market
  internals. **Upgrade**: replace its hardcoded 1:2 risk-reward with a
  volatility-scaled (ATR-based) sizing model feeding Layer 5 (Risk).
- **algo_trading_strategies_india's capital-proportional copy-trading
  engine** — directly relevant if this project ever runs multiple
  accounts. **Upgrade**: replace linear capital-ratio scaling with
  margin-aware, per-account risk-budget scaling.
- **next-gen-algo-trading-bot's Redis-TimeSeries + Ray-cluster pattern** —
  solves Kite's rate-limit pain for parallel per-instrument data fetch.
  **Upgrade**: extend Ray beyond signal compute into parallel
  backtest/parameter-sweep execution across the whole strategy layer.
- **AI-trader's composite signal scorer** (directional + flow + technical
  + regime bonus, weighted) and its **tick-level backtest replay engine**.
  **Upgrade**: the RL-based exit agent (learns when to cut winners/losers,
  rather than static SL/target) is a genuinely different paradigm worth a
  deliberate evaluation against this project's risk layer.
- **trading_with_shoonya's cron-driven expiry-day square-off scheduling**
  — a concrete pattern for Layer 8 (Session/Square-off).
- **nifty_bot's SQLite crash-recovery** (a bot restart doesn't lose an
  open position) and **Telegram kill-switch** — small but genuinely useful
  operational patterns.

## Found, wasn't asked (flagged explicitly)

- **Multi-account capital-proportional copy-trading** isn't in this
  project's stated layer list at all — worth a deliberate yes/no decision
  rather than an accidental omission, since it changes Layer 6's scope.
- **Ray-cluster distributed backtesting** — a real scaling idea for when
  the strategy menu (`research/07`) grows large enough that sequential
  backtesting becomes a bottleneck.
- **RL-based exit agents** (as opposed to static SL/target rules) —
  distinct from this project's existing RL-for-execution research
  (`research/09` category B) and worth cross-referencing there.
- **Telegram-as-remote-control-plane** (status queries, live param tuning,
  kill switch) recurs across two of these projects — worth considering as
  a standard ops interface alongside the eventual Layer 9 dashboard, not
  a replacement for it.

## Do not build on

`naveen7v/Bhavcopy` is dead and broken by NSE's own site changes — useful
only as a historical reference for the old bhavcopy format, not as a
starting point. `Kite-Trader` and `hjAlgos` are stale with thin,
narrow-scope code — read for the one utility each offers (rate-throttle
wrapper; dashboard-plus-model wiring pattern), not as a base to build on.

## Ranked — most worth reading actual source code from next

1. **PKScreener** — most mature/active, MIT, cleanest scanner-DSL
   abstraction to shortcut Layer 3/13's filter menu.
2. **NSE-Stock-Scanner** — broadest indicator/pattern/risk-sizing surface
   already wired to Kite.
3. **algo_trading_strategies_india** — real production Kite options-selling
   code today, including multi-account copy-trading and 2FA auto-login.
4. **next-gen-algo-trading-bot** — modern Redis-TimeSeries + Ray
   architecture for Layer 2's rate-limit problem.
5. **AI-trader** — for the composite-scoring and RL-exit-agent design
   pattern (architecture, not its TrueData integration).

See `research/20` for how these fit into one consolidated action plan
alongside the options-engine, AI-agent, cash-scanner, and risk/compliance
research (`research/17`-`19`, `15`).
