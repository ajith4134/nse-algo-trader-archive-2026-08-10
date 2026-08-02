# 177 — Trending-regime index-options arm with real edge (A3: trained direction + VRP + defined-risk debit)

**Date:** 2026-07-30
**Parent contract:** `docs/research/b18_index_options_ensemble_SPEC_2026-07-27.md` (arm **A3**). This doc
narrows A3 to the concrete engine to build now, grounded in NEW live evidence, and maps the reuse.
**Operator decision (2026-07-30):** after the task-#4 diagnosis, "build a trending-regime index arm"
— do NOT override the antibody veto.

---

## 1. Why (the decisive new evidence — task #4, live 2026-07-30)

The only option arm for a TRENDING index today is "buy a naked ATM long option on a spot ORB
breakout" (`_try_open_directional_option`). The live antibody surface proves it is a money-loser:

| mechanism | trades | predicted win | actual win | z | mean return | verdict |
|---|---|---|---|---|---|---|
| long ATM option on ORB breakout (ADX-trending) | **127** | 78.6% | **44.9%** | **−9.3** | **−0.2%/trade** | calibration **VIOLATED** — vetoed |

So indices (trending today) route to this arm → antibody **correctly** vetoes it → 0 index positions.
Stocks open because range-bound names route to the credit-spread arm (not vetoed). The veto is right;
the FIX is a trending arm with genuine edge, registered under a NEW mechanism name (so it is judged on
its OWN evidence, never inheriting the ORB arm's veto).

**Two root causes of the −0.2%/trade the new arm must beat:**
1. **Bad direction signal** — ORB breakout on indices is ~45% accurate (near coin-flip). ⇒ need a
   *trained* directional edge, evaluated leakage-free, that must BEAT a baseline before it acts.
2. **Naked long ATM = theta bleed + rich premium.** ⇒ replace with a **defined-risk directional DEBIT
   spread** (bull-call / bear-put): buy ATM, sell further-OTM same-expiry → cheaper, defined risk,
   less theta, positive-carry-relative structure.

---

## 2. Engine (Rule P) — a trained direction model + VRP gate driving a defined-risk debit spread

**Algorithm/model:** a LightGBM binary classifier P(next-window up | features), trained with
time-grouped walk-forward CV, that ACTS only once it has EARNED it (beats a base-rate baseline on
held-out log-loss) — exactly the `predictive_core.WinProbabilityEngine` contract, mirrored for index
direction. **Carried state:** the persisted trained model (joblib) + its evaluation + a per-(index)
maturity ledger. **Raw pipeline:** 5-min index bars + option ladder → engineered features. **Decision
output that changes behavior:** for a trending index, when the model is earned AND confident AND the
variance-risk-premium filter agrees, propose a defined-risk debit spread in the model's direction;
else abstain with a counted reason. **SOTA analog:** Qlib model pipeline (b18 §2, A3).

### 2a. Features (raw → engineered; ML-addendum: rich, not a handful, honest provenance)
Reuse existing indicators; engineer per (index, look):
- **VRP** = ATM IV − Yang-Zhang realized vol (`compute_yang_zhang_realized_volatility`) — the
  variance-risk-premium, the documented index-option edge (Carr & Wu). Sign + magnitude.
- **IV rank / percentile** (`compute_implied_volatility_rank`) — ABSTAIN for the 4 monthly-only
  indices until ~Sept 2026 (b18 hard constraint: 252-day lookback spans the weekly→monthly break).
- **Trend/momentum:** ADX, ADX slope, multi-window returns, distance from VWAP/opening range.
- **Dealer gamma exposure** (`dealer_gamma_exposure`) — sign gives pin/accelerant regime.
- **Term-structure + time-of-day + minutes-to-close** (intraday square-off constraint).
State the feature count + provenance honestly; expand rather than settle for a handful (Rule I).

### 2b. Label (leakage-free): sign of the index's forward N-bar return over the intraday horizon the
debit spread is held to (defined by the square-off clock). No look-ahead; time-ordered split only.

### 2c. Structure: `directional_debit_spread` builder in `strategy_engine` — buy ATM (model
direction), sell the K-th OTM strike same expiry (defined risk = net debit). Reuses the B9 nearest-
expiry chain + BS delta already used by the credit-spread selector.

### 2d. Maturity ladder (Rule Q — thin data NEVER shrinks the engine): build the FULL model now;
gate ACTIVATION on `is_performance_earned()` (beat baseline on held-out CV) AND a per-index minimum
closed-trade count. Until earned: the arm abstains (safe identity), the model still trains/评估 and
shows `have N / need M` on the dashboard. Activation is automatic as trades accrue.

---

## 3. Reuse map (sourcing = REUSE, Rule I/O; no new external dep — LightGBM 4.7.0 pinned)
- Model lifecycle idiom → **`predictive_core/win_probability_engine.py`** (train→CV→persist→serve +
  earned gate) + `win_probability_model_store.py` (joblib) + `win_probability_model.py` (time-grouped
  CV). Mirror, do not copy blindly.
- RV → `indicators/yang_zhang_realized_volatility.py`; IV → `black_scholes_implied_volatility.py`;
  IVR → `implied_volatility_rank.py`; GEX → `dealer_gamma_exposure.py`.
- Arm selection + delayed reward → `AdaptiveArmSelector` + `ArmSelectionPosteriorStore` (already wired
  for the 2 existing arms; the new arm registers as a 3rd arm name).
- Defined-risk sizing/margin → `risk_management` (`size_defined_risk_spread_lots`, gate).
- Rejected (Rule O.1, tier-1): no new library — a bespoke lite ML would be strictly worse than the
  installed LightGBM + the in-repo earned-gate pattern.

## 4. Build slices (each verified before the next — Rule A/F)
- **Slice 1 (THIS build): the direction-model ENGINE core** — `index_direction_features.py` +
  `index_direction_model.py` (LightGBM + time-grouped walk-forward CV + beats-baseline earned gate) +
  `index_direction_model_store.py` (joblib) + `index_direction_engine.py` (lifecycle, mirrors
  WinProbabilityEngine). Unit + property + leakage tests; Rule-F train on the REAL index bar/ATM-IV
  history the loop already stores.
- **Slice 2:** `directional_debit_spread` structure builder + defined-risk sizing (strategy_engine).
- **Slice 3:** decision integration — a NEW `try_open_trending_index_directional_arm` wired into the
  option pass for trending index underlyings, under a NEW mechanism name (own veto evidence), with the
  maturity ladder; records outcomes via the task-#4 instrumentation.
- **Slice 4:** dashboard surface (Rule N) — model earned/gathering, per-index maturity, VRP, arm P&L.
- **Slice 5:** Rule-F live — the arm opens defined-risk index debit spreads in a trending regime;
  the accrual of edge-vs-baseline is the one permissible market-gated open blocker (Rule K).

## 5. Acceptance (from b18 §5, applied to A3): the arm NEVER acts before the model beats baseline on
held-out data; every abstain has a counted reason; defined-risk only; costs (B28) netted before any
reward updates a posterior; no look-ahead (time-ordered split, pending-on-open/settle-on-close).
