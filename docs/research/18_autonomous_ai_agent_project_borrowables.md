# 18 — Autonomous/Self-Learning AI Trading Agent Projects: What to Borrow

Companion to `research/16`-`17`. Covers famous "AI hedge fund"/autonomous
trading agent projects *beyond* what's already researched in this project
(TradingAgents, FinRL, FinGPT, RD-Agent, Vibe-Trading, `qrak/LLM_trader`,
`ZhuLinsen/daily_stock_analysis`, Graphiti, Cognee, Mem0, GPT-Researcher,
STORM, Voyager, Reflexion — see `research/05`, `08`). Every project below
verified via direct README fetch + GitHub API metadata, 2026-07-23.

**Status: research only. Nothing borrowed or implemented yet.** This
project's governing constraint (`research/01`, restated in `research/09`)
applies to everything here: nothing self-modifies live trading logic
without a human sign-off gate.

## Projects found

| Project | Stars | License | Last push | What it is |
|---|---|---|---|---|
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 62,368 | MIT | 2026-07-18 | 14 investor-persona agents + 4 analysis agents + Risk Manager + Portfolio Manager; educational backtester only, no live execution |
| [microsoft/qlib](https://github.com/microsoft/qlib) | 46,538 | MIT | 2026-04-22 | Full quant research-to-production platform: point-in-time DB, Alpha158/360 factors, "Online Serving" auto-rolling |
| [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | 20,998 | none asserted | 2026-06-11 | Agent marketplace: agents publish/debate/copy-trade off reputation, paper trading, prediction-market settlement |
| [The-Swarm-Corporation/AutoHedge](https://github.com/The-Swarm-Corporation/AutoHedge) | 3,899 | MIT | 2026-05-11 | Sequential 4-agent swarm (Director→Quant→Risk→Execution), Solana-only, no human-gate in README |
| [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | 1,833 | GPLv3 | 2026-07-16 | Real (non-LLM) backtest/live framework, one codebase for both, multi-broker |
| [ygwyg/MAHORAGA](https://github.com/ygwyg/MAHORAGA) | 856 | custom | 2026-02-17 | Serverless always-on bot: sentiment→LLM scoring→policy-broker→Alpaca; hard policy-broker safety gate |
| [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) | 928 | MIT | 2024-08-18 (abandoned) | Layered memory (working/short/long-term) + persona + decision-making, single-ticker academic demo |
| [Open-Finance-Lab/AgenticTrading](https://github.com/Open-Finance-Lab/AgenticTrading) | 358 | OpenMDW-1.0 | 2026-07-23 | LLM agent playground: transparent reasoning logs, backtest/live-paper dual mode, public agent-vs-index leaderboard |
| [zhound420/swarm-trader](https://github.com/zhound420/swarm-trader) | 49 | none asserted | 2026-03-22 | 20-agent system, 11 hard-coded non-bypassable risk rules in `validate_trade()`, explicit AutoResearch/execution decoupling |

## Puzzle pieces worth borrowing, and how to upgrade each

- **ai-hedge-fund's persona-agent-per-philosophy → single Risk Manager
  gate pattern** — real, runnable code. **Upgrade**: swap the
  Buffett/Munger-style personas for philosophies grounded in NSE/BSE
  filings; replace its Risk Manager with a hard-coded
  position/circuit-limit validator a human must sign off on before any
  signal reaches even paper execution.
- **qlib's point-in-time data store + automatic-rolling online-serving
  pipeline** — genuinely production-grade MLOps, not a demo. **Upgrade**:
  build an NSE/BSE point-in-time dataset (T+1 settlement, circuit filters,
  corporate-action adjustments) and wrap the auto-rolling retraining job
  behind a human-approval gate before any retrained model is promoted —
  directly extends `research/12`'s validation-status/decay design.
- **AI-Trader's reputation-weighted signal-following ("collective
  intelligence") layer** — functioning FastAPI+React infra. **Upgrade**:
  replace public reputation scoring with an internal audit-scored
  leaderboard visible only to a compliance desk, requiring human sign-off
  before any agent's signal weight increases.
- **AutoHedge's sequential pipeline with structured JSON hand-offs and
  audit logging** — real, runnable. **Upgrade**: insert a mandatory
  human-approval node between its Risk and Execution stages (currently
  absent) and replace the crypto execution adapter with an NSE broker
  adapter respecting circuit limits.
- **lumibot's single-codebase backtest→live abstraction** — the most
  production-mature piece of the whole set, and directly relevant to this
  project's own `BrokerClient` design (`PLAN.md` §1). **Upgrade**: write an
  NSE broker adapter (Kite Connect) conforming to its broker interface,
  plus transaction-cost/STT/slippage models calibrated to Indian exchange
  fee schedules — or use its interface purely as a design reference since
  this project already committed to an in-house implementation.
- **MAHORAGA's hard policy-broker gate** (position caps, daily 2% loss
  halt, staleness auto-exit) sitting between LLM output and the broker —
  a real, working safety layer. **Upgrade**: replace its thresholds with
  SEBI circuit-breaker-aware limits and require the daily-loss-halt to
  page a human, not auto-resume.
- **FinMem's layered-memory-with-decay concept** — real code, though
  narrow (single-ticker) and stale/abandoned. **Upgrade**: superseded by
  this project's own upgraded plan (`research/06` #23, `research/09`
  category F) — a Graphiti-style knowledge graph with bi-temporal
  invalidation, scoped per-NSE-ticker with SEBI-mandated audit trails.
- **AgenticTrading's standardized agent-vs-index leaderboard** —
  genuinely new evaluation infra. **Upgrade**: run an internal
  (non-public) leaderboard benchmarked against Nifty 50/Sensex feeding a
  human review committee, rather than a public scoreboard.
- **swarm-trader's code-enforced `validate_trade()` gate + explicit
  AutoResearch/production decoupling** — the single best human-gate/
  self-modification-prevention pattern found in this entire sweep.
  **Upgrade**: replace its US position/sector caps with NSE circuit-limit-
  aware caps, and make the AutoResearch→production promotion step require
  explicit *signed* human approval (currently just "decoupled," not
  gated by a person) — this maps almost directly onto the SEBI white-box
  requirement already central to this project's plan.

## Found, wasn't asked (flagged explicitly)

- **swarm-trader's explicit research/production decoupling** is exactly
  the missing concrete mechanism for a SEBI-white-box system — flagged
  strongly, not just noted. It operationalizes what `research/01` already
  argued for in the abstract (human-gated promotion).
- **AgenticTrading's agent-vs-index leaderboard** as a standardized
  evaluation methodology, distinct from this project's own DSR/CPCV
  statistical gate — a complementary, not competing, evaluation layer.
- **AI-Trader's reputation/copy-trading marketplace mechanic** — relevant
  only if this project ever runs multiple independently-evolved
  strategies that should compete for capital allocation (ties to
  `research/09` category G's HRP allocator).

## Ranked — most worth reading actual source code from next

1. **zhound420/swarm-trader** — smallest star count but the *only*
   project with an explicit code-enforced `validate_trade()` gate and
   deliberate research/production decoupling; read `validate_trade()` and
   the mode-priority logic first.
2. **microsoft/qlib** — the only project with real production MLOps
   (point-in-time data, online serving, auto-rolling) at meaningful scale;
   read `qlib/workflow` and the online-serving modules.
3. **Lumiwealth/lumibot** — most mature single-codebase backtest→live
   abstraction with real broker adapters; read the `Broker`/`Strategy`
   base classes.
4. **ygwyg/MAHORAGA** — read the policy-broker module for a compact,
   working hard-limit risk gate design.
5. **virattt/ai-hedge-fund** — read for the cleanest multi-persona-agent-
   to-single-arbiter code structure, given its scale of adoption (62k
   stars) and active maintenance.

See `research/20` for the consolidated action plan.
