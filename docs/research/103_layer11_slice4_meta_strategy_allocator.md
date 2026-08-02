# Layer 11 Slice 4 — Meta-strategy allocator (LLM weights champion configs from memory)

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 11 slice 4 (BACKLOG).
Reuses the slice-1 `StrategyLlmClient` seam + swappable pool + memory read-model. Advisory this
slice; the decision-consumer (weights → real sizing) is QUEUED, calibration-gated (Rule K).

## 1. Goal (BACKLOG / MASTER_PROGRESS)
> "Slice 4 — meta-strategy allocator (LLM weights champion configs from memory)."

The bot runs three strategies, each with a tuned CHAMPION config (§53 slice 5c-i, global +
per-regime): `opening_range_breakout_v1` (cash ORB), `directional_option_orb_v1` (directional
options), `credit_spread_v1` (defined-risk spreads). Champion-challenger tunes EACH strategy's
config, but nothing decides how much to LEAN on each strategy given their real, differing track
records. This slice adds an LLM `MetaStrategyAllocator` that, grounded in each strategy's real
per-regime performance + its current champion config, proposes a normalized **allocation weight
per strategy** (a portfolio-of-strategies view) with rationale — the meta-layer above the
per-strategy champion tuning.

## 2. Why an LLM (not a formula)
A naive "weight ∝ historical win-rate" ignores regime context, sample thinness, calibration
health, and negative-edge flags — and would over-fit to a single-regime memory. The allocator
must weigh heterogeneous evidence (win-rate vs mean-return vs n vs per-regime split vs the
champion config's own aggressiveness) into a judgment — an LLM synthesis, grounded so it can't
invent numbers. It is ADVISORY until it earns calibration (same discipline as slices 1–3).

## 3. Component (Rule C)
`llm_strategy/meta_strategy_allocator.py`:
- `StrategyAllocationWeight(strategy_tag, weight, rationale)`.
- `MetaStrategyAllocation(generated, served_by, weights: tuple[...], overall_rationale,
  grounding_facts, note)` — `weights` NORMALISED to sum 1 on parse (clamped ≥0; degenerate → equal).
- `MetaStrategyAllocator(llm_client, experience_memory, champion_store=None)`:
  - `build_grounding_facts()` — per-strategy aggregate from the calibration board (group rows by
    `strategy_tag`: total n, experiment-weighted actual win-rate + mean return), the per-regime
    calibration cohorts, and (if a champion store is injected) the current GLOBAL champion config
    per the store.
  - `build_request(facts)` — forces the allocation JSON schema.
  - `allocate()` — one grounded LLM call → `MetaStrategyAllocation` (non-generated on pool
    exhaustion; weights re-normalised defensively regardless of what the model returns).

## 4. Wiring (Rule G) + cadence
- Service `_maybe_run_meta_strategy_allocation(now)` on the daily cadence (after the causal
  analysis), caching `_latest_meta_strategy_allocation`. Best-effort. The champion store is
  injected via the existing `_champion_store()` seam.
- Dashboard surface `meta_strategy_allocation` (Rule N): the weight per strategy + top rationale +
  served-by.

## 5. Advisory → decision-consumer (QUEUED, Rule K)
The weights are DISPLAY-ONLY this slice. The decision-consumer — scale per-strategy position
sizing / entry preference by the allocation weight (e.g. down-weight a strategy the allocator
distrusts), gated behind the allocation EARNING calibration (its weight ordering shown to track
realized per-strategy performance out-of-sample) — is the queued follow-up. Same advisory→gating
pattern as the debate-risk gate (slice 2c); it will reuse that earn-then-act discipline.

## 6. Verification
- Hermetic (Rule J): fake LLM + memory stub → assert grounding facts carry the per-strategy
  aggregates + champion config, schema forced, weights normalise to 1 (even when the model returns
  un-normalised / negative / a single strategy), pool-exhaustion → non-generated.
- Real-data (Rule F): run `allocate()` over the REAL 340-experience memory + real champion store
  through the real pool → a real normalised allocation across the three strategies.
  `scripts/verify_layer11_meta_strategy_allocation_realdata.py`.

## 7. Open items (Rule K)
- 🔵 Decision-consumer: apply weights to per-strategy sizing/selection, calibration-gated
  (earn-harness reused from slice 2c shape).
- 🔵 Per-regime allocation (weights conditioned on the live market regime), not just global.
