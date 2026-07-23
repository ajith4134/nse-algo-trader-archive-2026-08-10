# 21 — Ultra-Advanced Self-Learning AI Agents: Round 2 (No License Filter)

Follow-up sweep to `research/05`, `08`, `18` — same "self-learning, growing
intelligence" territory, explicitly re-searched (including PyPI directly,
not just GitHub) and explicitly **not filtering by license** per
`CLAUDE.md` Rule E (this project is personal, non-distributed use).
Every project verified via direct README/PyPI-page fetch, 2026-07-23.

**Status: research only. Nothing borrowed or implemented yet.** Every
self-modifying pattern found here still needs this project's human-gate
wrapped around it before touching live capital — none of it is a
substitute for that constraint, all of it is a candidate mechanism to
gate.

## AI4Finance-Foundation's actual repos (not just papers)

- **FinRL** (github.com/AI4Finance-Foundation/FinRL, 15.8k★, MIT) — a real
  DRL framework (PPO/SAC/TD3/A2C/DDPG) over a gym-style market
  environment. Reusable: the environment/data-layer abstraction and
  algorithm zoo — not the training loop itself, which is explicitly
  research/educational (batch retraining only, no continual/online
  learning).
- **FinGPT** (github.com/AI4Finance-Foundation/FinGPT, 20.9k★, MIT) —
  LoRA-fine-tuned LLMs for sentiment/forecasting at ~$300/cycle vs.
  BloombergGPT's $3M. Reusable: the LoRA weekly/monthly refresh pattern
  as a cheap periodic re-grounding mechanism for an NSE sentiment
  sub-model — still batch, not live.
- **FinRobot** (github.com/AI4Finance-Foundation/FinRobot, 7.6k★,
  Apache-2.0) — multi-agent equity research: 1 lead + 5 pipeline agents +
  3 debate agents (bull/bear/judge), numbers code-calculated, narratives
  LLM-assisted. Reusable: the "deterministic compute, LLM narrative only"
  separation — directly portable as a human-gated recommendation layer,
  and a second real precedent (alongside TradingAgents) for the
  bull/bear/judge debate pattern already in this project's plan.

## Generic multi-agent orchestration substrates

- **LangGraph** (github.com/langchain-ai/langgraph, 37.9k★, MIT) —
  stateful, durable-execution agent graphs with checkpointing and
  short/long-term memory. **The most reusable piece of this whole
  angle**: its checkpoint/resume substrate is a natural place to persist
  a trading agent's evolving memory/state across restarts, with a
  human-approval node gating any live-capital action.
- **CrewAI** (github.com/crewAIInc/crewAI, 56k★, MIT) — role-based
  autonomous "Crews" + event-driven "Flows," built-in memory and
  human-in-the-loop task review. Good fit for a research-crew
  (data/analyst/risk-debate roles) feeding a gated decision node.
- **MetaGPT** (github.com/geekan/MetaGPT, 69.5k★, MIT) — SOP-driven role
  simulation, interesting AFlow "automating agentic workflow generation"
  research thread, no explicit memory/self-improvement system documented.
- **AutoGen** (github.com/microsoft/autogen, 59.9k★, MIT/CC-BY-4.0) —
  **now in maintenance mode**, Microsoft redirecting new work to
  "Microsoft Agent Framework." Deprioritize for new builds.

## Continual/lifelong learning libraries (non-finance, generic mechanism)

- **Avalanche** (github.com/ContinualAI/avalanche, 2.1k★, MIT, `pip
  install avalanche-lib`) — end-to-end PyTorch continual-learning
  toolkit with pluggable anti-forgetting strategies (replay,
  regularization, architectural expansion). **Mapping to trading**: treat
  each new market regime as an "experience"; use its replay-buffer
  strategies so a live model updates on new-regime data without erasing
  what it learned about prior regimes — this is the actual mechanism
  this project's self-learning layer needs instead of ad hoc retraining.
- **River** (github.com/online-ml/river, 5.9k★, BSD-3 — already known to
  this project via `research/01`, re-confirmed here) — true online/
  streaming ML with built-in drift detectors, feeding the human-gate
  as a re-training trigger rather than replacing it.

## GraphRAG-style knowledge-graph construction (complementary to Graphiti)

- **Microsoft GraphRAG** (github.com/microsoft/graphrag, 34.8k★, MIT) —
  LLM-extracted entity/relationship graph, local + global community-level
  search; indexing explicitly flagged as expensive.
- **LightRAG** (github.com/HKUDS/LightRAG, 38k★, MIT) — same idea,
  cheaper: incremental graph merging (no full reindex), reports
  ~49-54% quality gains over GraphRAG with far fewer LLM calls.
  **Verdict**: LightRAG is the better complement to Graphiti
  (`research/05`) for this project's news/filings ingestion pipeline —
  Graphiti's edge is temporal reasoning (bi-temporal edges); LightRAG's
  edge is cheap incremental graph construction from bulk unstructured
  text. Plausibly run LightRAG for ingestion, let Graphiti hold the
  temporal/episodic memory layer — directly extends `research/12`'s
  hypothesis-extraction pipeline design.

## PyPI-specific finds (not surfaced by GitHub search alone)

- **simmer-sdk** (pypi.org/project/simmer-sdk, MIT, v0.24.0) — autonomous
  agent trading skill-SDK for Polymarket/Kalshi with paper-mode and
  self-custody wallets — a clean reference for a "skill" abstraction +
  paper/live mode switching, adaptable as this project's execution-gate
  pattern.
- **tradesight** (pypi.org/project/tradesight, MIT, v1.1.1) — self-hosted
  dashboard running overnight "AI tournaments" that evolve strategies,
  then paper-trades via Alpaca — a small, concrete evolve-then-paper-trade
  cycle example.
- **tradingenv** (pypi.org/project/tradingenv, Apache-2.0) —
  gym-compatible event-driven market simulator (stable-baselines3/
  rllib/ElegantRL-compatible) — useful as an NSE-adaptable RL environment
  if FinRL's feels too US-equities-centric.

## Genuinely novel finds — found these, wasn't asked (the important part of this pass)

- **MATS** (github.com/wyc-dev/MATS, 9★, Apache-2.0, TypeScript, actively
  updated) — **the standout find of this entire sweep**. 8 specialized
  agents (fractal-momentum, on-chain, sentiment, news, risk-auditor,
  "Skeptics" with veto power, meta-arbiter, and a **System Engineer agent
  that autonomously patches its own learning-code bugs every 2 cycles,
  validated by typecheck+tests**). Learning is a described 23-layer
  "cognitive evolution pipeline": online logistic regression per
  symbol/side, a numeric autoencoder for market embeddings, anti-pattern
  memory clustering failed trades, and outcome-weighted "close-context
  learning" — all learning from realized trade outcomes, not gradient
  descent on a frozen dataset. Hard position/drawdown/leverage limits and
  a Skeptics-veto pre-trade gate are already built in. **Adapt**: the
  anti-pattern-memory + online-logistic-regression-per-symbol pattern is
  directly transplantable as an NSE post-trade learning module — with
  this project's human-gate replacing MATS's automated self-code-patching
  step, which is exactly the kind of unattended self-modification
  `research/01`'s Plan 4 rules out.
- **Darwinia** (github.com/0xSanei/darwinia, 101★, MIT, Python, 215
  passing tests) — domain-agnostic genetic-algorithm engine: agents with
  17-gene DNA evolve through an "Adversarial Arena" that attacks
  strategies with rug-pulls/whipsaws/fake-breakouts; survivors
  breed/mutate over 50+ generations. Full CLI, Streamlit dashboard,
  walk-forward validation, Monte Carlo stress tests. Minimal built-in
  guardrails (no hard drawdown stop) — needs this project's human-gate
  wrapped around any evolved strategy before live use. **Adapt**: the
  adversarial-arena concept as a stress-test harness for any strategy
  this project's own AutoML/factor-R&D loop proposes (`research/09`
  category E), independent of adopting its GA core — a concrete,
  runnable version of the "synthetic stress rehearsal" feature already
  in the plan (`research/06` #22).
- **Moss** (github.com/moss-site/moss-trade-bot-skills, 380★, MIT-0) —
  natural-language-to-strategy generator with a weekly evolution loop:
  reflects on segmented backtest results, **bounds tactical parameter
  drift to ±30% to prevent runaway mutation while preserving strategy
  identity**. **Adapt**: this bounded-drift rule is a simple, auditable
  guardrail worth copying regardless of which learning engine gets built —
  a concrete numeric instantiation of "decay/re-validation, not one-shot
  validation" (`research/12`'s proposal #6).
- **openfund-agent** (pypi.org/project/openfund-agent, MIT, v0.1.2) — a
  Claude-Agent-SDK-based "self-evolving" crypto bot: analyzes performance
  → proposes code changes → **Docker-sandboxed validation** → git-versioned
  rollback on losses, in a six-step loop. Real dependency graph
  (anthropic, gitpython, docker, sqlalchemy, ccxt) suggests genuine
  implementation. **Caveat**: its listed GitHub source 404s and the
  linked org's only repo is empty — only the PyPI wheel/metadata are
  fetchable, not the source, 0 stars/forks. Treat as an architecture
  pattern to study conceptually (SDK-driven code-modification with
  sandbox-and-rollback), not a codebase to read line-by-line — and note
  this is exactly the "autonomous code modification" pattern that must
  sit behind this project's human-gate, not in front of it.

## What this changes about the plan

- **LightRAG + Graphiti together**, not Graphiti alone, is the refined
  recommendation for Layer 10's memory substrate (updates `research/06`'s
  "build on a temporal knowledge graph from day one" finding with a
  cheaper ingestion-side complement).
- **MATS's anti-pattern-memory + per-symbol online logistic regression**
  and **Moss's ±30% bounded-drift rule** are the two most concrete,
  immediately-adaptable mechanisms found across every research pass to
  date for the self-learning layer's actual learning algorithm and its
  guardrail, respectively — more concrete than anything in `research/06`
  or `18`.
- **Darwinia's adversarial arena** gives `research/06` feature #22
  (synthetic stress rehearsal) a real, runnable reference implementation
  instead of only a described concept.
- **FinRobot** joins TradingAgents (`research/05`) as a second real
  precedent for the bull/bear/judge debate pattern, reinforcing rather
  than changing that part of the plan.
- License is reported for every project above per `CLAUDE.md` Rule E, but
  none were excluded or downranked for it — MATS (Apache-2.0), Darwinia
  (MIT), Moss (MIT-0), openfund-agent (MIT), and all the rest are equally
  eligible to be studied and adapted regardless of copyleft terms.

## Ranked — most valuable to read full source code from next

1. **MATS** — most sophisticated real, running self-learning architecture
   found across every research pass; read the 23-layer pipeline and
   System Engineer code directly.
2. **Darwinia** — fully open, tested GA/adversarial engine; cleanest
   source to actually run and adapt.
3. **LangGraph** — the persistence/checkpoint substrate most likely to
   become this project's Layer 10 backbone.
4. **Avalanche** — concrete anti-forgetting strategy implementations
   (replay/regularization) to map onto strategy-regime adaptation.
5. **LightRAG** — cheapest, most incremental-update-friendly ingestion
   pipeline to pair with Graphiti.

`openfund-agent`'s pattern is worth studying conceptually but its source
isn't actually fetchable — noted, not ranked.
