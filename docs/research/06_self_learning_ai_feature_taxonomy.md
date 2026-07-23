# 06 — Self-Learning AI Feature Taxonomy (Base → Advanced → Ultra-Advanced)

This is the `expand-idea` pass over the user's own examples for the
self-learning AI layer: *"AI that researches online and converts new
findings into learning, finds common patterns in winning vs. losing
trades, maps all gathered knowledge with each learning/action, recalls
memory for related things, thinks, searches Google, and more like this —
plus whatever I forgot to mention."* Grounded in
`01_adaptive_learning_architecture_findings.md`, `04_...2026.md`, and
`05_self_learning_ai_oss_inspiration.md` — nothing below is invented
without a real technique/project backing it, cited where new.

**Status: research + planning only. Nothing implemented.**
**Governing constraint, unchanged from file 01: nothing in this layer ever
self-modifies live trading logic without a human sign-off gate — that's
both the safest engineering practice and the SEBI white-box compliance
mechanism.**

## Legend
⭐ user's own example, made concrete · ✅ common/adjacent, real & proven ·
🚀 advanced, real but higher-lift · 🌌 ultra-advanced/frontier

## The full taxonomy

| # | Feature | Tier | What it is | Real basis |
|---|---|---|---|---|
| 1 | Autonomous web-research agent | ⭐ | Decompose a question → search the web/news/filings → per-source summarize with citations → store as structured knowledge, not raw text | GPT-Researcher, STORM (file 05 §1) |
| 2 | Win/loss pattern mining | ⭐ | Attribution + rule mining across closed trades: what's common in winners vs. losers | Vibe-Trading (file 05 §4) |
| 3 | Knowledge-graph mapping of learnings/actions | ⭐ | Every action, outcome, and piece of research becomes a node; edges encode "led to," "contradicts," "supersedes" | Graphiti, Cognee (file 05 §3) |
| 4 | Memory recall for related situations | ⭐ | Hybrid graph + vector retrieval — "what happened last time something like this occurred" | Cognee/Mem0 retrieval (file 05 §3) |
| 5 | "Thinking" / reasoning traces as memory | ⭐ | The model's deliberation before a decision is itself stored and later searchable, not thrown away | Reflexion (file 05 §5) |
| 6 | Google/web search as a live tool | ⭐ | Real-time search wired into the research agent, not a static knowledge cutoff | Standard tool-use pattern, underlies #1 |
| 7 | Automated feature engineering | ✅ | Auto-generate and prune candidate indicator/feature combinations by importance, not just hand-picked indicators | Standard AutoML/quant practice |
| 8 | Drift detection + auto-retrain trigger | ✅ | Detect when live data distribution diverges from training data; trigger retraining instead of silent decay | River/DoubleAdapt, FreqAI (files 01, 05 §2) |
| 9 | News/social sentiment scoring | ✅ | FinBERT-style sentiment as one input feature, not a standalone signal | Industry-standard NLP-for-finance |
| 10 | Hyperparameter/AutoML tuning | ✅ | Bayesian optimization (Optuna-style) over model/strategy parameters instead of manual grid search | Standard MLOps |
| 11 | Self-explanation to the user | ✅ | Plain-language daily/weekly summary of what the system learned and why it traded as it did | Natural extension of SHAP explainability (file 04 §8) |
| 12 | Performance anomaly detection | ✅ | Detect when the bot's own live behavior deviates from its expected/backtested envelope | Same statistical toolkit as drift detection |
| 13 | Cross-asset/cross-market correlation learning | ✅ | Learn how NIFTY/BANKNIFTY relates to SGX/GIFT Nifty, US index futures, crude, USD-INR, and update those relationships over time | Standard macro-quant practice |
| 14 | Calendar/event-awareness learning | ✅ | Learn which days/events (RBI policy, Union Budget, F&O expiry, earnings) historically behave differently, and adjust automatically | Event-driven quant practice |
| 15 | Regime-aware research loop | 🚀 | Web-research findings (feature #1) are tagged by market regime in the knowledge graph, so retrieval conditions on "what was true in regimes like this one" | Proposal in file 05 (Graphiti + GPT-Researcher fusion) |
| 16 | Validated "skill library" of trade setups | 🚀 | New candidate setups must clear Deflated Sharpe Ratio + CPCV/regime-robustness before being added to a reusable playbook, each retrievable by similarity | Voyager pattern + de Prado gates (file 05 proposal #2) |
| 17 | Autonomous factor R&D loop | 🚀 | An agent proposes new candidate features/factors, implements and tests them, only human-gated candidates get promoted | RD-Agent-Quant (file 05 §2) |
| 18 | Curiosity-driven paper-mode exploration | 🚀 | In paper/shadow mode only (never live), an exploration policy deliberately probes edge-case setups to build experience faster than passively waiting | Bounded-risk analog of RL exploration bonuses |
| 19 | Active learning / human-in-the-loop labeling | 🚀 | When the system is uncertain about a pattern, it asks the user for a quick label/decision instead of silently guessing | Standard active-learning pattern, novel application here |
| 20 | Meta-learning across strategies ("learning to learn") | 🚀 | A layer that learns *which sub-strategy* tends to work in which regime, rather than learning within one strategy only | Extension of file 01's regime-gated ensemble |
| 21 | Transfer learning for newly listed instruments | 🚀 | Bootstrap pattern knowledge for a newly F&O-listed stock from similar, longer-history instruments instead of starting from zero | Standard transfer-learning practice, novel application |
| 22 | Synthetic stress rehearsal | 🚀 | GAN/diffusion-generated tail scenarios the bot hasn't lived through, run against every promotion candidate before it goes live | Fusion D, file 01 |
| 23 | Bi-temporal fact invalidation | 🌌 | Old "rules" are formally marked superseded when a regime changes, instead of being silently forgotten or catastrophically overwritten | Graphiti's bi-temporal model (file 05 §3, §6) — biggest single upgrade this research pass found |
| 24 | Graph-grounded multi-agent debate | 🌌 | Bull/bear/risk LLM agents must cite specific past trade nodes from the knowledge graph (not just today's data) before a disagreement/consensus score becomes a decision input | Fusion of TradingAgents debate + Graphiti (file 05 proposal #8) |
| 25 | Self-play adversarial red-teaming | 🌌 | A dedicated "attacker" model whose only job, in simulation, is to find scenarios that break the current strategy set; failures become priority memory | Extension of synthetic stress rehearsal, adversarial-validation research |
| 26 | Causal (not merely correlational) trade-outcome analysis | 🌌 | Causal-discovery methods distinguish "this indicator caused the win" from "this indicator was merely present," reducing spurious pattern-latching | Frontier of file 04 §8's XAI discussion |
| 27 | Federated cross-strategy learning | 🌌 | If multiple strategy instances run in parallel, validated skills cross-pollinate through the shared knowledge graph — still human-gated before any capital is touched | Novel combination, not found as a named technique anywhere in the research |
| 28 | End-to-end explainable audit trail | 🌌 | Every trade traceable back through exactly which memory nodes were retrieved → which reasoning trace fired → which validation gates it passed | Doubles as both an AI feature and the literal SEBI white-box registration requirement |

## What this changes about the existing plan

`01_adaptive_learning_architecture_findings.md` recommended building
toward **Plan 2** (vector-DB case-based memory) now, with **Plan 3**
(LLM-strategist) deferred. This file's new finding is that the memory
substrate itself should be upgraded: **build Plan 2 on a Graphiti-style
temporal knowledge graph from day one (features #3, #23), not a plain
vector store** — retrofitting bi-temporal invalidation later is far more
expensive than starting with it, the same argument file 01 already made
for explainable memory (its Fusion F). Everything else in this table slots
into the existing Layer 10 (Memory & Reflection) / Layer 11 (Strategic
LLM) split — see `../PLAN.md` for exactly which features land in which
layer and in which order.

## Open questions for discussion

- Do we adopt a real graph DB (Neo4j/FalkorDB) for this from Layer 10
  onward, or start flat and migrate? Given the "expensive to retrofit"
  lesson from file 01, the recommendation is to start with the graph.
- Curiosity-driven exploration (#18) and self-play red-teaming (#25) both
  need a safe sandbox to run in — this should piggyback on Layer 7
  (Backtesting & Paper Trading), not a separate system.
- Federated cross-strategy learning (#27) only becomes relevant once
  multiple validated strategies exist (Layer 4+), so it's explicitly
  sequenced late.
