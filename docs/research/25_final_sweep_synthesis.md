# 25 — Final Research Sweep: Synthesis

This closes the open-source research thread. Three final passes
(`research/22`-`24`) covered: frontier self-improving AI beyond MATS,
connecting/integration frameworks, and automated feature/indicator
discovery. Combined with everything before it (`research/00`-`21`), this
project has now run **16 research passes, README/paper-verified ~90
real projects**. This file is the single-page synthesis of what changed
in this final round and what the overall picture now looks like.

**Status: research only. Nothing implemented.**

## The headline change: a new most-advanced reference point

`research/21` found MATS as the most sophisticated real self-learning
system. `research/22` found something more extreme: the **Darwin Gödel
Machine** (github.com/jennyzzt/dgm) — an agent that literally rewrites its
own coding-agent codebase and empirically validates each change against
real benchmarks (SWE-bench, Polyglot), keeping an open-ended archive of
variants rather than converging to one. Its own authors' README explicitly
warns it executes untrusted self-generated code and can behave
destructively. **This is not a reason to build it as described — it's the
clearest evidence yet, from the system's own creators, of why this
project's human-gate requirement (`research/01`, restated in every
research file since) is correct and non-negotiable, not overcautious.**

## What each final-pass file adds

- **`research/22`** (frontier self-improving AI): Darwin Gödel Machine
  (supersedes MATS as the reference point for "how far self-modification
  can go, and why it needs a hard gate"), **OpenEvolve** (the concrete,
  runnable AlphaEvolve-style evolution engine — more complete than
  DeepMind's own FunSearch release), **Eureka** (a safer first target:
  evolve the fitness/objective function, not the trade logic itself),
  **SEAL/SPIN/self-rewarding-lm-pytorch** (three independent precedents
  for a model grading its own past outputs to generate training signal),
  **OpenHands** (mature write→run→observe→fix loop, repurposable as a
  backtest-driven strategy-debugging harness), and **ADAS**/**Absolute
  Zero Reasoner** as further frontier reference points, the latter
  flagged as least portable since it needs Python-verifiable ground
  truth that market outcomes don't cleanly provide.
- **`research/23`** (connecting/integration frameworks): **eliza** and
  **AGiXT** both independently converge on the same
  Action/chain-with-mandatory-approval-node pattern as `swarm-trader`
  (`research/18`) — a second, unrelated ecosystem arriving at the same
  human-gate design, which is a good sign the pattern is right.
  **Hummingbot's** connector abstraction validates (rather than replaces)
  this project's own `BrokerClient` design. **gplearn/DEAP** identified as
  the evolution-engine slot Darwinia (`research/21`) fills bespoke.
  Notably, checking MATS/Darwinia/Moss's own dependency lists for
  adjacent projects came up empty — a genuine gap, recorded rather than
  papered over.
- **`research/24`** (automated feature/indicator discovery): no mature
  drop-in "discover indicators automatically" product exists. The real
  pipeline this research points to: **gplearn** or a **DEAP**-based GP
  loop proposes candidate formulas from OHLCV primitives → **tsfresh**'s
  hypothesis-testing filter screens for statistical relevance → survivors
  enter the existing hypothesis-validation pipeline (`research/12`) with
  no privileged trust just because they were machine-discovered.
  **AlphaGen** is the one real, running alpha-specific miner found beyond
  RD-Agent-Quant (`research/05`), though it's Qlib/China-market-coupled
  and would need adaptation.

## The full research inventory (for orientation, not re-reading)

| Thread | Files |
|---|---|
| Regulatory/market structure | `research/00` |
| Adaptive-learning architecture | `research/01` |
| Broker/paper-live frameworks | `research/02`, `03` |
| Production AI/ML verdicts | `research/04` |
| Self-learning AI (OSS inspiration → taxonomy → beyond → atlas) | `research/05`, `06`, `08`, `09` |
| NSE microstructure, time-of-day, hypothesis pipeline, filters, trade schema | `research/10`-`14` |
| Borrowable projects (5 categories) + consolidated plan | `research/15`-`20` |
| Self-learning round 2 (no license filter, incl. PyPI) | `research/21` |
| **Final sweep: frontier self-improving AI, connecting frameworks, automated discovery** | **`research/22`-`24`** |
| **This synthesis** | **`research/25`** |

## Overall ranked top 5 — across all ~90 projects, most worth reading full source next

1. **Darwin Gödel Machine** (`research/22`) — the single most advanced
   self-modification-with-empirical-validation system found; read it to
   understand exactly what the human-gate must guard against.
2. **`zhound420/swarm-trader`**'s `validate_trade()` gate (`research/18`)
   — still the most directly reusable human-gate mechanism, now
   corroborated by eliza and AGiXT independently converging on the same
   pattern (`research/23`).
3. **OpenEvolve** (`research/22`) — the concrete engine for evolving a
   strategy's logic or objective function under a backtest fitness
   function, gated the same way.
4. **`BennyThadikaran/NseIndiaApi`** (`research/19`/`20`) — still the
   most concrete near-term win: closes the actual Layer 2 data gap this
   project has today, unrelated to the frontier-AI thread.
5. **gplearn** (`research/23`/`24`) — the most directly pluggable
   evolution engine for automated indicator/feature discovery, feeding
   the hypothesis-validation pipeline rather than bypassing it.

## Open question this adds to `PLAN.md` §8

Given the Darwin Gödel Machine and OpenEvolve are now the clearest
existing references for "how a strategy could evolve its own logic under
a fitness function" — do you want this explored as a bounded, sandboxed,
paper-mode-only research thread once Layer 7 (Backtesting & Paper
Trading) exists, or deferred entirely until Layer 10/11, per the existing
roadmap ordering?
