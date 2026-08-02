# XIII — contradiction resolution + deception/misinfo resistance  ·  research/132

**Trunk XIII EPISTEMICS (strongest cognitive trunk) — the 2 remaining 🔴.** Design doc (Rule D).
Sourcing: real pass (agent a7434e84, 24 tool-uses) — findings below; both are bespoke over OUR §10
memory with one vendorable statistical primitive each, evaluated for fit.

## Sourcing findings (real search)
- **Contradiction resolution:** TMS/ATMS (`ATMS-in-Python` 1★ incomplete), AGM belief-revision
  (`belief-revision-engine`, dormant), Dempster-Shafer (`pyds`, archived) all solve SYMBOLIC/evidential
  problems over propositions/BPAs — WRONG shape. The real shape is "does a regime cohort's win-rate
  significantly diverge from the global belief" = a **two-proportion z-test**. `statsmodels`
  (`proportions_ztest`) fits but is a heavy dep; `river.drift.ADWIN` is streaming-overkill. **Verdict:
  BUILD the z-test on `scipy` (already a dep), reference statsmodels/ADWIN; the detection policy is
  bespoke over the calibration cohorts.**
- **Misinfo resistance:** subjective-logic / beta-reputation (`SLEncodings`, `retrust` EBSL) is the
  right ALGORITHM but no clean licensed maintained package; `trueskill` (BSD, mature) is a vendorable
  Gaussian-rating primitive but is 1v1-game-shaped. **Verdict: BUILD beta-reputation (α=good+1, β=bad+1)
  from formula — the clean fit for binary source-credibility — reference TrueSkill/subjective-logic;
  policy bespoke over the calibration board.**

## The ideas
- **Contradiction resolution** — the system's global belief about a mechanism can be CONTRADICTED by
  regime-conditional evidence (globally "reliable", but in a specific regime the evidence says
  otherwise). Detect the significant divergences (z-test) and RESOLVE toward the more-specific
  evidence (regime-conditional belief wins — the epistemic entrenchment principle).
- **Deception / misinformation resistance** — treat each mechanism as an information SOURCE of
  beliefs; a source whose confident predictions are systematically WRONG is misinformation. A
  beta-reputation per source (credible vs not) + a RESISTANCE flag for sources that are OVER-TRUSTED
  relative to their credibility (high influence, low reputation) — the epistemic immune system.

## Targets
- `resolve_contradictions(regime_cohorts, global_hit_rate) -> ContradictionReport` — z-test each
  regime cohort vs the global belief; a significant divergence is a contradiction resolved toward the
  regime evidence.
- `assess_source_credibility(board) -> MisinfoReport` — beta-reputation per mechanism-source; flag
  over-trusted-but-unreliable sources to resist.

## Component parts (`epistemics/` — new package for Trunk XIII)
- `epistemics/contradiction_resolver.py` — `Contradiction`(regime, global_hit, regime_hit, z_score,
  p_value, resolution) + `ContradictionReport`(contradictions, has_contradiction, summary) +
  `resolve_contradictions` (two-proportion z on scipy).
- `epistemics/misinformation_resistance.py` — `SourceCredibility`(source, reputation, influence,
  is_over_trusted) + `MisinfoReport`(sources ranked, flagged, summary) + `assess_source_credibility`
  (beta-reputation α/β from calibrated-vs-confidently-wrong).

## Wiring (Rule G/N)
Daily `_maybe_run_epistemic_defense` builds both from the REAL memory (regime cohorts + calibration
board), caches them. Surfaces `contradiction_resolution` + `misinformation_resistance`. READ-ONLY
epistemic diagnostics — the acting (regime-conditional beliefs, source down-weighting) already exists
in part via recalibration/veto; a targeted consumer is a queued refinement (Rule K).

## Verification
- Hermetic (Rule J): a regime cohort sharply diverging from global → contradiction with z/p; a
  concordant cohort → none. A confidently-wrong high-influence source → low reputation + over-trusted;
  a calibrated source → high reputation.
- Real-data (Rule F): over the real §10 memory, report the real contradictions across regimes and the
  real source-credibility ranking.

## Atlas impact
contradiction resolution + deception/misinfo resistance 🔴→🟢. XIII 5🟢→7🟢 (0🔴 left; 6🟡 remain).
Overall built 54→56/197 (28.4%). NEW feature package `epistemics`.
