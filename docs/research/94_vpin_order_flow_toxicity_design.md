# research/94 — VPIN order-flow toxicity (§53 slice-5 ADVANCED; last code-buildable ADVANCED item)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD. Microstructure feature buildable from OHLCV volume (no L2 depth,
so not gated on P4b). Reference: Easley, López de Prado & O'Hara (2012), "Flow Toxicity and
Liquidity in a High-Frequency World," Review of Financial Studies.

## Sourcing sweep (sourcing-oss-parts)
Searched GitHub / PyPI / web for VPIN + bulk-volume-classification implementations.
Candidates: `ronaldzgithub/VPIN-1`, `SGTYang/VPIN`, `yt-feng/VPIN`, `jheusser/vpin`,
`theopenstreet/VPIN_HFT` (small individual GitHub repos, mostly TICK-data oriented, no
packaging/tests) and `monty-se/PINstimation` (comprehensive but R, not Python). **Verdict:
vendor-and-adapt the standard ALGORITHM from the reference** — it is ~40 lines of well-
specified math, and a clean from-formula implementation matching our OHLCV-bar input beats
reshaping a tick-data repo. Provenance recorded in the module (reference paper + note).

## Shape
- **Input:** a chronological series of `PriceBar` (close price + volume) for one instrument.
- **Behaviour:** (1) **Bulk Volume Classification (BVC)** — per bar, buy fraction =
  Φ(ΔP/σ_ΔP) (standard-normal CDF of the standardized close-to-close change); buy volume =
  V·Φ, sell volume = V·(1−Φ). (2) **Equal-volume bucketing** — accumulate bars into buckets
  of a fixed `bucket_volume`, splitting the boundary bar proportionally. (3) **VPIN** =
  mean over the last N buckets of |Vbuy − Vsell| / Vbucket ∈ [0, 1].
- **Output:** `VpinReading(vpin, bucket_count, ...)` — higher = more toxic / informed flow.

## Design
- `market_data/vpin_order_flow_toxicity.py` (PURE):
  - `bulk_volume_classified_bars(bars, sigma_window) -> [(buy_vol, sell_vol), …]`
  - `equal_volume_buckets(classified, bucket_volume) -> [BucketFlow]`
  - `compute_vpin(bars, bucket_volume=None, bucket_count=50) -> VpinReading` (auto bucket_volume
    = total_volume/bucket_count when not given). Returns None-ish (vpin=None) when too few bars.
- **Consumer / wiring (Rule G/N):** compute VPIN live on the benchmark's recent bars in the
  service, and **surface it via the feature-surface registry** (task #13) as a new
  "Order-flow toxicity (VPIN)" feature row (status + value). The entry-gate consumption
  (high VPIN → defer/size-down entries, like the opponent ledger) is a QUEUED follow-up —
  graded honestly (Rule K): computed + surfaced now, decision-consumer queued.

## Verification (Rule F)
Compute VPIN on the REAL stored benchmark bars (the 23 sessions) — assert it returns a value
in [0,1], monotone sanity (a synthetic all-one-direction series → VPIN≈1; a balanced series →
low VPIN), and a real reading printed. Hermetic unit tests for BVC + bucketing + edge cases.

## Files
- `src/nse_algo_trader/market_data/vpin_order_flow_toxicity.py`
- feature surface in `live_paper_trading_service._build_feature_surfaces` + manifest row
- `tests/test_market_data/test_vpin_order_flow_toxicity.py`
- `scripts/verify_vpin_realdata.py`

## Rule check
- **sourcing:** swept; vendor-from-formula with provenance.
- **Rule F/J:** hermetic algorithm tests + real-bar pass.
- **Rule G/N:** surfaced on the dashboard (real consumer); entry-gate consumer queued (Rule K).
- **Rule I/C:** standard algorithm, self-describing names.
