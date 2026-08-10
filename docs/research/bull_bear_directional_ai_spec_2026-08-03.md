# SPEC — BULL/BEAR directional AI (two features per segment bot) · engine-grade (Rule P)

**Rev:** 2026-08-03 · builds on the 3-segment-bot pod. Design = crypto Feature-Catalogue §03b (BULL/BEAR),
per-bot. Locked (user MCQ 2026-08-03): (1) **two independent calibrated models** (BULL P(up) + BEAR P(down))
+ an arbiter, NOT one 3-class; (2) direction **DECIDES the side**, the existing IV-rank/regime/flow logic
sizes + structures it; (3) **per-bot** — each bot trains its own pair on its own segment data (choice-B).

## Why (the gap it fills)
Today NO bot has a learned directional brain: INDEX-OPT's `trend_side` is hardcoded NEUTRAL (directional
CE/PE branches dormant); STOCK-OPT direction = rule-based flow gates; CASH side = a rank artifact. The
learned heads predict P(WIN) of an already-chosen trade, never direction. One P(up) scaffold exists
(`predictive_core/index_direction_features.py`) but is ORPHANED. This spec builds the missing directional AI.

## The two features (per bot) + arbiter
- **BULL model** — calibrated **P(up)**. High → CALL (options) / BUY (cash).
- **BEAR model** — calibrated **P(down)**. High → PUT (options) / SELL-short (cash).
- **Arbiter (meta-labelling)** — joint (P_up, P_down) → `LONG / SHORT / FLAT`: both-high (conflict) or
  both-low (no edge) → FLAT; else the stronger side, gated by a min-conviction margin. *Trade selection
  lives here* (§03b rule 6).
- **Trained on ALL data, never direction-filtered** (§03b: a bull trained only on up-moves cannot calibrate)
  — the BULL model learns P(up) over the full sample; the BEAR is its mirror. Labels = forward-return sign
  via a **counterfactual triple-barrier** (§03b: never train on realised fills the bot didn't control).
- Both **calibrated** (isotonic), **walk-forward** (leakage-free), **river drift** monitored, carried state
  per bot (own model store). Rule-Q maturity ladder: until earned, the bot keeps today's behaviour (no regression).

## Modules (new package `segment_bots/directional_ai/`, engine instantiated per bot)
1. `directional_feature_engine.py` — from a price series (+ optional context) build a directional feature
   vector + the counterfactual triple-barrier label. Reuses the momentum/ADX/RV/return factors (generalises
   `index_direction_features` so it also works for stock + cash, where ATM-IV/VRP context is optional).
2. `bull_bear_directional_engine.py` — the BULL (P↑) + BEAR (P↓) LightGBM pair + isotonic calibration +
   walk-forward + SHAP + ADWIN drift + model store; `directional_view(features) → (p_up, p_down, maturity)`.
3. `directional_arbiter.py` — `(p_up, p_down) → DirectionalVerdict{side: LONG/SHORT/FLAT, conviction, margin}`.

## Wiring (Rule G — decides side, replaces the weak path)
- **INDEX-OPT**: bot computes its directional verdict → sets `trend_side` (replaces hardcoded NEUTRAL) → the
  selector's directional branches (call/put debit, 0DTE gamma) fire; NEUTRAL verdict → today's vol structures.
- **STOCK-OPT**: per-name verdict → the `trend` param + confirms/overrides the flow gate → call vs put.
- **CASH**: per-name verdict → the long/short book side (BULL-confirmed longs, BEAR-confirmed shorts),
  intersected with the cross-sectional rank (rank picks candidates, direction confirms the side).

## Acceptance (engine-grade)
- [ ] BULL + BEAR each a real fitted LightGBM, isotonically calibrated, walk-forward AUC reported, on the
      FULL (un-filtered) sample; counterfactual triple-barrier labels; drift + SHAP; per-bot model store.
- [ ] Arbiter resolves conflict (both-high → FLAT) + margin-gates; the verdict CHANGES the bot's side
      (not display-only) — dormant directional branches wake, cash side becomes direction-confirmed.
- [ ] Rule-Q: un-earned → today's behaviour, no regression. Real-data pass on real bars (Rule F).
- [ ] Tests: unit + invariant (probs in [0,1]; both-high→FLAT) + adversarial + real-data; ruff+mypy clean.

## Build order
Slice 1: `directional_ai/` engine (feature engine + BULL/BEAR pair + arbiter), tested + real-data. Slice 2:
wire INDEX-OPT. Slice 3: wire STOCK-OPT. Slice 4: wire CASH. Each real-data verified, dashboard-surfaced.

## Sourcing
Integrate: `lightgbm` + `sklearn` isotonic + `river` drift + `shap` (all installed). Reuse in-repo:
`predictive_core/index_direction_features` (features/labels), the win-prob-head walk-forward/calibration
pattern. No new OSS.
