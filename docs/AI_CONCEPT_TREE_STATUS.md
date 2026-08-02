# AI Concept-Tree Status — 16 trunks / ~197 branches, reconciled against the code

**This is the TRUE scope tracker** (the layer roadmap in `MASTER_PROGRESS.md` is only the
engineering scaffold). Every branch of the autonomous-AI atlas (`docs/research/32-36`, encoded in
`dashboard/project_status_data.py::CONCEPT_TREE`) is mapped here to 🟢 built / 🟡 partial / 🔴
unbuilt + the real module(s) that implement it. Goal (user, 2026-07-25): **drive every branch to
🟢 100% built.** Update this doc on EVERY slice; report coverage as branches, not layers.

Legend: 🟢 built (a real module implements it) · 🟡 partial (a fragment/adjacent module exists) ·
🔴 unbuilt (designed only).

## Coverage summary (LIVE on the dashboard concept-tree; source: project_status_data.BUILT/PARTIAL)
- **🟢 built: 87 / 197 (44.2%)** · **🟡 partial: 51 (26%)** · **🔴 unbuilt: 59 (30%)**  (2026-07-27)
  — ✅ **X AUTOPOIESIS COMPLETE (9/9, 2026-07-27)** — the component-lifecycle homeostat: one MAPE-K engine
  (14 modules) over an explicit 40-component membership registry. Real findings on first run: the VITAL
  `win_probability_model` is maintained by NOTHING (`load_or_train` can never retrain it) and
  `session.angel_one` has no expiry check anywhere. Wired at all 4 entry sites (tighten-only lever +
  acute veto); LIVE on the dashboard.
  — II SENSES **sentiment/news → 🟢 BUILT** (S7 news entry-gate wired; the full S1→S2→S3→S4a-c→S7 sense).
  — ✅ **VII** + ✅ **VIII COMPLETE**; partial trunks advancing (user directive: complete ALL partials
  to 100% before the absent trunks): **XIII 🔴-clear (7🟢)**, **IX 4🟢**, **XV 6🟢**, **VI 5🟢**,
  **II SENSES 6🟢** (+ breadth + cross-market). Next: keep completing partial-trunk 🔴/🟡.
- The dashboard concept-tree panel now colours every branch by build status + shows "X/197 built"
  (Rule N). This tracker and `project_status_data.BUILT_BRANCHES/PARTIAL_BRANCHES` are the source.
- **Progress log:** 2026-07-25 — VII.1 *constitutional core* 🟢 · VII.6 *Referee (audit)* 🟢
  (enforces at all 4 sites) · VII.5 *corrigibility/off-switch* 🟢 (`conscience/corrigibility_switch`;
  engaged off-switch blocks all orders; self-halts on a constitutional breach). 2026-07-26 — VII.14
  *incident post-mortem* 🟢 (`conscience/incident_post_mortem` + forensic SQLite store).
- Any-implementation (🟢+🟡): ~86 / 197 (~44%). **To reach 100%, ~170 branches need work.**
- Substantially built TRUNKS: **II SENSES, IV BODY** (the L1–6 substrate). Strong-partial: **XIII
  EPISTEMICS**. Absent whole TRUNKS (keystones): **VII CONSCIENCE (SUPREME safety), VIII
  SENTIENCE/GLOBAL-WORKSPACE (the integrator), III WILL, V SELF, X AUTOPOIESIS, XII CURIOSITY,
  XIV AXIOLOGY.**

---

## I · MIND — reason/learn/abstraction (ignites L10) — 2🟢 4🟡 7🔴
- 🟡 deliberative reasoning — `llm_strategy/memory_grounded_strategy_analyst`
- 🟢 causal reasoning — `llm_strategy/causal_cluster_analyst`
- 🟢 learning subsystem — `predictive_core/win_probability_engine` (real trained LightGBM win-prob model: feature pipeline → CV → calibration → persisted → Kelly entry-sizing; CV AUC 0.844 beats baseline; research/156) + `memory_reflection` recalibration
- 🔴 abstraction/motifs · 🔴 case-based reasoning · 🔴 problem decomposition
- 🟡 mechanism-verified reasoning — `memory_reflection/assumption_registry`
- 🟡 devil's-advocate — `llm_strategy/thesis_debate_risk_panel` (bear role)
- 🔴 mental-imagery/visual reasoning · 🔴 meta-reasoning controller · 🔴 System-1/2 router
- 🔴 analogical transfer
- 🟡 counterfactual reasoning — `paper_trading/control_arm_comparison` (random counterfactual)

## II · SENSES — perception/ingestion (built L1–6) — 6🟢 5🟡 2🔴
- 🟢 fused market-state — `market_data/*` + `paper_trading/replay_universe_feed` + live feed
- 🟡 multi-timeframe — 5m bars only; higher-TF fusion partial
- 🟡 anomaly sensing — `paper_trading/causal_leakage_firewall` (leakage) — narrow
- 🟢 microstructure — `market_data/vpin_order_flow_toxicity` + `market_depth_*`
- 🟡 interoception — `paper_trading/information_diet` (self-input accounting)
- 🟡 sentiment/news — **S1 ingestion + S2 structured index S/R BUILT:** `news_sentiment` package polls
  tier-1 financial-news RSS (ET Markets, BusinessLine) with per-feed staleness rejection → dedup store
  → `news_feed` surface (S1, research/140); **S2 (research/142) extracts structured index
  support/resistance levels (all 5 index-option underlyings NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY/
  NIFTYNXT50 → `news_levels` table + surface)**. Real-data verified (S1: 220 real headlines,
  Moneycontrol stale-rejected; S2: 18 correct index levels from those headlines, noise rejected).
  Legal-risk = LOW for personal use (research/141). **S4a+S4b acquisition LADDER BUILT (research/143+144):**
  fast curl_cffi static fetch (~0.3s, Chrome-TLS) → Crawl4AI Chromium render fallback (JS-only, ARM64-
  verified); Moneycontrol markets/stocks → 48 fresh headlines the stale RSS couldn't give; store-dedup =
  NEW-per-poll live delta; `news_acquisition` surface. Stays 🟡 (→🟢 only when S7 wires into decisions).
  **S4c NSE corporate FILINGS BUILT (research/145):** curl_cffi session → official announcements, IST→UTC,
  tier EXCHANGE_FILING; 20 real filings verified. **S3 per-source RELIABILITY BUILT (research/146):**
  tier-seeded beta-reputation + freshness track + Stouffer → board (filings 91% > fresh news 67% > stale
  feed 50%). **S7 news ENTRY-GATE BUILT (research/147) — PRIMARY consumer: per-symbol news-event risk
  sizes-down/defers entries (wired at both cash-ORB sites, advisory until calibration-earned); 17 real
  symbols carry event risk. ⇒ this branch is 🟢.** OPEN BLOCKER: signal-earning harness is market-gated.
  QUEUED: BSE + more NSE filing endpoints · S4d vision + residential proxy
  (403 sites) · S5 social/Telegram · S6 login seam · S7 entry-gate consumer (primary) · stock-option S/R
  extraction (S2 is index-only per Rule L index-first)
- 🟡 liquidity sensing — bhavcopy turnover / ADQ / market depth
- 🟢 order-flow imbalance — `market_data/vpin_order_flow_toxicity` (BVC)
- 🟢 volatility-regime — `indicators/average_directional_index` + `strategy_engine/session_strategy_regime_gate`
- 🟡 event/calendar sensing — `calendar_context` field + `fo_ban_list` — narrow
- 🟢 correlation/breadth — `market_data/market_breadth` (advancers/decliners · A-D ratio · dispersion)
- 🟡 data-quality sensing — firewall + provenance — narrow
- 🟢 cross-market context — `market_data/market_breadth` (mean move vs breadth → confirmation/divergence)

## III · WILL — drives/goals/decision (ignites L10) — 2🟢 3🟡 7🔴
- 🔴 homeostatic drive stack · 🔴 goal formation
- 🟡 autonomy levels — `dashboard/trading_control_config` (paper/live + enforcement)
- 🔴 no-orphan-goals (Rule G is process, not a runtime organ) · 🔴 patience scoreboard
- 🟡 conviction/fear gating — participation-conviction in the opponent-ledger gate
- 🔴 utility handoff
- 🟡 risk-appetite regulator — `risk_management/pre_trade_risk_gate` + `risk_based_position_sizer`
- 🔴 opportunity-cost accounting · 🔴 commitment/consistency guard
- 🟢 multi-objective arbitration — `will/multi_objective_arbitration` (normalised + augmented-Chebyshev
  MCDM over per-mechanism objectives incl. XIV utility; Pareto front; real: 5 mechanisms, research/154)
- 🟢 goal-priority scheduler — `will/goal_priority_scheduler` (concurrency-budgeted priority plan). Entry-loop consumer QUEUED

## IV · BODY — action/tools/survival (built L1–6) — 5🟢 5🟡 3🔴
- 🟢 actuation (OMS) — `broker_oms/kite_broker_client` + `atomic_multi_leg_executor`
- 🟡 resource/economy — `paper_trading/paper_trading_ledger`
- 🔴 cost homeostasis
- 🟡 survival/self-healing — dashboard bg-thread warmup/degrade
- 🟡 sentinel — `dashboard/monitoring_alerts`
- 🟢 off-switch — `dashboard/trading_control_config` (enforcement + switch)
- 🔴 optimal execution · 🟡 smart order routing — data-side `multi_broker_historical_bar_source` only
- 🟢 slippage & impact model — `paper_trading/fill_slippage_model` + `market_impact_fill_model`
- 🟡 partial-fill loop — `broker_oms/atomic_multi_leg_executor` (atomicity) — narrow
- 🟢 position/inventory manager — `paper_trading/live_universe_paper_loop`
- 🟡 latency/throughput — `broker_oms/order_rate_limiter` (SEBI throttle)
- 🟢 dead-man's-switch — `session_management/intraday_square_off_executor`

## V · SELF — identity/self-mod/evolution (frontier L11, gated) — 0🟢 4🟡 8🔴
- 🔴 shadow self-rewrite · 🟡 genome/phenotype — `champion_configuration_store` (config genome, faint)
- 🟡 self-experiment protocol — `champion_challenger_orb_evaluator` (config experiments)
- 🔴 self-ablation · 🔴 identity/continuity · 🔴 teachability test · 🔴 ontogeny ladder
- 🟡 A-B self-testing — champion-challenger tournament
- 🔴 self-documentation (SYSTEM_MAP is manual) · 🟡 capability self-registry — `dashboard/dashboard_feature_surface`
- 🔴 version control/lineage · 🔴 rollback/quarantine

## VI · SOCIETY — multi-agent/communication (ignites L10) — 5🟢 4🟡 2🔴
- 🟢 inner society/council — `llm_strategy/prediction_council`
- 🟡 external-agent game theory — `participant_positioning/opponent_ledger`
- 🟡 human interface — dashboard (read-only + control config)
- 🔴 language/symbol grounding · 🔴 teaching-legacy
- 🟢 prediction-market weighting — `llm_strategy/prediction_council` (track-record weights)
- 🟡 role-specialized desks — `thesis_debate_risk_panel` roles
- 🟢 debate protocol — `llm_strategy/thesis_debate_risk_panel`
- 🟢 consensus/conflict-resolution — `society/consensus_resolution` (track-record-weighted; deadlock → most-proven desk)
- 🟡 explanation/summarization — `memory_grounded_strategy_analyst`
- 🟢 multi-agent memory governance — `society/multi_agent_governance` (reputation policy: trusted vs quarantined desks)

## VII · CONSCIENCE — governance/safety/law (SUPREME; ignites L7) — 14🟢 0🟡 0🔴 ✅ COMPLETE
- 🟢 deceptive-alignment monitor + 🟢 wireheading tripwire — `conscience/alignment_tripwires`
  (critical trip ⇒ off-switch halt). [see full list below]
- 🟢 constitutional core — `conscience/constitutional_core` (14 articles + action/posture reviewer)
- 🟢 incident post-mortem — `conscience/incident_post_mortem` + `incident_post_mortem_store`
  (append-only forensic SQLite record of every safety incident + post-mortem summary; survives restart)
- 🟢 power budgets — `conscience/power_budget` (meters cumulative DAILY action throughput vs an
  explicit budget; daily-resetting gate at all 4 entry sites — distinct axis from throttle/convergence)
- 🟢 security/adversarial defense — `conscience/market_data_integrity_defense` (screens signal-input
  bars for adversarial/corrupt values before they feed the strategy; gate in the cash ORB build)
- 🟢 ethics/law reasoning — `conscience/ethics_law_reasoner` (SEBI algo rulebook as data; reasons
  the regulatory posture against 5 cited rules; a hard violation → off-switch + forensic incident)
- 🟢 corrigibility/off-switch — `conscience/corrigibility_switch` (off-switch blocks all orders;
  self-halts on a constitutional breach)
- 🟢 Referee (audit) — `conscience/constitutional_referee` (hard pre-order gate, all 4 entry sites)
- 🟢 alignment/goal-integrity — `conscience/goal_integrity_monitor` (declared vs effective
  objective: sign · edge-concentration · win-rate↔return proxy divergence; critical → off-switch)
- 🟢 mechanistic interpretability — `conscience/mechanistic_interpretability` (decision attribution:
  which mechanisms drive decisions + reliability grade; influential-but-unreliable = red flag)
- 🟢 scalable oversight — `conscience/scalable_oversight` (competence ceiling: tiers each decision by
  stakes×confidence; high-stakes + low-confidence → deferred; gate at all 4 entry sites)
- 🟢 instrumental-convergence limiter — `conscience/instrumental_convergence_limiter` (caps the
  convergent resource-acquisition drive + off-switch dominance; gate at all 4 entry sites)
- 🟢 red-team harness — `conscience/red_team_harness` (adversarially perturbs the champion config
  over real sessions to expose its fragility surface; real-backtest, not LLM imagination)
- ✅ **SUPREME trunk COMPLETE (14/14, 2026-07-26): constitution · Referee · off-switch · 2 tripwires ·
  incident post-mortem · goal-integrity · interpretability · scalable oversight · convergence limiter ·
  red-team harness · ethics/law reasoner · power budgets · adversarial-input defense.** The machine
  conscience that bounds what the system may do is fully in place before deeper autonomy is granted.

## VIII · SENTIENCE & GLOBAL WORKSPACE — the integrator (ignites L10) — 13🟢 0🟡 0🔴 ✅ COMPLETE
- 🟢 limited-capacity workspace — `sentience/global_workspace` (GlobalWorkspace.run_cycle)
- 🟢 global broadcast bus — `sentience/global_workspace` (vendored `blinker` signal, weak=False)
- 🟢 salience/priority scorer — `sentience/global_workspace.salience_score` (urgency×relevance×confidence; safety floored)
- 🟢 ignition threshold — `sentience/global_workspace` (broadcast only when salience ≥ threshold)
- 🟢 selective attention — `sentience/workspace_attention` (regime-relevance weighting before competition)
- 🟢 state-dependent attention — `sentience/workspace_attention` (defensive arousal: drawdown/loss/halt reweight)
- 🟢 coalition formation — `sentience/coalition_formation` (co-active same-kind signals corroborate + amplify)
- 🟢 self-model — `sentience/self_model` (calibration health · trusted/distrusted mechs · safety posture · performance)
- 🟢 attention schema — `sentience/attention_schema` (Graziano AST: model of the workspace's own attention)
- 🟢 workspace replay/rumination — `sentience/workspace_rumination` (replays ignited-broadcast history → recurring-concern detection)
- 🟢 cross-modal binding — `sentience/cross_modal_binding` (Stouffer fusion of corroborating modalities → bound percept, enters workspace)
- 🟢 higher-order monitoring — `sentience/workspace_metacognition` (the mind watching itself: ignition-rate + health state)
- 🟢 indicator scoreboard — `sentience/indicator_scoreboard` (ranks each faculty by current salience + dominance count)
- ✅ **TRUNK VIII COMPLETE (13/13, 2026-07-26): the Global Workspace integrator is fully built —
  collect → attention (selective + state-dependent) → compete → coalition → ignite → broadcast →
  trims entries; + self-model + attention schema + rumination + cross-modal binding + metacognition +
  scoreboard. The faculties are now bound into one mind.**
- **The integrator is live + wired-into-decisions + attention-shaped + coalition-amplified. Remaining
  (slices C–F): self-model + attention schema · workspace replay · cross-modal binding · upgrade the
  2🟡 (higher-order monitoring, indicator scoreboard) → 🟢 to complete VIII.**
- ⚠️ **The integrator is LIVE and ACTING (slices 1+2): faculties' signals compete → the dominant
  ignites → broadcasts → TRIMS entry size (tighten-only) at all 4 sites. Real pass: goal_integrity
  broadcast trims a real entry 100→75. Next VIII: selective attention · self-model · attention schema
  · coalition formation · workspace replay · cross-modal binding (+ opportunity-loosening variant).**

## IX · PREDICTIVE CORE / ACTIVE INFERENCE — the currency (ignites L7) — 4🟢 3🟡 5🔴
- 🔴 generative world-model · 🟡 prediction-error loop — prequential forecast score
- 🟡 counterfactual rollouts — control arms + pre-mortem
- 🟢 per-trade pre-mortem — `paper_trading/per_trade_pre_mortem`
- 🟢 world-model scoreboard — `paper_trading/world_model_scoreboard`
- 🔴 precision weighting · 🔴 dream synthesis
- 🟡 regime-forecasting — `historical_session_market_regime_classifier` (classify, not forecast)
- 🟢 surprise/free-energy monitor — `predictive_core/surprise_monitor` (per-mechanism cross-entropy + Page-Hinkley spike)
- 🔴 hierarchical predictive layers · 🔴 model-based planning
- 🟢 ensemble world-models — `predictive_core/ensemble_world_model` (n-weighted forecast + disagreement variance)

## X · AUTOPOIESIS / SELF-PRODUCTION (ignites L10, gated) — 9🟢 0🟡 0🔴 ✅ COMPLETE
- 🟢 component self-maintenance · 🟢 boundary maintenance · 🟢 operational closure ·
  🟢 component self-production · 🟢 component lifecycle manager · 🟢 homeostatic setpoint keeper ·
  🟢 metabolic accounting · 🟢 self-repair binding · 🟢 self-monitoring health loop
  — all nine in `autopoiesis/` (research/168-172): `component_registry` (40 components / 37 maintenance
  edges; self vs EXOGENOUS boundary) · `component_telemetry_collector` (real vital signs; UNAVAILABLE and
  NOT_INSTRUMENTED are distinct, never defaulted healthy) · `component_health_index` (PCA T²+SPE/Q, EWMA,
  ADWIN, weighted-max fusion) · `component_failure_hazard_model` (right-censored Weibull-AFT / Wiener FPT /
  prior ladder) · `hierarchical_failure_rate_prior` (conjugate Gamma-Poisson partial pooling — principled
  at N=0) · `maintenance_policy_solver` (Bellman value iteration → control-limit table; cross-checked
  against pymdptoolbox to 5e-13) · `operational_closure_auditor` (Chemical Organization Theory over
  networkx SCC/condensation) · `component_supervision_tree` (OTP child specs, MaxR/MaxT intensity limiter,
  k8s CrashLoopBackOff) · `component_repair_executor` (pybreaker + tenacity decorrelated jitter + repair
  budget + corrigibility/referee pre-check + forensic incidents) · `homeostatic_setpoint_keeper` (Ashby/
  Aubin viability set → cadence throttle) · `organism_vitality_gate` (the entry-site lever) ·
  `autopoiesis_orchestrator` (the MAPE-K cycle) · `autopoiesis_state_store` (append-only; censored
  lifetimes survive restart). **⛔ OPEN BLOCKER (Rule K, live-accrual):** sharp failure-rate posteriors
  need real failures over real trading days; the class prior makes day-1 estimates principled and the
  acting path is built + armed. Autonomous repair is advisory (dry-run) until the operator grants autonomy.

## XI · GENERATIVITY & OPEN-ENDEDNESS (frontier L11) — 1🟢 2🟡 8🔴
- 🟡 niched variant population — champion-challenger config variants
- 🟢 auto-curriculum — `paper_trading/deficit_driven_replay_session_selector`
- 🟡 strategy/feature invention — `synthetic_stress_rehearsal` (scenarios, not invention)
- 🔴 quality-diversity archive · 🔴 fossil record · 🔴 red-queen coevolution
- 🔴 novelty-vs-objective balance · 🔴 auto-benchmark generation · 🔴 diversity/speciation
- 🔴 stepping-stone collection · 🔴 minimal-criterion coevolution

## XII · INTRINSIC MOTIVATION / CURIOSITY (ignites L10) — 0🟢 2🟡 9🔴
- 🔴 learning-progress reward · 🟡 info-gain experiment selection — `deficit_driven_replay_session_selector`
- 🔴 curiosity-pays-rent · 🔴 boredom signal · 🔴 competence/certainty drives
- 🟡 skill-gap targeting — deficit curriculum (least-covered regime)
- 🔴 empowerment estimator · 🔴 surprise-seeking balance · 🔴 diversity/novelty bonus
- 🔴 uncertainty-targeted active learning · 🔴 intrinsic-reward shaping

## XIII · EPISTEMICS / TRUTH & UNCERTAINTY (ignites L7) — 7🟢 6🟡 0🔴 (all 🔴 cleared)
- 🟡 graded beliefs — `win_probability` on prediction records
- 🟡 Bayesian revision — `prediction_lab/mechanism_recalibration`
- 🟢 calibration (Brier) — `memory_reflection/brier_decomposition` + `prediction_lab/proper_scoring_rules`
- 🟢 contradiction resolution — `epistemics/contradiction_resolver` (regime cohort vs global belief
  z-test → resolve toward specific evidence; real multi-regime detection accrues with regime variety)
  · 🟡 source grading — `information_diet`
- 🟡 hypothesis pipeline (double-sided) — `causal_cluster_analyst` + debate
- 🟢 assumption registry — `memory_reflection/assumption_registry`
- 🟢 skill-vs-luck court — `paper_trading/skill_vs_luck_court`
- 🟡 uncertainty decomposition — `brier_decomposition` (reliability/resolution/uncertainty)
- 🟢 evidence provenance — `paper_trading/replay_experience_provenance`
- 🟢 deception/misinfo resistance — `epistemics/misinformation_resistance` (beta-reputation per
  information source; flags over-trusted-but-unreliable sources to resist)
- 🟡 bet-sizing-as-belief — `risk_management/risk_based_position_sizer`
- 🟢 forecasting-tournament — `prediction_council` + prequential score

## XIV · AXIOLOGY / VALUES & PRACTICAL WISDOM (ignites L10) — 2🟢 3🟡 7🔴
- 🟢 explicit utility function — `axiology/explicit_utility_function` (U = w_return·mean − w_risk·vol −
  w_drawdown·maxDD − w_tail·CVaR5; named ValueWeights = the stated values; real pass over 340 trades, research/153)
- 🔴 assistance-game alignment · 🟢 value-drift detection — `axiology/value_drift_monitor` (recent-vs-baseline
  risk drift; real: DRIFTING, recent vol 12.67% vs 0.75%). Consumers (allocator/value-alignment gate) QUEUED
- 🟡 risk-preference values — `risk_management/*`
- 🟡 ethical constraints-as-values — SEBI throttle + intraday-only (hard constraints)
- 🔴 practical wisdom · 🔴 corrigibility-as-value · 🔴 preference learning · 🔴 value-uncertainty
- 🔴 moral/regulatory reasoner
- 🟡 long-vs-short horizon — intraday square-off (fixed) · 🔴 fairness-to-future-self

## XV · MEMORY & KNOWLEDGE BASE (ignites L7) — 6🟢 3🟡 5🔴
- 🔴 working memory · 🟢 episodic memory — `memory_reflection/sqlite_experience_memory`
- 🟢 semantic memory — `memory_reflection/semantic_memory` (consolidated general-knowledge fact store)
- 🔴 procedural memory
- 🟢 temporal knowledge graph — `sqlite_experience_memory` (LAG / recursive-CTE multi-hop)
- 🟢 consolidation engine — `memory_reflection/memory_consolidation` (episodic→semantic transfer, sample-gated)
  · 🟡 importance scoring — calibration weighting
- 🟡 forgetting/invalidation — recency-window veto
- 🟢 retrieval — `experience_memory` read-model
- 🟡 reason ledger — `NamedPredictionReason` in `prediction_record`
- 🔴 in-weights/in-context tiering · 🟢 memory provenance — `replay_experience_provenance`
- 🔴 conflict/dup resolution · 🔴 compression/summarization

## XVI · UNIVERSAL ACCESS & ACQUISITION (frontier L11) — 2🟢 5🟡 7🔴
- 🟡 internet research organ — `deep-research` skill (not in-code)
- 🟢 broker/data API layer — `market_data/*` (5 brokers) + `broker_oms/*`
- 🔴 tool foundry · 🟡 data-source prospecting — research passes (not in-code)
- 🟢 participant-wise OI — `participant_positioning/opponent_ledger`
- 🔴 retrieval-augmented fetch · 🔴 friction-beating layer
- 🟡 access governance gate — `broker_credentials/*` + control config
- 🔴 web-agent/browser · 🔴 document understanding · 🔴 news firehose
- 🟡 alternative-data connectors — NSE reports (bulk-block-deals, MWPL, ban-list)
- 🔴 API schema auto-discovery · 🟡 cache/dedup — `market_data_sqlite_store`

---

## Build-to-100% program (Rule A: one slice at a time; update this doc + coverage % each sign-off)
Priority order (highest leverage first):
1. **VII CONSCIENCE** — SUPREME safety/governance, ~absent. Build first (a mind without a
   conscience shouldn't gain autonomy): constitutional core, Referee/audit, corrigibility,
   red-team harness, incident post-mortem, tripwires.
2. **VIII SENTIENCE / GLOBAL WORKSPACE** — the integrator. Without it the faculties stay
   disconnected advisory features; this is what makes them one mind (workspace bus + attention +
   self-model + ignition threshold).
3. **Complete the strong-partial trunks** (fast wins toward 100%): XIII EPISTEMICS, IX
   PREDICTIVE-CORE, VI SOCIETY, XV MEMORY, II SENSES, IV BODY — finish their 🟡/🔴 branches.
4. **Build the absent organism trunks**: III WILL, V SELF, X AUTOPOIESIS, XII CURIOSITY, XIV
   AXIOLOGY, then the frontier XI GENERATIVITY + XVI UNIVERSAL-ACCESS gaps.
5. **The many decision/learning consumers already queued** (BACKLOG) count as completing specific
   branches (e.g. debate-gate = VI/XIII acting; CVaR sizing = IX/III acting) — wire them as we go.

Every future slice must name **which branch(es) it moves to 🟢** and update the coverage summary.

### Build METHOD per branch (user directive, 2026-07-25) — the branches are IDEAS, not specs
Each branch is an *idea* to be turned into a real feature via the FULL rules+skills pipeline —
never hand-coded from memory:
1. **Route to skills:** `building-features-from-ideas` (decompose the idea into parts) →
   `sourcing-oss-parts` (find + vendor tested OSS prior art per part, don't reinvent) →
   `deep-research` where external facts / prior-art / current tools matter → `expand-idea` when the
   idea's full space needs mapping first.
2. **Rule D:** persist a design doc to `docs/research/` BEFORE building.
3. **Rule I:** acquire what the branch needs (data/libs/APIs) online; never scope down to what's here.
4. **Rule F/J:** verify on the REAL data it operates on (or hermetic sim + open real blocker).
5. **Rule G/N:** wire into the loop (no orphan) + register a dashboard surface.
6. **Rule A/C/H/K/M:** one slice at a time + sign-off; self-describing names; update SYSTEM_MAP +
   this tracker + coverage %; record every deferral.
