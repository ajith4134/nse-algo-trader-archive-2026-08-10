# SPEC — INDEX-OPTION BOT (engine-grade, Rule P) · first of the 3 segment bots

**Rev:** 2026-08-03 · builds to `three_segment_bots_spec_2026-08-03.md` (+ its §8b advanced additions).
Approach locked (user 2026-08-03): sequential engine-by-engine, INDEX-OPT first, built by the main thread,
real-data verified per module. SOTA analog: **arch** (GARCH/HAR vol) + **py_vollib** (IV/greeks) +
**optopsy** (structure backtest) + **statsmodels Markov-switching** (regime) — a systematic index-vol desk.

## Intent & the decision it changes
A fully independent AI bot that trades the FULL NSE index-option universe (NIFTY, BANKNIFTY, FINNIFTY,
MIDCPNIFTY, NIFTYNXT50; weeklies + 0DTE). It owns its own data, vol/regime brain, models, risk sizing,
execution policy, and self-learning; it PROPOSES `TradeProposal`s to the portfolio supervisor (never places
orders itself — crypto §03b "proposes only"). It changes: which index-option structure to enter, its size,
and when to stand aside, driven by a measured implied-vs-realized vol edge conditioned on a learned regime.

## Module decomposition (the whole engine — built layer by layer)
1. **`segment_bots/segment_bot_protocol.py`** — the shared seam ALL bots + the supervisor bind to:
   `SegmentBot` Protocol, `TradeProposal`, `TradeSide`, `OptionStructurePlan`, `BotCompetency`. (built first)
2. **`segment_bots/index_option_bot/volatility_regime_engine.py`** — REAL engine #1: `arch`
   EGARCH/GJR-GARCH + HAR-RV conditional-vol forecast fused with a `statsmodels` Markov-switching regime
   filter (point-in-time, causal). Carried state = fitted model params + regime posterior, persisted +
   walk-forward refit. Output: `VolatilityRegimeState{regime, P(state), forecast_sigma, vrp_estimate}`.
3. **`index_option_bot/implied_vol_surface_engine.py`** — REAL engine #2: per-expiry IV + full greeks via
   `py_vollib_vectorized` over the real chain; SVI/SSVI smile fit (scipy) → skew, term-structure, 25Δ
   risk-reversal, IV-rank. Carried state = rolling IV-rank distribution per underlying.
4. **`index_option_bot/structure_selector.py`** — maps (regime, VRP, skew, 0DTE) → an `OptionStructurePlan`
   (short-strangle/iron-condor/credit-spread/directional/0DTE gamma), reusing `zero_dte_option_structures`
   + `credit_spread_leg_selector`. Delta-hedge scheduler for the vega/theta harvest.
5. **`index_option_bot/win_probability_model.py`** — the trained ML head (LightGBM) on the engineered vol/
   regime/skew feature store, calibrated (isotonic), walk-forward, SHAP; emits `calibrated_prob` +
   `expected_expectancy`. Reuses the existing `predictive_core` patterns + `river` drift detection.
6. **`index_option_bot/deterministic_index_option_policy.py`** — the P1 deterministic fallback + rollback
   target that GENERATES the dataset the learned head trains on (crypto §03b "ordering is forced").
7. **`index_option_bot/index_option_bot.py`** — assembles the above into the `SegmentBot`: own data adapter
   (reuse chain feeds), own state store, own self-learning loop, own track record; emits `TradeProposal`s.
8. **tests** — unit + property/invariant (VRP sign, greek-neutrality, regime-prob simplex) + adversarial +
   Rule-F real-data pass over the full index-option universe.

## Depth-justification (what a thin diagnostic version would OMIT — Rule P)
A thin version = "IV minus RV scalar → sell if positive." It omits: the FITTED conditional-vol model
(EGARCH captures vol clustering + leverage a scalar can't), the LEARNED regime (VRP is regime-dependent —
selling vol in a stress regime is how accounts blow up), the SVI SURFACE (skew/term-structure carry real
edge and risk), the CALIBRATED trained head with walk-forward + drift, the DELTA-HEDGE schedule (the harvest
is the hedged residual, not the raw premium), and 0DTE INTRADAY-resolution risk (gamma spikes 5–10× into
the close). Each omission is a real function loss; the LOC is justified by fitted models + carried state.

## Acceptance (engine-grade checklist)
- [ ] arch model actually FITTED + walk-forward refit; regime posterior a real simplex; state persisted.
- [ ] IV/greeks vectorized over the REAL full chain; SVI fit converges; IV-rank calibrated per underlying.
- [ ] LightGBM head trained, isotonic-calibrated, walk-forward, SHAP, river drift — reports n + optimism honestly.
- [ ] Emits `TradeProposal` that CHANGES the supervisor's decision (not display-only); deterministic fallback wired first.
- [ ] Tests incl. real-data pass over the full index-option universe (Rule F; hermetic sim if market-gated, Rule J).
- [ ] Wired (Rule G), SYSTEM_MAP + dashboard board (Rule H/N), backlog for the live-accrual blocker (Rule K).

## Sourcing (Rule I/O.1)
Integrate (installs done/pre-approved): `arch` 8.0.0 (GARCH/HAR — installed), `py_vollib` + `py_vollib_vectorized`
(IV/greeks — installed), `statsmodels` Markov-switching (regime — present), `scipy` (SVI fit — present),
`lightgbm` + `river` (head + drift — present per prior builds). Reuse in-repo: `zero_dte_*`,
`credit_spread_leg_selector`, `black_scholes_implied_volatility`, `yang_zhang_realized_volatility`,
`implied_volatility_rank`, `predictive_core`. Build in-house: SVI/SSVI fitter (no production OSS — surfaced).
Rejected: `hmmlearn` (stale Oct-2024 → use statsmodels Markov-switching); full sourcing evidence in
`three_segment_bots_sourcing_2026-08-03.md`.

## Build order (this + next focused slices)
Slice 1 (now): protocol seam + **volatility_regime_engine** (deep, tested, real-data). Slice 2: IV-surface
engine. Slice 3: structure selector + deterministic policy. Slice 4: trained head. Slice 5: assemble bot +
wire + dashboard. Then STOCK-OPT, CASH, SUPERVISOR.
