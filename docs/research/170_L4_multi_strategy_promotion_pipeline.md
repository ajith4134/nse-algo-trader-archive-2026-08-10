# 170 — L4: multi-strategy validated promotion pipeline (+ intraday mean-reversion family)

**Date:** 2026-08-03 · **Redesign layer:** L4 · **Skill:** building-engine-grade-features
**Operator directive:** take ALL strategy families to a proven edge (not just one) — but each must EARN
promotion independently through the L1/L2/L3 gates. The validation engine is the filter that keeps breadth
from becoming the prior sprawl.

## 1. Read-first
- Families that EXIST: `strategy_engine` ORB (`opening_range_breakout_strategy`), credit-spread
  (`credit_spread_leg_selector`), 0-DTE (`zero_dte_*`). **No mean-reversion family** (the one edge the
  harvested truth supports: NSE intraday mean-reverts; naive momentum loses ~0.23%/trade).
- Gates that EXIST: L1 cost gate + risk gate (wired) · L2 honest-N DSR + MinBTL + holdout + trial registry
  (`strategy_promotion_gate` + the new engines) · L3 crash-safe execution.
- Partial pipeline machinery: `shadow_rejected_arm`, `profit_provenance`, `skill_vs_luck_court`,
  `champion_configuration_store`. No UNIFIED per-family promotion-stage tracker → the gap.

## 2. The engine — `StrategyFamilyPromotionRegistry`
A persistent per-family state machine + validation gate:
- **Stages:** `RESEARCH → PAPER → SHADOW → REDUCED_LIVE → FULL_LIVE` (+ `HALTED`). Paper is always allowed;
  every stage ≥ SHADOW gates whether the family may touch real capital.
- **Advancement is EARNED, never manual-only:** a family advances only when, on ITS OWN real closed trades,
  the L2 gate says PROMOTE — honest-N DSR ≥ threshold (deflated by that family's cumulative trial count),
  MinBTL satisfied, holdout survived, minimum trades met, AND regime coverage (seen a real drawdown + a vol
  spike, not elapsed days). REDUCED_LIVE / FULL_LIVE additionally require a manual go-live flag (human gate).
- **Demotion:** a live family whose edge decays (DSR drops / drawdown breach) is auto-demoted to SHADOW —
  the antibody for whole families.
- **State store:** SQLite (per-family stage, verdict, edge stats, trades-in-stage, last-eval).

## 3. Per-family validation (reuses L2)
Each family gets its own honest trial identity (`family=<name>`) in the `StrategyTrialRegistry`, its own
holdout split, and its closed-trade returns feed `evaluate_strategy_for_promotion`. So ORB, credit-spread,
0-DTE, mean-reversion each earn (or fail) an INDEPENDENT edge verdict — no pooling.

## 4. New family — intraday mean-reversion (opus agent)
Engine-grade signal on the 2,400 cash universe: z-score / VWAP-reversion (price stretched N σ from an
intraday mean → fade toward it), with a real entry/stop/target + a regime filter (only in RANGE-BOUND, low
ADX — the inverse of ORB). Prediction records (like ORB/credit) so it's a first-class §9 experiment. Gated
by cost + risk + the promotion registry. Self-calibrating thresholds (percentile σ, not a magic 2.0).

## 5. Integration (mine — Rule G)
Tag every closed trade with its family; the service feeds each family's returns to the registry each eval
cadence; the registry's stage gates live action per family (paper unaffected). Dashboard surface (Rule N):
a per-family promotion board (stage · edge verdict · trades-in-stage · DSR · regime coverage). Real-data
verify on the live per-family closed-trade history.

## 6. Verification
Unit + property (a family with no edge never leaves PAPER; edge + coverage + manual flag → advances;
decay → demote) + adversarial (0 trades, thin data, regime not covered) + Rule-F on real per-family history.
Live REDUCED_LIVE/FULL_LIVE stay human-gated blockers (Rule K).

## 7. Sourcing (Rule O.1)
Mean-reversion family: agent runs sourcing (vectorbt signals, ta-lib z-score/bbands, pandas-ta) — expected
reuse the repo's own indicator stack; surface rejects. Promotion registry: bespoke SQLite state machine
(mirrors the trial registry / experience store), no OSS.
