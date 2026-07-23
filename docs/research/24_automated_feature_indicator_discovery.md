# 24 — Automated Feature/Indicator Discovery: Beyond the Fixed Indicator List

Final-pass companion to `research/07` §A (the ~40-indicator human-curated
menu) and `research/06` feature #7 (automated feature engineering). This
file looks specifically for libraries that **generate, search, or evolve**
new indicators/features from raw price/volume data, rather than relying
only on a fixed list. Every project verified via direct README/API fetch,
2026-07-23. License informational only, per `CLAUDE.md` Rule E.

**Status: research only. Nothing borrowed or implemented yet.**

## Bottom line

There is no mature, widely-used, drop-in "discover trading indicators
automatically" product. What exists splits into two buckets: general-
purpose automated-feature-engineering libraries (gplearn, tsfresh,
featuretools) that are well-maintained but domain-agnostic — this project
would have to point them at OHLCV-derived data itself — and academic/
hobbyist alpha-mining projects built specifically for factor discovery
(AlphaGen, AutoAlpha, GP-Alpha-Miner) that are real and runnable but
niche, mostly China-market-oriented, and thin on stars/maintenance.
**Every output from any of these is a candidate hypothesis, not a trusted
signal** — all are prone to overfitting/data-snooping on the very data
used to search them, so routing their output through this project's
existing hypothesis-validation pipeline (`research/12`) isn't optional,
it's the entire point of using them.

## Projects found

| Project | Stars | License | What it does |
|---|---|---|---|
| [trevorstephens/gplearn](https://github.com/trevorstephens/gplearn) | 1,871 | BSD-3 | Genetic-programming symbolic regression, scikit-learn API; `SymbolicTransformer` evolves a *population* of formulas and returns the best N as new engineered features |
| [DEAP/deap](https://github.com/DEAP/deap) | 6,423 | LGPL-3.0 | Generic evolutionary-computation toolbox (GP/GA/ES/multi-objective) — no built-in finance anything, a DIY toolkit |
| [blue-yonder/tsfresh](https://github.com/blue-yonder/tsfresh) | 9,277 | MIT | ~120+ automated time-series feature calculators (statistics, entropy/complexity, autocorrelation, FFT/CWT, trend, peaks) with a built-in hypothesis-testing feature-relevance filter |
| [alteryx/featuretools](https://github.com/alteryx/featuretools) | 7,665 | BSD-3 | Deep Feature Synthesis — needs a *relational* entity-set model (tables + relationships), not a single time series; weak fit for single-symbol OHLCV |
| [winedarksea/AutoTS](https://github.com/winedarksea/AutoTS) | 1,423 | MIT | GA-driven auto model *and* auto feature-transformation search across dozens of forecasting model classes |
| [ICT-FinD-Lab/alphagen](https://github.com/ICT-FinD-Lab/alphagen) | 1,163 | none asserted | PPO-RL formulaic-alpha search via Qlib + BaoStock (China A-share data); KDD 2023 paper, real and active, HARLA (LLM-assisted) extension published 2026 |
| AutoAlpha implementations (`bigsuperFishfish`/`AutoAlpha2022`) | 3-28 | varies | Zhang et al. 2020 hierarchical evolutionary alpha-mining algorithm — reference implementations, stale-ish |
| GP-Alpha-Miner (`IIcodehub`) | 7 | none asserted | GPU-accelerated GP framework targeting low-turnover, high-ICIR alpha factors — very new (Jan 2026), unproven |

## How gplearn maps onto NSE OHLCV specifically

Build a feature matrix of raw/derived series (returns, rolling stats,
volume ratios) as `X`, a forward-return or classification target as `y`,
give it a function set (+,-,*,/,sqrt,log,abs,max,min, custom), and let it
evolve arithmetic combinations over generations — literally synthesizing
indicator-like formulas (e.g., a `(close-mean(close,20))/std(close,20)`
style expression) without knowing it's "RSI-like" — it just searches for
correlation with the target. This is a genuinely different discovery mode
than picking from `research/07` §A's fixed list.

## tsfresh's real value for this project

Its `FeatureSignificanceTestFeatureSelector`/relevance table —
Benjamini-Hochberg-controlled hypothesis testing that keeps only
statistically relevant features against a target — is a genuine automated
first-pass filter, usable on any candidate feature stream (discovered or
hand-built), not just its own ~120 calculators. This is a concrete,
reusable piece of the hypothesis-validation pipeline's screening stage
(`research/12`), distinct from the final DSR/CPCV gate.

## Found, wasn't asked

A visible 2026 trend of **LLM-driven alpha mining**, distinct from
classic GP/RL: a Gemini + WorldQuant BRAIN API feedback loop
(`MiracleInvoker/AlphaGen`), GP on WorldQuant BRAIN (`0xceb1/brain-learn`),
and Qlib + coding agents mining factors (`JacobDu/agentic-alpha`). All
tiny/unproven (single-digit to 44 stars) but signal where this space is
heading — using an LLM as the mutation/proposal operator instead of pure
GP, then validating against a real alpha platform's backtest. Worth a
bookmark, not yet worth building on.

## What this means for the plan

The natural pipeline this research points to: gplearn's
`SymbolicTransformer` or a DEAP-GP loop proposes candidate formulas from
OHLCV-derived primitives → tsfresh's hypothesis-testing filter (or an
IC/IR + walk-forward test) screens for statistical relevance → survivors
enter the existing hypothesis-validation pipeline (`research/12`) exactly
like a hand-curated indicator would, with **no privileged trust just
because they were "discovered."** AutoTS's transformation search can run
in parallel as an independent forecasting-feature source feeding the same
gate. This extends `research/06` feature #7 (automated feature
engineering) from a described capability into a concrete, buildable
pipeline with real library candidates at each stage.

featuretools is flagged as a weak near-term fit — its relational
entity-set model doesn't match single-symbol OHLCV, but could matter
later if this project builds a multi-table schema (symbol × sector ×
macro-event tables), which ties to `research/13`'s relative-strength/
sector-rotation filters.

## Ranked — most worth reading actual source code from next

1. **gplearn** — `gplearn/genetic.py`'s `SymbolicTransformer` — most
   directly reusable for indicator-formula evolution today.
2. **AlphaGen** — the RL alpha-search loop and formula grammar
   (`alphagen/rl_pool`, `alphagen/data/expression.py`) — the only real,
   running alpha-specific miner found outside RD-Agent-Quant
   (`research/05`).
3. **tsfresh** — `tsfresh/feature_selection/relevance.py` — the
   hypothesis-testing gate, directly transplantable to any candidate-
   feature stream.
4. **DEAP** — `deap/gp.py` plus one worked example
   (`harveybc/heuristic-strategy`) — for a custom fitness function around
   Sharpe/IC instead of raw R².
5. **AutoTS** — its transformation-search config
   (`autots/tools/transform.py`) — lowest priority, useful mainly if
   forecasting becomes part of the pipeline.

## Caveats

None of the small alpha-mining repos (AutoAlpha, GP-Alpha-Miner, the
LLM-alpha projects) have independent third-party validation of their
claimed results — treat performance claims in their READMEs as unverified
marketing, exactly the discipline `research/12`'s pipeline exists to
enforce on any external claim, discovered-by-algorithm or blog-sourced
alike.

See `research/22` (frontier self-improving AI) and `research/23`
(connecting/integration frameworks) for the other two legs of this final
research pass.
