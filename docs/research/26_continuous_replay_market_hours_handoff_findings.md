# 26 — Continuous/24-7 Market Replay & Replay-to-Live Handoff: Findings

You asked for real, existing open-source projects that let a system run
paper trading / AI research continuously (24/7) by replaying historical
NSE data as a live feed when the real market (9:15–15:30 IST, weekdays
only) is shut, while real-money live trading via Zerodha Kite still only
runs during actual NSE hours — with paper trading continuing uninterrupted
even after live trading is switched on, using its own separate simulated
capital. Every project below was verified via direct README/docs fetch
(GitHub API metadata as of 2026-07-23), not search snippets. License is
noted for information only per Rule E — never a filter.

**Headline finding: nothing found does the full "replay-as-live with
automatic seamless handoff to real live data at market open" pattern
out of the box.** This is a genuine architecture gap this project would
be building itself, not adopting — see recommendation at the end.

## Projects found

| Project | Stars | License | What it does | Replay-as-live / seamless handoff? |
|---|---|---|---|---|
| [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 24.9k | LGPL-3.0 | Rust-core/Python event-driven engine; identical strategy code across backtest, sandbox (paper), and live | Same event-driven engine and message bus for backtest and live; a `DataEngine` swaps historical-catalog input for a live client feed. Does not itself auto-detect "market now open, switch source" — that orchestration is left to the user |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | 20.7k | Apache-2.0 | C#/Python "LEAN" engine; the reference algo-trading platform behind QuantConnect's cloud | `IDataFeed`/brokerage abstractions decouple algorithm code from data source; same algorithm deploys to backtest, paper, and live brokerages unmodified. No built-in exchange-hours-aware auto-switch between historical and live feed |
| [vnpy/vnpy](https://github.com/vnpy/vnpy) (VeighNa) | 43.8k | MIT | Chinese quant trading platform; CTA backtester + 40+ live gateways | Event-driven core lets the same CTA strategy run against historical bars (backtest module) or a live gateway; switching is a manual config/mode choice, not automatic on a clock. No NSE/Kite gateway exists — would need a custom gateway |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 52.6k+ | GPL-3.0 | Crypto trading bot | **Best "always-on" analog.** Main loop runs on a fixed throttle (`internals.process_throttle_secs`), each tick: pull open trades → fetch OHLCV (once per candle) → run strategy → update order status → evaluate exit → evaluate entry. Dry-run reuses this identical loop against real live prices with a virtual wallet and simulated fills — it runs 24/7 because crypto markets never close, so there is no "market closed" branch to study, only "always live data, simulated execution" |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) | 8.2k | AGPL/MIT (dual, verify per-file) | Crypto trading framework | Same three-mode pattern (backtest/paper/live) as Freqtrade; paper mode consumes live exchange data with simulated fills. Same caveat: crypto never closes, so it never has to solve the "replay when closed" problem |
| [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | 6.2k | LGPL-3.0 | Crypto bot (grid/DCA/AI strategies) | Same live/paper parity pattern via CCXT; same "always live" caveat as above |
| [i-d-lytvynenko/websocket-trade-replayer](https://github.com/i-d-lytvynenko/websocket-trade-replayer) | 0 | MIT | Tiny asyncio WebSocket server that replays a Parquet trade file, preserving original inter-trade timing | **Closest direct match to "replay engine that looks exactly like a live feed" for the specific mechanism** (a strategy client connects the same way whether it's this replayer or a real exchange socket) — but it's a minimal reference implementation (4 commits), not a maintained framework, and has no market-calendar/hours awareness or live-handoff logic at all |
| [Vishwesh28/nse-market-simulator](https://github.com/Vishwesh28/nse-market-simulator) | 2 | not asserted | **NSE-specific**, C++/Go/Rust: reconstructs NSE capital-market TBT (tick-by-tick) `.DAT` files and rebrodcasts over UDP with a full limit-order-book engine | Explicitly supports **"real-time, accelerated, and maximum-speed replay modes"** — directly answers the "compressed wall-clock replay" ask (research item 4). Early-stage/incomplete (matching engine still in progress per its own README), but the architecture pattern (jiffy-to-nanosecond timestamp normalization, UDP broadcast indistinguishable from an exchange multicast feed) is the right shape for NSE specifically. Flagged as **found this, wasn't asked** — worth reading in full even though small |
| [xaiassetmanagement/tradingenv](https://github.com/xaiassetmanagement/tradingenv) | 17 | Apache-2.0 | Event-driven Gym-protocol market simulator for backtest/RL | Event-agnostic — works across data frequencies (tick to monthly) and has built-in market-calendar scheduling, which is the one piece of "market hours awareness" found in any Gym-style env here. No live-trading path at all; RL/backtest only |
| [AminHP/gym-anytrading](https://github.com/AminHP/gym-anytrading) | 2.4k | MIT | The standard OpenAI-Gym trading env | Episodic, not continuous: steps through a fixed historical window once per episode then resets. Not built for 24/7 operation and has no live-data path |
| [ClementPerroud/Gym-Trading-Env](https://github.com/ClementPerroud/Gym-Trading-Env) | 496 | MIT | Newer, faster Gymnasium trading env | Same episodic model as gym-anytrading; "backtesting" (beyond RL training) is explicitly listed as "coming soon." No live path |
| [bhanukaranwal/Options-Trading-Bot](https://github.com/bhanukaranwal/Options-Trading-Bot) | 12 | MIT | **NSE/BSE-specific**, backtrader + Zerodha Kite | Claims backtest/paper(Kite sandbox)/live with the same strategy code, but paper trading only runs during real market hours like live does — no 24/7 replay-when-closed design |
| [aayushpandey01/AI-Quant-Trading-Platform](https://github.com/aayushpandey01/AI-Quant-Trading-Platform) | 7 | MIT | **NSE-specific**, Zerodha Kite, full data→backtest→paper/live→dashboard loop | Confirmed directly: paper trading runs on the **same 9:15–15:30 IST schedule as live**, polling every 60s — explicitly **not** 24/7. A single `OrderManager` abstracts paper vs. live (the same pattern this project's `BrokerClient` already uses), but the "keep paper running when the market is shut" problem is unsolved here too |

## Direct answers to the five research angles

1. **Replay engines built to be indistinguishable from live**: only
   `websocket-trade-replayer` is purpose-built for exactly this (timing-
   preserving replay over a live-shaped transport), but it's a toy
   reference, not a framework. NautilusTrader/LEAN/VeighNa solve the
   *code-parity* half (same strategy code, swappable data source) at
   production quality but leave the *replay speed / clock-substitution*
   half to the user.
2. **Gym-style continuous envs**: none of gym-anytrading, Gym-Trading-Env,
   or tradingenv are architected to run forever — all three are
   episodic-reset-on-historical-window by design. `tradingenv`'s market-
   calendar feature is the only piece transferable to "know when NSE is
   open."
3. **Crypto bots' 24/7 model (Freqtrade et al.)**: the mechanism is a
   fixed-interval poll loop with a mode flag (`dry_run: true/false`) that
   swaps a `Wallet`/`ExchangeSimulation` object in for real order
   submission — the *data* is always live because crypto never closes.
   That's the key limitation of this analog: none of Freqtrade/Jesse/
   OctoBot have ever had to build a "market closed → replay instead"
   branch, because their target markets have no such concept.
4. **Accelerated/compressed replay**: `nse-market-simulator`'s "real-time,
   accelerated, maximum-speed" modes and ChronoTick's (PranavDarshan,
   3★, TS/Python, on-demand only, not looping) adjustable playback speed
   are the only two concrete examples found; neither is production-grade
   or NSE-hours-aware end to end.
5. **Seamless replay→live handoff pattern**: not found anywhere as a
   named, documented pattern in any repo or search angle tried
   (including direct GitHub searches for "replay to live handoff",
   "market hours scheduler auto switch live" — zero matches). The
   closest conceptual analogs are NautilusTrader's/LEAN's swappable
   data-feed abstraction, which makes the *swap* cheap once you decide
   to trigger it — but none of them decide *when* to trigger it based on
   an exchange calendar. **This confirms the ask is a genuine gap**, not
   something to adopt wholesale.

## Ranked: 5 most valuable to read full source from next

1. **nautechsystems/nautilus_trader** — read the `DataEngine`/`data client`
   source to see exactly how it swaps historical-catalog data for a live
   client feed at the same message-bus seam this project would need for
   NSE-closed vs. Kite-live.
2. **freqtrade/freqtrade** — read the main bot loop (`worker.py`,
   `freqtradebot.py`) and dry-run wallet simulation to adapt the
   fixed-interval poll + wallet-swap pattern onto an NSE trading-calendar
   gate.
3. **Vishwesh28/nse-market-simulator** — the only NSE-specific project
   with accelerated/max-speed replay modes; read its timestamp
   normalization and UDP broadcast code even though it's incomplete.
4. **aayushpandey01/AI-Quant-Trading-Platform** — smallest, most directly
   comparable prior art (Kite, `OrderManager` abstraction like this
   project's `BrokerClient`); read it to see exactly where its "paper
   trading only during market hours" limitation lives in code, so this
   project doesn't repeat it.
5. **QuantConnect/Lean** — read the brokerage/data-feed interface layer
   as a second reference implementation of code-parity, to cross-check
   against NautilusTrader's approach before committing to a design.

## Recommendation for this project's architecture

Build a **market-clock-gated data-source router** sitting in front of the
existing `BrokerClient` abstraction, not inside it:

- A single `MarketClock` component (NSE calendar: 9:15–15:30 IST,
  Mon–Fri, minus NSE holiday list) is the only thing that knows whether
  "now" is inside a live session.
- A `DataSourceRouter` exposes one interface (`get_next_tick()` /
  `subscribe()`) to every downstream consumer — strategy code, the
  learning loop, the paper-trading engine. It never leaks whether the
  tick underneath came from Kite's live WebSocket or a replay file.
  This is exactly NautilusTrader's/LEAN's data-feed abstraction pattern,
  adapted with an `MarketClock`-driven selection instead of a manual
  mode flag.
- When `MarketClock` says closed: router serves a `HistoricalReplaySource`
  that streams stored NSE tick/bar data at configurable speed
  (real-time for realism drills, accelerated/max-speed for bulk RL
  training — following `nse-market-simulator`'s three-speed pattern),
  looping across different historical days/regimes so the learning loop
  never idles.
- When `MarketClock` flips to open: router drains/closes the replay
  source and subscribes the same interface to Kite's live feed — the
  "seamless handoff" this research found no existing project solving
  automatically. Because paper trading already goes through the router's
  single interface, it does not need to be told anything changed.
- **Paper trading and live trading must be two independent consumers of
  the router, each with its own `BrokerClient` instance and its own
  ledger/capital pool** (paper's is a purely simulated, separately
  configurable balance; live's is the real Kite account, small/limited
  capital per the project's constraints). Live trading additionally
  gates on `MarketClock == open` before it will submit real orders (per
  this project's non-negotiable: real capital only during actual NSE
  hours) — but paper trading has no such gate and keeps consuming
  whatever the router is currently serving (replay when closed, the
  *same* live Kite feed when open, so paper never diverges from live
  reality during market hours either). This gives exactly the required
  behavior: paper trading never pauses, ever; live trading is bounded to
  real NSE hours with careful capital, running in parallel off the
  identical data stream paper is also consuming at that moment.

## Not covered / would need a follow-up pass

NSE-specific historical tick/bar data *sourcing* for the replay store
(this note assumes data already exists via whatever pipeline
`research/15`/`research/16` established) was out of scope here — this
pass was about the replay/handoff *mechanism*, not the data acquisition
layer.
