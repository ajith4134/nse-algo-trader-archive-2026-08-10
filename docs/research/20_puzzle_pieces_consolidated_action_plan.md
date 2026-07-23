# 20 — Puzzle Pieces to Borrow: Consolidated Action Plan

You asked to treat this project like a puzzle — find famous/advanced
existing projects, read their READMEs, take the feature "pieces" worth
having instead of building from scratch, and upgrade each into an
ultra-advanced version fitted to this project. Five parallel research
passes (`research/15`-`19`) found and README-verified **41 real projects**
across NSE/Kite-specific bots, options engines, autonomous AI agents,
cash-intraday scanners, and risk/compliance/market-data infrastructure.
This file is the synthesis: what to actually borrow, in what order, and
what genuinely new ideas surfaced that weren't part of the original ask.

**Status: research + planning only. Nothing borrowed, vendored, or
implemented yet.** Every recommendation below still goes through Rule A
(one layer at a time, verify before advancing) — this file changes *how*
a layer gets built (borrow-and-adapt vs. from-scratch), never the build
order itself.

## The 12 highest-value pieces, mapped to layers

| # | Piece | From | Lands in | Why it's worth borrowing |
|---|---|---|---|---|
| 1 | NSE bhavcopy + delivery % + corporate-actions client | `BennyThadikaran/NseIndiaApi` (`research/19`) | Layer 2 | Solves exactly the Kite Connect data gap `research/13`/`14` identified — the hardest part (endpoint mapping, cookie/session handling) is already done |
| 2 | Incremental EOD sync + holiday calendar + split/bonus adjustment | `BennyThadikaran/eod2` (`research/19`) | Layer 2 | The single hardest-won piece of NSE data plumbing in this whole sweep — do not re-derive from scratch |
| 3 | 224-indicator pandas library | `xgboosted/pandas-ta-classic` (`research/19`) | Layer 3 | Shortcuts nearly all of `research/07` §A in one MIT-licensed import |
| 4 | Composable scanner DSL ("pipes") | `pkjmesra/PKScreener` (`research/16`, `19`) | Layer 3 | Closest existing precedent for `research/13`'s filter taxonomy as executable code |
| 5 | IV solver + closed-form Greeks | `vollib/py_vollib` (`research/17`) | Layer 3/4 | Numerically robust, standalone, MIT — the math core every options feature in `research/14` needs |
| 6 | Multi-leg Greeks/P&L data model | `rgaveiga/optionlab` (`research/17`) | Layer 4 | Directly matches `research/07` §C/D's "spread as one unit" requirement |
| 7 | Greeks-aware risk-constraint architecture (Rust core) | `lambdaclass/options_backtester` (`research/17`) | Layer 5 | Best-engineered `MaxDelta`/`MaxVega`-as-first-class-object pattern found |
| 8 | Kelly-criterion + 26-measure risk optimizer | `dcajasn/Riskfolio-Lib` (`research/15`) | Layer 5 | Deepest open risk-measure catalogue available; feeds `research/14`'s planned Kelly-fraction position sizing |
| 9 | Lot-size-aware discrete allocation | `PyPortfolio/PyPortfolioOpt` (`research/15`) | Layer 5 | Converts continuous portfolio weights into NSE-lot-size-legal share/lot quantities |
| 10 | Config-driven paper/live mode-switching skeleton | `bhanukaranwal/Options-Trading-Bot` (`research/17`) | Layer 6 | Closest existing analog to this project's own `BrokerClient` design (`PLAN.md` §1) |
| 11 | Code-enforced `validate_trade()` gate + research/production decoupling | `zhound420/swarm-trader` (`research/18`) | Layer 10/11 | The single best concrete mechanism found anywhere for the SEBI white-box human-gate requirement — operationalizes what `research/01` only argued for in the abstract |
| 12 | Tamper-evident Merkle-tree ledger | `codenotary/immudb` (`research/15`) | Layer 9/10 | A ready-made, production-grade audit trail instead of a bespoke hash-chain — directly serves the SEBI Algo-ID audit requirement |

## License map (informational only — not a filter, per Rule E)

Per `CLAUDE.md` Rule E: this project is personal, non-distributed use, so
no project below is excluded or downranked for its license. License is
noted here purely as forward-looking information — it becomes relevant
only if this project's status ever changes (distributed, hosted, sold,
open-sourced), at which point every borrowed piece gets revisited.

- **MIT/Apache/BSD**: pandas-ta-classic, vollib, PKScreener,
  options_backtester, PyPortfolioOpt, Options-Trading-Bot, immudb,
  virattt/ai-hedge-fund, qlib, AutoHedge, AgenticTrading (OpenMDW-1.0).
- **GPL/AGPL** (fully usable for this project's personal-use scope):
  optionlab, optopsy, stock-pattern, NseIndiaApi, eod2, backtesting.py,
  lumibot.
- **No license asserted**: NSE-Stock-Scanner, algo_trading_strategies_india,
  next-gen-algo-trading-bot, AI-trader, trading_with_shoonya, nifty_bot,
  HKUDS/AI-Trader, swarm-trader, jugaad-data ("LICENSE.YOLO.md" — worth
  reading the actual terms out of curiosity, not out of a usage
  restriction for this project).
- **Dead ends** (a code-quality/maintenance issue, not a license one):
  `naveen7v/Bhavcopy` (broken by NSE site changes), `Kite-Trader` and
  `hjAlgos` (stale, thin) — still not worth building on, but for
  maturity reasons, not licensing.

## All "found, wasn't asked" items, consolidated

These are genuinely new ideas/features across all five passes that
weren't part of this project's existing plan — each is a deliberate
decision point, not an automatic addition:

1. **Multi-account capital-proportional copy-trading** (`research/16`) —
   not in the current layer list at all; a scope decision for Layer 6.
2. **Ray-cluster distributed backtesting** (`research/16`) — relevant once
   the strategy menu grows large enough that sequential backtesting is a
   bottleneck.
3. **RL-based exit agents** (learn when to cut winners/losers, vs. static
   SL/target) (`research/16`) — a different paradigm from this project's
   existing RL-for-execution research (`research/09` category B).
4. **Telegram-as-remote-control-plane** (status, live param tuning, kill
   switch) (`research/16`, `19`) — recurs across three independent
   projects; worth considering as a standard ops interface alongside
   Layer 9's dashboard.
5. **GEX/DEX/VEX dealer-exposure analytics** and **pysabr/SSVI**
   arbitrage-free vol-surface fitting (`research/17`) — index-options
   skew/dealer-positioning signals adjacent to but distinct from
   `research/13`'s Max Pain/OI filters.
6. **qlib's point-in-time database + auto-rolling online serving**
   (`research/18`) — production MLOps rigor not currently in the plan;
   directly extends `research/12`'s validation-status/decay design.
7. **AI-Trader's reputation-weighted copy-trading marketplace**
   (`research/18`) — relevant only if multiple independently-evolved
   strategies ever compete for capital (ties to `research/09` category
   G's HRP allocator).
8. **AgenticTrading's standardized agent-vs-index leaderboard**
   (`research/18`) — a complementary evaluation layer, distinct from this
   project's DSR/CPCV statistical gate.
9. **swarm-trader's explicit research/production decoupling**
   (`research/18`) — the strongest single finding of this entire sweep;
   see piece #11 above.
10. **eod2's market-breadth/PE-alert module** (`research/19`) — a
    macro-regime filter for gating intraday strategies, not in the
    original brief.
11. **vnpy's pre-trade `RiskManager`** (order-flow-rate/cancel-count
    limiting) (`research/15`) — a distinct exchange-facing throttle layer
    from portfolio VaR.
12. **immudb as a ready-made tamper-evident ledger** and **Chronicle
    Queue's no-backpressure, replay-first architecture** for tick
    ingestion (`research/15`) — better starting points than a bespoke
    hash-chain logger or a generic Kafka pipeline.

## What this changes about the plan

No layer order changes — Rule A still governs. What changes is the
**build method** for several layers: Layers 2, 3, 5, and 6 now have a
credible "adapt a real, working open-source piece" path instead of
building every function from a blank file, which should be weighed
against build-from-scratch when each layer's turn actually comes. Item
#11 in the top-12 table (swarm-trader's `validate_trade()` gate pattern)
is the strongest single addition to the Memory & Reflection / Strategic
LLM layers' design (`PLAN.md` §3b, `research/09`) found in any research
pass this project has run.

## Ranked — overall top 6 projects to read full source code from next (across all 41)

1. **BennyThadikaran/NseIndiaApi** — closes the Layer 2 data-gap
   identified independently by `research/13` and `14`.
2. **zhound420/swarm-trader** — the human-gate mechanism this project's
   SEBI-compliance requirement has been describing abstractly since
   `research/01`; now there's real code that does it.
3. **dcajasn/Riskfolio-Lib** — richest risk-measure/Kelly/HRP
   implementation for Layer 5.
4. **vollib/py_vollib** — the options-math foundation nearly every other
   options feature depends on.
5. **codenotary/immudb** — the actual compliance-ledger candidate for the
   SEBI Algo-ID audit trail.
6. **xgboosted/pandas-ta-classic** — shortcuts the bulk of Layer 3's
   indicator menu in one MIT import.

## Open questions this adds to `PLAN.md` §8

- Which of the 12 pieces above (if any) do you want to commit to
  borrowing-and-adapting now, vs. treating purely as reference while
  building from scratch?
- Do you want the multi-account copy-trading and Telegram-control-plane
  ideas (found, not asked) scoped into the plan, or explicitly declined
  like `research/09`'s category H items?
