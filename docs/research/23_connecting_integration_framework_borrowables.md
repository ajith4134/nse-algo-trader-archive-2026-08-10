# 23 — Connecting/Integration-Layer Projects: Wiring the Pieces Together

Final-pass companion to `research/16`-`21`. Those files found isolated
puzzle pieces (a Greeks library here, a memory framework there). This
file looks specifically for **connecting pieces** — full-stack or
glue-layer projects that integrate memory + strategy + execution as one
coherent pattern, which could beat hand-stitching separate libraries
together. Every project verified via direct README fetch, 2026-07-23.
License is informational only, per `CLAUDE.md` Rule E — nothing here is
excluded or downranked for its license.

**Status: research only. Nothing borrowed or implemented yet.**

## Cross-reference check: MATS/Darwinia/Moss's own dependencies

Checked directly for adjacent-ecosystem clues: MATS (wyc-dev/MATS) cites
only academic papers (prioritized experience replay, MC-dropout,
attention-residual transfer) — no adjacent software. Darwinia and Moss
list only generic deps (pandas/numpy/ccxt, Streamlit). This angle came up
dry — a genuine completeness gap, not an oversight, worth recording as
such rather than silently omitted.

## Projects found

| Project | Stars | License | What it is |
|---|---|---|---|
| [elizaOS/eliza](https://github.com/elizaOS/eliza) | 18,800 | MIT | Local-first "AI agent OS": `AgentRuntime` binds memory/state to Actions (execution), Providers (context), Services, Evaluators (post-processing); non-custodial wallet requiring approval before any transfer |
| [Josh-XT/AGiXT](https://github.com/Josh-XT/AGiXT) | 3,200 | MIT | Automation platform: agent memory, "chains" (workflows), 40+ extensions; docs explicitly list crypto trading as a supported chain type |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | 19,200 | Apache-2.0 | Crypto exchange-agnostic strategy/connector architecture — cleanest strategy/execution decoupling pattern found in this whole sweep |
| [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) | 70,900 | AGPLv3 | "Connect once, consume everywhere" data layer, Python SDK, REST API, MCP server for AI agents |
| [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) | 81,800 | active (Jul 2026 release) | Self-hosted control center running coding agents across local/remote/cloud; multi-backend orchestration |
| [Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | 186,000 | MIT (platform code: Polyform Shield) | Still active, pivoted to a managed platform (AutoPilot/Dashboard/Marketplace) |
| [yoheinakajima/babyagi](https://github.com/yoheinakajima/babyagi) | 22,300 | MIT | **Archived Sept 2024** — historical reference only |
| [trevorstephens/gplearn](https://github.com/trevorstephens/gplearn) | 1,900 | BSD-3 | Genetic-programming symbolic regression, scikit-learn API |
| [DEAP/deap](https://github.com/DEAP/deap) | 6,400 | LGPL-3.0 | Lower-level evolutionary-computation toolkit (GA/GP/multi-objective) underlying TPOT and Sklearn-genetic-opt |
| [letta-ai/letta](https://github.com/letta-ai/letta) | 23,900 | Apache-2.0 | Ecosystem has moved beyond the legacy V1 server into Letta Code CLI, an Agent SDK, and a hosted Constellation cloud |

## Puzzle pieces worth borrowing, and how to upgrade each

- **eliza's Action↔Memory↔Evaluator loop** — a clean template for
  "signal generation → human-approved order → outcome written back to
  memory." **Upgrade**: use the plugin scaffold to wrap this project's
  Greeks/scanner libraries as Providers and route every generated order
  through an Action gated behind manual confirmation — never wire the
  wallet-style auto-execute path to a live NSE broker.
- **AGiXT's chains-as-DAGs** — declaratively compose
  research→signal→risk-check→(gated)execution steps. **Upgrade**: model
  the self-learning loop as a chain with a mandatory human-approval node
  before any broker-API step, directly operationalizing this project's
  SEBI white-box requirement the same way `swarm-trader`'s
  `validate_trade()` gate does (`research/18`).
- **Hummingbot's connector abstraction** (strategy code is
  exchange-agnostic; a connector class handles venue-specific execution)
  — the cleanest strategy/execution decoupling pattern in this entire
  sweep, even though it's crypto-only with zero NSE support today.
  **Upgrade**: this is exactly the shape of this project's own
  `BrokerClient` protocol (`PLAN.md` §1) — worth reading as validation of
  that existing design decision, not as a codebase to adopt.
- **OpenBB's MCP-server-for-agents pattern** — directly reusable as the
  data-fetch layer a research agent queries (ties to `research/12`'s
  external-knowledge pipeline). No NSE data confirmed, so this is an
  architecture reference, not a data source.
- **OpenHands' multi-backend agent orchestration** — adaptable as the
  runtime for a strategy-code-generation-and-self-repair loop, echoing
  MATS's "System Engineer" auto-fix agent (`research/21`) — still needs a
  hard stop before any generated code touches a broker.
- **gplearn/DEAP as the evolution engine between memory and strategy** —
  the natural slot Darwinia (`research/21`) fills bespoke-in-Python.
  **Upgrade**: DEAP for a custom multi-objective (return/drawdown/Sharpe)
  fitness function if gplearn's symbolic-regression scope is too narrow;
  see `research/24` for the fuller automated-feature-discovery treatment
  of these same two libraries.

## Found, wasn't asked (flagged explicitly)

- **Hummingbot's connector architecture** and **OpenBB's data layer** are
  both unprompted discoveries, included because they're strong
  architecture references despite having no NSE support.
- **AutoGPT's platform pivot** and **BabyAGI's archival** are worth
  knowing as a maintenance-status update — neither is a lightweight
  library to build on anymore; AutoGPT is now a managed platform,
  BabyAGI is a dead end.

## What this means for the plan

No project here replaces this project's own `BrokerClient`/OMS design
(`PLAN.md` §1) — Hummingbot's connector pattern actually validates that
decision rather than suggesting an alternative. The most concrete addition
is the **Action/chain-with-mandatory-approval-node pattern** (eliza,
AGiXT) as a second, independent real-world precedent for the human-gate
mechanism, alongside `swarm-trader`'s `validate_trade()` (`research/18`) —
two different ecosystems converging on the same design, which is a good
sign the pattern is right, not just convenient.

## Ranked — most worth reading actual source code from next

1. **elizaOS/eliza** — closest existing template for memory↔action↔
   human-approval wiring.
2. **gplearn** — most directly pluggable evolutionary engine for the
   strategy-discovery layer (see `research/24` for full treatment).
3. **hummingbot** connector architecture — best reference for decoupling
   strategy from execution, even without NSE support.
4. **DEAP** — for a custom multi-objective fitness engine if gplearn's
   scope is too narrow.
5. **AGiXT** — chain/workflow model for enforcing the human-gate step
   before any broker call.

See `research/22` (frontier self-improving AI) and `research/24`
(automated feature/indicator discovery) for the other two legs of this
final research pass, and `research/20` for the earlier consolidated
action plan this one extends.
