# Research/48 — Proper scoring rules (vendor python-prediction-scorer)

**Layer 10 / §9 grading enrichment.** Rule D design doc. Rule E/sourcing record.
Closes the research/44 queued borrow.

## 1. The gap
§9 grading (`prediction_outcome_grading.grade_prediction`) scores only **Brier**
(`brier_contribution = (win_prob − actual)²`). Brier **saturates** — a confidently
wrong call (predict 0.95, lose) and a mildly wrong one are punished on a bounded
[0,1] scale, so a mechanism that is *confidently* wrong doesn't stand out sharply.
The **logarithmic score** punishes confident-wrong toward ∞, which is exactly what
the antibody tripwire wants for catching an over-confident thesis fast.

## 2. Sourced (sourcing-oss-parts; steps 1-5 done, research/44 + this pass)
**python-prediction-scorer** (yhoiseth, MIT). Deep-scanned its real `rules.py` +
`_common.py` (verbatim). Its scoring rules take **p = the probability the
prediction assigned to the outcome that ACTUALLY happened**:
- `brier_score(p) = 2·(1−p)²`   → 0 best, 2 worst (two-class sum form).
- `logarithmic_score(p) = −log₂(p)`   → 0 best (p=1), →∞ as p→0.
- `quadratic_score(p) = p·(2−p) − (1−p)²`   → +1 best, −1 worst.
- `practical_score` — a bounded Metaculus log variant (not needed here).
Uses `Decimal` + an OO `Prediction`/`Category` API we don't need.

**Decision: VENDOR-AND-ADAPT** (research/44's plan). Copy the 3 formulas as small
float functions with self-describing names (Rule C), drop `Decimal`/OO, add a
`p_outcome` mapper and a cohort cross-entropy. Depending on the lib to pull a
Decimal OO API for 3 one-line formulas is not worth it.

## 3. The mapping (single-probability binary prediction)
Our record stores `win_probability` w and the realized outcome. The probability
assigned to what happened:  **p_outcome = w if the trade WON, else 1 − w.**
Then per graded prediction: `logarithmic_score = −log₂(p_outcome)` (clipped away
from 0), `quadratic_score`, `brier_score_two_class` as above. (Existing
`brier_contribution = (w−actual)²` is kept unchanged so current aggregation is
untouched; the new two-class Brier is just 2× it.)

**Cohort log-score with NO schema change:** a mechanism cohort already exposes
`predicted_win_rate` p̄ and `actual_win_rate` ā on the calibration board. The
cohort mean log-score = the **calibration cross-entropy**
`H(ā, p̄) = −[ā·log₂(p̄) + (1−ā)·log₂(1−p̄)]` (bits) — derivable from the two
aggregates already stored/queried, so the antibody gets log-score without touching
the SQLite schema or per-experiment rows. Baseline: an always-0.5 predictor scores
1.0 bit; a confidently-wrong cohort (p̄=0.85, ā=0.15) scores ≈2.36 bits.

## 4. Design — files & wiring (Rule C, Rule G)
- `prediction_lab/proper_scoring_rules.py` (vendored): `probability_assigned_to_outcome`,
  `logarithmic_score`, `quadratic_score`, `brier_score_two_class`,
  `calibration_cross_entropy_bits`. Provenance comment (repo + MIT + what changed).
- `GradedPrediction` gains `logarithmic_score`, `quadratic_score` (set in
  `grade_prediction` from p_outcome; defaults keep test constructions working).
- `TableScore` gains `mean_logarithmic_score`, `mean_quadratic_score`; surfaced on
  the §9 prediction-tables dashboard.
- `CalibrationBoardRow` gains `mean_log_score` (cohort cross-entropy from
  predicted/actual rates, computed at build — no SQL/schema change); surfaced on the
  Reflection panel.
- **Primary consumer (Rule K — decisions, not display):** the assumption registry's
  calibration tripwire ALSO trips (and `vetoed_mechanisms` also vetoes) when a
  cohort is **over-confident** (ā < p̄) AND its `mean_log_score ≥
  CONFIDENTLY_WRONG_LOG_SCORE` (1.0 bit — worse than a coin-flip). This is an OR
  with the existing one-sided binomial z-test, so it only ADDS trips (log-score
  catches confident-wrong the binomial misses at smaller n); existing pass/hold
  behaviour is preserved. Feeds the existing antibody veto directly.

## 5. Verification
- Hermetic: exact scores vs hand-computed (logarithmic_score(0.5)=1.0,
  quadratic_score(1)=1, brier_score_two_class(1)=0; cross-entropy monotonic);
  tripwire trips on a confident-wrong cohort via log-score even when binomial is
  borderline; existing assumption tests stay green.
- **Rule F (real data — achievable now):** recompute log/quadratic over the REAL
  closed experiments in `~/.nse_algo_trader/experience_memory.sqlite3` and assert
  the new scores are finite/consistent with stored Brier, and the calibration board
  carries a real `mean_log_score` per mechanism. No market needed.

## 6. Scope / backlog
- **This slice:** log + quadratic proper scores; §9 + calibration-board aggregation;
  log-score antibody trip; real-data verify.
- **Queued (docs/BACKLOG.md):** `briertools` Brier decomposition (calibration/
  discrimination) for a reliability view — separate enrichment, borrow later.
