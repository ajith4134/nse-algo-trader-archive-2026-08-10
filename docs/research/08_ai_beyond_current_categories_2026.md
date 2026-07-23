# 08 — AI Capabilities Beyond the Already-Researched Categories (2025-2026)

Companion to `04_ai_ml_production_trading_techniques_2026.md` (which covered
LLM strategy agents, RL execution, HMM regime detection, classical ML
ensembles, DSR/CPCV statistical rigor, drift detection, case-based
memory/knowledge graphs, autonomous web-research agents, win/loss pattern
mining, self-reflection journaling) and `06_self_learning_ai_feature_taxonomy.md`.
This file researches seven **new** categories explicitly out of scope of
those files, as of 2026-07-23. Grading: **A** = primary/peer-reviewed/official,
**B** = reputable secondary (established outlet, maintained OSS repo with
real activity), **C** = blog/marketing/unverified single-source.

**Status: research only. Nothing implemented.**

## 1. Multi-modal AI reading chart images directly

Real and active research area, not vaporware. Vision Transformers (ViT) fed
256×256 candlestick images are being used to predict return direction —
Byun, Na & Song, SSRN, Apr 2025 [B, SSRN preprint, page paywalled behind
403 — cited via search abstract only, not independently re-verified].
Hybrid ViT + Temporal Fusion Transformer models (ResearchGate, 2025) [B]
and CNN-on-Gramian-Angular-Field encodings (`raphant/cnn_gaf` GitHub,
paper: "Encoding Candlesticks as Images for Pattern Classification Using
CNNs") [B, working OSS code] show the pattern is technically real, not
just a numeric-feature model in disguise. `pecu/FinancialVision` GitHub is
the most-cited open dataset/toolkit for this specific niche [B].
The most concrete production-adjacent evidence: **`qrak/LLM_trader`**
(GitHub, 113 stars/38 forks/343 commits, BETA) generates live 4K candlestick
PNGs and feeds them to Gemini for pattern reading, and the maintainer's own
notes say "chart-pattern code was dropped because the AI reads charts
better than hardcoded rules" [B — verified by reading the repo directly].
This is the strongest signal that vision-LLM chart reading already beats
hand-coded pattern detectors for at least one solo-developer crypto bot.
**Verdict: realistic and cheap to prototype for an NSE intraday bot** —
render the chart, send to a vision-capable LLM (Gemini/Claude) as a
secondary confirmation signal, never as the sole trigger.

## 2. Alternative data + AI

Institutional-scale and real: Deloitte's 2025 Alternative Data Survey found
87% of institutional funds use ≥3 alt-data sources (up from 62% in 2021),
and money managers spent $2.8B on alt data in 2025, +17% YoY [B, cited via
multiple secondary sources incl. internationalbanker.com, thedatascore
Substack, Haas/Berkeley newsroom — satellite parking-lot counting
(Walmart/Costco/Lowe's) is the canonical, well-triangulated example, worth
~4-5% edge around earnings per Berkeley's Panos Patatoukas [B]]. YipitData
and Eagle Alpha are real, active vendors (Eagle Alpha ran alt-data
conferences in Feb and Sep 2025 discussing AI/MCP integration) [B, own
site]. **For India specifically**, the picture is much thinner: Integrity
Research (2025) [B] names only two India-specific alt-data providers —
Snapbizz (POS data from 1M+ grocery stores) and Bobble AI (smartphone
usage/search-intent signals) — and explicitly calls India's alt-data market
"nascent." No satellite/credit-card panel vendor was found serving Indian
retail-accessible pricing. GST e-way bill data exists as a public macro
series (CEIC) but no evidence surfaced of it being packaged for
equity-research alpha. **Verdict: honest flag — this category is close to
irrelevant for a retail NSE trader today.** It's institutional-only by cost
(alt-data contracts run five-to-six figures USD/year) and by data
availability (almost no India-specific vendor ecosystem exists yet). Not
worth building toward; revisit only if the project scales to
institutional AUM.

## 3. Conversational/RAG copilot grounded in the system's own logs

Real and buildable today, not speculative. TradingAgents (TauricResearch,
GitHub) [B] persists a decision log per ticker and re-injects realized
returns + past reasoning into the next run's prompt — this is RAG over the
system's own trade history, not general web knowledge. `qrak/LLM_trader`
independently implements the same idea with ChromaDB vector storage of
past trades/rejected trades plus a "reflection engine" [B]. Consumer
trading-journal SaaS (TradeZella, TradesViz) already ship "ask your trading
data anything in plain English" chat as a shipped, paying-customer feature
[C/B — marketing pages, but the feature itself is now table-stakes in that
product category, i.e. triangulated across ≥2 vendors independently].
**Verdict: highly realistic and one of the highest-value adds for this
project** — a local RAG layer over your own SQLite/Postgres trade logs +
risk state, answering "why did you take this trade" grounded strictly in
retrieved rows (never free-generated), is a weekend-scale build with an
open-source LLM.

## 4. AI-assisted strategy/code generation with human-review gate

Real, growing, and risky. Open-source examples: `VibeTradingLabs/vibetrading`,
`AsutoshaNanda/llm-trading-strategy-generator`, `HKUDS/Vibe-Trading` (25.4k★
per skillsllm.com listing — unverified independently, treat as C), and
`llmbacktest.com` — describe strategy in English → LLM writes
Python/Backtrader code → backtest → LLM-assisted refinement loop [B, based
on reading multiple independent project READMEs]. **Documented failure
modes are the important part**: practitioner write-ups (FabTrader.in,
d4much.substack.com, technetexperts.com) [C, single-author blogs but
mutually consistent across 3 independent authors] converge on the same
three failures: (1) code that passes backtest but silently mishandles
live slippage/API quirks and keeps firing orders with no kill-switch; (2)
LLMs hallucinating fallback values for missing data instead of erroring;
(3) overfitting to the exact backtest window because the LLM iterates
directly against backtest P&L as its reward signal, re-discovering the
classic multiple-comparisons overfitting problem (this is exactly why
DSR/CPCV from file 04 exists — LLM code-gen makes that problem worse, not
better, by generating dozens of variants per session). **Verdict:
realistic and valuable as a *drafting* tool, dangerous as an
autonomous one** — mandatory human-review gate + the project's existing
DSR/CPCV validation must sit between any LLM-generated strategy and paper
trading, let alone live capital.

## 5. Graph Neural Networks for market relationships

Real, active academic area; **no verified institutional production case
study found**. Papers are numerous and recent: heterogeneous GNNs with
sector/supply-chain/correlation edge types and "PEARL" positional
embeddings (ResearchGate, 2025) [B]; Full-State Graph Convolutional LSTM
over supplier-customer value chains (arXiv 2303.09406) [A]; GNN+multi-agent
RL hybrids (Medium/arXiv, 2025) [B]. Search for production adoption at
named funds (Two Sigma, BlackRock) turned up plenty of general ML/AI
commentary (Two Sigma's 2026 outlook, BlackRock's Aladdin Portfolio Guard)
but **nothing GNN-specific and attributable** [gap — flag explicitly:
absence of evidence, not evidence of absence, since funds don't disclose
proprietary signal architecture]. **Verdict: institutional-research-stage,
speculative for retail** — the sector/correlation-graph idea is sound in
principle (a shock to one stock propagating to its NSE sector peers or
known supply-chain partners) but building and maintaining a real
supplier-customer graph for NSE names is a data-acquisition problem before
it's a modeling problem; not a good first investment for this project.

## 6. Automated narrative/report generation

Real and already mainstream at OSS scale, though closer to "daily decision
dashboard" than SEBI-audit-narrative. `ZhuLinsen/daily_stock_analysis`
(GitHub, **36.1k★**, actively maintained, verified by direct repo read)
[B] is an LLM-driven system that pulls multi-source market data, news,
sentiment, and fundamentals and auto-generates a daily plain-language
decision dashboard pushed to Telegram/Discord/Slack/email, on a
zero-cost scheduled run. TradeZella/TradesViz [C] independently ship
"daily performance summaries with improvement suggestions" as a paid
feature. No example was found of an LLM auto-generating a **SEBI-audit-style**
narrative specifically (that appears to be a genuine gap — everyone builds
trader-facing summaries, not regulator-facing ones). **Verdict: realistic
and directly usable** — a daily/weekly LLM summary generated from this
project's own trade logs, strictly template-grounded (no invented
numbers), is straightforward and doubles as a human-readable layer on top
of the SEBI-mandated audit log (SEBI circular
SEBI/HO/MIRSD/MIRSD-PoD/P/2025/0000013, effective 4 Feb 2025 /
compliance by 1 Oct 2025, Algo-ID tagging mandatory from 1 Apr 2026 —
[B, cross-checked via mondaq.com law-firm summary and 3 independent algo
brokerage blogs]; note several blog posts float a "2027 daily AI
simulation mandate" / "2028 AI Guardrails" framework — **these are NOT in
any primary SEBI circular found and should be treated as C-grade
speculation, not upcoming law**, until a primary SEBI source confirms them).

## 7. Found this, wasn't asked

- **Diffusion models for synthetic market data.** CoFinDiff (IJCAI 2025)
  [A] and several arXiv 2024-2025 papers generate synthetic OHLCV series
  that preserve fat-tails/volatility-clustering "stylized facts," explicitly
  for stress-testing and deep-hedging training data — a genuinely useful,
  little-known way to generate more realistic synthetic test scenarios
  than a plain bootstrap/Monte Carlo shuffle for CPCV-style validation.
- **Earnings-call vocal-tone/stress analysis.** Beyond text sentiment,
  firms (Markets EQ, SimianX, EarningsEdge.ai) [C, vendor marketing] plus
  academic backing (Stanford/MIT research on CEO vocal hedging cues cited
  secondhand) analyze *how* management sounds, not just what they say, on
  earnings calls — a real, if vendor-hype-heavy, niche. Low relevance to
  NSE intraday (most Indian mid/small-cap calls aren't transcribed/audio
  processed by any of these vendors) but worth knowing exists.
- **LLM-populated market simulators for strategy testing.** StockSim
  (arXiv 2507.09255) [A] and "Can LLMs Trade?" (arXiv 2504.10789) [A] build
  full limit-order-book simulators populated by LLM agents with distinct
  personas (value/momentum/market-maker) to test strategies against
  synthetic-but-reasoning agents instead of historical replay only —
  interesting for stress-testing against adversarial-ish synthetic
  counterparties, though current literature admits these LLM-populated
  markets behave "too rational" vs. real human order flow [A, same
  papers, self-reported limitation].

## Advanced-version proposals for this project

(Python, NSE, Zerodha Kite, intraday, SEBI white-box constraints — all
additive layers, none replacing the core rule-based/statistical engine.)

1. **Vision-confirmation layer**: render each candidate setup as a
   candlestick chart image server-side, send to a vision LLM as a
   *non-blocking second opinion* logged alongside the numeric signal —
   never gate the actual order on it initially; measure agreement rate
   for a month before considering it a filter.
2. **Local RAG trade-copilot**: embed every trade's entry/exit reasoning,
   indicator snapshot, and P&L into a local vector store; expose a
   CLI/Telegram "why did you take trade #4231" and "what's my current
   open risk" query answered strictly from retrieved rows, with the
   retrieved rows shown alongside the answer (auditable, not opaque).
3. **LLM strategy-draft sandbox**: a strictly sandboxed "propose a
   strategy variant in English → LLM drafts code → auto-run through the
   existing DSR/CPCV validation harness → human approves before it ever
   touches paper trading" pipeline — treating the LLM as a very fast
   junior quant whose homework is always graded by the existing
   statistical-rigor pipeline, never trusted directly.
4. **Diffusion-augmented synthetic stress tests**: use a lightweight
   diffusion or GAN model trained on NSE index/sector OHLCV to generate
   additional synthetic adverse scenarios (gap-downs, vol spikes) to widen
   the CPCV validation set beyond what actual history provides.
5. **SEBI-narrative auto-report**: a scheduled job that turns the
   mandatory Algo-ID-tagged audit log into a plain-English daily/weekly
   summary (trades taken, why, risk limits touched, any override events)
   — template-grounded, zero free-generation of numbers — both a
   human-readable ops report and a head start on any future SEBI
   explainability requirement.
6. **Explicitly deprioritize**: satellite/credit-card/GNN-supply-chain
   signals — genuinely institutional-only or India-data-absent right now;
   revisit only if capital/scope changes materially.
