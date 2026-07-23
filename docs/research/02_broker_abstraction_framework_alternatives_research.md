# 02 — Broker-Abstraction Framework Landscape (alternatives to OpenAlgo)

Research for Layer 6 (Broker Integration & Order Execution / OMS) and Layer 7
(Backtesting & Paper Trading): does an existing Python framework already give
genuine same-code paper-live parity via a broker-abstraction layer, with
Zerodha Kite Connect / NSE support — or should this project build that
boundary in-house? Findings only; the actual build decision happens when
Layer 6/7 is started.

Researched 2026-07-23. GitHub facts below pulled live via `api.github.com`
(pushed_at / commit history), not from search snippets or training memory —
snippets were cross-checked against the API and one snippet turned out to be
stale (see backtrader).

## 1. AlgoBulls
SaaS platform (Phoenix/Odyssey/AlgoBuddy) with an open-source companion SDK,
`pyalgotrading` (MIT, 299★, pushed 2026-02-04) and a companion strategy pool
`pyalgostrategypool` (MIT, pushed 2026-07-16) — both live, not abandoned.
The SDK exposes a `get_historical_api()` / `get_realtime_api()` split so the
same strategy class can run in backtest, paper ("papertrading"), and real
modes, but execution actually happens **inside AlgoBulls' hosted platform**,
not your own process — it's a client SDK to their cloud, not a standalone
local broker-abstraction library. NSE/BSE/MCX, "empanelled" but broker list
not published on the marketing site. **Material 2026 event**: per AlgoBulls'
own blog and independently corroborated by Motilal Oswal, Tradetron, uTrade
Algos, and Sahi — SEBI's Feb 2025 circular becomes fully mandatory
**April 1, 2026**, requiring every retail algo order to route through a
broker-registered, Algo-ID-tagged path. AlgoBulls states live/paper
trading will no longer execute directly on their platform after that date;
users are redirected through partner-broker rails. This SEBI shift affects
every third-party India algo SaaS in this list, not just AlgoBulls — it's
the reason `pykiteconnect`/broker-native routing is becoming the only
durable path for a from-scratch bot. License: MIT (SDK). Verdict: not a
fit — parity is real inside their platform, but it's a hosted SaaS
dependency, and the regulatory ground is shifting under exactly this model.

## 2. Zerodha Streak / Kite Connect templates
Streak is a **no-code, Zerodha-only** condition-builder (indicators → rules),
not a programmable framework — no shared code path between its backtest
engine and live deployment beyond the rule definition itself, and it can't
run arbitrary Python strategy logic. Kite Connect itself is just the raw
REST/WebSocket API — Zerodha ships official client libraries
(`pykiteconnect`, MIT license, actively maintained: last commit
2026-04-23, v5.1.0 released 2026-03-27) but **no backtest/paper-trading
engine and no broker-abstraction layer** — you get order placement, quotes,
and streaming only. Any paper/live parity has to be built by the user on
top of it. This is effectively the "build it yourself" baseline, not a
competing framework.

## 3. backtrader
Popular Python backtesting library with a live-broker bridge for
Interactive Brokers, Oanda, and Visual Chart via the same `Cerebro`/`Strategy`
API used for backtests — genuine same-strategy-class parity for those three
brokers specifically. **Upstream is stale**: `mementum/backtrader`'s last
real commit is 2023-04-19 (verified via GitHub API `pushed_at:
2024-08-19`* and commit list — the 2024 pushed_at was a housekeeping push,
the actual last content commit is April 2023); 63+ open PRs sit unmerged.
No official NSE/India broker adapter. Community fixes this two ways: (a)
community forks such as `cloudQuant/backtrader` (GPL-3.0, pushed
2026-07-10 — actively maintained, adds CTP/CCXT/IB) and `backtrader_next`
(smalinin); (b) bolt-on bridges, e.g. `p2c2e/openalgo-backtrader` (MIT,
pushed 2025-09-04) which wraps OpenAlgo itself as a backtrader broker/store,
giving backtrader users Kite-via-OpenAlgo access. Net: usable NSE path
exists only by relying on a fork or a third-party bridge, not upstream.

## 4. vn.py (VeighNa)
Mature Chinese-origin quant framework (MIT license, v4.4.0 released
2026-05-14, very active — commits into May 2026) with a real gateway/engine
split (`vnpy.gateway.*` implements a broker, `vnpy.app.*` strategies stay
gateway-agnostic) — genuine paper/live-style abstraction pattern, similar
in spirit to what this project wants. Gateway coverage is overwhelmingly
**China-domestic (CTP, XTP, Tora, Esunny, Femas) plus Interactive
Brokers/international futures** — no Zerodha, Upstox, Angel One, or any
NSE gateway exists in the ecosystem today. Architecturally interesting as
a reference design; would require writing a from-scratch NSE gateway to use
it, at which point you've built most of the abstraction layer anyway.

## 5. Jesse
Crypto-only algorithmic trading framework (MIT license, active — 3,390+
commits, recent activity into 2026). Its docs describe backtest, paper, and
live modes as separate deployment surfaces around the same strategy class,
with exchange drivers abstracting execution — the pattern is transferable,
but the driver layer is written specifically against crypto exchange APIs
(ccxt-style spot/futures/DEX), so none of it is reusable for NSE order
types, circuit-limits, or Kite's auth flow without a full rewrite.

## 6. Freqtrade
Crypto-only bot (GPL-3.0, actively maintained, releases into 2026, e.g.
2026.6). Its "dry-run" mode is a clean, well-documented reference for the
*pattern* this project wants: the same `IStrategy` code runs unchanged, with
a config flag (`dry_run: true/false`) switching between simulated fills and
real exchange orders, and it deliberately keeps separate SQLite DBs for
dry-run vs. live so paper trades never mix with real ones — worth copying
as a design idea. Exchange abstraction is entirely CCXT-based; adding NSE
would mean writing a full CCXT-incompatible broker driver, i.e., not
practically portable, only the *pattern* is worth taking.

## 7. NautilusTrader
Rust-core, Python-API event-driven engine (LGPL-3.0 + CLA, very active:
v1.230.0 released 2026-06-29, 137 releases, ~25k★). The parity claim is
**verified as genuine and architecturally real**, not marketing: strategies
talk only to abstract `DataClient`/`ExecutionClient` interfaces and a shared
`Cache`/`MessageBus`/`Portfolio`; in backtest the same interfaces are backed
by a `SimulatedExchange`, in live/sandbox by a real venue adapter — "no
code changes" is accurate per their own docs, though live mode does add
engine-level concerns (order-state reconciliation on startup, in-flight
polling) that backtest doesn't need — these live outside strategy code, so
parity holds at the strategy layer. **No India broker adapter exists**
(confirmed: 17 integrations, all crypto CEX/DEX, Interactive Brokers,
Betfair, Databento/Tardis/Polymarket data — no Zerodha/Upstox/Angel One).
Interactive Brokers doesn't give resident-Indian retail traders direct
NSE equity/options access either, so IB isn't a backdoor to NSE here. This
is the strongest **architecture to imitate**, but would require writing a
Kite Connect `ExecutionClient`/`DataClient` adapter from scratch (a real,
non-trivial Rust/Python contribution) before it is India-usable.

## 8. QuantConnect LEAN
Open-source engine (Apache-2.0, both the core `QuantConnect/Lean` repo and
brokerage plugins) — genuinely self-hostable, not just the hosted
QuantConnect.com cloud. **A community-maintained `Lean.Brokerages.Zerodha`
plugin already exists and is actively maintained** (verified via commit
history, not just repo pushed_at: real commits through 2026-06-18,
including a net10 update Dec 2025 and a RestSharp→HttpClient rewrite Dec
2025 — this is genuinely live, not abandoned). It integrates with LEAN's
standard `IBrokerage` interface, meaning the same backtest/live algorithm
class structure LEAN uses everywhere else applies to Zerodha too — real
parity by design (LEAN's whole selling point). Caveats for a from-scratch
NSE intraday bot: strategies are written in LEAN's C#/Python (not
pure-Python-idiomatic) algorithm framework, self-hosting needs .NET 10 +
Docker, historical data setup wants a paid data vendor (TrueData mentioned
in the plugin README) since LEAN's default data isn't India-market-shaped,
and margin/product-type mapping (MIS/CNC/NRML) is handled but adds
plugin-specific configuration surface. Heavier operationally than a
pure-Python stack, but the most credible "not proprietary SaaS, not
abandoned, real India adapter" option on this list.

## 9. Other India-specific open-source projects found
No other project rises to "framework" status (i.e., a reusable
broker-abstraction layer with paper/live parity, not a single strategy
script). What search turned up were single-strategy repos built directly
against `pykiteconnect` (e.g. `buzzsubash/algo_trading_strategies_india`,
`AdityaPawade/...`, `aeron7/Mastering-AlgoTrading...`) — useful as
implementation reference for Kite Connect quirks (auth flow, order types,
freeze-limit slicing) but none provide a mode-switchable
paper/live abstraction of their own; OpenAlgo (the framework this research
is alternatives-to) remains the only India-native project actually
built as a general-purpose, multi-broker, self-hosted abstraction layer —
it is itself AGPL-3.0 licensed and very actively maintained (commits same-day
as this research). Commercial India platforms (Tradetron, AlgoTest,
AlgoCrab, uTrade Algos) were also surfaced but are closed-source SaaS, not
libraries — same category as AlgoBulls/Streak, excluded from the table below
for that reason.

## Ranked comparison

| Framework | Paper/live code parity | Broker-abstraction quality | India/NSE support | Maintenance (as of 2026-07-23) | License |
|---|---|---|---|---|---|
| **NautilusTrader** | Genuine, verified — same strategy class, engine swaps Sim↔real venue | Excellent design (Data/Execution client split); no Kite adapter exists yet | None out of the box — would need a custom Kite adapter | Very active — v1.230.0, 2026-06-29 | LGPL-3.0 + CLA |
| **QuantConnect LEAN** | Genuine, by design (`IBrokerage` interface) | Strong, proven with a real community-maintained Zerodha plugin | **Yes — working Zerodha plugin**, actively maintained | Active — core + plugin both committed within days/weeks | Apache-2.0 |
| **Freqtrade** | Genuine pattern (`dry_run` flag, same `IStrategy`), but CCXT-only | Good pattern, not portable to non-crypto brokers | None (crypto-only) | Very active — 2026.6 release | GPL-3.0 |
| **vn.py** | Genuine gateway/engine split | Good design reference | None (China/IB gateways only) | Very active — v4.4.0, May 2026 | MIT |
| **Jesse** | Claimed, docs light on internals; CCXT-only | Adequate for crypto | None (crypto-only) | Active | MIT |
| **backtrader (upstream)** | Real for IB/Oanda/Visual Chart only | Dated but functional | Only via 3rd-party bridge (OpenAlgo-backtrader) or forks | **Stale — last real commit 2023-04-19** | GPL-3.0-ish (custom) |
| **backtrader (cloudQuant fork)** | Same model as upstream, extended | Improved, adds CCXT/CTP | Via OpenAlgo bridge only | Active — pushed 2026-07-10 | GPL-3.0 |
| **AlgoBulls (pyalgotrading)** | Genuine but tied to their hosted execution backend | N/A — not a local abstraction layer | Yes, but SaaS-hosted, and SEBI Apr-2026 rules disrupt this model | Active | MIT (SDK only) |
| **Zerodha Streak** | None (no-code, not programmable) | None | Zerodha-only | Active (commercial product) | Proprietary |
| **Kite Connect / pykiteconnect** | N/A — raw API client, no engine | None (you build it) | Native, official | Active — 2026-04-23 | MIT |

## Recommendation

For a from-scratch NSE intraday bot with a Kite Connect-first, swappable
broker layer (per this project's `CLAUDE.md` stack decision):

1. **Evaluate QuantConnect LEAN further, specifically `Lean.Brokerages.Zerodha`** —
   it is the only option here with *both* a verified-genuine parity
   architecture *and* a real, currently-maintained NSE/Zerodha adapter. The
   cost is operational weight (.NET/Docker, non-Python-idiomatic algorithm
   API, paid historical data) — worth a hands-on spike before committing.
2. **Study NautilusTrader's architecture as a design template even if not
   adopted wholesale** — its Data/Execution-client boundary is the cleanest
   published version of exactly the abstraction this project needs to
   design in-house (Layer 6). Not adopting it directly avoids taking on a
   from-scratch Kite adapter in Rust/Python as a side project.
3. **Recommend building the broker-abstraction layer in-house**, informed
   by (1) and (2): a thin `BrokerClient` protocol (`place_order`,
   `modify_order`, `cancel_order`, `get_positions`, `get_quote`,
   `subscribe_ticks`) implemented once against `pykiteconnect` for live and
   once against a simulated fill engine for paper — mirroring Freqtrade's
   `dry_run` flag pattern (same strategy code, a boolean/config switch, and
   separate state stores for paper vs. live) and NautilusTrader's
   client-interface split. This keeps the project pure-Python, avoids a
   GPL/AGPL/LGPL license entanglement question for a project that may later
   need to stay closed, and matches the "broker-integration layer must stay
   swappable" constraint already in `CLAUDE.md` — a thin in-house interface
   is easier to keep swappable than retrofitting a third-party engine's
   assumptions.

## What this did not cover
- No hands-on code spike of LEAN/Zerodha or NautilusTrader was run — this is
  a documentation/repo-metadata-level review, not a working prototype.
- Did not evaluate Interactive Brokers' actual legal/practical NSE access
  terms for resident Indian individuals in depth (mentioned only in
  passing) — if that path is ever reconsidered, verify directly with IB,
  not from this note.
- Did not price out LEAN's required data-vendor subscription (TrueData or
  equivalent) for NSE historical/tick data — needed before a real go/no-go
  on option 1 above.
- Zerodha Streak's internal architecture (whether its backtest engine and
  live engine share any code) was not independently verifiable — it's
  closed-source, so this is inferred from product docs, not source review.

## Sources (primary/official unless noted)
- AlgoBulls: https://github.com/algobulls (pyalgotrading, pyalgostrategypool repos), https://algobulls.com/, https://algobulls.com/blog/industry-insights-and-updates/sebi-new-algotrading-regulations-for-retail-investors-2026
- SEBI Apr 2026 mandate corroboration: Motilal Oswal (https://www.motilaloswal.com/learning-centre/2025/6/sebi-regulations-on-algorithmic-trading-in-india), Tradetron blog, uTrade Algos blog, Sahi blog — 4 independent secondary sources agreeing on the Feb 2025 circular / Apr 1 2026 mandatory date, consistent with `docs/research/00_market_structure_and_regulatory_findings.md` already on file for this project
- Zerodha: https://github.com/zerodha/pykiteconnect (commit history via GitHub API), https://kite.trade/forum, https://zerodha.com/z-connect/streak/introducing-streak-algo-trade-without-coding
- backtrader: https://github.com/mementum/backtrader (commit history via GitHub API — last real commit 2023-04-19), https://github.com/cloudQuant/backtrader, https://github.com/p2c2e/openalgo-backtrader
- vn.py: https://github.com/vnpy/vnpy (commit history + release v4.4.0)
- Jesse: https://github.com/jesse-ai/jesse, https://jesse.trade/
- Freqtrade: https://www.freqtrade.io/en/stable/ (dry-run/strategy-customization docs), https://github.com/freqtrade/freqtrade
- NautilusTrader: https://nautilustrader.io/docs/latest/concepts/live/, https://nautilustrader.io/blog/why-nautilustrader-exists/, https://github.com/nautechsystems/nautilus_trader
- QuantConnect LEAN: https://github.com/QuantConnect/Lean, https://github.com/QuantConnect/Lean.Brokerages.Zerodha (commit history via GitHub API confirms active maintenance through 2026-06-18)
- India OSS scan: https://github.com/topics/zerodha-kite, https://github.com/buzzsubash/algo_trading_strategies_india, and related single-strategy repos surfaced via GitHub topic search
- OpenAlgo (baseline being compared against): https://github.com/marketcalls/openalgo (AGPL-3.0, confirmed via GitHub API)
