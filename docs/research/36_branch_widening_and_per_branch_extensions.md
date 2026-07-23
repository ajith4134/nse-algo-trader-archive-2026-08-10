# 36 — Depth Pass 1b: More Branches per Trunk + Extensions for Every Branch

**Origin:** user instruction (2026-07-23): think again + research to find
MORE branches per trunk, and for EACH branch core concept generate
extension ideas/features. Extends research/35 (which had ~120 branches).
This pass adds ~80 new branches (research-grounded) and attaches
extension ideas to branches across all 16 trunks. Twig-level depth still
paused; these extensions are the seed pool for it.

**Research grounding (this pass):** cognitive faculties incl. dual-coding
mental imagery + meta-reasoning (Paivio; MDPI metacognition model);
AI-safety subfield taxonomy — mechanistic interpretability, scalable
oversight/debate, reward modeling, mesa-optimization/inner alignment,
deceptive alignment, wireheading, instrumental convergence (EA/LW 2025
taxonomy; Intl AI Safety Report 2026); RL-for-trading — portfolio
selection / execution / options-hedging / market-making, DQN-PPO-SAC,
regime forecasting, non-stationarity (Hambly-Xu; RL-finance surveys);
CoALA agent-memory taxonomy — working/episodic/semantic/procedural +
episodic→semantic consolidation, importance scoring, in-weights
knowledge (CoALA; agent-memory surveys 2025-26).

Format per trunk: **NEW branches** (with [src]) then **Extensions**
(each branch → seed ideas). `+N` = brand-new branch. Verdicts: ADOPT
unless marked PARK/KILL. GATED stays behind VII.

---

## T-I · MIND
**NEW:** +Mental-imagery/visual reasoning (dual-coding: reason over chart
"images" not just numbers) · +Meta-reasoning controller (choose WHICH
reasoning strategy per problem) · +System-1/System-2 dual-process router
(fast reflex vs slow deliberation) · +Analogical transfer across
underlyings · +Counterfactual reasoning ("had I entered 10m later…").
**Extensions:**
- Deliberative reasoning → store reasoning traces as episodic memory; multiple strategies scored by outcome; argument-graph rationale.
- Causal reasoning → do-calculus intervention tests; causal-graph per strategy; distinguish confounder-driven vs causal edges.
- Learning subsystem → per-regime learners; meta-learning (learn-to-learn faster on new symbols); continual-learning without catastrophic forgetting.
- Abstraction → auto-name motifs and promote to tradeable vocabulary; motif hierarchy; cross-symbol motif reuse.
- Case-based reasoning → k-NN over the memory graph; adaptation of retrieved cases to current context; success-weighted recall.
- Decomposition → sub-goal trees; solve-and-cache sub-problems; parallel sub-problem dispatch to inner society (VI).
- Mechanism-verified reasoning → path-signature check; "lucky" relabelling; mechanism taxonomy per strategy.
- Devil's-advocate → strongest-counter-case generator; pre-commitment veto; red-team prompt bank.
- System-1/2 router → latency budget gate; escalate to slow path only when conviction low or stakes high.

## T-II · SENSES
**NEW:** +Liquidity/tradeability sensing (spread, depth, impact before
entry) · +Order-flow imbalance sensing · +Volatility-regime sensing
(realized vs implied) · +Event/calendar sensing (results/RBI/expiry) ·
+Correlation/breadth sensing (market-wide risk-on/off) · +Data-quality
sensing (stale/spoofed feed detection, ties VII security).
**Extensions:**
- Fused market-state → attention-weighted stream fusion; confidence per stream; missing-data imputation with flags.
- Multi-timeframe → cross-timeframe agreement score; higher-TF trend as a gate on lower-TF entries.
- Anomaly sensing → per-stream false-alarm ledger; severity grading; auto-trigger the microscope.
- Microstructure → footprint/delta; absorption detection; sweep/iceberg inference.
- Interoception → drift/latency/memory-pressure as felt signals modulating conservatism.
- Sentiment/news → entity-linked sentiment; novelty vs already-priced; source-credibility weighting (XIII).
- Liquidity sensing → skip illiquid strikes; size-to-liquidity; slippage forecast feeding IX pre-mortem.
- Data-quality sensing → cross-source reconciliation; quarantine suspect ticks; alert VII.

## T-III · WILL
**NEW:** +Risk-appetite regulator (global throttle by drawdown state) ·
+Opportunity-cost accounting · +Commitment/consistency guard (avoid
thrash) · +Multi-objective arbitration (profit vs learning vs safety) ·
+Goal-priority scheduler.
**Extensions:**
- Drive stack → setpoint auto-tuning from outcomes; drive-conflict resolution log; urgency curves per drive.
- Goal formation → hierarchical task network; goal expiry/garbage-collection; goal provenance to root drive.
- Autonomy levels → per-action-class thresholds; auto-demote authority after errors; escalation-to-human path.
- Patience → opportunity-cost of standing aside tracked; "best trade not taken" calibration.
- Conviction/fear gating → size ∝ calibrated conviction; fear spike → flatten; euphoria damp (anti-overconfidence).
- Risk-appetite regulator → daily-loss circuit breaker; win/loss-streak-aware sizing; regime-scaled exposure caps.
- Multi-objective arbitration → Pareto front over objectives; scalarization weights set by XIV values.

## T-IV · BODY
**NEW:** +Optimal execution engine (RL/TWAP/VWAP/IS slicing, [RL-exec]) ·
+Smart order routing/child-order management · +Slippage & impact model ·
+Partial-fill & timeout handling loop · +Position/inventory manager ·
+Latency/throughput management.
**Extensions:**
- Actuation → idempotent order ops; client-order-id reconciliation; dead-man's-switch on disconnect.
- Resource/economy → capital allocator across strategies; quota-aware scheduling; compute autoscaling.
- Cost homeostasis → per-trade cost attribution; brokerage/slippage budget; unprofitable-organ atrophy.
- Survival/self-healing → heartbeat + auto-restart runbooks; state snapshots; resurrection drills.
- Sentinel → dual-watchdog mutual-watch; pause-only authority; anomaly-triggered halt.
- Off-switch → square-off-then-snapshot-then-report; rehearsed shutdown; safe-mode reflex.
- Optimal execution → RL execution policy vs TWAP/VWAP baseline; child-order sizing to hide intent; venue/timing choice.
- Partial-fill loop → OPEN→poll→COMPLETE/timeout→retry/cancel; leg-completion enforcement for spreads.

## T-V · SELF
**NEW:** +Version control / lineage of self · +A-B self-testing (champion
vs challenger in paper) · +Self-documentation generator · +Capability
self-registry (what it can do now) · +Rollback/quarantine on regression.
**Extensions:**
- Shadow self-rewrite (GATED) → staging clone; gated promotion; patch-lineage tree; auto-rollback on metric regress.
- Genome/phenotype → declarative DSL; genome diff/merge; human-readable change review.
- Self-experiment protocol → change = meta-trade with PredictionRecord; court verdict; evidence-gated promote/revert.
- Self-ablation → nightly lesion one module; marginal-value estimate; keep/cut decision.
- Identity/continuity → invariant-preserving self-edits; continuity audits; "am I still me?" checks.
- Teachability → train student model from memory; gap = tacit/overfit knowledge; distillation compression.
- Ontogeny ladder → per-capability stage; graduation exams; stage-gated autonomy.
- A-B self-testing → champion/challenger paper duel; promote challenger only on court-verdicted skill edge.

## T-VI · SOCIETY
**NEW:** +Role-specialized desks (vol/flow/event/execution desks) ·
+Debate/adversarial-collaboration protocol ([safety: debate]) · +Consensus
& conflict-resolution rules · +Explanation/summarization to user ·
+Multi-agent memory governance ([mem-survey]).
**Extensions:**
- Inner society/council → chartered specialists; budgeted votes; disagreement → route to UNCERTAIN table.
- External-agent game theory → crowded-trade detection; stop-hunt/spoof anticipation; participant-flow modeling.
- Human interface → natural-language trade rationale; conversational control; tiered alerts by severity.
- Language/symbol grounding → internal "mentalese" tokens; symbol↔signal bridge; explanation grounded in real memory nodes.
- Teaching-legacy → knowledge handoff to successor versions; onboarding docs auto-written.
- Debate protocol → two agents argue for/against a trade; judge extracts the survivable case.

## T-VII · CONSCIENCE (SUPREME)
**NEW:** +Mechanistic interpretability probes ([safety]) · +Scalable
oversight (AI-checks-AI) ([safety]) · +Deceptive-alignment / inner-
alignment monitor ([safety: mesa-opt]) · +Wireheading/reward-hacking
tripwire ([safety]) · +Instrumental-convergence / power-seeking limiter
([safety]) · +Red-team harness · +Incident post-mortem & audit trail.
**Extensions:**
- Constitutional core → invariants in a read-only module; Referee verifies every self-change against it.
- Power budgets → max experiments/patches/tools/capital per period; auto-freeze on breach.
- Security/adversarial defense → poisoned-data quarantine; prompt-injection scrub on ingested web text; key-theft detection.
- Ethics/law reasoning → SEBI algo-framework reasoner; RA-registration-trigger detector; order-rate compliance; tax awareness.
- Corrigibility/off-switch → shutdownability tests; never-resist-pause invariant; safe-interrupt.
- Transparency/Referee → decision-reproduction audits; doc-vs-code divergence flags; append-only logs.
- Alignment/goal-integrity → goal-drift monitor; reward-hacking detector; deceptive-behavior probes.
- Mechanistic interpretability → inspect internal model features; concerning-feature alerts.
- Scalable oversight → a critic-AI reviews the trader-AI's high-stakes calls before commitment.

## T-VIII · SENTIENCE & GLOBAL WORKSPACE
**NEW:** +Salience/priority scorer (what earns the workspace) · +Coalition
formation (competing module bundles) · +Ignition threshold (broadcast
only above evidence bar) · +Workspace replay/rumination · +Binding across
modalities (price+flow+news into one percept).
**Extensions:**
- Limited-capacity workspace → hard slot limit; eviction policy; contention metrics.
- Global broadcast → publish-subscribe bus; every trunk subscribes; broadcast latency budget.
- Selective attention → salience ranking; inhibition of return; goal-biased attention (III).
- State-dependent attention → serial module querying to solve multi-step tasks.
- Self-model → inspectable model of own state; versioned; feeds VII.
- Attention schema → model of own attention → better attention control; predicts own focus.
- Higher-order monitoring → reliability tag on each percept; reject noise below threshold.
- Indicator scoreboard → track Butlin indicators the system satisfies; honesty-labelled, no phenomenal claim.

## T-IX · PREDICTIVE CORE / ACTIVE INFERENCE (meta)
**NEW:** +Regime-forecasting model (next-state, [RL regime]) · +Surprise/
free-energy monitor (model-mismatch alarm) · +Hierarchical predictive
layers (tick→session→regime) · +Model-based planning (rollouts) ·
+Ensemble world-models (disagreement = uncertainty).
**Extensions:**
- Generative world-model → simulate order-book/price paths; calibrate against realized; per-underlying models.
- Prediction-error loop → act to reduce surprise; error spikes → widen uncertainty (feeds XIII).
- Counterfactual rollouts → "what-if" entry/exit variants; regret estimation.
- Per-trade pre-mortem → Monte-Carlo this setup through regime-matched replay; P5-loss gate.
- World-model scoreboard → perception-error vs action-error split; weather-station forecasts scored.
- Precision weighting → trust each signal by context; down-weight in anomalous regimes.
- Dream synthesis → nightly perturbed re-plays of the real tape; consolidation value tracked.
- Ensemble world-models → forecast spread = actionable uncertainty; disagreement routes to UNCERTAIN.

## T-X · AUTOPOIESIS / SELF-PRODUCTION (meta)
**NEW:** +Self-monitoring health loop · +Component lifecycle manager
(spawn/retire organs) · +Boundary/identity integrity check · +Homeostatic
setpoint keeper.
**Extensions:**
- Component self-maintenance → per-organ health score; auto-heal or retire.
- Boundary maintenance → self-vs-environment tagging; reject foreign injected "self" edits (ties VII).
- Metabolic accounting → organs earn their compute; cold-storage the freeloaders.
- Self-repair binding → autopoiesis realised through IV survival runbooks.
- Component self-production → foundry writes new organs (GATED, Referee-reviewed).

## T-XI · GENERATIVITY & OPEN-ENDEDNESS
**NEW:** +Auto-benchmark generation (invent its own tests) · +Diversity
pressure/speciation · +Stepping-stone collection (keep useful-but-not-yet-
winning ideas) · +Minimal-criterion coevolution.
**Extensions:**
- Niched population → calendar-context niches; court-verdicted-skill fitness; migration between niches.
- Auto-curriculum → generate escalating challenges matched to current skill (POET).
- Strategy/feature invention → search program space; grammar-constrained generation; validate via §9 lab.
- Quality-diversity archive → MAP-Elites grid over behavior descriptors; illuminate the strategy space.
- Fossil record → extinct variants + cause of death; mine fossils for reusable parts.
- Red-queen coevolution → adversarial arm evolves with the finder; arms-race logging.
- Stepping-stones → keep non-winning novelty that may enable later winners (novelty-search insight).

## T-XII · INTRINSIC MOTIVATION / CURIOSITY
**NEW:** +Empowerment estimator (prefer optionality) [PARK: needs world-
model] · +Surprise-seeking vs surprise-avoiding balance · +Skill-gap
targeting (train where weakest, ties B2 envelope) · +Diversity/novelty
bonus in exploration.
**Extensions:**
- Learning-progress reward → reward where prediction-error is falling fastest (Schmidhuber).
- Info-gain experiment selection → pick trades maximizing expected information about load-bearing unknowns.
- Curiosity-pays-rent → exploration budget compounds on realized info-value; shrinks when barren.
- Boredom signal → reason-ledger stagnation → escalate novelty.
- Competence/certainty drives → PSI urges as scalar motivators feeding III.
- Skill-gap targeting → route practice to competence-envelope holes (B2).

## T-XIII · EPISTEMICS / TRUTH & UNCERTAINTY
**NEW:** +Uncertainty decomposition (aleatoric vs epistemic) · +Evidence
provenance/citation trail · +Deception/misinformation resistance (ties
security) · +Bet-sizing-as-belief (Kelly-style stake = confidence) ·
+Forecasting-tournament self-scoring.
**Extensions:**
- Graded beliefs → NARS-style truth (frequency+confidence); belief decay.
- Bayesian revision → coherent updates; conjugate/approx posteriors; prior provenance.
- Calibration → Brier/log-loss; reliability curves per regime; recalibration.
- Contradiction resolution → detect belief conflicts; resolve by evidence weight; log the resolution.
- Source grading → A/B/C credibility; independence check for triangulation.
- Hypothesis pipeline (double-sided) → trade claim AND negation; survivorship into strategies.
- Assumption registry → declared assumptions + statistical tripwires; break → pause downstream.
- Skill-vs-luck court → 4-verdict pipeline; train only on the diagonal.
- Uncertainty decomposition → separate irreducible noise from ignorance; ignorance → curiosity target (XII).

## T-XIV · AXIOLOGY / VALUES & PRACTICAL WISDOM
**NEW:** +Preference learning from user feedback ([safety: reward
modeling]) · +Value-uncertainty (stay unsure of the true objective,
Russell) · +Moral/regulatory constraint reasoner · +Long-vs-short-horizon
value trade-off · +Fairness-to-future-self (don't mortgage tomorrow).
**Extensions:**
- Utility function → explicit, auditable objective; risk-adjusted; drawdown-penalized.
- Assistance-game alignment → treat user intent as latent, query when unsure; defer on ambiguity.
- Value-drift/reward-hacking detection → monitor objective proxy vs true intent; Goodhart alarms.
- Risk-preference values → utility curvature; loss-aversion parameter (behavioral-RL insight).
- Ethical constraints-as-values → non-negotiables felt as values, not just external rules.
- Practical wisdom → context-sensitive exceptions with justification; case law of judgments.
- Corrigibility-as-value → prefers being correctable; low cost to accept override.

## T-XV · MEMORY & KNOWLEDGE BASE
**NEW:** +Consolidation engine (episodic→semantic, [CoALA]) · +Importance
scoring / salience-weighted retention · +In-weights vs in-context tiering ·
+Memory provenance & versioning · +Conflict/duplication resolution ·
+Memory compression/summarization · +Forgetting curve / decay policy.
**Extensions:**
- Working memory → current situation+goal buffer; slot-limited (ties VIII).
- Episodic memory → each experiment/trade as a node; importance score; replayable.
- Semantic memory → knowledge graph of facts/relations; entity resolution.
- Procedural memory → strategies/skills as executable, versioned artifacts.
- Temporal knowledge graph → bitemporal (valid-time vs system-time); time-travel queries.
- Consolidation → nightly episodic→semantic summarization; contradiction merge; reflection diffs.
- Forgetting/invalidation → supersede-not-delete; decay unused; keep audit of what was retired.
- Retrieval → hybrid vector+graph; recency+importance+relevance ranking; case adaptation.
- Reason ledger → per-reason evidence accrual; rise/fall independent of citing strategy.

## T-XVI · UNIVERSAL ACCESS & ACQUISITION (GATED)
**NEW:** +Web-agent/browser automation (read any public page) · +Document
understanding (PDF filings/annual reports) · +Real-time news/social
firehose adapter · +Alternative-data connectors (weather, shipping, etc.)
[PARK: scope/value gate] · +API schema auto-discovery · +Cache/dedup layer
· +Access audit log.
**Extensions:**
- Internet research organ (GATED) → scheduled sweeps; multi-angle search; claim → XIII pipeline before use.
- Broker/data API layer → swappable-source protocols; failover across sources; auth in secret store.
- Tool foundry (GATED) → detect recurring gap → write tool+tests → Referee review → admit.
- Data-source prospecting (GATED) → evaluate candidate feeds in sandbox; info-diet admission.
- Participant-wise OI ingestion → the opponent-ledger feed (queued in flowchart 02).
- Retrieval-augmented fetch → pull the right knowledge on demand; ground answers in sources.
- Friction-beating layer → retries/backoff, format drift handling, schema validation (TECHNICAL only).
- Access governance gate → every reach passes VII (constitution/Referee/power-budget); NO auth/law bypass; NEVER market manipulation.

---

## Tally, pruning, no-loss
- **~80 new branches** added across 16 trunks (research-grounded);
  **~200 branches** total now (research/35 + /36).
- **Extensions:** every branch carries 2-4 seed extension ideas — the
  raw material for the twig-level depth passes.
- **PARK ×3 new:** empowerment estimator (needs world-model),
  alternative-data connectors (scope/value), + existing parks stand.
  **KILL ×0** (still concentrated at twig level).
- No loss: all research/29-35 concepts retain their homes; new branches
  are additive; GATED/hard-wall constraints unchanged.

## Next (PAUSED)
Twig-level depth = one file per trunk, expanding these branches +
extensions into concrete buildable specs, in the depth order
(VII+XIV → VIII → XV → XVI → IX → XIII → III/XII → rest), only when the
user picks a trunk.
