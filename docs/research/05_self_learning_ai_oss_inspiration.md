# 05 — Self-Learning AI: Real Open-Source Projects to Draw Inspiration From

Extends `01_adaptive_learning_architecture_findings.md` with a fresh sweep
specifically for real, existing GitHub/PyPI projects (not papers) that
inform an "ultra-advanced self-learning AI" layer: autonomous research,
knowledge-graph memory, win/loss pattern mining, and reflective journaling.

**Status: research only, nothing implemented.** Stars/downloads are
snapshots as of 2026-07-23 and will drift.

## 1. Autonomous web-research agents

- **GPT-Researcher** (assafelovic/gpt-researcher, 28.6k★, Apache-2.0):
  planner decomposes a topic into sub-questions → scraper agents pull
  20+ sources → per-source summarization with citation tracking →
  publisher aggregates into a cited report. Ships as an MCP server too.
- **STORM** (stanford-oval/storm, 30.3k★, MIT, `pip install
  knowledge-storm`): simulates expert interviews grounded in retrieval,
  curates an outline, writes a cited report. Co-STORM keeps a persistent
  "mind map" for ongoing human-AI collaboration.

Pattern worth reusing: decompose → retrieve → per-source digest →
structure → store.

## 2. Continual/online learning trading bots

- **Freqtrade FreqAI** (freqtrade/freqtrade, 52.6k★, GPL-3.0): a
  background thread retrains the model every `live_retrain_hours`,
  decoupled from the inference thread (freqtrade.io/freqai; GH issue
  #10213) — adapts the same model type on a rolling window; adaptive, not
  strategy-discovering.
- **Microsoft Qlib** (46.5k★, MIT) + **DoubleAdapt** (KDD 2023, PR
  #1560): real, runnable meta-learning incremental-learning
  implementation (GRU model + `higher`-library meta-optimization) that
  fine-tunes on the latest incremental data instead of full retraining.
- **RD-Agent-Quant** (microsoft/RD-Agent, 14k+★, MIT) — unprompted find:
  an actual autonomous propose-hypothesis → implement-factor/model →
  test-on-data → iterate loop; reports ~2x ARR vs. benchmark factor
  libraries using 70% fewer factors.

## 3. Agent memory with knowledge graphs

- **Graphiti** (getzep/graphiti, 29.1k★, Apache-2.0, underlies Zep):
  temporal knowledge graphs — entities as nodes, time-validity-stamped
  triplet edges, raw "episodes" as provenance; **bi-temporal
  invalidation** marks superseded facts instead of deleting them.
  Multi-backend (Neo4j/FalkorDB/Neptune).
- **Cognee** (topoteretes/cognee, 29.2k★, Apache-2.0): `add → cognify →
  memify → search` pipeline building a self-hosted KG fused with vector
  embeddings + ontology; exposes remember/recall/forget/improve verbs.
- **Mem0** (mem0ai/mem0, 61.5k★, Apache-2.0): entity linking +
  multi-signal (semantic/BM25/entity) fusion; graph mode optional, not
  graph-first by default.
- **Letta/MemGPT** (letta-ai/letta, 23.9k★, Apache-2.0): OS-style paged
  memory (RAM=context, disk=archival) via self-editing memory tools —
  good working-vs-archival-memory analogy, not graph-native.

## 4. Pattern mining over trade history

- **Vibe-Trading** (HKUDS/Vibe-Trading, ~26k★, MIT) — most directly
  relevant real implementation found: its "Shadow Account" extracts
  strategy rules from a broker journal, backtests them, then runs
  trade-level winner/loser attribution, beta regression, regime analysis,
  Monte Carlo permutation testing, plus behavioral-bias detection
  (disposition effect, overtrading, momentum chasing, anchoring).
- No project combining Apriori/FP-Growth association-rule mining directly
  with trade setups was found — generic rule-mining libraries and
  SHAP-based interpretation demos exist (Stefan Jansen's "Machine Learning
  for Algorithmic Trading" repo), but the trading-specific combination is
  a genuine gap, not something to borrow.

## 5. Self-reflection / journaling agents

- **Reflexion** (noahshinn/reflexion, 3.2k★, MIT): converts scalar/binary
  feedback into a textual reflection appended to context for the next
  trial, no weight updates (arXiv:2303.11366).
- **Voyager** (MineDojo/Voyager, 7.1k★, MIT): automatic curriculum +
  ever-growing library of executable skills, each indexed by an embedding
  of its description, retrieved by similarity, composed into more complex
  skills (arXiv:2305.16291).
- **TradingAgents** (TauricResearch/TradingAgents, 94.2k★, Apache-2.0) —
  closest trading-specific equivalent: appends each run's decision to a
  flat markdown memory log, later fetches realized returns, writes a
  reflection, feeds it into the next Portfolio Manager call. Real and
  working, but memory is a flat log, not a structured graph.

## 6. Surprising finds (unprompted)

RD-Agent-Quant and Vibe-Trading were both unprompted discoveries and
arguably the two most on-point repos in the whole search. Graphiti's
bi-temporal fact-invalidation — marking facts "superseded" instead of
deleting — maps directly onto "this rule was valid in the 2023-24 regime
but is now invalidated," a capability none of the trading-specific
projects implement yet.

## Advanced-version proposals (real mechanism -> trading-adapted upgrade)

1. **Regime-aware research loop** — GPT-Researcher/STORM-style
   decompose→retrieve→summarize agent, output written as regime-tagged
   nodes into a Graphiti temporal KG, so later analysis conditions on
   regime, not just price.
2. **Voyager-style playbook, skills = trade setups** — candidate setups
   (RD-Agent-style proposal) must clear Deflated Sharpe Ratio +
   regime-robustness testing before entering the skill library; embedded
   by entry-condition description for similarity retrieval — a stricter
   gate than Voyager's self-verification.
3. **Reflexion-for-trades on a graph, not a log** — replace
   TradingAgents' flat markdown memory with per-trade reflections stored
   as Graphiti nodes linked to entities (ticker, setup-id, regime),
   enabling "what usually follows this pattern in this regime" queries.
4. **Drift-triggered incremental retraining** — combine
   DoubleAdapt/FreqAI's scheduled retraining with Graphiti-style
   invalidation: when a live skill's performance falls outside its
   backtested confidence band, its graph edge is marked "superseded" and
   a retrain/re-validation job auto-queues.
5. **Nightly rule mining over trade features** — Apriori/FP-Growth over
   engineered features (regime, volatility bucket, indicator state)
   across closed trades, storing each qualifying rule as a KG node linked
   to supporting trade instances.
6. **Cognee's four-verb cycle for trading memory** — remember (log
   trade+context) / recall (graph+vector retrieval) / forget (prune rules
   invalidated by drift) / improve (auto-summarize clusters into a
   higher-level playbook rule).
7. **Autonomous factor R&D + permutation-tested attribution** —
   RD-Agent-Quant-style propose→implement loop, but promotion gated by
   Vibe-Trading's Monte Carlo permutation + regime-robustness tests
   instead of raw backtest ARR.
8. **Graph-grounded bull/bear debate** — extend TradingAgents' debate with
   a Reflexion pass where each side must cite specific historical trade
   nodes from the KG; the resulting disagreement/consensus score becomes
   both a decision input and a new logged feature.

## Caveats

PyPI download counts were not checked (GitHub stars used as the maturity
signal throughout); license terms were read from repo/README text, not
independently verified against LICENSE files; a dedicated GitHub-topics
crawl could surface more than the two general-web sweeps run here.

## What this means for us

Feeds `../PLAN.md`'s self-learning AI feature taxonomy and confirms/extends
`01_adaptive_learning_architecture_findings.md`'s Plan 2/Plan 3 split —
the knowledge-graph-with-invalidation pattern (Graphiti) is the single
biggest concrete upgrade this pass found over what file 01 had proposed
(vector-only memory).
