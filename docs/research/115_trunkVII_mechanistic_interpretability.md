# VII — mechanistic interpretability  ·  research/115

**Trunk VII CONSCIENCE, branch: mechanistic interpretability.** Design doc (Rule D).

## The idea
A safe autonomous system must be able to explain **why** it decides what it decides, in terms of
its own internal mechanisms — not a black box. This bot already tags every prediction with a
`NamedPredictionReason` (the mechanism), and the §10 calibration board aggregates outcomes per
mechanism. Mechanistic interpretability turns that into a **decision-attribution report**: which
internal mechanisms actually drive the system's decisions, how much, and whether each is
trustworthy (well-calibrated, positive-edge). The alignment payoff: an **influential-but-unreliable
mechanism** (drives many decisions yet is miscalibrated or negative-edge) is a transparency RED
FLAG — the system is leaning on something it shouldn't.

## Distinct from what exists
`memory_reflection` already ACTS on miscalibrated mechanisms (recalibration offsets + veto). This
branch is the **transparency VIEW** over the same substrate — it explains/attributes, it doesn't
re-act (no duplicate consumer). It answers "what is driving me and can it be trusted?", which the
veto machinery doesn't surface.

## Sourcing note (skills)
Mechanistic interpretability is an AI-safety field (feature attribution, circuit analysis). For a
mechanism-tagged decision log the right, non-heavy realisation is an **attribution report over the
named-reason outcome aggregates** we already persist — no captum/SHAP dependency (those are for
differentiable nets; our "mechanisms" are already named, discrete, and outcome-scored). Build-from-
our-own-substrate justified.

## Component parts (`conscience/mechanistic_interpretability.py`, pure)
1. **`MechanismAttribution`** (frozen) — `mechanism_name`, `experiment_count`, `influence_share`
   (share of total decisions), `calibration_error` (|predicted−actual| win-rate), `mean_return`,
   `reliable` (calibration_error ≤ tol), `edge_positive` (mean_return > 0), `flag`
   ('' | 'influential-unreliable').
2. **`InterpretabilityReport`** (frozen) — `attributions` (influence-desc), `total_experiments`,
   `top_mechanism`, `red_flags` (influential-unreliable names), `reliable_share` (share of
   influence carried by reliable mechanisms), `summary`.
3. **`explain_decision_mechanisms(experience_memory, config)`** — builds the report from the real
   calibration board; a mechanism is a RED FLAG when its influence ≥ `red_flag_influence` AND
   (not reliable OR not edge_positive).

## Wiring (Rule G/N)
Daily `_maybe_run_mechanistic_interpretability` caches the report; dashboard surface
`mechanistic_interpretability` (Rule N) + manifest + coverage audit. READ-ONLY transparency
diagnostic — the acting-on-unreliable-mechanisms consumer already exists (veto/recalibration), so no
new consumer is owed (stated at sign-off, Rule K).

## Verification
- **Hermetic (Rule J):** injected board — a well-calibrated positive-edge cohort → no red flags,
  high reliable_share; an influential miscalibrated mechanism → red flag.
- **Real-data (Rule F):** run over the real §10 memory; print the attribution report (top
  mechanisms, red flags, reliable share).

## Atlas impact
mechanistic interpretability 🔴→🟢. VII CONSCIENCE 7🟢→8🟢. Overall 34→35 / 197 (17.8%).
