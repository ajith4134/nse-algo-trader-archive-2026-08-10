# NSE Algo Trading Bot — Master Build Plan

**Status: planning/discussion document. Nothing in this file has been
implemented. No existing code has been touched while writing this — Layer
1 is untouched and still awaiting your sign-off separately.**

This is the "decide all the features first" document you asked for, before
any more implementation happens. It ties together every research file
under `research/` into one build plan, proposes a testing method for every
step, and ends with open decisions for you to make. Read `research/00`
through `research/09` for the full backing detail — this file is the
synthesis, not a replacement for them.

**Note on the AI layer specifically:** the first pass of this plan under-
represented the AI side by only citing `research/06` (self-learning
features). `research/08` and `research/09` extend this to the full set —
see §3a below and the dashboard's AI Feature Atlas panel for the complete,
detailed breakdown (~47 features across 8 functional categories, not 28
in one bucket).

## 1. The core architecture decision: paper/live parity

**Question researched:** is there an existing framework like OpenAlgo that
lets one strategy run in paper and live mode with zero code difference?

**Answer** (`research/02`, `research/03`): OpenAlgo does this genuinely (one
API surface, a mode toggle) but is a separate self-hosted web app (AGPL-3.0)
with a sandbox that its own docs admit doesn't model slippage/partial
fills/broker-specific RMS realistically. Of every alternative checked
(AlgoBulls, Streak, backtrader, vn.py, Jesse, Freqtrade, NautilusTrader,
QuantConnect LEAN), only **NautilusTrader** and **QuantConnect LEAN**
have a genuinely verified parity design, and only LEAN currently has a
maintained NSE/Zerodha broker adapter — at the cost of a C#/Python/.NET
Docker stack that doesn't fit this project's pure-Python, layer-by-layer
build style.

**Decision: build the broker-abstraction layer in-house.** A small
`BrokerClient` protocol (interface), implemented twice:
- `KiteBrokerClient` — talks to Zerodha Kite Connect for real
- `SimulatedBrokerClient` — fills orders against a realistic simulated
  exchange (see §1.2)

Every strategy calls only the `BrokerClient` interface. A single config
value (`TRADING_MODE=paper|live`) decides which implementation gets
constructed. This is exactly Freqtrade's `dry_run` flag pattern and
NautilusTrader's Data/Execution-client split (`research/02`) — both
verified-real mechanisms — reimplemented in pure Python with no
AGPL/GPL/LGPL license entanglement, so it stays ours to modify freely and
matches the existing `CLAUDE.md` constraint that the broker layer must
stay swappable.

### 1.1 Why not just adopt OpenAlgo / LEAN wholesale
- OpenAlgo: separate running service, AGPL-3.0, sandbox realism gap
  documented by the project itself, and this project's layer-by-layer
  build style (Rule A) doesn't compose well with adopting someone else's
  monolith mid-build.
- LEAN: genuinely the most rigorous parity design found, and worth
  revisiting later if the in-house layer turns out to be more work than
  expected — flagged as an open question in §8, not closed off.

### 1.2 The one gap every existing option has: realistic options fills

`research/07` §D flags this directly: options have much wider bid-ask
spreads than cash equity, especially far-OTM/illiquid strikes, and
OpenAlgo's own docs admit this isn't modeled. Our `SimulatedBrokerClient`
needs an explicit slippage/spread model for options fills from day one —
this is a design requirement for Layer 7 (Backtesting & Paper Trading),
not an afterthought.

### 1.3 Multi-leg orders are a first-class OMS concept, not N single orders

Per `research/07` §D: every spread/straddle/condor/butterfly must be
placed and squared off as one atomic logical unit with a shared strategy
tag — never as independently-tracked legs that could end up naked. This is
a hard design constraint on Layer 6 (Broker Integration & OMS).

### 1.4 Continuous 24/7 operation: paper trading never stops

**You asked for this directly**: NSE only trades ~9:15 AM-3:30 PM IST on
weekdays, but paper trading, learning, and research should run
continuously — 24/7, the way crypto bots never stop since crypto markets
never close — and paper trading must keep running even after the system
switches into live trading with real capital.

**Research finding** (`research/26`): no existing open-source project
does this out of the box. Crypto bots (Freqtrade, Jesse, OctoBot) run
24/7 trivially because their markets never close — none has ever needed
a "market shut → replay instead" branch. NSE/Kite hobby bots checked
(`aayushpandey01/AI-Quant-Trading-Platform`, `bhanukaranwal/Options-Trading-Bot`)
confirmed the opposite of what's needed: their paper trading follows
live's market-hours schedule and simply stops when NSE closes.
Institutional engines (NautilusTrader, QuantConnect LEAN, vn.py) solve
the *code-parity* half well (identical strategy code across backtest/
paper/live via a swappable data-feed) but leave the *when to swap*
decision manual — nothing auto-detects "NSE just opened, switch now."
**This is a genuine architecture gap this project builds itself, not
adopts.**

**Decision: a `MarketClock`-gated `DataSourceRouter` in front of
`BrokerClient`.**

- A single `MarketClock` component (NSE calendar: 9:15-15:30 IST, Mon-Fri,
  minus holidays) is the only thing that knows whether "now" is inside a
  live session.
- A `DataSourceRouter` exposes one interface (`get_next_tick()`/
  `subscribe()`) to every downstream consumer — strategy code, the
  learning loop, the paper-trading engine. It never leaks whether a tick
  came from Kite's live WebSocket or historical replay.
- **When closed**: the router serves a `HistoricalReplaySource` streaming
  stored NSE tick/bar data at configurable speed — real-time for realism
  drills, accelerated/max-speed for bulk learning throughput (following
  `Vishwesh28/nse-market-simulator`'s three-speed pattern, `research/26`)
  — looping across different historical days/regimes so the learning
  loop never idles.
- **When open**: the router drains the replay source and subscribes the
  same interface to Kite's live feed — the "seamless handoff" this
  research found no existing project solving automatically.
- **Paper trading and live trading are two independent consumers of the
  router, each with its own `BrokerClient` instance and its own
  ledger/capital pool.** Paper's balance is purely simulated and dynamic
  (relaxed, for experimenting with every AI feature/finding/research
  result). Live's is the real Kite account — small, limited capital, and
  it additionally gates on `MarketClock == open` before submitting any
  real order (this project's non-negotiable: real capital only during
  actual NSE hours, handled with maximum caution). **Paper trading has no
  such gate and never stops** — it keeps consuming whatever the router is
  currently serving (replay when closed, the same live Kite feed when
  open, so paper never diverges from live reality during market hours
  either).
- This is the concrete, buildable version of the concurrency rule you
  specified: live trading (careful, capital-protected, limited capital)
  and paper trading (always-on, relaxed, dynamic virtual capital, the
  permanent sandbox for testing every AI feature/finding/learning result)
  run **simultaneously, always** — never either/or.

**What this changes about Layer 7**: Backtesting & Paper Trading is no
longer only a pre-live validation gate — it becomes an **always-on
service** that starts when the system starts and never stops, with the
`MarketClock`/`DataSourceRouter` as new first-class components of that
layer, feeding both the continuous learning loop (Layer 10) and whichever
strategies are currently in paper mode.

## 2. Dashboard plan

Base tier (build alongside Layer 9):
- Live positions, orderbook/tradebook, day/strategy/instrument P&L
- Paper-vs-live mode indicator (impossible to accidentally not know which
  mode you're in)
- Risk metrics: margin utilization, current drawdown, per-strategy
  exposure
- Per-strategy on/off toggles
- Order/audit log, searchable

Advanced tier (build once Layer 10/11 exist):
- AI self-explanation panel — plain-language "what it learned today and
  why it traded as it did" (feature #11 in `research/06`)
- Research-agent findings feed (feature #1)
- Knowledge-graph browser for memory/reflection (features #3, #23)

Reference for feature ideas, not adoption target: OpenAlgo's dashboard
ships real-time positions/orderbook/P&L, WebSocket quote/order streaming,
and 12 options-analytics tools (Greeks, IV Smile, Max Pain, GEX) —
`research/03`. Worth matching that options-analytics feature list even
though we're not adopting the underlying app.

**Tech stack: decided — full React SPA** (§8a.2), not server-rendered.

**Sequencing, confirmed by you this pass**: for now, the build console
artifact (already published) grows a "Live Output" panel that runs real,
implemented code and shows genuine output — starting with Layer 1's actual
instrument-classification output, nothing mocked. Once the full layer
roadmap is implemented, a real running Layer 9 web app (per this section)
replaces/extends it as the actual trading dashboard.

## 3. Full feature menu (the "decide everything first" list)

Every feature is catalogued, tiered (⭐ your examples · ✅ common ·
🚀 advanced · 🌌 ultra-advanced), and cited to real sources. Nothing here
is built yet — this is the menu Layer 3/4/10/11 will be built from,
one item at a time, per Rule A.

| Domain | File | What's in it |
|---|---|---|
| Technical indicators | `research/07` §A | ~40 indicators across trend/momentum/volatility/volume/breadth/options/pattern/statistical/microstructure |
| Trading strategies | `research/07` §B | Trend-following, mean-reversion, stat-arb, relative-strength, event-driven, scalping, systematic/quant, portfolio-level |
| Option order types | `research/07` §C-D | Every atomic PE/CE action plus every 2-leg/multi-leg/arbitrage combination, and how each maps to real order placement |
| Self-learning AI features | `research/06` | 28 features from your examples (web research, pattern mining, knowledge mapping, memory recall, reasoning traces) through frontier items you hadn't named (bi-temporal fact invalidation, causal trade-outcome analysis, graph-grounded multi-agent debate, federated cross-strategy learning) |
| Adaptive-learning architecture | `research/01` | The 4 candidate architecture plans, ranked; Plan 2 (Memory-Augmented Hybrid) recommended as the near-term target, Plan 3 (LLM-Strategist) as the deferred frontier, Plan 4 (fully autonomous self-modifying live agent) explicitly ruled out |
| Which AI/ML techniques are actually production-proven vs. hype | `research/04` | Per-technique verdicts with 2025-2026 sources |
| Real open-source projects to draw inspiration from | `research/05` | GPT-Researcher, STORM, FreqAI, Qlib/DoubleAdapt, RD-Agent-Quant, Graphiti, Cognee, Mem0, Vibe-Trading, Reflexion, Voyager, TradingAgents — with 8 concrete "advanced version of X" proposals |
| Broker/paper-live framework landscape | `research/02`, `research/03` | Why in-house, full comparison table |
| AI beyond self-learning (multi-modal, alt-data, RAG copilot, LLM code-gen, GNNs, auto-reporting) | `research/08` | 7 new categories researched with sources; alt-data and GNNs explicitly researched-then-deprioritized (not skipped) for India/retail scope |
| **Top-level AI feature atlas (all categories, consolidated)** | `research/09` | **The answer to "how many AI features are there, really": ~47 features across 8 functional categories (Signal/Prediction, Execution, Risk/Compliance, Interface/Copilot, Generative/Code, Research/Learning, Portfolio/Meta, Frontier/Deprioritized) — read this one first for the full AI picture** |
| NSE microstructure claims, evidence-checked (52-week high, circuit dynamics, GIFT Nifty, index lead-lag, pre-open auction) | `research/10` | Separates real/evidenced from folklore/unverified for 5 specific retail claims |
| NSE time-of-day session behavior & strategy playbook | `research/11` | U-shaped volatility confirmed; incoming NSE Closing Auction Session (2026-08-03) flagged as untested territory |
| External knowledge → validated hypothesis pipeline | `research/12` | How to turn books/blogs/forum claims into memory *without just believing them* — LLM extracts structure only, a deterministic DSR/CPCV pipeline judges truth |
| NSE scanner/filter taxonomy (52-week high is one of ~30) | `research/13` | Full filter categories incl. F&O-native OI-buildup matrix, MWPL ban list, delivery %, bulk/block deals — plus which of this data Kite Connect actually provides |
| **Trade log data schema** (every column, cash vs. options) | `research/14` | Full trade-record schema so every open/closed trade carries enough data for later AI pattern-mining — shared columns, cash-only columns, options-only columns (Greeks/IV/decay). Corrects `research/13`: Kite Connect **does** provide historical OI via `oi=1` |
| NSE/Kite bot projects — what to borrow | `research/16` | PKScreener, NSE-Stock-Scanner, algo_trading_strategies_india, and 7 more — puzzle pieces + upgrade paths |
| Options-engine projects — what to borrow | `research/17` | vollib, optionlab, options_backtester, and 7 more — Greeks/IV/multi-leg puzzle pieces |
| Autonomous AI agent projects — what to borrow | `research/18` | ai-hedge-fund (62k★), qlib, swarm-trader, and 6 more — includes the strongest human-gate mechanism found in any research pass |
| Cash-intraday scanner/data projects — what to borrow | `research/19` | NseIndiaApi, eod2, pandas-ta-classic, vectorbt, and 6 more — closes the Layer 2 data gap directly |
| Risk/compliance/market-data infra — what to borrow | `research/15` | Riskfolio-Lib, PyPortfolioOpt, immudb, QuestDB, vnpy's RiskManager — Layer 5/9/2 pieces |
| **Consolidated action plan — 41 projects, 12 top picks** | `research/20` | **Read this one first**: which pieces to borrow, license map, all "found, wasn't asked" ideas, ranked read-next list |
| Ultra-advanced self-learning agents, round 2 (no license filter, incl. PyPI) | `research/21` | MATS (self-patching multi-agent, anti-pattern memory), Darwinia (adversarial-arena GA engine), Moss (±30% bounded-drift rule), LangGraph, Avalanche, LightRAG — the most concrete self-learning mechanisms found in any pass so far |
| Frontier self-improving AI beyond MATS | `research/22` | **Darwin Gödel Machine now supersedes MATS** as the most advanced self-modifying-agent reference; OpenEvolve, Eureka, SEAL/SPIN, OpenHands, ADAS, Absolute Zero Reasoner |
| Connecting/integration frameworks | `research/23` | eliza, AGiXT, Hummingbot, OpenBB, OpenHands — the "wire the pieces together" layer; two independent ecosystems (eliza, AGiXT) converge on the same human-gate pattern as swarm-trader |
| Automated feature/indicator discovery | `research/24` | gplearn, DEAP, tsfresh, AlphaGen — a real pipeline for machine-discovered indicators, all routed through the hypothesis-validation gate, none privileged |
| **Final sweep synthesis — ~90 projects across 16 research passes** | `research/25` | **Read this one for the closing picture**: overall top-5 ranked, why the Darwin Gödel Machine reinforces the human-gate requirement |
| Remaining self-learning categories (meta-learning, active learning, federated learning, synthetic data, explainability, cognitive architectures, curriculum learning, novelty detection, quality-diversity) | `research/27` | learn2learn, modAL/baal, Flower/PySyft, ydata-synthetic (TimeGAN), Captum/InterpretML, Soar/ACE, PyOD, pyribs — closes every "described but never matched to a project" gap in `research/06`'s 28-feature taxonomy |
| **24/7 continuous market replay + seamless live handoff** | `research/26` | **No existing project does this — a genuine architecture gap this project builds itself.** Full recommended design: `MarketClock`-gated `DataSourceRouter`, paper trading as an always-on independent consumer that never stops, even during live trading |
| **v1 shortlist deep evidence re-check** | `research/28` | Re-verified PKScreener/NSE-Stock-Scanner/AI-trader for concrete backtest numbers (only AI-trader has any, ~50-trade self-reported sample); confirms §7's shortlist as-is **plus adds ADX** as a regime-gate indicator; flags Iron Condor as a v1.1 (not v1) once both credit-spread directions are validated |

### 3a. The AI layer, by function (not just "Layer 10/11")

`research/09` reorganizes every AI feature found across all research
passes by what it *does*, since "Memory & Reflection" and "Strategic LLM"
are pipeline-position labels, not a feature count:

| Category | Count | Headline items | Lands in layer |
|---|---|---|---|
| A. Signal & Prediction AI | 7 | GBM ensembles, HMM regime detection, vision-LLM chart reading, RL signal-gen (academic-only) | 3, 4, 10 |
| B. Execution AI | 2 | RL order-slicing (JPMorgan LOXM precedent), gamma-scalping automation | 6 |
| C. Risk & Compliance AI | 5 | Drift detection, adversarial-validation trip wire, SEBI-narrative auto-report, explainable audit trail | 5, 10 |
| D. Interface & Copilot AI | 4 | Self-explanation panel, RAG trade-copilot ("why did you take this trade"), auto narrative reports | 9, 10 |
| E. Generative / Code AI | 3 | LLM-assisted strategy drafting (human-gated), autonomous factor R&D, full self-rewriting (ruled out) | 10, 11 |
| F. Research & Learning AI | 28 | Full self-learning taxonomy — see `research/06` | 10, 11 |
| G. Portfolio & Meta AI | 2 | HRP capital allocator, meta-learning across strategies | 10 |
| H. Frontier / Deprioritized | 4 | Synthetic diffusion data, LLM market simulators, alt-data (India-thin), vocal-tone analysis | 11 / declined |

### 3b. The hypothesis-validation pipeline — how external knowledge earns trust

You asked for the AI to read books/articles/blogs/community discussion
about NSE strategies and turn it into memory. `research/10` is the reason
this can't mean "believe what it reads": widely-repeated NSE claims (the
circuit "magnet effect," GIFT Nifty's quoted accuracy %, pre-open auction
predicting the day) turned out to be unverified or actively contradicted
by the one study that exists. `research/12` researches real prior art for
this exact problem (Quantpedia's paper-to-backtest pipeline is the closest
production analog) and proposes the mechanism:

1. An LLM extracts a **structured hypothesis** from source text — it never
   judges whether the claim is true, only its shape (condition, predicted
   effect, instrument, timeframe, direction). This closes a real risk
   `research/12` surfaced: an LLM asked to judge a historical claim may
   already know market history from pretraining, a lookahead-bias vector
   distinct from ordinary backtest overfitting.
2. Every extracted hypothesis is tagged `untested`, then run through the
   **same DSR/CPCV gate** already planned for internally-derived strategies
   (`research/01`), and only promoted to `confirmed` if it survives — with
   a *harder* significance bar than internally-derived factors, since a
   near-unbounded blog/forum corpus inflates the number of trials.
3. Hypotheses carry provenance (source, extraction date, raw claim) and a
   validation status that can later flip to `decayed` on re-test — none
   of the memory frameworks already researched (Graphiti/Cognee/Mem0,
   `research/05`) ship this schema natively, so it's a deliberate addition
   to Layer 10's knowledge graph, not an afterthought.
4. `research/10`'s five graded claims are the pipeline's natural first
   backlog once built — they're already extracted and partially graded.

This is a concrete mechanism for `research/06` feature #1 (autonomous
web-research agent) and feature #2 (win/loss pattern mining) — those were
described in general terms before; this is how they actually avoid
laundering blog folklore into false confidence. Lands in Layer 10.

### 3c. NSE-specific feature/filter library and a Layer 2 data-source gap

`research/13` catalogues the full scanner-filter taxonomy your two examples
(52-week breakout, circuit proximity) belong to — price-level, volume,
F&O-native (OI buildup matrix, MWPL ban list), relative-strength,
technical-pattern, options-flow, and corporate-action filters. Most of it
is real and shipped in production Indian tools (Chartink, Sensibull) today.

**Concrete Layer 2 (Market Data) design constraint surfaced by this
research**: Kite Connect's historical API has **no historical Open
Interest field and no delivery-% field at all** — both would need separate
ingestion from NSE's public bhavcopy/security-wise-delivery/bulk-deal
reports, not from Kite. Several of the most exchange-authentic filters
(OI buildup classification, F&O ban list, delivery %, bulk/block deals)
depend on this data. Layer 2 needs an explicit decision on whether to
build this secondary ingestion now or defer it — flagged as an open
question in §8.

`research/11`'s time-of-day findings (real U-shaped volatility, the
incoming 2026-08-03 NSE Closing Auction Session) feed Layer 4 as a
regime-gating dimension, same caveat as above: every specific rule routes
through the §3b validation pipeline before being trusted, evidence grade
notwithstanding.

### 3d. Puzzle pieces to borrow, not build from scratch

You asked for a deep search of famous/advanced existing projects whose
features could be borrowed as "puzzle pieces" instead of building
everything from zero — read their READMEs, take what fits, upgrade it.
Five research passes (`research/15`-`20`) README-verified **41 real
projects**. The full picture is in `research/20`; the 12 highest-value
pieces, each mapped to a layer:

| Piece | From | Lands in |
|---|---|---|
| NSE bhavcopy/delivery-%/corporate-actions client | NseIndiaApi | Layer 2 |
| Incremental EOD sync + holiday calendar + split/bonus adjustment | eod2 | Layer 2 |
| 224-indicator pandas library | pandas-ta-classic | Layer 3 |
| Composable scanner DSL | PKScreener | Layer 3 |
| IV solver + closed-form Greeks | py_vollib | Layer 3/4 |
| Multi-leg Greeks/P&L data model | optionlab | Layer 4 |
| Greeks-aware risk-constraint architecture (Rust core) | options_backtester | Layer 5 |
| Kelly-criterion + 26-measure risk optimizer | Riskfolio-Lib | Layer 5 |
| Lot-size-aware discrete allocation | PyPortfolioOpt | Layer 5 |
| Config-driven paper/live mode-switching skeleton | Options-Trading-Bot | Layer 6 |
| **Code-enforced `validate_trade()` gate + research/production decoupling** | **swarm-trader** | **Layer 10/11 — the strongest human-gate mechanism found in any research pass this project has run** |
| Tamper-evident Merkle-tree audit ledger | immudb | Layer 9/10 |

**License** (informational only, per Rule E below — never a filter for
this personal-use project): spans MIT/Apache/BSD, GPL/AGPL, and
no-license-asserted repos; all are equally eligible to study and adapt.

**12 more "found, wasn't asked" ideas** are catalogued in `research/20`
(multi-account copy-trading, Ray-distributed backtesting, RL exit agents,
GEX/DEX/VEX dealer-exposure analytics, qlib's point-in-time MLOps,
agent-reputation marketplaces, a standardized agent-vs-index leaderboard,
vnpy's pre-trade order-flow throttle, Telegram-as-control-plane, and
more) — each is a deliberate scope decision, not an automatic addition.

### 3e. Round 2 — the most concrete self-learning mechanisms found yet

`research/21` re-swept the self-learning-AI space (this time including
PyPI directly, and explicitly not filtering by license — see the new Rule
E in `CLAUDE.md`). Two finds are more concrete than anything in
`research/06`/`18`: **MATS**'s anti-pattern-memory + per-symbol online
logistic regression (a real, running "learn from realized outcomes"
mechanism) and **Moss**'s ±30% bounded parameter-drift rule (a simple,
auditable guardrail against runaway strategy mutation). **Darwinia**'s
adversarial-arena GA engine gives `research/06` feature #22 (synthetic
stress rehearsal) a runnable reference implementation instead of only a
described concept. **LightRAG** is now the recommended ingestion-side
complement to Graphiti for Layer 10's memory substrate — Graphiti holds
temporal/episodic memory, LightRAG handles cheap incremental
knowledge-graph construction from bulk text. Every self-modifying pattern
found (MATS's self-patching agent, openfund-agent's code-modify-sandbox-
rollback loop) is a candidate mechanism to put *behind* this project's
human-gate, never a substitute for it — consistent with `research/01`'s
Plan 4 being permanently ruled out.

### 3f. Final sweep — the Darwin Gödel Machine and why the human-gate is right, not overcautious

`research/22` found the **Darwin Gödel Machine** (jennyzzt/dgm) — an
agent that literally rewrites its own codebase and empirically validates
each change, keeping an open-ended archive of variants. It supersedes
MATS as the most advanced self-modifying system found across every
research pass. Its own authors' README warns it executes untrusted
self-generated code and can behave destructively. **This is the strongest
evidence yet, from the creators of the most advanced system found, that
this project's human-gate requirement (`research/01`) is the correct
design, not excessive caution.** `research/23` found two independent
ecosystems (eliza, AGiXT) converging on the same mandatory-approval-node
pattern as `swarm-trader` (`research/18`) — three unrelated projects
landing on the same answer. `research/24` closes the loop on indicators:
gplearn/DEAP can propose candidate formulas and tsfresh can screen them,
but every discovered feature still enters the same hypothesis-validation
pipeline (`research/12`) as everything else — discovery earns no shortcut
around validation.

This closes the open-source research thread: 16 passes, ~90 projects
README/paper-verified, synthesized end-to-end in `research/25`.

## Rule E — license is not a filter (added to `CLAUDE.md`)

Per your explicit instruction: this project is personal, non-distributed
use, so no research pass excludes or downranks a project for its
license. Copyleft obligations trigger on distribution/hosting-as-a-
-service, not private use — revisit only if that status ever changes.
This is now documented as Rule E in the project's own `CLAUDE.md`, not
just in this plan.

## 4. Revised layer roadmap

| # | Layer | What's new/confirmed this pass |
|---|---|---|
| 1 | Universe & Instrument Registry | Unchanged — built, awaiting your sign-off |
| 2 | Market Data | **Decided (§8a.6, §8a.12)**: build secondary NSE ingestion now (historical OI, delivery %, bulk/block deals, MWPL ban list), and design it multi-broker from the start — Kite plus Upstox/Angel One/ICICI Direct/Groww APIs (user providing access next session), not Kite-only |
| 3 | Indicator / Feature Engineering | Build from `research/07` §A menu, one indicator family at a time |
| 4 | Strategy / Signal Engine | Build from `research/07` §B/§C menu; §7 below proposes a v1 shortlist |
| 5 | Risk Management | Must explicitly model per-combination margin (naked vs. recognized spread) and undefined-risk-leg detection, per `research/07` §D |
| 6 | Broker Integration & OMS | **Architecture decided in §1**: in-house `BrokerClient` protocol, `KiteBrokerClient` + `SimulatedBrokerClient`; multi-leg orders are one atomic unit (§1.3) |
| 7 | Backtesting & Paper Trading | Must include a realistic options slippage/spread model (§1.2); also hosts the curiosity-driven paper-mode exploration sandbox (`research/06` #18); **now an always-on service, not just a pre-live gate** — hosts `MarketClock`/`DataSourceRouter` for 24/7 continuous replay-when-closed operation (§1.4) |
| 8 | Session / Square-off Management | Square-off ordering must never leave a naked leg open, even for one tick, on multi-leg positions (`research/07` §D.4) |
| 9 | Dashboard, Monitoring, Logging & Alerting | Dashboard scope defined in §2 (folded in here rather than a separate layer) |
| 10 | Memory & Reflection | **Upgraded recommendation**: build on a Graphiti-style temporal knowledge graph from day one, not a plain vector store (`research/06`'s single biggest new finding) — hosts `research/06` features #1-22 plus atlas categories C/D/F/G (`research/09`) |
| 11 | Strategic LLM / Autonomous Research Agent | Deferred until Layer 10 is live and validated; hosts `research/06` features #23-28 plus atlas categories A/E/H's higher-risk items (`research/09`) |

## 5. How to test every layer's completion

Rule A already requires tests + a manual check + explicit sign-off before
advancing. Concretely, per layer type:

- **Data layers (1-3):** unit tests on transformation logic against fixed
  fixture data, plus a manual cross-check of computed indicator values
  against a known reference implementation (e.g. TA-Lib or pandas-ta on
  the same sample) so "the math is right," not just "the code runs."
- **Strategy/Signal (4):** historical backtest → walk-forward validation →
  Deflated Sharpe Ratio + CPCV gate (`research/01`) before any candidate
  is even allowed into shadow/paper mode. No strategy reaches live capital
  without clearing this gate.
- **Risk (5):** one test per guardrail (margin breach, max position size,
  undefined-risk-leg detection), plus adversarial tests that deliberately
  try to construct a position that breaks a guardrail.
- **Broker/OMS (6):** the same strategy code run against
  `SimulatedBrokerClient` and a mocked `KiteBrokerClient` must produce
  identical order-intent sequences; a dedicated test simulates a
  partial-fill/one-leg failure on a multi-leg order and confirms atomic
  handling (no accidental naked leg).
- **Backtesting/Paper (7):** compare simulated fills against the slippage
  model's expected bounds; require a multi-week shadow/paper run,
  reviewed by you, before any layer-8+ live wiring is considered.
- **Session/Square-off (8):** forced-failure tests — simulate a broker
  outage or network drop right at square-off time — confirm no position
  is ever left open.
- **Dashboard/Monitoring (9):** manual UI walkthrough of every panel, plus
  alert-firing tests (inject a fake breach condition, confirm the alert
  actually fires).
- **Memory & Reflection (10):** retrieval-accuracy check against a
  hand-labeled set of "situations that should be found as similar";
  confirm invalidation actually marks old facts superseded rather than
  deleting or ignoring them; every nightly reflection output must be a
  reviewable diff, not a silent update.
- **Strategic LLM (11):** every debate/reasoning trace is checked for
  hallucinated citations (does it actually reference a real memory node?)
  before its output is trusted; latency and per-decision LLM cost are
  budgeted and monitored, since this layer runs on a slow cadence by
  design (never in the tick-level hot path, per `research/01`).

## 6. Non-negotiables carried into this plan (unchanged from `CLAUDE.md`)

Intraday-only, auto-square-off, broker-swappable, self-describing names,
living flowchart notes, research-to-file discipline, SEBI white-box
constraint (nothing self-modifies live logic without human sign-off — this
is why Plan 4 in `research/01` stays permanently off the table, and why
every AI feature in `research/06` above the ✅ tier lists a human gate).

## 7. Proposed v1 shortlist (recommendation, not a decision)

Building "all ~40 indicators and every option combination" before writing
a single strategy would violate Rule A (one layer at a time) and produce
nothing testable for a long time. Recommended v1 slice, open for your
edits:

- **Indicators:** EMA, RSI, Supertrend, VWAP, ATR, IV Rank, PCR — enough to
  build one directional and one income strategy.
- **Strategies:** Opening-Range Breakout (directional, cash or index
  futures-equivalent via options) + a Bull Put / Bear Call credit spread
  (income, defined-risk options strategy) — one from each of section B and
  section C of `research/07`, deliberately avoiding any undefined-risk
  naked-option strategy in v1.
- **AI layer:** none in v1 — Layers 3-9 should exist and be validated
  before Layer 10 starts, per the existing roadmap ordering.

**Re-checked and confirmed** in `research/28` (deeper evidence pass on
request), with one addition: add **ADX** to the indicator list as a
trend/range regime gate deciding which of the two v1 strategies runs on a
given session. Iron Condor is flagged as the natural v1.1 (not v1) once
Bull Put and Bear Call are each independently validated.

## 9. Prediction-Labeled Trade Tables — the Falsification-Driven Paper Lab (adopted 2026-07-23)

User's core concept, expanded and adopted (full design + taxonomy:
`research/29`). The Layer 7 paper engine is not one portfolio: it is an
**experiment allocator** across prediction-labeled open-trades tables,
and every trade carries an immutable PredictionRecord written BEFORE
entry.

**The tables:**
| Table | Role |
|---|---|
| CONFIDENT-WIN | trades predicted profitable, with reasons — the deployable-edge candidate pool |
| CONFIDENT-LOSS | trades deliberately opened to LOSE, each targeting a named failure mechanism — proves causal understanding of losing (its predictions "win" when its trades lose) |
| UNCERTAIN | near-50% / novel-reason trades — active learning; graduation source for both tables |
| RANDOM-CONTROL 🚀 | coin-flip null baseline; also feeds the DSR gate's null distribution |
| SHADOW-REJECTED 🚀 | virtual tracking of risk-gate rejections — evidence-tunes Layer 5 config |
| ADVERSARIAL 🌌 | self-play policy hunting the WIN-model's blind spots |
| INVERSE-HARVEST 🌌 | auto-mirrors of well-calibrated LOSS trades (where inversion is valid) |

**PredictionRecord (per trade, immutable at open):** predicted outcome,
calibrated win-probability, expected R if right / loss if wrong, named
machine-readable reasons, predicted exit cause; (ultra: path bounds,
P&L distribution).

**Scoring:** per-table hit rates; Brier score/log-loss calibration;
reliability curves per regime/strategy; a per-reason evidence ledger;
(ultra: single-reason interventional trades, CRPS).

**Learning integration:** every closed experiment becomes a Layer 10
memory node; nightly reflection diffs the reason ledger; the
promotion/demotion ladder (UNCERTAIN -> WIN/LOSS -> DSR/CPCV -> human
sign-off) is the ONLY path to live-capital candidacy; research/12's
hypothesis pipeline runs double-sided (trade the claim AND its negation).

**Guardrails:** all tables paper-only; LOSS/RANDOM/ADVERSARIAL arms
permanently barred from live; every table's trades still pass the Layer
5 risk gate with paper budgets; predictions append-only.

**Build order:** base tier (WIN/LOSS/UNCERTAIN + PredictionRecord +
scoreboard) lands WITH Layer 7; advanced arms in 7.5; ultra tier fuses
with Layer 10. Trade-log schema (research/14) gains the
PredictionRecord fields from day one.

## 10. Self-Generated Core Concepts — the adopted institution (2026-07-23)

Product of the generate->critique->generate ideation loop the user
requested (full loop, including killed ideas and reasons: `research/30`).
Unifying frame: the bot as a **self-auditing scientific institution** —
adversarial departments that keep each other honest, so the system
cannot easily fool itself (the root failure mode of self-learning
traders).

**Adopted, with build order:**
- **With Layer 7 base:** per-trade pre-committed KILL CRITERIA
  (thesis-falsification exits beyond stops; new PredictionRecord field);
  CALENDAR-CONDITION partition key on every table/ledger (expiry days,
  event days, ban-heavy days are different games); REFEREE v0
  (decision-reproduction audits — re-derive yesterday's decisions from
  logs, flag divergence); mechanism-name field groundwork.
- **Layer 7.5:** SKILL-vs-LUCK COURT (verdicts SKILL-WIN / LUCKY-WIN /
  UNLUCKY-LOSS / DESERVED-LOSS from outcome x mechanism-manifestation x
  provenance; learning trains ONLY on the diagonal — lucky wins are
  never reinforced); LOSS EPIDEMIOLOGY (structured death certificates
  -> outbreak detection -> auto-distilled veto antibodies);
  WORLD-MODEL SCOREBOARD (trade-independent market forecasts scored
  like a weather station — splits perception error from action error);
  PER-TRADE PRE-MORTEM (entry-time Monte Carlo of THIS setup through
  regime-matched replay paths); PROFIT PROVENANCE (P&L decomposed
  against §9 control arms: edge/luck/costs/regime/timing).
- **Layer 10:** ASSUMPTION REGISTRY (every strategy declares its silent
  assumptions; each gets a statistical tripwire; broken assumption ->
  downstream flagged/paused before P&L shows it); OPPONENT LEDGER
  (every trade names the counterparty thesis, checked against NSE's
  daily participant-wise OI — requires adding that report to Layer 2's
  ingestion set); INFORMATION DIET accounting; prediction-market
  council weighting (parked until the council exists).

**Killed/parked register** (kept deliberately): ghost-portfolio family
(combinatorial cost; shadow arm + provenance cover 80%), internal
prediction market (premature pre-council), immune-system framing
(folded into epidemiology), attention economics (vague), deception
detection (thin at retail scale), self-impact mirror (irrelevant at
this size), synthetic nightmares (already Plan 3 stress rehearsal).

## 8a. Decisions log (resolved 2026-07-23)

All 12 open questions below have been answered. Resolutions:

1. **Architecture**: confirmed — in-house `BrokerClient` (§1), not LEAN.
2. **Dashboard stack**: **full React SPA** (not server-rendered HTMX) for
   the eventual Layer 9 trading dashboard.
3. **v1 shortlist**: confirmed in principle, **plus a deeper research
   pass requested** on stronger/additional candidates — see §7 update
   below.
4. **Layer 10 memory substrate**: deferred — decide right before Layer 10
   starts, per the original recommendation.
5. **Layer 1 sign-off**: **implementation resumes next session with the
   Fable 5 model** — sign-off itself to be finalized then.
6. **Layer 2 data sourcing**: confirmed — build secondary NSE ingestion
   (historical OI, delivery %, bulk/block deals, MWPL ban list) now, as
   part of Layer 2, not deferred.
7. **Hypothesis-validation pipeline**: confirmed — build as part of Layer
   10 as originally planned, not pulled earlier.
8. **Puzzle pieces (`research/20`)**: confirmed — decide per-layer as
   each layer's turn comes up, not committed to en masse now.
9. **Found-not-asked ideas**: confirmed — decide later, per-idea, as each
   becomes relevant, not scoped in or declined wholesale now.
10. **Darwin Gödel Machine / OpenEvolve-style logic evolution**: deferred
    entirely to Layer 10/11, per the existing roadmap ordering.
11. **24/7 continuous-replay architecture (§1.4)**: **confirmed** — the
    `MarketClock`-gated `DataSourceRouter` design is locked in.
12. **Replay-store data sourcing**: confirmed — reuses Layer 2's planned
    NSE data ingestion, **and is now multi-broker, not Kite-only**: the
    user will provide additional data-source APIs (Upstox, Angel One,
    ICICI Direct, Groww) alongside Kite Connect for sourcing historical/
    replay data, expected next session. This extends `CLAUDE.md`'s
    existing "broker-integration layer must stay swappable" constraint
    from execution to data sourcing as well — Layer 2's data-ingestion
    design should treat Kite as one of several interchangeable sources,
    not the only one, for anything feeding the replay store specifically.

13. **Broker scope for the build-out (decided 2026-07-23):** Kite-only
    until all layers are complete — Upstox/Angel One/ICICI/Groww adapters
    and their session automation are deferred to a post-completion pass,
    not built per-layer. The swappable protocols stay (Kite remains one
    implementation behind them), so adding the other brokers later is
    additive, not a refactor.

14. **Full-universe mandate (user directive, 2026-07-23, before Layer
    5):** every layer must be designed AND verified across the entire
    phase-1 universe — 2,000+ NSE cash equities intraday, options on all
    5 indices and all ~210 stock-option underlyings, with ATM/ITM/OTM
    moneyness as a first-class concept — never validated only against
    NIFTY/RELIANCE-style samples. Implemented immediately:
    `option_moneyness_classifier` (ladder-step-aware ATM/ITM/OTM) and a
    215/215-underlying breadth sweep of the IV/PCR/spread pipeline
    (documented in `flowcharts/04`). Layer 5+ must include a breadth
    verification pass alongside any single-symbol spot-check.

## 8. Open questions for you to decide

**All 12 below are now resolved — see §8a for the decisions log. Kept
here, unedited, as the historical record of what was asked, per Rule B
(never delete, only append).**

1. **Architecture:** confirm the in-house `BrokerClient` decision (§1), or
   do you want a hands-on evaluation of QuantConnect LEAN +
   `Lean.Brokerages.Zerodha` first, given it's the only option with a
   verified working NSE adapter?
2. **Dashboard stack:** simple server-rendered (Flask/FastAPI + HTMX) or a
   full React SPA like OpenAlgo's?
3. **v1 shortlist (§7):** confirm, or swap in different indicators/
   strategies to start with?
4. **Layer 10 memory substrate:** Neo4j, FalkorDB, or a lighter embedded
   graph store — this can be decided later, right before Layer 10 starts,
   but flagging it now since `research/06` recommends deciding it before
   any memory code is written, not retrofitting.
5. Separately from this whole planning pass: **do you still sign off on
   Layer 1**, so Layer 2 can start once this discussion concludes?
6. **Layer 2 data sourcing (`research/13`):** build secondary ingestion for
   NSE data Kite Connect doesn't provide (historical OI, delivery %,
   bulk/block deals, MWPL ban list) now as part of Layer 2, or defer until
   a strategy that actually needs one of these is queued up?
7. **Hypothesis-validation pipeline (`research/12`):** build this as part
   of Layer 10 as planned, or pull it earlier since `research/10`'s five
   graded NSE claims are ready to serve as its first real test case?
8. **Puzzle pieces (`research/20`):** which of the 12 top borrowable
   pieces do you want to commit to adapting when their layer comes up,
   vs. treating purely as reference while building from scratch?
9. Do you want the found-not-asked ideas (multi-account copy-trading,
   Telegram control-plane, Ray-distributed backtesting, etc., full list in
   `research/20`) scoped into the plan, or explicitly declined the way
   `research/09`'s category H items were?
10. **Darwin Gödel Machine / OpenEvolve-style logic evolution
    (`research/25`):** explore as a bounded, sandboxed, paper-mode-only
    research thread once Layer 7 exists, or defer entirely to Layer 10/11
    per the existing roadmap?
11. **24/7 continuous replay architecture (§1.4, `research/26`):** confirm
    the `MarketClock`-gated `DataSourceRouter` design — this is a new,
    non-trivial piece of Layer 7's scope, so worth an explicit sign-off
    before it's treated as settled, the same way Layer 1 needs sign-off.
12. **Replay-store data sourcing**: the router's `HistoricalReplaySource`
    needs a store of NSE historical tick/bar data for both segments to
    replay from — does this reuse Layer 2's planned data ingestion
    (`research/13`/`14`/`19`'s NseIndiaApi/eod2 pieces), or does it need
    its own dedicated acquisition/storage pass?
