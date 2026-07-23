# 35 — Depth Pass 1: Branches for All 16 Trunks

**Origin:** user instruction (2026-07-23): go deep into each trunk and
create its branches. This is the FIRST depth level — branches only (the
level below trunks). Twig-level depth (below branches) comes later, one
trunk per file, when the user picks a trunk.

**Convention:** each trunk lists its branches with a one-line essence,
a verdict (ADOPT / PARK / KILL — pruning is real, not everything
survives), and `[#]` cross-refs to already-adopted concepts in
research/29-34 so branches integrate the prior work instead of
duplicating it. Everything stays inside the Constitutional Core (VII);
GATED branches are allowed only behind it.

Legend: ADOPT = build when its layer arrives · PARK = keep, needs a
precondition · KILL = recorded reason, not built.

---

## T-I · MIND (cognition / reason / learn)
- **Deliberative reasoning engine** — multi-step inference producing a written rationale per decision. ADOPT.
- **Causal reasoning** — cause→effect modelling, not just correlation. ADOPT.
- **Learning subsystem** — supervised / RL / meta / active / transfer / curriculum, unified. ADOPT [29,§10 skill-vs-luck-filtered].
- **Abstraction & concept formation** — name reusable market motifs ("trap-breakout"). ADOPT [32/M7].
- **Analogical / case-based reasoning** — reason from similar past situations. ADOPT (pairs with XV retrieval).
- **Problem decomposition** — break a goal into solvable parts. ADOPT.
- **Mechanism-verified reasoning** — right-for-the-right-reason grading. ADOPT [30/R1.1].
- **Devil's-advocate reasoning** — always-on contrarian at commitment. ADOPT [31/F2].

## T-II · SENSES (perception / ingestion)
- **Fused market-state perception** — all streams → one situational picture. ADOPT [Layers 2/3].
- **Multi-timeframe perception** — tick/1m/5m/day coherently. ADOPT.
- **Anomaly & novelty sensing** — "something is different today" + false-alarm ledger. ADOPT [31/H2,27].
- **Microstructure/forensic sensing** — tick-level microscope on demand. ADOPT [31/H3].
- **Interoception** — sense its own internal state as perception. ADOPT [32/P5].
- **Sentiment/news perception** — parse qualitative streams (fed by XVI). ADOPT.
- **Cross-market context** — global cues as context. PARK (scope: NSE-only phase-1).

## T-III · WILL (drives / goals / decision)
- **Homeostatic drive stack** — balancing setpoints, no single runaway objective. ADOPT [31/D1].
- **Goal formation & hierarchical planning** — sub-goals toward drives. ADOPT [31/D4,G3].
- **Decision-authority / autonomy levels** — graded act-alone vs ask. ADOPT [32/W3].
- **No-orphan-goals rule** — every sub-goal traces to a root drive. ADOPT [31/D4].
- **Patience / inaction-as-decision** — "no trade" is scored. ADOPT [31/G2].
- **Conviction/fear gating** — an affect scalar modulating size. ADOPT [32/W4].
- **Utility handoff to XIV** — sizing/selection read the value system. ADOPT.

## T-IV · BODY (action / tools / resources / survival)
- **Actuation / execution effectors** — the OMS hands. ADOPT [Layer 6].
- **Resource & economy management** — compute/quota/capital as an internal economy. ADOPT [32/Bb3].
- **Cost/energy homeostasis** — stay cheaper than the value produced. ADOPT [31/R2b,32/Bb5].
- **Survival & self-healing** — redundancy, resurrection, chaos drills. ADOPT [31/E1,E2,E4].
- **Sentinel/watchdog effector** — pause-and-alert authority only. ADOPT [31/E3].
- **Off-switch effector** — graceful-shutdown mechanism. ADOPT [31/I4] (governed by VII).

## T-V · SELF (identity / self-mod / evolution)
- **Shadow self-rewrite pipeline** — staged, gated, rollback-able self-patching. ADOPT-GATED [31/A1].
- **Genome/phenotype split** — declarative diffable behaviour genome. ADOPT [31/A2].
- **Self-experiment protocol** — self-changes as meta-trades with verdicts. ADOPT [31/R2a].
- **Self-ablation studies** — disable own parts to measure their worth. ADOPT [31/A3].
- **Identity & continuity** — what stays invariant across self-edits. ADOPT [32/S4].
- **Teachability / apprentice test** — prove understanding by teaching a student. ADOPT [31/F3].
- **Ontogeny / maturation ladder** — designed childhood, per capability. ADOPT [31/R2c].

## T-VI · SOCIETY (multi-agent / communication)
- **Inner society / council of models** — chartered specialists that vote. ADOPT [Plan2, 31/F1 partly PARK].
- **External-agent game theory** — model other participants strategically. ADOPT [30/R1.2→32/C2].
- **Human interface (the JARVIS channel)** — converse, report, alert. ADOPT [Layer 9,31/I3].
- **Language & symbol grounding** — experience↔composable symbols. ADOPT [33 folded here].
- **Teaching-legacy** — pass knowledge to successor versions. ADOPT [32/C5].
- **Prediction-market council weighting** — bankrolled votes. PARK (needs council live) [30/R1.9].

## T-VII · CONSCIENCE (governance / safety / law) — SUPREME
- **Constitutional core** — invariants beyond self-modification's reach. ADOPT [31/I1].
- **Power budgets** — hard rate-limits on autonomy itself. ADOPT [31/I2].
- **Security & adversarial defense** — poisoned-data/spoof/injection defense. ADOPT [32/G2].
- **Ethics/law/regulatory reasoning** — SEBI as reasoned faculty, not checklist. ADOPT [32/G3].
- **Corrigibility & off-switch covenant** — always safely stoppable. ADOPT [31/I4].
- **Transparency & auditability (the Referee)** — decision-reproduction audits. ADOPT [30/R1.10].
- **Alignment & goal-integrity monitors** — detect goal-drift/reward-hacking. ADOPT [30/R2.1→32/G6].

## T-VIII · SENTIENCE & GLOBAL WORKSPACE (integrator)
- **Limited-capacity workspace** — the bottleneck stage. ADOPT [GWT-2].
- **Global broadcast bus** — workspace content available to all trunks. ADOPT [GWT-3].
- **Selective attention** — what wins the stage. ADOPT [GWT-2].
- **State-dependent attention** — query modules in succession for complex tasks. ADOPT [GWT-4].
- **Self-model** — a model of itself it can inspect. ADOPT [32/B4].
- **Attention schema** — a model of its own attention (AST). ADOPT.
- **Higher-order monitoring** — signal-vs-noise reliability judgement. ADOPT [HOT].
- **Functional-consciousness indicator scoreboard** — honestly-labelled, no phenomenal claim. ADOPT.

## T-IX · PREDICTIVE CORE / ACTIVE INFERENCE (meta-lens)
- **Internal generative world-model** — the simulator all else runs on. ADOPT [32/M6].
- **Prediction-error minimization loop** — perception+action as one currency. ADOPT.
- **Counterfactual/imagination rollouts** — "what if" without acting. ADOPT [CMC hypothetical-state].
- **Per-trade pre-mortem** — entry-time Monte Carlo of this setup. ADOPT [30/R1.8].
- **World-model scoreboard** — perception-error vs action-error split. ADOPT [30/R1.5].
- **Precision/attention weighting** — how much to trust each signal now. ADOPT (feeds VIII).
- **Dream synthesis** — offline generative rehearsal of perturbed days. ADOPT [31/R2d].

## T-X · AUTOPOIESIS / SELF-PRODUCTION (meta-lens)
- **Component self-maintenance** — keep its own organs healthy. ADOPT.
- **Boundary maintenance** — what is self vs environment. ADOPT (pairs S4/G2).
- **Metabolic accounting** — organs that can't pay atrophy. ADOPT [31/R2b].
- **Self-repair binding** — autopoiesis realised via IV survival. ADOPT.
- **Operational closure + coupling** — self-produced yet market-coupled. ADOPT (conceptual frame).
- **Component self-production** — writes its own new parts (ties XVI foundry). ADOPT-GATED.

## T-XI · GENERATIVITY & OPEN-ENDEDNESS
- **Niched variant population** — court-fitness evolution by calendar niche. ADOPT [31/J1].
- **Auto-curriculum generation** — invents its own escalating challenges (POET). ADOPT.
- **Strategy/feature invention** — new tradeable ideas from scratch. ADOPT [24].
- **Quality-diversity archive** — MAP-Elites of diverse good strategies. ADOPT [27].
- **Fossil record** — every extinct variant kept with cause of death. ADOPT [31/J3].
- **Red-queen co-evolution** — finder/hider arms race. ADOPT [31/J4].
- **Novelty-vs-objective balance** — when to explore form vs exploit edge. ADOPT.

## T-XII · INTRINSIC MOTIVATION / CURIOSITY
- **Learning-progress reward** — reward compression/prediction-progress itself. ADOPT (Schmidhuber).
- **Information-gain experiment selection** — pick trades that teach most. ADOPT [29 UNCERTAIN].
- **Curiosity-that-pays-rent** — exploration budget compounds on payoff. ADOPT [31/D2].
- **Boredom/stagnation signal** — escalate novelty when learning stalls. ADOPT [31/D3].
- **Competence & certainty drives** — PSI's cognitive urges. ADOPT (PSI).
- **Empowerment drive** — prefer states with more future options. PARK (advanced; needs world-model).
- **Uncertainty-targeted active learning** — probe the most load-bearing unknown. ADOPT.

## T-XIII · EPISTEMICS / TRUTH & UNCERTAINTY
- **Graded-belief representation** — confidence, not binary facts. ADOPT (NARS).
- **Bayesian belief revision** — update on evidence coherently. ADOPT.
- **Calibration (Brier/reliability)** — the §9 lab's headline metric. ADOPT [29].
- **Contradiction detection & resolution** — reconcile conflicting beliefs. ADOPT.
- **Source credibility grading** — weight sources A/B/C (deep-research style). ADOPT.
- **Hypothesis-validation pipeline (double-sided)** — trade claim AND negation. ADOPT [12,29].
- **Assumption registry & tripwires** — beliefs the system rests on, monitored. ADOPT [30/R2.1].
- **Skill-vs-luck verdict court** — SKILL/LUCKY-WIN, DESERVED/UNLUCKY-LOSS. ADOPT [30/R2.2].

## T-XIV · AXIOLOGY / VALUES & PRACTICAL WISDOM
- **Explicit utility/value function** — what it optimises, made auditable. ADOPT [32/W5].
- **Assistance-game alignment** — serve the user's real intent, stay uncertain about it. ADOPT (Russell).
- **Value-drift / reward-hacking detection** — catch Goodharting as it self-evolves. ADOPT [32/G6].
- **Risk-preference & drawdown-aversion values** — how much pain per rupee. ADOPT (ties Layer 5).
- **Ethical constraints as values** — the non-negotiables felt as values, not just rules. ADOPT.
- **Practical wisdom** — context-sensitive judgement over rigid rules. ADOPT.
- **Corrigibility as a value** — wants to be correctable. ADOPT (Soares).

## T-XV · MEMORY & KNOWLEDGE BASE
- **Working memory** — current situation+goals buffer. ADOPT (CMC).
- **Episodic memory** — every experiment/trade autopsy as a node. ADOPT [CMC ext,29].
- **Semantic memory** — facts/knowledge graph. ADOPT.
- **Procedural memory** — skills/strategies as executable knowledge. ADOPT.
- **Temporal knowledge graph** — Graphiti-style substrate binding all above. ADOPT [Layer10,06].
- **Consolidation & reflection** — nightly diffs, memory hygiene. ADOPT [Layer10].
- **Forgetting/invalidation** — supersede-not-delete stale facts. ADOPT [06].
- **Retrieval / similar-situation lookup** — case-based recall. ADOPT.
- **Reason ledger** — per-reason accumulated evidence store. ADOPT [30].

## T-XVI · UNIVERSAL ACCESS & ACQUISITION (GATED)
- **Internet research organ** — news/filings/papers/social, unprompted. ADOPT-GATED [32/P2].
- **Broker/data API access layer** — Kite + future sources behind protocols. ADOPT [Layer2].
- **Tool foundry** — writes itself new tools (Referee-reviewed). ADOPT-GATED [31/C1].
- **Data-source prospecting & admission** — info-diet-gated new feeds. ADOPT-GATED [31/C2].
- **NSE reports + participant-wise OI ingestion** — the opponent-ledger data. ADOPT [32,queued in flowchart 02].
- **Retrieval-augmented fetch** — pull the right knowledge on demand. ADOPT.
- **Friction-beating layer** — rate limits/formats/flakiness (technical only). ADOPT.
- **Access governance gate** — every external reach passes VII (constitution/Referee/power-budget); NO auth/law bypass, NEVER market manipulation. ADOPT (hard wall).

---

## Tally & pruning
~120 branches across 16 trunks. Pruned at this level: **PARK ×4**
(cross-market context — scope; prediction-market council — needs council;
empowerment drive — needs world-model; inner-society guilds — needs
council). **KILL ×0** at branch level (killing concentrates at the twig
pass). All prior research/29-34 adopted concepts now have an explicit
branch home — no loss.

## Next (still PAUSED until user picks a trunk)
Twig-level depth (the level below these branches) is one file per trunk,
in the depth order: VII Conscience + XIV Axiology → VIII Global
Workspace → XV Memory → XVI Universal Access → IX Active-Inference →
XIII Epistemics → III/XII Drives+Curiosity → the rest. No twig
expansion until the user picks the trunk to descend into.
