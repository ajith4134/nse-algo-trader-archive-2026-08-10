# 04 — AI/ML in Production Algo Trading, 2025-2026 State of Practice

Companion to `01_adaptive_learning_architecture_findings.md`. That file
answers "what architecture should we build" (Plan 2 recommended). This file
answers a narrower question researched afresh: of all the AI/ML techniques
in the taxonomy, which are actually verified in production today (not
research papers, not marketing) as of 2026-07-23?

**Status: research only, nothing implemented.**

## Bottom line

Classical ML (gradient boosting) and rigorous statistical validation remain
the true production workhorses. LLMs have moved from pure hype to
documented, narrow production use (research copilots, fine-tuned
classifiers) at large firms — not autonomous traders. RL is
production-proven for execution, still mostly academic for signal
generation. Regime detection and drift monitoring are standard engineering,
not exotic AI.

## 1. LLM strategy/signal agents

Documented production use: JPMorgan's DocLLM (layout-aware document
parsing) and IndexGPT (GPT-4-generated keywords → NLP news scan → thematic
baskets) — disclosed across JPM's 300+ production AI use cases
(Klover.ai/emerj, 2025). BlackRock: fine-tuned LLMs forecasting earnings-call
market reaction, built with "evaluation-driven development" for regulated
production (ZenML LLMOps DB, MarkTechPost, Aug 2025). Bridgewater's AIA
Labs, live since Dec 2023/Jul 2024, combines proprietary causal ML with
fine-tuned/frontier LLMs and a multi-layer guardrail stack (ai-street.co,
longtermwiki.com, Jul 2026) — **caveat: specific performance figures
(~$2B fund, 11.9% return) come from a single tertiary source that itself
flags most citations as unverified; treat as plausible, not confirmed.**
Debate/council LLM frameworks (TradingAgents, arXiv:2412.20138; HedgeAgents)
remain research-only — no vendor or fund has documented these running live
capital.

**Verdict:** narrow, guardrailed LLM use is production-proven at large
firms; autonomous LLM-council trading is experimental.

## 2. RL: execution vs. signal generation

Execution/market-making RL (order sizing, venue selection, aggression) is
live at JPMorgan (LOXM) and plausibly underlies Hudson River Trading's
AI-heavy market-making stack. Academic RL for optimal execution (PPO-based,
arXiv 2507.06345, 2511.15262, 2025) is active but sim-to-real transfer
remains the acknowledged blocker. RL for alpha/signal generation
(GFlowNets/PPO formulaic-alpha search, arXiv 2306.12964, 2509.01393) shows
persistent overfitting and instability documented in the papers themselves.

**Verdict:** execution RL works in production; signal-generation RL is
still largely academic.

## 3. Regime detection

HMMs, changepoint detection, and clustering classify bull/bear/high-vol
states and gate strategy allocation or veto trades (QuantStart, QuantInsti,
2025). Man AHL has run ML-driven systematic strategies since 2014.

**Verdict:** proven, standard engineering.

## 4. Ensemble / council-of-models

LLM debate ensembles exist only as research prototypes (TradingAgents,
FinCom arXiv 2606.00939). Classical ensembling (multiple GBM/RF models
voting, blended with regime filters) is production-standard.

**Verdict:** classical ensembling = production-standard; LLM-debate
councils = research-only, no confirmed live-capital deployment found.

## 5. Classical ML vs. deep learning

Mixed, contested evidence. 2025-2026 studies (ITM Web Conf. Yan et al.;
arXiv 2601.08896) show XGBoost's regularization gives strong, stable
out-of-sample generalization; Transformers capture longer dependencies but
converge less predictably. On Temporal Fusion Transformers specifically,
several 2025 studies find no consistent edge over plain LSTM/BiLSTM.

**Verdict:** gradient boosting is the safer workhorse; deep sequence
models show promise but no consensus of superiority.

## 6. Statistical rigor (DSR, CPCV, SPA, walk-forward)

De Prado's Deflated Sharpe Ratio and CPCV are professional-standard per de
Prado's own framing. Independent 2024-2025 comparisons (Arian et al.)
confirm CPCV reduces backtest-overfitting probability better than plain
walk-forward, but walk-forward remains the de facto industry default.
White's Reality Check (2000) / Hansen's SPA test (2005) are established,
decades-old multiple-testing corrections.

**Verdict:** proven and standard among rigorous shops; adoption is uneven
industry-wide.

## 7. Drift / adversarial validation

PSI, KL-divergence, KS/Chi-square tests via Evidently AI/Alibi Detect are
standard MLOps practice adapted to trading; QuantInsti's Autoregressive
Drift Detection Method compares live vs. backtest error rates to trigger
retraining.

**Verdict:** proven, borrowed directly from general ML-ops.

## 8. XAI / memory (RAG, case-based reasoning)

SHAP/TreeExplainer used for feature attribution with known caveats
(correlated-feature instability, arXiv 2505.08345). FINMEM-style layered
vector-memory RAG architectures exist only in research papers (arXiv
2508.02366).

**Verdict:** SHAP explainability is production-usable with caveats;
trading-specific case-based-reasoning memory remains research-stage —
consistent with `01_adaptive_learning_architecture_findings.md`'s finding.

## Not covered

Crypto-specific market-making, options/derivatives-specific ML, and
Chinese/Indian domestic quant-shop practices were out of scope for this
pass.

## Sources

JPMorgan DocLLM/IndexGPT (Klover.ai/emerj, 2025); BlackRock LLMOps (ZenML
DB, MarkTechPost, Aug 2025); Bridgewater AIA Labs (ai-street.co,
longtermwiki.com, Jul 2026); TradingAgents (arXiv:2412.20138); HedgeAgents,
FinCom (arXiv 2606.00939); JPMorgan LOXM, Hudson River Trading (aInvest);
PPO execution RL (arXiv 2507.06345, 2511.15262); GFlowNet/PPO alpha search
(arXiv 2306.12964, 2509.01393); QuantStart/QuantInsti regime tutorials; Man
AHL (man.com); XGBoost vs. Transformer studies (ITM Web Conf. Yan et al.;
arXiv 2601.08896); TFT comparisons (2025 studies, mixed); Deflated Sharpe
Ratio / CPCV (GARP whitepaper; Arian et al. 2024-2025); White's Reality
Check (2000); Hansen's SPA test (2005); Evidently AI / Alibi Detect;
QuantInsti Autoregressive Drift Detection Method; SHAP caveats (arXiv
2505.08345); FINMEM (arXiv 2508.02366).
