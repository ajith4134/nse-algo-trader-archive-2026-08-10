# Research/64 — §53 Slice 3b-i: provenance INTO decisions (design)

**Rule D design doc.** Slice 3a made memory provenance-*separable* (a
`data_provenance` filter + the live/replay mix on the dashboard). 3a's PRIMARY
consumer — provenance actually changing what the bot does — was queued (Rule K).
This slice (3b-i) wires it in. The dense per-step prequential scorer is a separate
increment (3b-ii, research/63; still queued after this).

## The requirement (research/53 §8.2)
"Weight replay BELOW live so a replay-only lesson never overrides live evidence,
and over-reliance on replay trips the information-diet health WARNING." 24/7
replay must keep the bot LEARNING while the market is closed — but a bar-only,
era-thin replayed day must never carry the same authority as a real live session.

## Decision: provenance-WEIGHTED evidence (not exclusion)
Considered three policies:
- **A. Live-authoritative (exclude replay from hard decisions).** Simplest,
  absolute "never overrides", but makes replay learning INERT for the veto/
  recalibration path — contradicts the whole point of 24/7 replay learning.
- **B. Provenance-weighted evidence (CHOSEN).** Each experience contributes to
  the veto/recalibration calibration with a weight by provenance
  (`live`=1.0, `replay_faithful`=0.25 default, config `replay_evidence_weight`).
  A cohort's *effective* sample size = Σ(weight × count). Live dominates any mix;
  a replay-ONLY cohort needs ~4× the experiences to reach `minimum_samples`, so it
  can inform but not unilaterally veto live trading. Directly implements §8.2.
- **C. Hybrid gate (soft replay recalibration, hard veto needs live).** More
  moving parts for no real gain over B.

**B is correct** (Rule I — don't compromise the feature): replay still shapes
decisions, just subordinately, and can never outweigh live evidence.

## Key property: ZERO behaviour change on today's all-live data
Every one of the real 293 experiences is `live` (weight 1.0). With only live rows,
weighted effective-n == raw count and weighted means == plain means, so
`vetoed_mechanisms` / `learn_mechanism_recalibrations` return byte-identical
results to before. The weighting only bites once replay experiences accrue — so
the Rule-F real-data pass proves *no regression*, and a hermetic injection
(Rule J) proves the discount actually works.

## Implementation (all in `memory_reflection/assumption_registry.py` + info-diet)
1. `AssumptionConfig.replay_evidence_weight: float = 0.25`.
2. New `provenance_weighted_calibration_board(memory, config, recency_window)`:
   reuses the slice-3a `calibration_board(data_provenance=…)` per provenance
   (from `experiment_count_by_provenance()`), then combines cohorts with weight =
   `weight_for(prov) × row.experiment_count` into weighted predicted/actual/brier/
   return + an effective count; drops cohorts under `minimum_samples` effective.
   No SQL change — pure Python over the tested board, keeps Layer-10 off the
   sqlite backend.
3. `vetoed_mechanisms` and `learn_mechanism_recalibrations` iterate the WEIGHTED
   board instead of the raw one (the two hard-action consumers the service already
   calls each pass → the L7 loop's veto/recalibration gate). `evaluate_trading_
   assumptions` stays RAW/pooled — it is the transparency surface + WARNING alert,
   not a trade gate, so it should still show the full picture including replay.
4. Information-diet over-reliance: `read_information_diet` gains
   `live_experience_count` / `replay_experience_count`; new field
   `replay_experience_share`; a new WARNING when memory is active but replay is
   ≥ `_MAX_HEALTHY_REPLAY_SHARE` (0.5) of a sufficient experience base — "over-
   relying on 24/7 replay". Service passes the counts from
   `_memory_experiment_count_by_provenance()`.

## Verification
- **Hermetic (Rule J):** replay-only losing cohort (eff-n below `minimum_samples`)
  is NOT vetoed; the same cohort with live losses IS vetoed; a live-good +
  replay-bad mix stays live-dominated (not vetoed); high replay share → info-diet
  WARNING.
- **Real data (Rule F):** on the real 293-live DB, weighted veto/recalibration ==
  raw veto/recalibration (no regression); info-diet replay share = 0 → no false
  over-reliance WARNING.

## Wiring (Rule G) & backlog (Rule K)
Weighted board → veto/recalibration → the loop (already called by the service).
Info-diet counts → dashboard WARNING + monitoring alert. Queued after this:
**3b-ii** the dense per-step prequential scorer (vendor River `LogLoss` +
`BrierScore`, research/63).
