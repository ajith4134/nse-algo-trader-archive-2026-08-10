# Code Depth & Scale: SOTA OSS Projects vs. a Thin "Advisory Diagnostic" Architecture

Date: 2026-07-26
Scope: honest benchmarking of code depth/scale in (A) production algo-trading frameworks and (B) cognitive-architecture ("AI organism") projects, against a hobby project whose modules are small pure-Python functions (50-150 lines) computing scalar diagnostics over a small SQLite of paper trades, plus dashboard panels and mostly-advisory gates.

Methodology: six parallel research passes, each doing live GitHub API calls, direct repo clones with hand-counted LOC (not third-party estimates), WebFetch of official docs/source files, and reading of primary papers (arXiv, peer-reviewed). Every claim below is sourced; unverifiable numbers are flagged as such rather than guessed. Full URL list at the end.

---

## Direct answer

Every SOTA project below — even the "thin" ones in each category — has at least one component that is **a real, load-bearing numerical/logical engine**: a solved optimization problem, a formal calculus with derivation trees, a queue-position order-book simulator, or a tested production-rule/chunking kernel with dedicated subsystems per faculty. None of them ship a faculty as a single 50-150 line function that computes a scalar from a SQLite query and calls it done — even their weakest, most "aspirational" components (e.g., OpenCog's abandoned PLN, MicroPsi's untested emotion model) are hundreds to thousands of lines of runnable math/logic with test suites, not single functions. A hobby project whose "SELF," "CONSCIENCE," "risk engine," or "execution model" faculties are each one scalar-diagnostic function is not a thinner version of what LEAN/Qlib/SOAR/NARS do — it is a different category of artifact: a labeling/dashboard layer over data that already exists, with no engine underneath producing the number. That's fine as a monitoring/observability layer (and genuinely useful for that), but it should not be described with the same vocabulary ("execution model," "risk engine," "reasoning," "portfolio optimizer") used for systems where those words denote a working algorithm with inputs, a solver/inference procedure, and a verifiable output — because in the thin version there is no solver, no inference procedure, and no state carried between decisions.

---

## Category A — Production algo-trading / quant frameworks

### Scale & language summary

| Project | Primary language(s) | Scale (measured/estimated) | Stars | Maturity signal |
|---|---|---|---|---|
| QuantConnect LEAN | C# (94.2%), Python (5.6%) | ~800K-1M LOC (byte-derived estimate, not exact) | 20,847 | ~232 contributors (GitHub), Apache-2.0 |
| NautilusTrader | Rust (~68%), Python (~21%), Cython (~5%) | ~1.0-1.2M Rust + ~300-350K Python (estimate) | 25,024 | ~174 contributors, 20+ Rust crates, 15 venue adapters |
| Microsoft Qlib | Python | LOC unverified (GitHub API blocked); MIT | 46.7k | 4-layer architecture, ongoing commits past v0.9.0 |
| vnpy | Python (~100%) | 14,447 LOC (core repo, directly measured); ecosystem of 77+ satellite repos | 43,919 | 154 contributors, v4.4.0, 21 gateways |
| Freqtrade | Python (exact % unverified) | LOC unverified; 22 top-level packages | 52.6k | ~390 contributors (secondary source) |
| backtrader | Python | LOC unverified; 122 built-in indicators | 22,572 | **Dormant** — last commit April 2023 |
| Zipline / zipline-reloaded | Python | LOC unverified | 20,009 / 1,844 | Original dormant since 2020; community fork actively maintained (last push Jan 2026) |
| FinRL | Python (17%) + Jupyter (83% of repo bytes) | 84 files, 16,383 LOC core (directly measured) | 15,817 | ≥100 contributors |
| TradingAgents | Python (~100%) | 137 files, 13,733 LOC + 56 test files/6,335 LOC (directly measured) | 94,613 | 19 contributors (confirmed exact) |
| Lumibot | Python (100%) | 605 files, 200,578 LOC (directly measured) — largest of the nine | 1,850 | 38 contributors (confirmed exact) |

### Depth by component (what's real vs. what's a stub)

**Execution/fill model — the axis with the widest spread of realism:**
- **NautilusTrader is the deepest**: genuine L1/L2/L3 order-book support, real **queue-position modeling** (snapshots same-side depth at order placement, decrements via matching trade ticks, resets on modify), a nanosecond **LatencyModel** (inflight queues for submit/modify/cancel), and 9+ named fill-model variants (`ProbabilisticFillModel`, `SizeAwareFillModel`, `CompetitionAwareFillModel`, etc.). Source: nautilustrader.io/docs/latest/concepts/backtesting/.
- **Zipline** has a genuine parametric market-impact model: `VolumeShareSlippage` — price impact = `price*(1 ± impact*volume_share²)`, capped at 2.5% of bar volume — plus a separate futures volatility-impact formula `MI = eta*sigma*sqrt(psi)`. Source: zipline/finance/slippage.py.
- **Qlib** has a quadratic `impact_cost` term proportional to `(order value / total traded value)²`, but explicitly "no order-book depth simulation or partial queue-based fills" (read directly from qlib/backtest/exchange.py).
- **LEAN, vnpy, backtrader, Freqtrade, Lumibot** are all next-bar/next-tick fill approximations with selectable slippage percentages — none simulate queue position or book depth. Freqtrade's docs candidly state this is a known limitation since true intracandle price paths are unknown.
- **FinRL and TradingAgents don't model fills at all** — they operate on portfolio-value deltas or discrete LLM decisions, not simulated order execution.

**Risk/portfolio engine:**
- **Qlib** ships a real convex optimizer (`EnhancedIndexingOptimizer`, solved via CVXPY/ECOS) with objective `max_w d@r − λ(v@cov_b@v + var_u@d²)` — genuine mean-variance/factor-risk optimization, though the factor-covariance/specific-risk data must be supplied by the user (BYO risk model).
- **LEAN** ships Mean-Variance, Black-Litterman, and Risk Parity portfolio-construction models plus per-security/per-position-group margin models for multi-leg options.
- **vnpy_optionmaster** implements Black-76, Black-Scholes, and Binomial Tree pricing (Cython-accelerated) with live Greeks and a volatility-surface view — a real numerical options-pricing engine, not a labeled field.
- **FinRL's** only "risk model" is a single scalar "turbulence index" that force-liquidates all positions above a threshold — a real, working circuit breaker, but not a covariance/VaR engine.
- **TradingAgents'** risk layer is three LLM personas (risk-seeking/neutral/conservative) debating in natural language before a manager finalizes — judgment-based, not quantitative.
- **Lumibot, backtrader, Freqtrade** have no portfolio optimization; sizing is fixed/percent-based, margin is a pass-through to the exchange.

**Data/backtest engine (point-in-time integrity, corporate actions):**
- **Zipline** has a dedicated SQLite adjustments database tracking splits, mergers, dividends, and dividend payouts keyed by declared/ex/pay/record dates, dynamically applied to avoid lookahead — read directly from `zipline/data/adjustments.py`.
- **Qlib's PIT database** stores each fundamental field as `(date, period, value, next-offset)` chains specifically to prevent restated-financial-report lookahead, though scoped to quarterly/annual fundamentals only.
- **LEAN's Security Master** tracks splits/dividends/symbol changes/delistings/mergers with multiple adjustment-mode options.
- **NautilusTrader explicitly has NO built-in corporate-actions support** — confirmed via an open, unaddressed GitHub issue (#3307, opened Dec 2025) stating this verbatim.
- **vnpy's core `BaseDatabase` interface has no adjustment-factor fields at all.**
- **Freqtrade/FinRL/TradingAgents**: not applicable (crypto-only or not fill-based) or not confirmed.

**ML depth:**
- **Qlib is the deepest**: 24 distinct named, real trained models (LightGBM through Transformers/TFT/HIST) verified directly from its own benchmarks table, with Alpha158/Alpha360 feature-engineering pipelines and MLflow-like experiment tracking (`Recorder`/`qrun`).
- **Freqtrade's FreqAI** is a real train/predict/retrain subsystem: auto-expanding feature engineering (10K+ features from simple hooks), LightGBM/XGBoost/CatBoost + optional PyTorch/RL (stable-baselines3 + Gym, PPO default), genuine walk-forward sliding windows, and real outlier/OOD detection (Dissimilarity Index, SVM, DBSCAN, PCA).
- **FinRL** wraps real RL libraries (Stable-Baselines3/ElegantRL/RLlib) around a real Gym environment with continuous action space and transaction-cost-aware reward, but reward is a simple P&L delta (no walk-forward validation found — confirmed absent from source).
- **TradingAgents** is genuinely LangGraph-orchestrated (not a single prompt loop): 7 confirmed distinct agent roles matching the arXiv paper exactly, real n-round bull/bear debate with a facilitator, SQLite-checkpointed state, and a lightweight but real reflection/memory log — though its own paper self-flags anomalously high reported Sharpe ratios (5.6-8.2) as unrepresentative of a 3-month, 3-ticker backtest window.
- **vnpy.alpha** (since v4.0) is a real multi-factor pipeline (Alpha158-style features, Lasso/LightGBM/MLP templates).
- **LEAN** has real example NN training code (TensorFlow/Keras) but ONNX is unimplemented (confirmed via an open community forum request).
- **NautilusTrader, backtrader, Zipline have no built-in ML** — left entirely to user code.
- **Lumibot's** AI layer is the thinnest: a recently-added LiteLLM-based agent-team runtime (tool-calling harness around external LLM APIs), not a proprietary ML/RL implementation — its 200K LOC is concentrated in broker/data-source/execution plumbing (10 real broker adapters, real Greeks tied to IBKR/ThetaData/Tradier), not in model training.

---

## Category B — Cognitive architectures / "AI organism" systems

### Scale & health summary

| Project | Language | Scale (measured) | Age | Maintenance status |
|---|---|---|---|---|
| AtomSpace (OpenCog KR layer) | C++/Scheme/Python | 113,863 LOC | ~11 yrs | Active (last push Feb 2026) |
| PLN (classic) | Scheme/C++ | 12,329 LOC, 129 rule files | ~11 yrs | **Abandoned** — maintainers' own README: "no longer maintained" |
| PLN (Hyperon-native rewrite) | Python/MeTTa | 911 LOC | <1 yr | Active but early (last push Mar 2026) |
| Hyperon/MeTTa | Rust/Python/MeTTa | ~44,500 LOC | ~5 yrs | Active but self-described "pre-alpha" |
| SOAR | C++/C/Java | 206,913 LOC total; 96,799 in kernel | **~43 yrs** | Actively maintained (last push Jul 2026, v9.6.5) |
| ACT-R | Common Lisp | 111,131 LOC (core); +pyactr ~4,071-10,722 LOC Python reimplementation | ~30+ yrs | Actively maintained (rev 3493, Jul 2026) |
| LIDA | Java | 45,498 LOC (canonical impl.) | ~20 yrs | **Dormant since 2016**; Python successor (lidapy) active to May 2025 but omits the Global Workspace entirely |
| NARS (OpenNARS Java) | Java | 29,379 LOC | ~12 yrs | Dormant since ~2020-2021 |
| NARS (ONA, C rewrite) | C + Python | 12,838 LOC (C) + 7,042 LOC (Python tooling) | ~6 yrs | Active into 2025 |
| MicroPsi2 | Python/JS | 33,569 LOC Python; JS mostly vendored (12,901/23,363 lines is a third-party library) | ~14 yrs | **Dormant since Feb 2018** (later "activity" is unmerged bot commits) |

### Faculty depth — what's a real engine vs. an aspiration

**SOAR is the deepest of the six**: every faculty it claims — working memory, semantic memory (8,798 LOC), episodic memory (6,705 LOC), reinforcement learning integrated with chunking (2,676 LOC), chunking/explanation-based learning (10,000+ LOC combined), and perception/SVS (13,453 LOC) — has a dedicated kernel subsystem, backed by 441 unit tests and 947 runnable demo-agent files (Blocks World, Eight Puzzle, Tower of Hanoi, Water Jug) that are executed as regression tests, not merely described in a paper.

**ACT-R** has genuinely load-bearing equations, not decorative ones: the activation equation `Ai = Bi + Si + Pi + ε` and the utility-learning delta rule `Ui(n) = Ui(n-1) + α[Ri(n) - Ui(n-1)]` are directly implemented in `procedural.lisp`/`utility-and-reward-1.lisp` and independently re-implemented in the Python port (pyactr) — confirmed by reading both source trees, not just the reference manual. A peer-reviewed paper built 39 quantitative ACT-R models and reported RMSD fits to real human RT/decision data.

**NARS/ONA** has a real 9-level formal truth-value calculus (`TruthFunctions.java`: revision, deduction, induction, abduction, analogy, comparison, etc.) validated against 216 regression-tested `.nal` scripts with expected numeric truth-value outputs, plus quantified benchmark results (Pong hit/miss ratio 156.6 vs. baseline 2.5, <10s learning time) from a peer-reviewed AGI-conference paper.

**OpenCog's AtomSpace** is a genuinely deep, tested hypergraph/pattern-matching engine (13,597 LOC pattern matcher, 240+ typed atom classes, 609 test functions) — but **PLN, the "reasoning" faculty**, is the clearest documented example of grand-ambition-vs-thin-implementation in this whole set: the maintainers' own README admits the (now-abandoned) classic version's "rules are often crudely implemented," "confidence calculation is usually very crude" — and its from-scratch Hyperon successor is only 911 lines, explicitly "still in progress" per the project's own Alpha announcement.

**LIDA's** Global Workspace broadcast mechanism is real, working code (`GlobalWorkspaceImpl.java`, coalition competition + refractory timer + broadcast pub/sub) but small (~1,433 LOC), embedded in a codebase where 40% of the LOC is generic framework scaffolding rather than cognitive-faculty code, and the canonical implementation hasn't been touched since 2016; its one active successor drops the Global Workspace faculty entirely.

**MicroPsi2's** Psi-theory motivation/emotion dynamics are real running equations (`stepoperators.py`, ~200 lines: pleasure/competence/joy/securing-rate modulators recomputed every simulation step) — genuine math, not a diagram — but total ~250-300 lines, contain the original author's own "todo: we don't know how to calculate this yet" stub comments, have zero dedicated test coverage, and the project has had no substantive human commit since February 2018.

**Common pattern across all six**: even the weakest/most "aspirational" faculty in any of these projects (abandoned PLN at 911-12,329 LOC; MicroPsi's emotion model at ~250 LOC) is still an order of magnitude larger than a 50-150 line function, is a real formula/inference-rule set with documented mathematical semantics, and in most cases has an accompanying test suite proving it executes correctly — even when the maintainers themselves call it "crude."

---

## The depth gap: 8 concrete, specific examples

1. **Order fill realism.** NautilusTrader tracks queue position by snapshotting same-side order-book depth at placement time and decrementing it as matching-side trades print, with a nanosecond-resolution latency model for order submit/modify/cancel round-trips (nautilustrader.io/docs/latest/concepts/backtesting/). A thin diagnostic layer that reads "filled" rows from a paper-trades SQLite has no fill *model* at all — there is no function anywhere computing whether/when/at what price an order would have actually executed against real book liquidity; it's recording an assumption, not deriving one.

2. **Market impact as a solved function of real inputs.** Zipline's `VolumeShareSlippage` computes `price*(1 ± impact*volume_share²)` from actual bar volume and Qlib's `impact_cost` is `(order_value/total_traded_value)²` scaled by a coefficient — both take real market data as input and produce a cost number as output of an actual formula. A scalar-diagnostic version typically has no analogous "impact of my order size on price" function at all; "risk" or "cost" fields are usually derived post-hoc from the fill price already recorded, not predicted from market state before the trade.

3. **Portfolio construction as constrained optimization.** Qlib's `EnhancedIndexingOptimizer` solves `max_w d@r − λ(v@cov_b@v + var_u@d²)` via CVXPY/ECOS against a real factor-covariance matrix and specific-risk vector; LEAN ships working Black-Litterman and Risk Parity allocators. An "advisory gate" that thresholds a single scalar (e.g., "flag if concentration > X%") is not solving an optimization problem — there is no objective function, no constraint set, no solver, and no matrix of covariances being inverted; it is a single comparison operator.

4. **Options pricing as real numerical methods.** vnpy_optionmaster implements Black-76, Black-Scholes, and Binomial Tree pricing (with Cython acceleration for speed) plus a live volatility surface — Greeks come out of an actual pricing model recomputed on live/historical inputs. A thin version that stores a "delta" or "IV" column and computes summary stats on it is consuming a number, not producing one via a pricing model — if the input pricing model doesn't exist, the "risk" being surfaced isn't Greeks, it's whatever proxy was hand-picked to stand in for them.

5. **ML with a real training/validation loop.** Qlib runs 24 distinct trained models (LightGBM through Transformer variants) through a YAML-configured pipeline (`qrun`) with Alpha158/360 feature engineering and MLflow-like experiment tracking; FreqAI runs sliding-window walk-forward retraining with genuine out-of-distribution detection (Dissimilarity Index, SVM/DBSCAN outlier removal, PCA). A scalar-diagnostic function computing, say, a rolling win-rate or a Sharpe-like ratio over a SQLite table has no train/test split, no held-out validation, no retraining cadence, and no feature store — it's a fixed-formula descriptive statistic, not a model with generalization claims to be evaluated at all.

6. **Corporate-action/point-in-time correctness as dedicated infrastructure.** Zipline maintains a SQLite adjustments database keyed by declared/ex/pay/record dates that dynamically rewrites historical prices to prevent lookahead bias from splits/dividends/mergers (`zipline/data/adjustments.py`); Qlib's PIT database uses byte-offset chains to serve only the fundamental-data value that would have been known as of each historical date. Even NautilusTrader — one of the most technically sophisticated frameworks here — has an *open, unaddressed* GitHub issue (#3307) admitting it has *no* corporate-actions handling at all, which the researchers here treat as a real, documented gap, not something papered over. A diagnostic layer over a small paper-trades SQLite typically doesn't address this question in either direction because it never ingests raw point-in-time market data to begin with — the correctness problem doesn't arise because the system isn't reconstructing history, it's summarizing outcomes already produced elsewhere.

7. **Multi-agent "debate"/"gates" as a real stateful graph with persistence.** TradingAgents' seven agent roles run inside an actual LangGraph `StateGraph` with SQLite-backed checkpointing (`SqliteSaver`), and its bull/bear researcher debate runs a genuine n-round dialogue loop where a facilitator agent selects a winning argument and logs it to a `TradingMemoryLog` for future reflection — confirmed directly from source (`graph/setup.py`, `agents/utils/memory.py`), not just from the paper's prose. A "mostly-advisory gate" that returns a boolean/scalar from one function call has no state carried across calls, no multi-round exchange between distinct reasoning perspectives, and nothing analogous to a memory/reflection log being consulted on the next decision — each call starts from zero.

8. **Cognitive faculties as dedicated, tested subsystems vs. a single function.** SOAR's semantic memory (8,798 LOC), episodic memory (6,705 LOC), and reinforcement learning integrated with chunking (2,676 LOC) are each independent kernel modules with their own data structures, backed by 441 unit tests and 947 runnable demo agents proving multi-step problem-solving (Blocks World, Tower of Hanoi). Even OpenCog's *abandoned, self-admittedly crude* PLN — the weakest reasoning implementation surveyed — is still 911-12,329 lines of an actual rule-based inference engine with truth-value propagation and worked examples. A faculty named "SELF" or "CONSCIENCE" implemented as one 50-150 line function returning a scalar has no analogous internal state, no rule set, no multi-step derivation it can replay or explain, and nothing a test suite could exercise beyond "does this function return a number in range" — it is not a thin cognitive architecture faculty, it is a labeled metric.

---

## Sources

**Category A**
- https://github.com/QuantConnect/Lean
- https://github.com/QuantConnect/Lean/tree/master/Common/Orders/Fills
- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/portfolio-construction/supported-models
- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/key-concepts
- https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/supported-models/immediate-model
- https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models
- https://www.quantconnect.com/forum/discussion/5291/Onnx+Runtime
- https://www.lean.io/
- https://github.com/nautechsystems/nautilus_trader
- https://nautilustrader.io/docs/latest/concepts/architecture/
- https://nautilustrader.io/docs/latest/concepts/backtesting/
- https://docs.rs/nautilus-risk
- https://docs.rs/nautilus-portfolio
- https://github.com/nautechsystems/nautilus_trader/issues/3307
- https://nautilustrader.io/blog/why-nautilustrader-exists/
- https://github.com/microsoft/qlib
- https://arxiv.org/abs/2009.11189
- https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py
- https://qlib.readthedocs.io/en/stable/component/strategy.html
- https://qlib.readthedocs.io/en/stable/advanced/PIT.html
- https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md
- https://github.com/microsoft/qlib/blob/main/qlib/contrib/strategy/optimizer/enhanced_indexing.py
- https://github.com/vnpy/vnpy
- https://github.com/vnpy/vnpy_ctastrategy/blob/main/vnpy_ctastrategy/backtesting.py
- https://github.com/vnpy/vnpy_riskmanager
- https://deepwiki.com/vnpy/vnpy_optionmaster
- https://github.com/veighna-global/vnpy_evo
- https://github.com/freqtrade/freqtrade
- https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/optimize/backtesting.py
- https://www.freqtrade.io/en/stable/backtesting/
- https://www.freqtrade.io/en/stable/freqai-feature-engineering/
- https://www.freqtrade.io/en/stable/freqai-reinforcement-learning/
- https://www.freqtrade.io/en/stable/freqai-parameter-table/
- https://www.freqtrade.io/en/stable/lookahead-analysis.md
- https://github.com/mementum/backtrader
- https://github.com/mementum/backtrader/blob/master/backtrader/brokers/bbroker.py
- https://github.com/quantopian/zipline
- https://github.com/quantopian/zipline/blob/master/zipline/data/adjustments.py
- https://github.com/stefan-jansen/zipline-reloaded/blob/main/src/zipline/finance/slippage.py
- https://pypi.org/project/zipline-reloaded/
- https://github.com/AI4Finance-Foundation/FinRL
- https://github.com/TauricResearch/TradingAgents
- https://arxiv.org/abs/2412.20138
- https://github.com/Lumiwealth/lumibot
- https://lumibot.lumiwealth.com/backtesting.html

**Category B**
- https://github.com/opencog/atomspace
- https://wiki.opencog.org/w/Pattern_engine
- https://github.com/opencog/pln
- https://github.com/opencog/pln/blob/master/opencog/pln/README.md
- https://github.com/trueagi-io/PLN
- https://github.com/trueagi-io/hyperon-experimental
- https://singularitynet.io/announcing-the-release-of-opencog-hyperon-alpha/
- https://github.com/SoarGroup/Soar
- http://soar.eecs.umich.edu/
- https://en.wikipedia.org/wiki/Soar_(cognitive_architecture)
- https://arxiv.org/pdf/2205.03854
- https://link.springer.com/article/10.1007/BF00116249
- https://act-r.psy.cmu.edu/
- https://act-r.psy.cmu.edu/software/
- http://act-r.psy.cmu.edu/log/actr6log.txt
- https://act-r.psy.cmu.edu/actr7.x/reference-manual.pdf
- https://github.com/jakdot/pyactr
- https://www.cambridge.org/core/journals/judgment-and-decision-making/article/using-the-actr-architecture-to-specify-39-quantitative-process-models-of-decision-making/5919301DC9811886ECC45FC329E57D37
- https://en.wikipedia.org/wiki/LIDA_(cognitive_architecture)
- https://github.com/CognitiveComputingResearchGroup/lida-framework
- https://github.com/CognitiveComputingResearchGroup/lidapy
- https://github.com/opennars/opennars
- https://github.com/opennars/OpenNARS-for-Applications
- https://cis.temple.edu/~pwang/NARS-Intro.html
- https://agi-conf.org/2020/wp-content/uploads/2020/06/AGI-20_paper_52.pdf
- https://cis.temple.edu/tagit/publications/ONA.pdf
- https://github.com/joschabach/micropsi2
- https://www.researchgate.net/publication/300646235_Modeling_Motivation_in_MicroPsi_2

## What was NOT covered / explicit gaps

- Exact LOC counts for Qlib, Freqtrade, backtrader, Zipline, LEAN, and NautilusTrader could not be independently verified via cloc/OpenHub (GitHub API rate limits / 403s during research); byte-derived estimates are flagged as such above, not stated as fact.
- Contributor counts for several projects are pagination-based, anonymous-inclusive estimates (upper bounds), not exact confirmed figures.
- LIDA's peer-reviewed "replicates real experimental data" claim could not be independently verified (source pages returned 403) — reported as weaker-sourced than ACT-R's directly-confirmed RMSD-fit paper.
- No independent third-party confirmation was found for some vendor-reported adoption claims (e.g., LEAN's "300+ hedge funds," ONA's Cisco/NASA JPL collaborations) — these are noted as self-reported, Grade-C claims.
