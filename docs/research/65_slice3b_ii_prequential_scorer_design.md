# Research/65 — §53 Slice 3b-ii: dense prequential forecast scorer (design)

**Rule D design doc.** The running predict-then-reveal forecast-skill score
(§8.1) — a proper-score (log-loss + Brier) over the prediction stream, separable
live vs replay — so we can see whether 24/7-replay forecasting is as skilful as
live, and watch skill move as the bot learns.

## Deviation from research/63 (the sourcing pass) — and why
research/63 recommended vendoring River's `LogLoss` as an ONLINE accumulator
(stream of `(p, y)` → running mean). On building, two facts make that the wrong
shape here:
1. **We already have the formulas.** `paper_trading/prediction_lab/
   proper_scoring_rules.py` (vendored MIT) already gives `logarithmic_score`
   (−log₂p) and Brier. Re-vendoring River's `LogLoss` would DUPLICATE scoring
   logic (Rule C / DRY smell).
2. **Every prediction is already persisted.** Each closed §9 experiment is a row
   in the experience memory with `win_probability`, `actual_outcome`, and (slice
   3a) `data_provenance`. A running prequential mean is order-independent, so it
   is exactly an aggregate over that stored stream.

**A query over the persisted stream beats an in-memory accumulator:** it is
stateless (survives restart — an accumulator would reset), naturally
provenance-separable (reuses the slice-3a filter), and **verifiable on the real
293 predictions right now** (Rule F) instead of only on future live ticks. This
is a legitimate sourcing outcome (sourcing-oss-parts step 8 — reuse/adapt beats
importing machinery we don't need), not a compromise (Rule I): the query is the
better feature. River stays the documented swap-up if a per-BAR (finer than
per-trade) accumulator is ever needed.

## What it computes
`ExperienceMemory.prequential_forecast_score(data_provenance=None)` →
`PrequentialForecastScore(count, mean_log_loss_bits, mean_brier)` over the stored
predictions:
- per-prediction **log-loss (bits)** = −log₂(p) if the trade won else −log₂(1−p),
  p clamped off 0/1 — the strictly-proper score that punishes confident-wrong
  hardest (research/48). Layer-10 keeps its own inlined formula (no Layer-7 import).
- per-prediction **Brier** = (p − won)².
- `data_provenance` filter (slice 3a) → the LIVE vs REPLAY skill split.

Distinct from the calibration board (per-mechanism predicted-vs-actual *win-rate*
gap): this is the scalar *forecast skill / sharpness* over the whole stream — the
standard prequential-evaluation output.

## Wiring (Rule G)
Service computes overall + live + replay scores from the memory (writer thread,
owns the connection) → published snapshot `prequential_forecast_score` → read
model → server → the dashboard **Reflection panel** (a "forecast skill" line:
log-loss bits · Brier, live vs replay). Same pipe as slice-3a's provenance mix.

## Verification
- **Rule F (real 293-prediction DB):** compute the running log-loss/Brier over the
  real stored predictions (all live today); assert it matches a direct
  independent recomputation, and that `data_provenance="replay_faithful"` is empty
  until replay accrues.
- **Hermetic:** a confident-wrong stream scores a high log-loss; a calibrated
  stream scores low; live vs replay are separated.

## Backlog (Rule K)
Per-BAR (finer than per-trade) prequential scoring needs per-step predictions the
loop does not emit yet — that is the River-accumulator use-case and stays a future
item if wanted. Not promised by this slice.
