# Research/49 — Brier-score decomposition (reliability vs resolution)

**Layer 10 reflection / explainable-memory enrichment.** Rule D design doc.
Sourcing verdict (sourcing-oss-parts): **vendor the formula, do NOT depend.**

## 1. Gap & why
The antibody now knows a thesis is over-confident (gap, z, log-score). It does not
say *why* the miscalibration exists. The **Murphy Brier decomposition** answers that:
`BS = Reliability − Resolution + Uncertainty`.
- **Reliability (REL)** — calibration error: how far each forecast bin's predicted
  rate sits from its actual rate. High REL = the numbers are biased but the mechanism
  may still *discriminate* → recalibratable.
- **Resolution (RES)** — discrimination: how far bin outcomes spread from the base
  rate. ~0 RES = the mechanism has **no edge** at all (its "confident" and "uncertain"
  calls win at the same rate).
- **Uncertainty (UNC)** — `ō(1−ō)`, the irreducible base-rate variance.

This is the "explainable memory" Layer-10 goal: distinguish *recalibrate* (bias,
high REL, decent RES) from *no edge* (RES≈0).

## 2. Sourcing verdict (agent-verified 2026-03, deep-research)
- **`briertools`** (PyPI v0.0.4, 2026-03-25; github.com/nullset-mit/briertools) is a
  brand-new research repo for a threshold/cost-weighted Brier & decision-curve paper
  (arXiv:2504.04528). It does **NOT** expose Murphy REL/RES/UNC — only a private
  isotonic (CORP-style) calibration/discrimination split — and drags in numpy +
  sklearn + matplotlib + scipy + matplotcheck + pandas, with **no license file**.
  Installing it to get math it doesn't expose is a bad trade.
- **Decision: VENDOR** the ~15-line Murphy formula (Murphy 1973, *A New Vector
  Partition of the Probability Score*; mirrored on Wikipedia "Brier score"). A
  published equation, provenance-noted, matching the project's vendored-math pattern.

## 3. Formula (binary, binned) — agent-confirmed
Over K bins, bin k with n_k forecasts, mean forecast f_k, observed rate o_k, base ō:
- `REL = (1/N) Σ n_k (f_k − o_k)²`
- `RES = (1/N) Σ n_k (o_k − ō)²`
- `UNC = ō(1 − ō)`  →  `BS ≈ REL − RES + UNC`
**Binning:** the identity is exact only when grouping by unique forecast values;
with continuous probabilities a small within-bin residual remains (Stephenson 2008,
Ferro & Fricker 2012). For ~200 points use **~10 equal-frequency bins** (5 too
coarse, 20 inflates REL at ~10/bin); return per-bin counts so sparse bins are visible.

## 4. Design — files & wiring (Rule C, Rule G, Rule K)
- `memory_reflection/brier_decomposition.py` (vendored math; Layer 10 owns it — it is
  a reflection concern, no Layer-7 import): `murphy_brier_decomposition(predicted,
  outcomes, bin_count=10) -> BrierDecomposition(reliability, resolution, uncertainty,
  brier_total, sample_count, bin_count)` (equal-frequency bins) + `reliability_diagnosis`
  ("miscalibration reliability-driven — recalibratable" vs "resolution≈0 — no edge" vs
  "well-resolved").
- `ExperienceMemory.reliability_decomposition(minimum_experiments=12,
  recency_window=None) -> list[MechanismReliability]` (protocol + sqlite): fetch each
  cohort's per-experiment (win_probability, won) and decompose. Reuses the recency
  window (slice-4 pattern).
- **Primary consumer (explainable memory — a stated Layer-10 goal):** the calibration
  tripwire verdict's detail gains the **diagnosis** (why the thesis fails: reliability
  vs resolution), and the Reflection panel shows REL/RES per cohort. The verdict is the
  antibody's *explanation* of a refutation → decision-adjacent, not decoration.
- **Queued future consumer (Rule K):** auto-recalibration of win_probability for a
  high-REL / good-RES mechanism (recalibratable) vs hard-veto for RES≈0 (no edge) —
  a later slice; recorded in docs/BACKLOG.md.

## 5. Verify
- Hermetic: REL/RES/UNC on hand-built bins; `BS ≈ REL−RES+UNC` reconstruction within
  the binning residual; a well-resolved-but-biased set → high REL / high RES; a
  no-edge set → RES≈0.
- **Rule F (real, now):** decompose the real 213 SQLite experiences per cohort; assert
  reconstruction holds and the confidently-wrong theses show the expected REL/RES.
