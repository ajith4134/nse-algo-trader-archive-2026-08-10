# BACKLOG — deferred work, tracked so nothing is silently skipped (Rule K)

This is the authoritative standing to-do memory across turns/sessions. Every
"queued / next / named-future-consumer / deferred / open-blocker" promise lands
here the moment it is made, under its owning feature, and is struck through /
moved to **Done** only when actually delivered + verified (or the user drops it).
Reconcile with the live task list at each session start.

Status key: 🔴 not started · 🟡 in progress · 🟢 done (moved to Done) · ⛔ blocked

---

## Opponent ledger (Layer 10 §10)
- 🟢 **Slice 1 — divergence → strategy bias.** DONE (2026-07-24): entries opposed
  by institutional positioning (FII lean + retail-trapped divergence) are deferred
  at all 4 entry sites; real-data verified (real reading defers a LONG). *(task #22)*
- 🟢 **Slice 2 — participant VOLUME file.** DONE (2026-07-24): volume_on() added;
  FII churn (vol/OI) → participation_conviction, wired into the gate (suppress
  defer on "low" conviction); real-data verified (live churn 0.354 → normal). *(task #23)*
- 🟢 **Slice 3 — multi-day FII-net trend.** DONE (2026-07-24): 5-day FII-net
  least-squares trend (confirming/weakening/flat) wired into the gate (weakening
  suppresses the defer); real-data verified (live walk → building short →
  confirming). *(task #24)* — **opponent-ledger feature COMPLETE.**

## §9/§10 grading — proper scoring rules (research/44 borrow)
- 🟢 **Vendor python-prediction-scorer (MIT) proper scores.** DONE (2026-07-24):
  log/quadratic on §9 grading + scoreboard; cohort mean_log_score on the
  calibration board; antibody trips on confidently-wrong log-score. Real-data
  verified over 213 SQLite experiences. *(task #25)*

## Layer 10 — §10 institution features
- 🟢 **Information diet (accounting).** DONE (2026-07-24): per-source influence +
  diet-health read; inert-learning raises a monitoring WARNING; panel wired. Real-data
  verified (real memory → recalibration 100% / veto 47% → healthy). *(task #30)*
  ~~The one §10 institution feature not yet built~~
  (PLAN §10 order: assumption registry ✓, opponent ledger ✓, INFORMATION DIET,
  epidemiology→antibody ✓). Account for WHAT information the bot consumes to decide —
  the sources/signals feeding entries (ADX regime, opponent ledger, memory priors) and
  their diversity/quality/provenance — so an over-reliance or echo-chamber is visible.
  ("information-diet-DIRECTED research targeting" is separately PARKED to Layer 11.)
  Done = a per-decision information-source ledger + a diet-health read, wired + verified.

## Layer 10 memory substrate
- 🟢 **Graph substrate decision + SQLite multi-hop.** DONE (2026-07-24):
  Graphiti/Neo4j REJECTED (LLM-text-extraction KG, server+LLM required, Kùzu
  deprecated — impedance mismatch for structured records; research/50). Delivered
  the multi-hop capability in SQLite: outcome_sequence_dependence (LAG) → non-iid
  clustering feeds the antibody verdict. Real-data verified over 213 experiences.
  *(task #28)*
- 🔴 **Regime-transition fragility + cross-regime co-failure clusters (queued).**
  The LAG/recursive-CTE substrate is built; these need MULTI-REGIME data (real
  data is single-regime "normal" today). Done = fragility/co-failure derived +
  consumed, verified once regimes vary.
- 🟢 **Brier decomposition** (Murphy reliability/resolution/uncertainty). DONE
  (2026-07-24): vendored (briertools rejected — no Murphy fn, 6 deps, no license);
  reliability_decomposition() + diagnosis fed into the antibody's tripwire detail;
  real-data verified over 213 experiences. *(task #26)*
- 🟢 **Auto-recalibration consumer.** DONE (2026-07-24): learn_mechanism_recalibrations
  → per-mechanism bias offset applied to win_probability at all 4 entry sites (demotes
  over-confident theses; re-derives table) + no-edge (resolution≈0) hard-veto.
  Real-data verified (post-breakout-trend −0.72 → 0.84 recalibrates to 0.12).
  *(task #27)*

## Open real-data blockers (Rule F/J — sim-verified, real pass pending)
- ⛔ **Shadow-arm recovery (slice 4) live pass.** Functionally verified via sim
  harness; real-data pass = live shadow-probe counts / a real refute→recover
  cycle over an open market session. Needs market open.

---

## Done
_(move items here with the commit/date when delivered + verified)_
- 🟢 **Opponent ledger core** (fetch NSE participant OI + read model + dashboard
  panel) — real-data verified, committed `e042067` (2026-07-24).
