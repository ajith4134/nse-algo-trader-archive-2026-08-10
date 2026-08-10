# 166 — L2 validation engine completion (honest trial registry + holdout custodian + MinBTL)

**Date:** 2026-08-03 · **Redesign slice:** L2 / build-order 0.3 · **Skill:** building-engine-grade-features
**North-star (redesign §3 L2):** *"Trial registry (honest cumulative N incl. discarded runs) · holdout
custodian · Deflated Sharpe as the in-loop fitness · CPCV · MinBTL · PBO · mechanism declaration. This is
what kills overfitting — the thing that sank the prior attempt."*

## 1. What ALREADY exists (read-first, like L1's cost model)
- **CPCV** — `paper_trading/combinatorial_purged_cross_validation.py` (+ 6 refs). Reuse.
- **Deflated Sharpe / PSR / promotion gate** — `paper_trading/strategy_promotion_gate.py`:
  `compute_deflated_sharpe_ratio`, `estimate_deflated_sharpe_benchmark`, `evaluate_strategy_for_promotion`.
- **PBO** — 1 file. Champion-challenger evaluator + per-regime champion + reevaluation scheduler.

## 2. The GAP (what's missing — 0 files)
- **Trial registry** — the DSR's `number_of_trials` is set to `len(all_scorecards)` in
  `champion_challenger_orb_evaluator.py:94` — only THIS batch, NOT the honest cumulative count of every
  config ever tried (incl. discarded). López de Prado's DSR deflation is only valid with the TRUE trial
  count; undercounting → optimistic DSR → overfitting slips the gate. **This is the core defect.**
- **Holdout custodian** — no guardian sealing a never-touched holdout window (the "one-shot" final test).
- **MinBTL** — no minimum-backtest-length gate (given N trials, the min #observations so the expected max
  Sharpe from noise stays under target; short backtests + many trials = guaranteed false discovery).

## 3. Sourcing (Rule O.1)
**Search EXECUTED per-part by the 3 build agents** (each runs `sourcing-oss-parts`: GitHub/PyPI queries for
mlfinlab / pyfinance / López-de-Prado backtest-overfitting impls, trial-registry / experiment-tracking libs,
holdout-guard patterns) and surfaces vendor/reject with tier-labelled evidence; findings consolidated back
here at integration. Preliminary read-first assessment (to be confirmed by the agents' live search):
- CPCV/DSR/PSR/PBO: REUSE in-repo (no vendor). The redesign's "vendor cpcv.py from nse-crypto-bot-final" is
  moot — a CPCV already exists here; only reuse if the vendored one is deeper (agent C checks).
- MinBTL / PBO formulas: canonical reference impl is **mlfinlab** (Hudson & Thames) — now
  commercial/license-gated, so NOT vendorable; the formulas are public (López de Prado, "The Deflated Sharpe
  Ratio" 2016 + "Building Diversified Portfolios that Outperform Out-of-Sample" — MinBTL eq.). Implement
  directly from the equations (each agent surfaces this rejection + cites the formula).
- Trial registry + holdout custodian: bespoke infra (no standard OSS); build in-repo on SQLite (mirrors the
  existing experience-memory / posterior stores).

## 4. Engine parts (built by 3 parallel agents; I integrate)
- **A. `strategy_trial_registry.py`** — SQLite-persistent log of EVERY strategy trial (config hash,
  strategy_family, trial Sharpe, kept/discarded, timestamp, provenance). `register_trial(...)`,
  `cumulative_trial_count(family)`, `sharpe_std_across_trials(family)`; dedup by config hash. Feeds the
  honest N + cross-trial Sharpe std into the DSR. Carried STATE (persists across restarts).
- **B. `holdout_custodian.py`** — seals the most-recent H% of the timeline as a HOLDOUT; serves research
  data freely, REFUSES holdout access unless `unseal_for_final_validation()` (one-way, logged, counts
  touches). Prevents the final test set from leaking into tuning.
- **C. `minimum_backtest_length.py`** — López de Prado MinBTL (min #obs vs N trials + target Sharpe) + a
  verified PBO. Returns a gate verdict (too-short-for-N-trials → reject).

## 5. Integration (mine — Rule G, no orphan)
Wire the trial registry's honest N + Sharpe-std into `champion_challenger_orb_evaluator` (replace
`len(all_scorecards)`) and `evaluate_strategy_for_promotion`; add a MinBTL gate + holdout-seal check to the
promotion outcomes; register every champion-challenger trial. Dashboard surface (Rule N): cumulative trial
count, DSR benchmark at honest N, MinBTL verdict, holdout seal status. Real-data verify on the live
champion-challenger evaluations.

## 6. Depth justification
Not a scalar: persistent trial state that changes the DSR benchmark (honest N raises the bar → strategies
that passed on optimistic N now correctly fail), a real López de Prado MinBTL solver, a stateful holdout
guardian. SOTA analog: mlfinlab's backtest-overfitting suite + a proper trial ledger. The output CHANGES
which strategies promote to live capital.

## 7. Verification
Unit + property (honest N ≥ batch N; DSR benchmark monotonic in N; MinBTL rises with N) + adversarial
(0/1 trials, empty returns, holdout double-unseal) + Rule-F on the real champion-challenger trial history.
