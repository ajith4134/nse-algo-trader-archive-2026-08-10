# MASTER BUILD ORDER — the combined plan (existing bot + 9 ideas + gap engines)

**Created 2026-08-02.** Synthesizes: the EXISTING system (288 modules / 25 packages, 87/197 atlas
branches built) + the 9 new ideas (`docs/ideas/`) + the 3 gap engines (`docs/ideas/_GAP_ANALYSIS…`) +
the redesign (`REDESIGN_v1…` + `feature_atlas`). **Principle: REUSE-FIRST deepening (Rule G/I/E) — most
"new" ideas are additions to mature packages, not rebuilds.** Each item: engine-grade (Rule P), gated,
self-calibrating (no hard-codes), verified on real data (Rule F). Plugins auto-invoked per task (see the
skill-gate hook).

## Reuse map (idea → existing package to extend)
| New idea | Existing base to REUSE/extend |
|---|---|
| #8 LLM gateway | **`llm_strategy/swappable_multi_provider_llm_client` + `llm_provider_registry` + ollama/anthropic/openai providers** — add subscription lane + router |
| #4 news/online-research organ | **`news_sentiment/`(22)** + `crawl4ai` (installed) |
| #5 memory | **`memory_reflection/`(7)** — add Graphiti bitemporal KG |
| #2 radar | **`market_data/`(33) + `paper_trading/`(57)** |
| #4 directional bots | **`llm_strategy/`** debate/council/allocator + **`predictive_core/`(13)** |
| #1 regime brain/router | **`llm_strategy/meta_strategy_allocator` + `sentience/`(global-workspace integrator)** |
| gap risk+alloc | **`risk_management/`(6) + `capital_allocation/`(9)** |
| gap ops/exec | **`broker_oms/`(8) + `broker_sessions/`(8)** |
| #9 chat + dashboard | **`dashboard/`(12)** + frontend-design plugin |
| gap validation | vendor **`cpcv.py`** (nse-crypto-bot-final) + `paper_trading` |

## The order (dependency-first; ▶ = slice-1 start)

### PHASE 0 — Foundation (everything gates on these)
- **0.1 ▶ LLM gateway subscription lane (#8)** — extend the existing swappable client: add
  `claude_code_subscription_provider` (Agent SDK, **Haiku+minimal, warm persistent client** — spiked
  ✅ `research/llm_gateway_spec…`) + cost-ladder router + auto-fallback. *Unblocks all LLM organs + chat.*
- **0.2 Cost engine (L1 net-EV gate)** — STT/brokerage/GST/stamp/slippage; every signal passes it. Survival.
- **0.3 Validation engine (gap #8)** — vendor cpcv.py + Deflated Sharpe + trial registry + holdout
  custodian + promotion pipeline. *The gate every idea feeds.*
- **0.4 Memory upgrade (#5)** — Graphiti bitemporal KG on `memory_reflection`; reflection/consolidation.

### PHASE 1 — Perception / evidence (reuse-heavy)
- 1.1 Online-research + news organ (#4 §2d-e) on `news_sentiment` + crawl4ai/browser-use + **dual-LLM
  quarantine** + data-target catalog. · 1.2 Radar (#2) on market_data/paper_trading. · 1.3 Global
  linkage (#6). · 1.4 Tipster harness (#7) on paper_trading. · 1.5 Kronos organ (#4 §2c, NSE-finetune).

### PHASE 2 — Decision
- 2.1 Directional BULL/BEAR bots (#4) on llm_strategy+predictive_core (meta-labeling arbiter, calibration,
  online-learning, SHAP). · 2.2 Greeks/IV surface engine (extend black_scholes IV). · 2.3 Regime brain +
  bandit router (#1) on meta_strategy_allocator + sentience.

### PHASE 3 — Act + survive
- 3.1 Risk + allocation (gap #9) on risk_management+capital_allocation (drawdown ladder, portfolio
  Greeks/VaR, vol-target+Kelly+bandit+CVXPY). · 3.2 Ops/execution/governance (gap #10) on broker_oms
  (WAL, reconciliation, netting, **SEBI Algo-ID**). · 3.3 The 4 regime strategy engines (Rule-Q armed).

### PHASE 4 — Visible + conversational
- 4.1 Dashboard upgrade (gap #13) on `dashboard/` — **[frontend-design + dataviz auto]** — P&L
  attribution, engine health, promotion state, cockpit verdict. · 4.2 Chat panel (#9) **[frontend-design]**
  → assistant agent (read-only state tools) → gateway.

### PHASE 5 — Organism (self-improvement)
- 5.1 Self-evolution loop (gplearn/PySR/OpenEvolve gated by 0.3; meta-model over ledger). · 5.2 Cognitive
  faculties deepening (pymdp active-inference, py_trees control loop, torchhd) on conscience/sentience/autopoiesis.

## Rules for every slice
Reuse-first (Rule G/I) · engine-grade (Rule P) · self-calibrating, no hard-codes ·
gated (net-EV + validation + risk) · real-data verified (Rule F) or hermetic-sim (Rule J) + logged blocker ·
update SYSTEM_MAP + dashboard surface (Rule H/N) · one slice, sign off, advance (Rule A) · **auto-invoke
the right plugin/skill per task** (frontend-design=UI, dataviz=charts, building-engine-grade-features=build,
code-review=review, firecrawl=web, context7=lib-docs).

**START: slice 0.1 — LLM gateway subscription lane** (highest-ready, most reuse, unblocks chat + organs).
