# research/89 — Slice 5c-ii: market-impact fill model (ADVANCED tier §53)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD (this turn). ADVANCED-tier fill-fidelity slice.
**PLAN ref:** research/62 §4 slice 5 ("queue/impact fills"); §1.2 realistic slippage.

## Problem
`fill_slippage_model` makes the taker pay a bid-ask half-spread — but it **explicitly
ignores order size** ("quantity is not used by the model"). A big order should move the
price more than a tiny one; ignoring that flatters large-size strategies. The queue-
position half of realistic fills needs L2 depth (P4b, market-gated), but the **market-
impact** half is computable now from real VOLUME.

## Model — square-root impact law (Rule I: standard, not invented)
The well-established practitioner form: temporary impact grows with the square root of
participation. `participation = order_quantity / average_daily_quantity (ADQ)`;
`impact_bps = min(impact_coefficient_bps · sqrt(participation), max_impact_bps)`. The
taker pays it in the trade direction (buys fill higher, sells lower), ADDED to the
half-spread. Defaults are conservative v1 estimates, tunable + later calibrated against
real fills (same Rule-F caveat as the slippage model).

## Design
1. **`market_impact_fill_model`** (pure): `MarketImpactConfig` (coefficient_bps,
   max_impact_bps); `estimate_market_impact_bps(order_quantity, average_daily_quantity)`
   (0 when ADQ ≤ 0 — unknown liquidity → no impact, never a crash); `apply_market_impact_
   to_price(reference_price, side, impact_bps)`.
2. **Compose into the fill path (Rule G, extend not fork):** `fill_slippage_model.
   slipped_fill_price` / `estimate_slipped_fill_price` gain OPTIONAL `order_quantity` +
   `average_daily_quantity` + `market_impact_config`; when ADQ is given & > 0, the impact
   bps are added to the half-spread (same taker direction). Omitting them = today's
   behaviour exactly (no regression).
3. **Wire the cash fill sites** (`live_universe_paper_loop` entry/exit): pass the order
   `quantity` and the instrument's ADQ from a new `LiveUniversePaperState.
   average_daily_quantity_by_token` map (default empty → no impact). The service populates
   it best-effort from the REAL stored bar volumes (ADQ = mean per-session total volume
   per token) at start.

## Real-data verification (Rule F)
On the real stored bars: compute each token's ADQ from real volume; show impact is
MONOTONE in order size (a 5% -of-ADV order pays fewer bps than a 50% order), the combined
fill price worsens with size, and a tiny order ≈ the pure-spread price (impact→0). Also
verify a zero/unknown ADQ yields no impact (safety).

## Queued (Rule K)
- Queue-position fills (needs L2 depth — P4b, market-gated).
- Permanent (vs temporary) impact + impact on the exit-vs-entry asymmetry — v2.
- Calibration of the coefficient against real realized fills (needs live/paper fills).

## Files
- `src/nse_algo_trader/paper_trading/market_impact_fill_model.py`
- edits to `paper_trading/fill_slippage_model.py` (optional impact compose)
- edits to `paper_trading/live_universe_paper_loop.py` (state field + fill-site wiring)
- edits to `dashboard/live_paper_trading_service.py` (populate ADQ from real volumes)
- `tests/test_paper_trading/test_market_impact_fill_model.py`
- `scripts/verify_market_impact_fill_realdata.py`

## Rule check
- **Rule I/C:** standard square-root law; extends the existing fill model; self-describing.
- **Rule F/J:** hermetic model tests + a real-volume monotonicity/backward-compat pass.
- **Rule G:** wired into the real fill path (P&L), default-off safe (empty ADQ map).
- **Rule A:** one slice (impact half); queue-position + calibration queued.
