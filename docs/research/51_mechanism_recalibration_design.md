# Research/51 — Mechanism recalibration (act on the Brier diagnosis)

**Layer 10 → §9 feedback.** Rule D. Closes task #27 (the Brier-decomposition
follow-on consumer). Turns the reliability/resolution *diagnosis* into an *action*.

## 1. The idea (the §9 model asked for this)
`adx_confidence_prediction` sets `win_probability` from a fixed ADX logistic and
says in its own docstring: *"deliberately un-calibrated at first — the scoreboard
measures how wrong it is (Brier) so later layers can recalibrate."* The memory now
knows, per mechanism, the calibration gap and whether the miscalibration is a fixable
bias (reliability-driven, has resolution) or fundamental (resolution≈0, no edge).
Act on it:
- **Recalibratable** (biased but discriminates): apply a memory-learned **bias
  offset** to `win_probability` so the recorded confidence matches reality, and
  re-derive the CONFIDENT_WIN/LOSS/UNCERTAIN table — an over-confident thesis is
  demoted instead of silently repeating its over-confidence.
- **No edge** (resolution≈0): **hard-veto** the mechanism — it has no predictive
  power, recalibration can't help.

## 2. The offset (bias correction — preserves resolution)
Additive bias correction per mechanism: `offset = actual_win_rate − predicted_win_rate`
(from the calibration board). `recalibrated = clamp(raw + offset, 0.01, 0.99)`.
Additive (not multiplicative) so the mechanism's *relative* ordering/discrimination
(resolution) is preserved while the mean bias is removed — matching the "biased but
discriminates" diagnosis. Real example: post-breakout-trend predicted 0.84, actual
0.09 → offset −0.75 → a raw 0.84 becomes 0.09 (demoted CONFIDENT_WIN→CONFIDENT_LOSS/
UNCERTAIN). Only applied with ≥ minimum_samples history.

## 3. Design — files & wiring (Rule C, Rule G, Rule K)
- `prediction_lab/mechanism_recalibration.py`:
  - `assign_table_and_outcome(win_probability, target_reward_multiple)` — the band
    logic (CONFIDENT_WIN ≥0.60 / CONFIDENT_LOSS ≤0.40 / UNCERTAIN), **extracted and
    shared** with `adx_confidence_prediction` so recalibration and the base model can
    never diverge.
  - `recalibrate_prediction_record(record, offset_by_mechanism) -> TradePredictionRecord`
    — keeps `mechanism_name` (identity from the raw model), shifts `win_probability`
    by the mechanism's offset, re-derives table + predicted_outcome + expected reward.
    **Empty offsets → identity** (cold-start safe; all existing §9 tests unchanged).
- `memory_reflection.learn_mechanism_recalibrations(memory, config) ->
  (offset_by_mechanism, no_edge_mechanisms)`: offsets from the calibration board
  (actual−predicted, ≥ minimum_samples); `no_edge` = reliability_decomposition rows
  whose diagnosis is resolution≈0.
- **Wiring (Rule G):** the service computes both each pass (alongside
  `vetoed_mechanisms`) and sets `state.recalibration_offset_by_mechanism` +
  folds `no_edge` into `state.vetoed_mechanisms`. At each of the 4 entry sites the
  loop applies `recalibrate_prediction_record(...)` right after building the record,
  so the recorded/scored prediction carries the corrected confidence and table.
- **Decision effect:** recalibration changes the table (CONFIDENT_WIN→UNCERTAIN for a
  demoted thesis) and the recorded win_probability → changes §9 scoring, memory, and
  which trades count as "confident"; no-edge → the entry is vetoed.

## 4. Verify
- Hermetic: offset shifts probability + re-derives table (0.84 + (−0.75) → CONFIDENT_
  LOSS band); empty offsets = identity (record unchanged); no-edge mechanism ends up
  in the veto set. Existing §9/assumption tests stay green.
- **Rule F (real, now):** learn offsets from the real 213-experience board — assert
  the over-confident theses get the expected large negative offsets and a raw
  prediction recalibrates to ≈ their historical actual rate; the no-edge set matches
  the resolution≈0 diagnosis.

## 5. Backlog note
This is the last queued Layer-10 §10/reflection consumer. After it, Layer 10 is
functionally complete (real-data verified) — the only remaining Layer-10 open item is
the shadow-arm slice-4 LIVE real-data pass (needs an open market). Pause before the
next step (24/7 after-hours simulated live trading) per the user.
