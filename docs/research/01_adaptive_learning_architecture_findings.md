# 01 — Adaptive Learning / Memory / Self-Evolving Architecture Research

Research commissioned before building any Strategy/Signal, Risk, or Memory
layer, in response to the goal of a "self-evolving, learning, memory-like-
humans, ultra-advanced" trading system. Five parallel research angles, then
a combination/escalation pass. This file is the source of truth for that
design decision until superseded by a newer note.

**Status: research + planning only. Nothing in this file has been
implemented yet.**

## Headline finding

Nothing in the public literature or industry practice shows a system that
fully self-modifies its own **live** trading logic unattended, running with
real capital, with verified evidence of working. Where "self-evolving" and
"memory" *are* real and evidence-backed, they run offline/slow-cadence with
a **human sign-off gate** before anything touches live capital. This isn't
just caution for its own sake — SEBI's white-box classification (see
`00_market_structure_and_regulatory_findings.md`) requires transparent,
stable logic; a strategy that silently rewrites itself live risks tipping
into black-box territory, which requires Research Analyst registration.
Human-gated promotion is simultaneously the safest engineering practice
*and* the thing that keeps this bot legally simple.

## Taxonomy, graded by real evidence

| Dimension | Technique | Evidence grade |
|---|---|---|
| Adaptive ML | Online/incremental learning + drift detection (River, Hoeffding Adaptive Trees, DoubleAdapt) | ✅ Real, production-grade libraries; known forgetting/drift trade-off |
| Adaptive ML | Meta-labeling / ensemble confidence-gating (López de Prado) | ✅ Evidence-backed, contested for pure end-to-end ML — not a silver bullet |
| Adaptive ML | Regime detection (HMM/changepoint) | ✅ Legitimate, moderate evidence, oversold in retail blogs |
| Adaptive ML | RL for execution (JPMorgan's LOXM) | ✅ One real named live deployment — narrow scope (order slicing only) |
| Adaptive ML | RL for signal-generation/position-sizing | 🚀 Academic-only — a 2025-2026 review of 167 RL-finance papers found zero verifiable live deployments |
| Memory | Vector-DB memory stream + reflection (Generative Agents, Reflexion) | ✅ Real, working, open-source code — general AI-agent pattern |
| Memory | Case-based reasoning / trade-journal retrieval (FinMem, FinAgent, TradingAgents) | 🚀 Real code, backtest-only evidence, none live |
| Memory | Regime-aware memory decay/forgetting | 🌌 Active 2025-26 research, not integrated into any trading framework yet — an open gap |
| Self-evolution | Walk-forward AutoML re-selection (shadow→canary→live) | ✅ Real, standard MLOps practice at systematic shops |
| Self-evolution | Genetic-programming alpha mining | ✅ Real, production-adjacent, always human-gated before capital |
| Self-evolution | Meta-learning regime adaptation (X-Trend, Oxford-Man/Man AHL-linked) | 🚀 Strong paper, backtest-only |
| Self-evolution | LLM-driven strategy code rewriting (MadEvolve, AlphaAgent) | 🌌 Newest, least proven, authors themselves flag overfitting risk |
| Multi-agent LLM | Role-divided LLM agents (TradingAgents, FinRobot) | 🚀 Real, running code; backtests are tiny (weeks, 3 tickers) and non-reproducible |
| Multi-agent LLM | LLM in the tick-level hot path | ❌ Not viable — every credible source keeps LLMs at second-to-daily cadence |
| Governance | Shadow-mode → canary → human-gated live promotion | ✅ Industry standard; doubles as the SEBI white-box compliance mechanism |

## Candidate architecture plans, ranked

1. **Plan 1 — Classical Adaptive Quant (no LLM).** Meta-labeled ensemble +
   HMM regime gate + walk-forward AutoML re-selection (weekly retrain,
   shadow-mode validated before promotion) + structured statistical trade
   journal (win-rate by setup/regime feeding position sizing — memory as
   numbers, not prose). Lowest risk, highest evidence, cleanly white-box,
   builds directly on the existing Layer 1-9 roadmap. Not "ultra-advanced."

2. **Plan 2 — Memory-Augmented Hybrid. (Recommended starting target.)**
   Plan 1's deterministic core + a real episodic case-based memory (vector
   DB of past trade setups → outcomes, Generative-Agents-style retrieval by
   recency + relevance + importance) + a nightly reflection job (LLM
   allowed here — off-hours, not in the hot path) that produces an updated
   confidence "playbook," reviewed and promoted before the next session.
   This is what "memory like a human trader, building experience" concretely
   and safely means. Most advanced architecture with real, working parts
   underneath every component.

3. **Plan 3 — LLM-Strategist + Quant-Execution. (Phase 2/3 upgrade, the
   real path to "ultra-advanced.")** Adds a TradingAgents-style role-divided
   LLM layer (pre-market + slow intraday cadence — minutes, never ticks)
   producing strategic tilts (risk-on/off, sector/regime calls) that
   parameterize Plan 2's execution layer. A separate offline sandbox
   continuously proposes/backtests candidate strategy variants
   (genetic/LLM-driven); only human-reviewed, backtest-validated variants
   promote. Higher risk (more moving parts, LLM cost/latency to manage), no
   one has proven this exact combination live — the genuine frontier.

4. **Plan 4 — Fully autonomous, self-modifying live agent. NOT
   recommended, ever, as literally described.** No public evidence of this
   working with real capital anywhere. Likely breaks SEBI white-box
   classification the moment logic changes without human sign-off. The one
   place research came back with a flat no.

**Recommendation: build toward Plan 2 now. Treat Plan 3 as the explicit
roadmap item once Plan 2 is live and validated in shadow mode. Never build
Plan 4.**

## Combination / escalation pass (fusions across the taxonomy)

| Fusion | What it does | Why it's bigger than the sum of its parts | Evidence |
|---|---|---|---|
| **A — Council of Models** | Classical ensemble, regime-HMM layer, and case-based-memory score each vote independently; trade only taken above an agreement threshold | Disagreement itself becomes a risk signal; genuinely different paradigms are less likely to fail the same way at once | ✅ real components, novel combination |
| **B — Deflated-Sharpe Promotion Gate** | Every AutoML/GP-sandbox candidate must clear Deflated Sharpe Ratio + Combinatorial Purged Cross-Validation before shadow mode, not just raw backtest return | Directly closes the #1 failure mode flagged in the self-evolution research (GP "bloat," LLM-evolved strategies degrading OOS) | ✅ established (Bailey/López de Prado) |
| **C — Adversarial-Validation Trip Wire** | Background classifier tries to distinguish live feature distribution from training distribution; AUC spike → auto-throttle/kill-switch + log as new "regime break" memory case | Fuses the "no framework does regime-aware memory decay yet" gap with the kill-switch governance pattern — a principled trigger for the failure mode that produced a real 33%+ drawdown (Numerai, 2023) | ✅ real ML technique, novel application here |
| **D — Synthetic Stress Rehearsal** | GAN/diffusion market generator trained on own NSE history produces tail scenarios; every promotion-candidate strategy is run through crashes it hasn't lived through, failures stored as pre-emptive memory | A flight simulator for the bot — strictly more than backtesting (replays only what happened) or live memory (learns only after getting hurt) | 🚀 real, active research area, not yet standard in retail systems |
| **E — Meta-Strategy Capital Allocator** | Once multiple validated strategies exist, treat each as an "asset" and allocate capital via Hierarchical Risk Parity on return correlation instead of picking one winner | Portfolio theory applied one level up — the real answer to "self-evolution produced several good variants, now what" | ✅ established (HRP), novel application |
| **F — Explainable Memory** | Every stored case carries a SHAP feature-attribution snapshot at decision time, not just the outcome; retrieval filters by "what actually drove this" | Moves memory from "looked like this before" to "this specific factor was the driver before" — closer to expert generalization. Must be built in from day one — expensive to retrofit | ✅ established (SHAP), novel application |
| **G — Debate-as-Risk-Check** | Repurpose TradingAgents' bull/bear debate not for idea generation but as a mandatory pre-execution adversarial check — a red-team LLM agent argues against a trade the deterministic engine already wants, blocking/resizing it if the case scores strong | Keeps the LLM out of idea-generation (highest hallucination/latency risk) and puts its slowness where it's actually fine — low-frequency, right before execution | 🚀 real, working code (TradingAgents), repurposed application |

**One frontier idea flagged as pure speculation, not literature-backed:**
**Digital-twin risk calibration** — elicit the specific user's own
loss-aversion/risk comfort (questionnaire, or fit from their own past manual
trades) and use it to calibrate the Kelly-fraction/position-sizing formula.
Not found anywhere in the research as a named technique — a plausible
combination, not a proven one.

## Sequencing recommendation

| Fold into Plan 2 now (cheap, high-value) | Defer to Plan 3 (needs LLM-strategist infra first) |
|---|---|
| A — Council of models | G — Debate-as-risk-check |
| B — Deflated-Sharpe/CPCV gate | E — Meta-strategy allocator (needs multiple validated strategies first) |
| C — Adversarial-validation trip wire | D — Synthetic stress rehearsal (real value, heavier lift) |
| F — Explainable memory (must start day one) | Digital-twin calibration — lowest priority |

## What this implies for the layer roadmap

Adds two layers to `docs/flowcharts/00_project_overview.md`'s roadmap
(not yet built):
- **Memory & Reflection layer** — after Risk Management, alongside/before
  Backtesting. Implements Plan 2's case-based memory + fusions A/B/C/F.
- **Strategic LLM layer** — deferred, implements Plan 3 + fusions D/E/G.

## Sources (representative, not exhaustive)

- Online learning / drift: river library docs; DoubleAdapt (KDD'23,
  arxiv.org/pdf/2306.09862); Hoeffding Adaptive Trees (arxiv.org/pdf/2410.20242).
- RL for trading: JPMorgan LOXM (marketsmedia.com); 167-paper RL review
  (arxiv.org/html/2512.10913v1); FinRL (arxiv.org/pdf/2111.09395).
- Meta-labeling: hudsonthames.org triple-barrier writeup; QuantConnect
  critique (quantconnect.com/forum/discussion/14706).
- Memory architectures: Generative Agents (arxiv.org/abs/2304.03442);
  Reflexion (arxiv.org/abs/2303.11366); FinMem (arxiv.org/abs/2311.13743,
  github.com/pipiku915/FinMem-LLM-StockTrading); FinAgent
  (arxiv.org/abs/2402.18485); TradingAgents (arxiv.org/abs/2412.20138,
  github.com/TauricResearch/TradingAgents); FinCon (arxiv.org/abs/2407.06567).
- Memory decay research: STALE (arxiv.org/html/2605.06527); SSGM
  (arxiv.org/html/2603.11768); Oblivion (arxiv.org/html/2604.00131).
- Self-evolution: Warm Start GP (arxiv.org/abs/2412.00896); X-Trend
  (Journal of Financial Data Science 6(2), 2024); MadEvolve
  (arxiv.org/abs/2605.23007); Alpha-GPT (ACL 2025 demo, WorldQuant
  Championship result).
- Multi-agent LLM survey: Agentic Trading reproducibility audit
  (arxiv.org/html/2605.19337v1); QuantAgent latency mismatch flag
  (arxiv.org/pdf/2509.09995); FinRobot (github.com/AI4Finance-Foundation/FinRobot).
- Failure modes/governance: Knight Capital SEC order (sec.gov, Release
  34-70694); Bailey/López de Prado Deflated Sharpe Ratio (SSRN 2326253);
  SEC v. Two Sigma (sec.gov press release 2025-15); Gary Klein
  Recognition-Primed Decision model; Olsen 2002 (J. Psychology and
  Financial Markets).
- Combination-pass sources: GAN/diffusion market generators (CFA Institute
  2025 report; arxiv.org/pdf/2110.13287); adversarial validation
  (arxiv.org/pdf/2112.10078); Hierarchical Risk Parity
  (quantpedia.com/hierarchical-risk-parity, arxiv.org/html/2509.03712v1);
  Deflated Sharpe Ratio / CPCV production use (en.wikipedia.org/wiki/Deflated_Sharpe_ratio).
