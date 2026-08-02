# Advanced-intelligence software catalog (cognition · learning · memory · knowledge)

**Seed (user):** *"research online — projects, repos, research/thesis papers, everything — to find code/
features with TRUE intelligence, learning, memory, knowledge — not simple code but advanced architecture,
deep logic, institutional-grade or robotics-software-grade — find all the high-level software to include."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring (4 research agents running) · live GitHub data via `gh` 2026-08-02

---

## 0. The discipline (or this becomes hype-collection, not engineering)
The user wants the FULL space — but "true intelligence" software splits hard into **integrate / adapt /
admire-only**, and **stars ≠ works**. Three rules govern inclusion (Rule O sourcing + the whole session's
evidence):
1. **The committee anti-pattern is real** — the highest-starred trading item (TradingAgents 95k⭐) is a
   multi-LLM debate; budget-matched committees UNDERPERFORM (Berkeley MAST 41–86% fail) and self-correction
   degrades. High stars, wrong pattern. **Admire, don't adopt as-is.**
2. **Everything gated** — any "intelligent" component sits behind the deterministic validation gate
   (purged-CV + DSR + net-EV); it may *propose*, never *decide* capital (idea #4's invariant).
3. **Integrate real engines, not demos** — prefer maintained, licensed, installable libraries with real
   math (Rule P) over research repos that are one-paper proofs-of-concept.

## 1. Live candidate tables (real ⭐/license/last-push via `gh`, 2026-08-02)

### 1a. Memory & knowledge (give the organism real memory + self-knowledge)
| Project | ⭐ | Lic | Push | Verdict |
|---|---|---|---|---|
| **mem0ai/mem0** | 62k | Apache | 2026-08 | **INTEGRATE** — production memory layer (add/search/consolidate) |
| **getzep/graphiti** | 29.5k | Apache | 2026-08 | **INTEGRATE** — **temporal/bitemporal knowledge-graph memory** (perfect: no look-ahead, "believed-at vs true-at") |
| **letta-ai/letta** (MemGPT) | 24k | Apache | 2026-08 | **ADAPT** — OS-tiered self-editing memory (episodic/archival) |
| **microsoft/graphrag** | 35k | MIT | 2026-07 | **ADAPT** — graph RAG over filings/news (behind quarantine) |
| **OSU-NLP-Group/HippoRAG** | 3.9k | MIT | 2026-07 | **ADAPT** — hippocampus-inspired retrieval indexing |
| joonspk-research/generative_agents | 22k | Apache | 2024-08 (stale) | **ADMIRE** — the memory-stream+reflection+planning *pattern* (reference, not a dep) |
| langchain-ai/langmem · agiresearch/A-mem | 1.6k/1.1k | MIT | 2026/2025 | **ADAPT** — memory recipes |

### 1b. Continual learning · world models · forecasting priors (learn as it goes)
| Project | ⭐ | Lic | Push | Verdict |
|---|---|---|---|---|
| **online-ml/river** | 5.9k | BSD | 2026-08 | **INTEGRATE** — online learning + **drift (ADWIN/DDM)** (already in idea #4) |
| **PriorLabs/TabPFN** | 7.7k | (custom) | 2026-08 | **INTEGRATE-TEST** — Bayesian tabular foundation model (strong small-N priors — fits Rule Q) |
| **amazon-science/chronos** · **google-research/timesfm** | 5.7k/27k | Apache | 2026-07 | **ADAPT** — time-series foundation models (zero-shot forecast prior, sibling to Kronos) |
| **pyro-ppl/numpyro** | 2.7k | Apache | 2026-08 | **INTEGRATE** — Bayesian posteriors (uncertainty into sizing) |
| **scikit-learn-contrib/MAPIE** | 1.6k | BSD | 2026-07 | **INTEGRATE** — conformal prediction (calibrated intervals = "knows what it doesn't know") |
| ContinualAI/avalanche | 2k | MIT | 2025-03 | **ADAPT** — continual-learning methods (EWC/replay) |
| danijar/dreamerv3 · learnables/learn2learn | 3.6k/2.9k | MIT | 2026/2025 | **ADMIRE** — world-model RL / meta-learning (hard on financial data — flag) |

### 1c. Reasoning · neuro-symbolic · active inference (advanced logic)
| Project | ⭐ | Lic | Push | Verdict |
|---|---|---|---|---|
| **infer-actively/pymdp** | 723 | MIT | 2026-07 | **ADAPT** — **Active Inference / Free Energy** (brain-inspired perceive→act under uncertainty) |
| **scallop-lang/scallop** | 502 | MIT | 2026-06 | **ADAPT** — differentiable Datalog (learned signal + hard rules) |
| ML-KULeuven/deepproblog · lab-v2/pyreason · LTN | 351/344/370 | Apache/–/MIT | mixed | **ADMIRE/ADAPT** — neuro-symbolic (rules + nets) |
| opencog/atomspace · trueagi-io/hyperon | 988/266 | (custom)/MIT | 2026 | **ADMIRE** — AtomSpace knowledge + PLN reasoning (deep but heavy) |

### 1d. Cognitive architectures (the "organism" brainstem — mostly academic, genuinely deep)
| Project | ⭐ | Lic | Push | Verdict |
|---|---|---|---|---|
| **nengo/nengo** | 938 | (custom) | 2026-08 | **ADAPT** — Semantic Pointer Architecture / neuromorphic (Spaun brain) |
| SoarGroup/Soar · jakdot/pyactr (ACT-R) | 427/181 | (custom)/GPL | 2026/2025 | **ADMIRE** — chunking / declarative+procedural memory *patterns* to mirror, not embed |

### 1e. Self-improving · evolutionary discovery (autonomous strategy/feature search — gated)
| Project | ⭐ | Lic | Push | Verdict |
|---|---|---|---|---|
| **stanfordnlp/dspy** | 36.5k | MIT | 2026-07 | **INTEGRATE** — self-optimizing LLM programs (compile prompts against a metric, not vibes) |
| **openevolve** (AlphaEvolve OSS) | 6.8k | Apache | 2026-07 | **ADAPT** — evolve code/strategies **behind a hard evaluator** (FunSearch pattern) |
| **MilesCranmer/PySR** · trevorstephens/gplearn · DEAP | 3.7k/1.9k/6.4k | mixed | 2026 | **INTEGRATE** — symbolic regression / GP for interpretable alpha discovery |
| google-deepmind/funsearch | 1.1k | Apache | 2024-02 | **ADMIRE** — the generate→hard-evaluator→keep-winners *pattern* (the discipline itself) |

### 1f. Financial cognitive agents
| Project | ⭐ | Lic | Push | Verdict |
|---|---|---|---|---|
| **microsoft/qlib** | 47k | MIT | 2026-07 | **INTEGRATE** — the real institutional one (Nested Decision Execution + **DDG-DA** drift, the router reference) |
| AI4Finance/FinRL | 16k | MIT | 2026-07 | **ADAPT** — RL trading env (RL-for-alpha is shaky — flag) |
| **TauricResearch/TradingAgents** | 95k | Apache | 2026-07 | **ADMIRE-ONLY** — multi-LLM committee = the anti-pattern; mine ideas, don't adopt |
| pipiku915/FinMem | 931 | MIT | 2024-08 | **ADMIRE** — LLM trader with layered memory (pattern reference) |

## 2. Research findings (4 agents — all complete, cited) ✅

### 2A. Memory (agent-B)
- **🥇 Graphiti/Zep (arXiv 2501.13956) = THE backbone** — **bi-temporal BY DESIGN** (valid-time vs
  ingestion-time) = **no-look-ahead by construction** (the exact trading need) + strongest provenance.
  Neo4j/FalkorDB, Apache. → episodic trade-ledger spine.
- **HippoRAG2** (MIT) = associative multi-hop semantic recall ("what else does this regime affect");
  **LangMem** = procedural (strategy) memory; **LanceDB** = native time-travel vector store.
- **Reimplement** the reflection formula (Generative Agents: recency×importance×relevance decay) +
  **A-MEM** memory-evolution as the consolidation engine (ledger→lessons). **mem0 deprioritized**
  (vector-only, too shallow for audit despite 62k★). **Meta-memory** (confidence + belief-half-life +
  known-unknowns) = a CUSTOM layer extending Graphiti (no OSS covers it — maps to your Rule-Q ladder).

### 2B. Continual learning / world models (agent-C)
- **🥇 The usable loop:** **river** (online + ADWIN/DDM drift) → on drift, **EWC + replay** (hand-roll
  ~300 LOC on your nets) → **learn2learn** (MAML/Reptile) fast regime-adapt → **MAPIE** (conformal
  intervals) + **NumPyro/GPyTorch** (Bayesian/GP uncertainty) = "knows what it doesn't know."
- **Forecasting priors (feature, never sole signal):** Kronos (candlestick, verify Rule F — self-reported
  benchmarks) · Chronos/TimesFM/Moirai (time-series FMs) · **TabPFN** (Bayesian tabular — ⚠️ v3 weights
  NON-COMMERCIAL, read license).
- **🔴 World-model RL (DreamerV3/MuZero/EfficientZero) = RESEARCH-DEMO tier** — markets are non-stationary
  + REFLEXIVE (react to your actions) → the learned-simulator premise breaks; no credible financial
  deployment. **Decision Transformer** = the most defensible RL (offline, trains on your own logs). Skip
  world-model planning for core alpha.

### 2C. Cognitive architectures (agent-A)
- **🥇 py_trees** (Python behavior-tree control loop) = highest-confidence DEPLOYABLE — replaces ad-hoc
  if/else strategy/execution arbitration with composable, auditable, hot-swappable nodes + blackboard.
- **torchhd (VSA/HDC, MIT, JMLR'23)** = production-grade — **bind heterogeneous signals** (technical +
  sentiment + regime + fundamental) into ONE associative-memory vector → "find similar past market states."
- **htm.core** = streaming online **anomaly/regime detection** (no batch retrain). **SOAR** (BSD, Python
  bindings) = episodic(EpMem)/semantic(SMEM)/procedural + **chunking** (auto-compile deliberation→reflex on
  novel-state impasse) — the deliberative layer.
- **🥇 Shared Global Workspace (Goyal et al. ICLR'22, arXiv 2103.01197)** = the MODERN upgrade for the
  project's existing `global_workspace` module (specialists compete for a bandwidth-limited broadcast).
  LIDA/Sigma/EPIC/ICARUS = **relics** (borrow ideas, don't vendor); pyClarion = design reference (implicit/
  explicit/motivational/metacog split).

### 2D. Neuro-symbolic · active inference · self-improving · financial (agent-D)
- **Scallop** (differentiable Datalog, MIT) = strongest neuro-symbolic fit (hard rules + neural
  confidences in one query) + **PySwip/Prolog** = deterministic compliance/blackout VETO layer.
- **Self-improvement:** **OpenEvolve** (only mature FunSearch/AlphaEvolve OSS, Apache) + **PySR/gplearn/
  DEAP** (symbolic-regression → interpretable alpha) — ALL gated by a **deterministic walk-forward backtest
  evaluator** (never LLM-judges-itself; Self-Refine = the failure mode). **DSPy** = optimize the LLM organs
  against a metric.
- **Active inference:** **pymdp / RxInfer** = brain-inspired perceive→act with an epistemic
  (info-seeking) drive — but **not decision-core-ready**; use as a regime-belief *feature*.
- **🔴 Financial LLM agents — the honest evidence:** **Alpha Arena (real money, Oct-2025): 4 of 6 frontier
  LLMs finished in the RED** (one ~−63%). **TradingAgents (95k★) = committee anti-pattern** (shared
  pretraining priors → stylistic not informational disagreement → amplifies bias). **Qlib (47k, MIT) =
  the real infra pick** (+ FinRL for RL execution). Eloquent reasoning ≠ statistical edge.

## 3. Honest top picks to ACTUALLY integrate (pending agent depth)
- **Memory:** mem0 + **graphiti (bitemporal KG)** → the organism's episodic(ledger)/semantic(market)/
  reflective memory; letta pattern for tiered self-editing.
- **Learning-as-it-goes:** **river** (online+drift) + **TabPFN/Chronos** priors + **numpyro/MAPIE**
  (uncertainty) + Qlib **DDG-DA** (drift-aware). 
- **Reasoning:** **pymdp** (active inference perceive→act) + **scallop** (rules+signals).
- **Self-improvement:** **dspy** (optimize the LLM organs) + **PySR/gplearn** + **openevolve** — ALL behind
  the hard evaluator (FunSearch discipline).
- **Router reference:** **Qlib**. **Admire-only:** TradingAgents, generative_agents, SOAR/ACT-R (mirror the
  *patterns* — global workspace, chunking, memory-stream — which the project's organism modules already echo).

## 4. Map to the project's organism modules (reuse the deferred trunks)
The redesign paused conscience/will/sentience/epistemics/autopoiesis/axiology/society/intrinsic_motivation.
This catalog is what makes them REAL engines instead of scalars: memory→`memory_reflection`;
active-inference→`epistemics`/`predictive_core`; self-improvement→`autopoiesis`; knowledge-graph→a new
semantic-memory store; Qlib-DDG-DA→the brain's drift adaptation. Each still gated (Rule Q maturity ladder).

## 5. Finalized decision
_[pending — after agent depth + user picks which tier (integrate-now set) to commit.]_
