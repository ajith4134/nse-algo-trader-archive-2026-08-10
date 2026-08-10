# Directional verdict → 3 segment bots (slices 2–4)

**Problem.** The BULL/BEAR directional AI (`segment_bots/directional_ai/`) is built + tested (slice 1)
but ORPHANED — no bot consumes its verdict. All three bots read a passive `adapter.trend_side(underlying)`,
and the production adapter (`market_store_data_adapters.py`) hard-returns `TradeSide.NEUTRAL`. So every
directional (CE/PE, cash long/short) branch is DORMANT: the structure selectors only ever see NEUTRAL and
fall through to their non-directional defaults.

**Fix.** Give each bot its OWN directional brain that computes the side from the bot's own price data
(which each bot already pulls via `price_series`), replacing the passive `adapter.trend_side` NEUTRAL stub.

## Shared engine (no ×3 duplication)

`directional_ai/directional_side_brain.py` — `DirectionalSideBrain(store_dir)`:

- Owns a per-underlying `BullBearDirectionalEngine`, persisted under `store_dir/<underlying>/`, cached in
  memory. One brain instance per bot; one engine per underlying (full universe, keyed by symbol).
- `verdict_for(underlying, prices) -> DirectionalVerdict`:
  1. normalize `prices` (Series close-only OR OHLC DataFrame) → bars DataFrame.
  2. load/cache the engine; if not earned, `build_directional_training_samples` + `engine.train`
     (persists on success; the `_MIN_SAMPLES_TO_TRAIN=400` / `_MIN_PER_CLASS=30` ladder gates activation
     — Rule Q, so a thin series stays `gathering`→NEUTRAL, never a shrunken algorithm).
  3. `directional_features_now(bars)` → `engine.directional_view(feats)` → `DirectionalArbiter().arbitrate`.
- `side_for(underlying, prices) -> TradeSide` convenience (verdict.side).

The arbiter already encodes the meta-labelling (conflict→FLAT, weak-edge→FLAT, else stronger side +
conviction), so the brain is pure glue + lifecycle around the existing engine — the depth lives in the
engine, not re-implemented here.

## Wiring per bot

| Slice | Bot | Change |
|-------|-----|--------|
| 2 | INDEX-OPT | `trend = self._brain.verdict_for(underlying, prices).side` in `_propose_one`; feeds structure_selector's ZERO_DTE_GAMMA / VERTICAL_DEBIT_SPREAD directional branches |
| 3 | STOCK-OPT | same swap in `_propose_one`; feeds stock_option_structure_selector directional (call vs put) |
| 4 | CASH | wire verdict.side → long/short book selection in cash_intraday_bot |

`adapter.trend_side` stays on the Protocol as an OPTIONAL override (a live-feed trend source can still be
injected later), but is no longer the primary path. Prod stub NEUTRAL becomes irrelevant — the brain
computes the side. No adapter/fake breakage.

## Verification (Rule F / J)

Real data: bot `price_series` over the real market store. Market-gated for live opens, but the brain's
train+infer runs on stored bars offline. Unit: extend `test_directional_ai` sibling test for the brain
(train→earned→verdict flips with drift); per-bot tests assert the directional branch wakes when the brain
returns LONG/SHORT (inject a fake brain via the seam, no leak — Rule J).

## Backlog (Rule K)

- OHLC bars: `price_series` is close-only → high/low degrade to close in the feature engine (ATR-ish
  features weaker). Upgrade adapters to expose OHLC bars for the directional brain.
- Retrain cadence: brain trains once until earned; add a periodic/drift-triggered retrain hook.
- Full-universe perf: per-underlying engines over 2000+ names — lazy + cached now; profile + batch later.
