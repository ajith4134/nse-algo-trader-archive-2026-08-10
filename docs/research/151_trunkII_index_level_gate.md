# research/151 — Trunk II SENSES · index-option S/R proximity gate (closes the S2-index Rule-K gap)

**Slice:** wires the S2 **index** `news_levels` into the OPTION entry path — closing the last news
decision gap (index S/R levels were display-only). Opening an index-option position right at a fresh,
reliable analyst S/R level = elevated reversal/whipsaw risk → size-down / defer.

## Sourcing (Rule I) — N/A: in-house decision-wiring (like S7)
No external component — connects the built S2 index levels + S3 reliability to the built option-entry
gate pattern (`debate_risk_size_multiplier`). Logged here per the gate; no OSS to search.

## Design — DIRECTION-AGNOSTIC proximity (safe)
Credit-spread directional semantics vs S/R are subtle, so the gate is **direction-agnostic**: proximity
to ANY fresh, reliable index level (support/resistance/pivot) is caution — levels are where reversals
happen. `index_level_size_multiplier(spot, level_values, earned)`: nearest level distance% = |spot−lvl|/spot;
within **0.3%** → 0.0 (defer), within **1.0%** → 0.5 (size-down), else 1.0. Identity until calibration
earned (mirrors S7 — an uncalibrated signal never moves a real trade). Only index underlyings
(NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY/NIFTYNXT50); levels reliability-filtered.

## Build / wiring
- `index_level_gate.py` (PURE): the multiplier above.
- `live_universe_paper_loop` state: `index_level_values_by_underlying` (set by the service),
  `index_level_calibration_earned` (False), deferred/sized-down counters; method
  `index_level_size_multiplier(underlying, spot)`.
- Apply at BOTH `option_credit_spread_live_path` entry sites (credit-spread `lots *= …` + directional)
  using `underlying_symbol` + `spot_price` already in scope.
- Service: push `index_level_values_by_underlying` from the stored index `news_levels`
  (underlying ∈ the 5 index symbols), reliability-filtered; `index_level_gate` surface.

## Verify
- Hermetic (Rule J): spot near a level → (earned) size-down/defer; not earned → 1.0 (safe); no level → 1.0.
- Real-data (Rule F): the real stored NIFTY levels (23,600/23,800/24,000/24,200) → a spot near 24,000
  sizes-down once earned; cold-start identity.

## Rule K — after this
Earning harness for the index-level signal (market-gated, same class as S7/debate) · direction-aware
refinement once the credit-spread S/R semantics are modelled.
