# SOURCING EVIDENCE — Three Segment-Bots + Supervisor (2026-08-03)

Actual OSS sourcing search behind `three_segment_bots_spec_2026-08-03.md` (Rule I / option-3). Four
parallel research passes (GitHub/PyPI evaluated on mechanical facts: maintenance date, stars, license,
API fit). Each row = repo evaluated → vendored or rejected + reason. `[MAINT]` = pushed/version seen.

## CASH bot — cross-sectional intraday equity
- **microsoft/qlib** (`pyqlib`) — [MAINT] active, Microsoft, RD-Agent 2025-26. Alpha158/360 + LightGBM +
  cost-aware backtest. **VENDOR/INTEGRATE** — spine; needs NSE data adapter.
- **lightgbm** — active (Microsoft). **INTEGRATE** — primary rank-IC baseline.
- **alphalens-reloaded** (stefan-jansen) — maintained fork (orig quantopian dead). **INTEGRATE** — IC/quantile/turnover.
- **cvxportfolio** (Boyd/Stanford) — active. **INTEGRATE** — multi-period txn-cost-aware construction (lead).
- **PyPortfolioOpt** / **Riskfolio-Lib** — active. INTEGRATE (baseline MV/HRP / CVaR).
- **zipline-reloaded** — active fork. Optional (event-driven backtest Pipeline API).
- **vectorbt** — OSS core active (Pro paid). Optional (fast sweeps; weak fills).
- **hftbacktest** — active 3.8k★. Optional (L2/OFI mechanics; crypto-origin).
- **mlfinlab** (hudson-and-thames) — **REJECT** ⚠ paywalled enterprise license; reimplement frac-diff/meta-label from AFML.

## INDEX-OPT bot — vol/regime
- **arch** (bashtage) — [MAINT] active ~1.5k★. **INTEGRATE** — GARCH/EGARCH/TARCH/HAR (regime + RV decomp).
- **py_vollib** + **py_vollib_vectorized** — [MAINT] py_vollib active (2026-05), vectorized 2024-12.
  **VENDOR/INTEGRATE** — IV + greeks over full chains; pin the vectorized wrapper.
- **hmmlearn** — [MAINT] **STALE** (v0.3.3 Oct-2024, no 2025/26 release). **CONDITIONAL** — prefer
  `statsmodels` Markov-switching (active) as primary regime engine; hmmlearn secondary cross-check only.
- **optopsy** (goldspanlabs fork) — [MAINT] active 2026-06, 1.4k★, AGPL-3.0. **VENDOR/ADAPT** — structure
  backtest DSL (38 structures); needs NSE chain adapter. License not a blocker (personal, non-distributed).
- **QuantLib-Python** — active. INTEGRATE only for exotic/curve-sensitive pricing (py_vollib default).

## STOCK-OPT bot — single-name event/IV/skew
- **py_vollib_vectorized** — as above. **VENDOR** — per-name IV/greeks.
- **optopsy** — as above. **VENDOR/ADAPT** — per-name backtest.
- SVI/SSVI surface: `arkonique/ssvi`, `JackJacquier/SSVI`, `XanderRobbins/Arbitrage-Free-Vol-Surface` —
  **REJECT** all (notebook-grade, not on PyPI). **BUILD IN-HOUSE** SVI fitter (scipy.optimize) on vollib IVs.
- **jugaad-data** (jugaad-py) — [MAINT] pushed 2026-08-02, 547★. **INTEGRATE** — primary NSE equity+F&O bhavcopy/chain.
- **nsepython** (aeron7) — [MAINT] 2026-03, 360★. **INTEGRATE** — secondary live chain/quote.
- Corporate-event / earnings calendar — no maintained free pip pkg. **BUILD scraper** vs nseindia.com
  corporate-filings-event-calendar (Rule I; same pattern as existing bhavcopy scraper).
- Option-flow / unusual-activity — no free OSS for NSE (Benzinga/Intrinio/Barchart = US commercial).
  **BUILD IN-HOUSE** from NSE option-chain OI+volume snapshots (vol/OI ratio + PCR-shift).

## SUPERVISOR — multi-strat capital allocation + arbitration
- **cvxpy** — mature industry-standard. **INTEGRATE** — custom CVaR/risk-budget QPs.
- **PyPortfolioOpt** — [MAINT] v1.6.0 Feb-2026, 5.9k★. **INTEGRATE** — Black-Litterman sleeve-view blend + HRP.
- **Riskfolio-Lib** (dcajasn) — [MAINT] v7.3 2026, 4.4k★, CVXPY. **INTEGRATE** — ERC + CVaR-constrained (deeper).
- **riskparityportfolio** (convexfi) — [MAINT] **UNVERIFIED** (page failed). **CONDITIONAL** — prefer Riskfolio-Lib; vendor only if SCA solver needed.
- **universal-portfolios** (Marigold) — [MAINT] **likely stale**, 858★. **VENDOR/ADAPT** the EG/ONS/Hedge
  algo module, or hand-roll EG (~10 lines: `w ∝ w·exp(η·r)`, renormalise). Don't take as live dep.
- Bayesian sleeve-Sharpe allocation — no finance-specific pkg. **BUILD** with `pymc`/`numpyro` (active PPLs).
- **skfolio** — newer sklearn-native. Optional (younger ecosystem).

## Existing in-repo parts to reuse (no external source needed)
- `capital_allocation/` — optimizer, Ledoit-Wolf covariance, integer-lot allocator, objective programs,
  constraint builder → supervisor allocator spine.
- `society/` — consensus_resolution, multi_agent_governance → arbiter spine.
- `StrategyFamilyPromotionRegistry` (paper_trading) → per-bot competency/promotion pattern.
- Trial Registry / Holdout Custodian / CPCV / DSR / MinBTL (paper_trading) → extend to JOINT registry.
- `indian_trading_cost_model`, `historical_bar_replay_source`, `live_universe_paper_loop` → cost + verify.
- `conscience` / `memory_reflection` / `will` → shared organism cognition wrap.

## Net new-build items (no adequate OSS — logged to BACKLOG)
1. In-house SVI/SSVI vol-surface fitter.
2. NSE corporate-event/earnings calendar scraper.
3. NSE option-flow (vol/OI + PCR-shift) signal.
4. JointTrialRegistry + PerBotAlphaAttribution (repo-specific extension).
5. Net-exposure netting layer + price-reconciliation guard (repo-specific).
