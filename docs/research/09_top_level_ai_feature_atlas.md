# 09 — Top-Level AI Feature Atlas (All Categories, Consolidated)

The dashboard's flowchart was collapsing the entire AI side of this project
into two boxes ("10 · Memory and Reflection", "11 · Strategic LLM /
Research Agent"). That's a real gap: `research/06` only ever catalogued
one slice — *self-learning* AI (research/memory/pattern-mining). This file
is the full consolidation: every AI feature researched across
`research/01`, `04`, `06`, and `08`, organized by **function** instead of
by which research pass found it, so "all the top-level AI features" is
actually visible in one place. Nothing new is invented here — every row
cites back to the file that researched it.

**Status: research + planning only. Nothing implemented.**
**Unchanged governing constraint (research/01): nothing here self-modifies
live trading logic without a human sign-off gate.**

## Legend
⭐ directly requested · ✅ common/proven · 🚀 advanced · 🌌 ultra-advanced/frontier
· ⛔ researched and explicitly deprioritized (documented why, not just skipped)

## Category A — Signal & Prediction AI

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| Classical ML ensembles (GBM/XGBoost/Random Forest) | ✅ | Production workhorse, best out-of-sample generalization evidence | `research/04` §5 |
| Meta-labeling / ensemble confidence-gating | ✅ | Evidence-backed, contested as sole signal | `research/01` |
| Regime detection (HMM, changepoint, clustering) | ✅ | Proven, standard engineering | `research/01`, `04` §3 |
| Deep sequence models (LSTM/Transformer/TFT) | 🚀 | Promising, no consensus of superiority over GBM | `research/04` §5 |
| Multi-modal vision chart reading (candlestick images → vision LLM) | 🚀 | Real, cheap to prototype as a *secondary confirmation* signal, never sole trigger | `research/08` §1 |
| RL for signal-generation / position-sizing | 🌌 (academic) | Zero verified live deployments in a 2025-26 review of 167 papers | `research/01`, `04` §2 |
| Graph Neural Networks over sector/supply-chain relationships | ⛔ | Sound in principle, no verified production case study, NSE graph is a data-acquisition problem before a modeling one | `research/08` §5 |

## Category B — Execution AI

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| RL for execution (order slicing, venue/aggression selection) | ✅ | One real named live deployment (JPMorgan LOXM), narrow scope | `research/01`, `04` §2 |
| Gamma scalping automation (dynamic delta-hedging of options positions) | 🚀 | Execution-heavy, market-making-adjacent | `research/07` §C |

## Category C — Risk & Compliance AI

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| Drift detection + auto-retrain trigger | ✅ | Standard MLOps, proven | `research/01`, `04` §7 |
| Performance anomaly detection (live vs. backtested envelope) | ✅ | Same toolkit as drift detection | `research/06` #12 |
| Adversarial-validation trip wire (live-vs-training distribution classifier) | 🚀 | Real ML technique, novel application here | `research/01` Fusion C |
| SEBI-narrative auto-report (audit log → plain-English compliance summary) | 🚀 | Realistic, directly usable, genuine gap in the market (nobody builds regulator-facing summaries, only trader-facing ones) | `research/08` §6 |
| End-to-end explainable audit trail | 🌌 | Doubles as an AI feature and the literal SEBI white-box requirement | `research/06` #28 |

## Category D — Interface & Copilot AI

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| Self-explanation to user (plain-language daily "what it learned/why it traded") | ✅ | Natural extension of SHAP explainability | `research/06` #11 |
| Automated narrative/report generation | ✅ | Real, mainstream at OSS scale (e.g. `ZhuLinsen/daily_stock_analysis`, 36.1k★) | `research/08` §6 |
| Conversational RAG copilot grounded in own trade logs ("why did you take this trade") | 🚀 | Highly realistic, one of the highest-value adds found across all research passes — weekend-scale build | `research/08` §3 |
| Active learning / human-in-the-loop labeling for uncertain patterns | 🚀 | Standard active-learning pattern, novel application | `research/06` #19 |

## Category E — Generative / Code AI

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| LLM-assisted strategy/code drafting (English description → code, human-reviewed) | 🚀 | Real ecosystem, but documented failure modes (silent live-slippage bugs, hallucinated fallback values, backtest overfitting) — valuable as a *drafting* tool only, mandatory DSR/CPCV + human gate before paper trading | `research/08` §4 |
| Autonomous factor R&D loop (propose → implement → test → iterate) | 🚀 | Real (RD-Agent-Quant), promotion still human-gated | `research/05` §2, `research/06` #17 |
| LLM-driven full strategy self-rewriting, unattended | 🌌 (ruled out) | No public evidence of this working live anywhere; explicitly Plan 4 in `research/01`, never to be built as described | `research/01` |

## Category F — Research & Learning AI (self-learning layer — full detail in `research/06`)

28 features, base → ultra-advanced, spanning: autonomous web-research
agent, win/loss pattern mining, knowledge-graph mapping of every
learning/action, memory recall, reasoning-trace journaling, automated
feature engineering, sentiment scoring, hyperparameter AutoML,
cross-asset/calendar-event learning, regime-aware research loops,
validated skill libraries, curiosity-driven paper-mode exploration,
transfer learning, synthetic stress rehearsal, bi-temporal fact
invalidation, graph-grounded multi-agent debate, self-play red-teaming,
causal trade-outcome analysis, and federated cross-strategy learning.
**See `research/06` for the complete, individually-cited table — not
duplicated here to avoid drift between two copies of the same list.**

## Category G — Portfolio & Meta AI

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| Meta-strategy capital allocator (Hierarchical Risk Parity across validated strategies) | ✅ | Established portfolio theory, novel application once multiple strategies exist | `research/01` Fusion E |
| Meta-learning across strategies ("learning to learn" which sub-strategy fits which regime) | 🚀 | Extension of regime-gated ensemble | `research/06` #20 |

## Category H — Frontier / Explicitly Deprioritized (researched, not ignored)

| Feature | Tier | Verdict | Source |
|---|---|---|---|
| Diffusion/GAN-generated synthetic OHLCV for stress-testing | 🌌 | Real (CoFinDiff, IJCAI 2025), useful to widen CPCV validation sets beyond real history | `research/08` §7 |
| LLM-populated market simulators (agents with personas testing strategies against synthetic order flow) | 🌌 | Real (StockSim, arXiv 2507.09255) but agents admit behaving "too rational" vs. real order flow | `research/08` §7 |
| Alternative data (satellite imagery, credit-card panels, foot-traffic) + AI | ⛔ | Institutional-scale and real globally, but India-specific vendor ecosystem is "nascent" (only 2 providers found) — near-irrelevant for a retail NSE trader today, cost-prohibitive regardless | `research/08` §2 |
| Earnings-call vocal-tone/stress analysis | ⛔ | Real niche, vendor-hype-heavy, low relevance — most Indian mid/small-cap calls aren't transcribed by any of these vendors | `research/08` §7 |

## Totals (what "all the top-level AI features" actually means, counted)

- **7 functional categories** of applied AI (A-E, G-H) + **1 full sub-taxonomy** (F, 28 items on its own) = **~47 individually catalogued AI features**, not 2.
- Of those: **6 already in production elsewhere** (✅), **~18 advanced/real-but-higher-lift** (🚀), **~13 frontier/research-only** (🌌), **3 explicitly researched-then-deprioritized** (⛔), and **1 permanently ruled out** (Plan 4, full autonomous self-rewriting).

## What this changes about the plan and the roadmap

- Layer 10 (Memory & Reflection) now explicitly hosts categories **C, D, F,
  G** — risk/compliance, interface/copilot, the full self-learning
  taxonomy, and portfolio meta-AI.
- Layer 11 (Strategic LLM / Research Agent) hosts the higher-risk pieces of
  **A, E, F** — vision-confirmation signal AI, LLM-assisted code drafting,
  and the frontier self-learning items (bi-temporal invalidation's
  consumers, graph-grounded debate, causal analysis, federated learning).
- Category **B** (execution AI) belongs conceptually to Layer 6 (Broker
  Integration & OMS), not the AI layers — it's an execution-time technique,
  not a learning/strategy technique. Flagged here so it isn't lost by only
  living in a "Layer 10/11" mental bucket.
- Category **H** items are recorded specifically so they're never silently
  "forgotten" vs. "considered and declined" — the difference matters for
  anyone reviewing this plan later.

See `../PLAN.md` §3 for how this atlas slots into the overall feature menu,
and the dashboard's AI Feature Atlas panel for the visual version of this
table.
