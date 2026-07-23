# 22 — Frontier Self-Improving AI Beyond MATS (Final Sweep)

Final pass in the self-learning-AI research thread (`research/01`, `05`,
`08`, `18`, `21`). Explicitly excluded from re-profiling because already
covered: MATS, Darwinia, Moss, openfund-agent, LangGraph, CrewAI, MetaGPT,
AutoGen, Avalanche, River, LightRAG, GraphRAG, Graphiti, Cognee, Mem0,
Voyager, Reflexion, GPT-Researcher, STORM, RD-Agent-Quant, TradingAgents,
FinRobot, FinGPT, FinRL. Every project below verified via direct README/
paper fetch, 2026-07-23. License reported per Rule E, never a filter.

**Status: research only.** Nothing here self-modifies live logic without
this project's human-gate — every mechanism below is a candidate pattern
to adapt behind that gate, not a substitute for it.

## The six requested targets

- **AI Scientist v1** (github.com/SakanaAI/AI-Scientist, 14.3k★, custom
  Responsible-AI-derived license) — real, working pipeline: LLM proposes
  an idea within one of 3 fixed templates (NanoGPT/2D-diffusion/Grokking),
  writes and executes `experiment.py`, generates plots, writes a LaTeX
  paper with Semantic Scholar novelty checks, then an LLM "reviewer" (best
  with GPT-4o) scores it. **No before/after self-improvement claim** —
  it's one-shot idea→paper generation per run, not an iterative
  self-improving loop. Success rate varies heavily by model/template;
  license legally requires disclosing AI authorship in any resulting
  manuscript.
- **AI Scientist v2** (github.com/SakanaAI/AI-Scientist-v2, 6.9k★, same
  license) — replaces fixed templates with "progressive agentic tree
  search" guided by an experiment-manager agent, generalizing across ML
  domains. Sakana's own README admits v2 has a **lower success rate** than
  v1 when a good template exists — an honest anti-hype admission. Its
  actual "achievement" is one workshop paper that passed peer review, not
  a demonstrated self-improvement metric.
- **AlphaEvolve reimplementation → OpenEvolve**
  (github.com/codelion/openevolve, 6.8k★, Apache-2.0, active, PyPI-shipped)
  — an independent (not DeepMind-authored) open reimplementation of the
  AlphaEvolve concept: MAP-Elites quality-diversity population + LLM
  ensemble mutation + custom fitness evaluators + an "artifact side
  channel" feeding stderr/profiling data back into the next mutation
  prompt. Claims 2-3x real speedups, SOTA circle-packing (n=26), 2.8x GPU
  kernel gains, +23% HotpotQA accuracy via prompt evolution. This is the
  **single most directly transplantable mechanism** for a strategy that
  evolves its own logic under a backtest fitness function.
- **FunSearch — official** (github.com/google-deepmind/funsearch, 1.1k★,
  Apache-2.0/CC-BY-4.0) — genuinely DeepMind's own Nature-paper release,
  not a reimplementation, though it ships only the evolutionary loop,
  program database and evaluator harness — the actual LLM and sandboxed
  execution used in the paper are **not included**, so it only runs as a
  toy on cap-sets/bin-packing/admissible-sets out of the box. Confirms
  OpenEvolve is the more complete/adaptable of the two.
- **Eureka** (github.com/eureka-research/Eureka, 3.2k★, MIT) — real
  mechanism, verified: LLM writes a reward-function in Python from a task
  description → RL policy trains against it → LLM receives training
  metrics and rewrites the reward via "in-context evolutionary
  optimization," repeated for N iterations. Claims outperforming human
  reward design on 83% of 29 RL tasks (avg +52% normalized), including a
  Shadow Hand pen-spinning demo. **This reward-evolution loop maps almost
  1:1 onto evolving a strategy's objective function** (e.g., letting an
  LLM iteratively rewrite a Sharpe/drawdown-weighted fitness function
  based on walk-forward results) rather than the strategy's trade logic
  itself — a narrower, safer surface to automate.
- **OpenHands** (github.com/All-Hands-AI/OpenHands, 81.8k★, open-source,
  formerly OpenDevin) — confirmed self-correction loop: agent writes code
  → executes in a sandboxed container → observes stdout/stderr → revises
  → repeats until the task passes or attempts exhaust. Now a broader
  "developer control center" (multi-backend, ACP-compatible, Slack/GitHub/
  Linear integrations) rather than a single research prototype. Directly
  adaptable as this project's strategy-development-and-debugging harness —
  point it at the backtest engine as the "test suite" a candidate
  strategy must pass before ever reaching the human-gate.
- **Self-rewarding LMs / SPIN** — two distinct, both real:
  - **SPIN — official** (github.com/uclaml/SPIN, 1.2k★, Apache-2.0, ICML
    2024) — a model plays against snapshots of its own earlier iterations,
    generating its own preference pairs from existing SFT data (no new
    human labels), and iteration-1 already surpasses DPO-on-62k-new-data
    on most benchmarks per the repo's own reported numbers.
  - **self-rewarding-lm-pytorch** (github.com/lucidrains/self-rewarding-lm-pytorch,
    1.4k★, MIT) — implements Meta AI's "Self-Rewarding Language Models"
    (LLM-as-its-own-judge → DPO), plus bundles the SPIN idea. Both confirm
    a "grade your own past outputs, train on the grading" pattern that
    maps onto a trading model **journaling and self-critiquing its own
    past decisions** to generate training signal — still gated by human
    review before any resulting policy change goes live.

## Found these, wasn't asked (genuinely frontier, real code + paper)

- **Darwin Gödel Machine (DGM)** (github.com/jennyzzt/dgm, 2.2k★,
  Apache-2.0, arXiv:2505.22954, Sakana AI + collaborators) — **the closest
  thing in this entire multi-pass sweep to MATS's "System Engineer"
  concept, but more extreme**: the agent literally rewrites its own
  coding-agent codebase, empirically validates each self-modification
  against SWE-bench and the Polyglot benchmark, and keeps an open-ended
  archive of agent variants rather than converging to one. README
  explicitly warns it executes untrusted model-generated code and can
  behave destructively. **This is the pattern to study, never to run
  unattended** — the human-gate this project already mandates is exactly
  the missing piece DGM's own authors flag as a real risk.
- **ADAS — Automated Design of Agentic Systems**
  (github.com/ShengranHu/ADAS, 1.6k★, Apache-2.0, arXiv:2408.08435,
  NeurIPS 2024 Outstanding Paper) — a meta-agent that writes the code for
  *new* agents based on what worked before, building an archive of
  discovered agent architectures across ARC/DROP/GPQA/MGSM/MMLU. Adjacent
  to DGM but scoped to agent-workflow design rather than the agent's own
  runtime code — a gentler, more auditable version of the same idea.
- **SEAL — Self-Adapting Language Models** (github.com/Continual-Intelligence/SEAL,
  1.8k★, MIT, arXiv:2506.10943, MIT CSAIL, June 2026) — a model uses RL to
  generate its own "self-edits" (fine-tuning data + update directives) and
  applies them to its own weights, tested on knowledge incorporation and
  few-shot adaptation. Directly relevant to a design where the trading
  model proposes its own retraining data from recent trade outcomes,
  subject to the human-gate before weights actually update live.
- **Absolute Zero Reasoner** (github.com/LeapLabTHU/Absolute-Zero-Reasoner,
  1.9k★, MIT, arXiv:2505.03335, Tsinghua) — trains with **zero external
  data**: the model alternates PROPOSE (generate its own reasoning tasks
  via abduction/deduction/induction, Python-execution-validated,
  learnability-rewarded) and SOLVE (attempt them, accuracy-rewarded),
  reportedly beating models trained on thousands of curated examples.
  Conceptually the most extreme "self-improvement" system in the sweep —
  worth knowing exists, but the least directly portable to trading since
  it needs a Python-verifiable ground truth per task, which market
  outcomes don't cleanly provide.

## What this changes about the plan

- **OpenEvolve** is now the concrete reference implementation for
  `research/06`'s AutoML/factor-evolution category — more mature and
  complete than FunSearch's own official release.
- **Eureka's reward-rewriting loop**, not full strategy-logic evolution,
  is the safer first target for LLM-driven automation: let an LLM evolve
  the *fitness function* scoring backtests, keep trade-logic mutation
  under OpenEvolve/DGM-style gating with mandatory human sign-off.
- **DGM** now supersedes MATS as the most advanced example of
  "self-modifying agent code, validated empirically" found across every
  pass — and its authors' own safety warnings reinforce, rather than
  loosen, this project's human-gate requirement.
- **SPIN/self-rewarding/SEAL** together give three independent, working
  precedents for "grade or edit your own outputs to generate training
  signal without new human labels" — directly relevant to a self-learning
  layer that critiques its own past trades to build training data, still
  gated before any weight update reaches the live model.

## Ranked — most valuable to read full source/paper from next

1. **Darwin Gödel Machine** (github.com/jennyzzt/dgm) — the most advanced
   self-modifying-agent-with-empirical-validation system found in the
   entire sweep; read the outer loop (`DGM_outer.py`) and archive
   mechanics directly.
2. **OpenEvolve** (github.com/codelion/openevolve) — most complete,
   actually-runnable AlphaEvolve-style evolution engine; the clearest
   candidate to prototype a strategy/objective-function evolution loop.
3. **Eureka** (github.com/eureka-research/Eureka) — cleanest, smallest
   reward-rewriting loop; lowest-risk place to start automating fitness-
   function design.
4. **SEAL** (github.com/Continual-Intelligence/SEAL) — self-generated
   training-data mechanism most transferable to "learn from your own past
   trade outcomes."
5. **OpenHands** (github.com/All-Hands-AI/OpenHands) — most mature,
   production-grade write→run→observe→fix loop to repurpose as the
   backtest-driven strategy-debugging harness.

Sources (all directly fetched, not snippet-only): github.com/SakanaAI/AI-Scientist,
github.com/SakanaAI/AI-Scientist-v2, github.com/codelion/openevolve,
github.com/google-deepmind/funsearch, github.com/eureka-research/Eureka,
github.com/All-Hands-AI/OpenHands, github.com/uclaml/SPIN,
github.com/lucidrains/self-rewarding-lm-pytorch, github.com/jennyzzt/dgm
(arXiv:2505.22954), github.com/ShengranHu/ADAS (arXiv:2408.08435),
github.com/Continual-Intelligence/SEAL (arXiv:2506.10943),
github.com/LeapLabTHU/Absolute-Zero-Reasoner (arXiv:2505.03335).
