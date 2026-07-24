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

## Layer 10 memory substrate
- 🔴 **Graphiti/Neo4j temporal-KG swap-up.** Named swap-up for the semantic /
  multi-hop tier when categorical SQLite queries no longer suffice (research/43).
  Deferred by design until multi-hop queries are actually needed.
- 🔴 **briertools Brier decomposition** (calibration/discrimination reliability)
  for the reflection board — enrichment, borrow later (research/44).

## Open real-data blockers (Rule F/J — sim-verified, real pass pending)
- ⛔ **Shadow-arm recovery (slice 4) live pass.** Functionally verified via sim
  harness; real-data pass = live shadow-probe counts / a real refute→recover
  cycle over an open market session. Needs market open.

---

## Done
_(move items here with the commit/date when delivered + verified)_
- 🟢 **Opponent ledger core** (fetch NSE participant OI + read model + dashboard
  panel) — real-data verified, committed `e042067` (2026-07-24).
