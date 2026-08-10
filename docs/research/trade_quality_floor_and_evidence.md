# Trade-quality floor + per-trade evidence card

Two additions so trades are economically meaningful AND their profit-proof is visible.

## A. Min-EV / min-credit floor (StructurePayoffOptimizer)
Today the optimizer picks the max-EV real-strike structure but accepts trivially-small ones (near-expiry
chains with ₹0.05 legs → E[P&L] ₹3 on ₹3 risk — technically positive, economically pointless). Add TWO
floors in `_evaluate`, both RELATIVE (no magic constants):
1. **Meaningful premium** — the structure's net entry cashflow magnitude per lot must be ≥
   `min_premium_fraction × spot × lot_size` (default 5 bps of notional). Kills near-worthless-premium trades.
2. **Positive, non-trivial edge** — `E[P&L] > 0` AND `E[P&L] ≥ min_return_on_risk × max_loss` (default 3% of
   the capital at risk). Kills negative/tiny-edge trades even if they were the best candidate.
A structure failing either is rejected; if NO candidate for the engine passes, the name stands aside (no
trade) — the honest outcome, not a forced trivial trade.

## B. Per-trade evidence card (dashboard)
The proof already flows in `proposal.feature_provenance` (engine · expected_pnl · p_profit · max_loss · cvar
· rationale) and is persisted on the pod position (`features`). Surface it:
1. The Option-table row's **TABLE badge = the profit ENGINE** (Θ/Δ/ν/Γ/RV) that trade is on — instant "which
   edge" per contract (repurposes the existing `assigned_table` badge; no renderer change).
2. A **Trade Evidence** dashboard surface (tile via the feature-surface registry) showing the freshest opened
   structures with their engine · E[P&L] · P(profit) · defined-risk max-loss · rationale — so the operator can
   INSPECT the forecast behind each open trade, not just trust it. Pod publishes a `recent_trade_evidence`
   list in last_cycle.json; the prober renders the tile.

## Verification (Rule F)
Optimizer: on the near-expiry NIFTY chain the ₹3 condor is now REJECTED (fails the premium floor); a real
rich-premium name still passes with a meaningful credit + edge. Evidence: the tile shows a real opened trade's
engine + E[P&L] + P(profit) + max-loss.

## Sourcing (Rule I / Rule O.1)
No external OSS search was run and none is warranted — both parts are internal: (A) is two relative-threshold
comparisons inside the existing `StructurePayoffOptimizer` (a bespoke min-EV/min-premium gate is the standard
approach; no library computes "reject a structure whose net credit < X% of notional over MY terminal
distribution"), and (B) surfaces provenance the pipeline already persists (`feature_provenance` → pod position
`features`) through the existing `DashboardFeatureSurface` registry + the validated dashboard palette. The one
external artifact reused is the dataviz skill's `validate_palette.js` (ran it on the 5-engine Okabe-Ito ramp →
PASS with label-relief). Logged as an explicit "no external search needed" per Rule I option-3, mirrored in
`docs/BACKLOG.md`.

## Backlog (Rule K)
- Calibrate `min_premium_fraction` / `min_return_on_risk` from the realised track record once trades accrue
  (slice-5 learning) — defaults (5 bps / 3% ROR) are documented priors.
- Scorer regime-calibration: on a single-name / stressed-synthetic regime the scorer over-ranks VEGA
  (`+0.6·stressed_prob`) even when long-vol is negative-EV; engine-fallback masks it but the ranking itself
  should be revisited (its own slice, not this one).
- Real-data (Rule F) LIVE pass: confirm the evidence card + engine badges render on the LIVE dashboard during
  market hours (verified now over a real after-hours background cycle + hermetically; open until market reopens).
