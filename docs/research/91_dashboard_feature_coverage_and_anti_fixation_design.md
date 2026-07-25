# research/91 — Two process mechanisms: (1) display ALL features on the dashboard, (2) never lose the whole plan

**Date:** 2026-07-25
**Status:** DESIGN (Rule D). Requested by the user before resuming #13/#14. The point is
STRUCTURAL fixes, not another one-off — so the problems can't recur.

Both problems have the same root cause: **there is no single, enforced place that holds the
WHOLE.** The dashboard holds a hand-picked subset of panels; my working memory holds the
current feature's local backlog. New features fall out of both silently.

---

## PROBLEM 1 — Display ALL features on the dashboard (systematically, not panel-by-panel)

### Why it happens
`render_dashboard_html` renders a HARD-CODED list of panels. Each new feature needs (a) its
state threaded into the published snapshot and (b) a bespoke panel hand-written. I built the
§53/ADVANCED features (multi-broker, curriculum, champion-challenger, market-impact, regime
memory) and skipped (b) — so they run but are invisible. Doing it per-feature by hand
guarantees I forget again.

### Design — a Feature-Surface REGISTRY + generic renderer + COVERAGE AUDIT
Turn "display a feature" from bespoke HTML into "register a surface," and make a missing
surface a **test failure + a visible dashboard row**, not silence.

1. **`DashboardFeatureSurface`** (uniform shape any feature can emit):
   `key, title, section, status ∈ {active, idle, blocked, off, gathering}, headline_metrics:
   dict[str,str], rows: list[dict] (optional table), note`. One shape → one renderer.
2. **`feature_surface_registry`** — features (or thin service-side providers) register a
   `build_surface() -> DashboardFeatureSurface | None`. The service calls every provider at
   publish and puts the results in `published.feature_surfaces`.
3. **Generic renderer** `render_feature_surface(surface)` — a standard "metrics row + optional
   table + status chip" panel matching the EXISTING dashboard design system (READ the dataviz
   skill before writing it; reuse the current CSS/tokens so it looks native). Adding a feature
   = implement its surface, zero bespoke HTML.
4. **Canonical FEATURE MANIFEST + coverage audit.** A manifest lists every feature that should
   surface (seeded from SYSTEM_MAP §2 registry). Two enforcement points:
   - `test_dashboard_feature_coverage` — asserts every manifest feature has a registered
     provider (fails CI when a new feature is built without a surface).
   - A **"Feature coverage" panel** on the dashboard itself that lists ALL manifest features
     with status (surfaced/live/blocked/off/not-yet-surfaced) — so "is the dashboard up to
     date?" is answerable at a glance, by anyone, without reading code.
5. **Enforcement rule (ties to Rule G/H):** a feature is not "done" until it has a surface
   provider + manifest entry, exactly as it isn't done until wired + mapped. (Add to Rule K's
   sign-off checklist and the new Rule M below.)

### First slice of #13 (when we build it)
Build the registry + `DashboardFeatureSurface` + generic renderer + the coverage panel +
the audit test, then register surfaces for the already-built-but-invisible features:
multi-broker fleet/failover status, replay fidelity tier + regime-curriculum coverage,
champion config (global + per-regime), market-impact config, market-regime memory calibration.
Real-data verified against the live snapshot. (dataviz skill read first.)

---

## PROBLEM 2 — Never get fixated on one topic / forget the whole plan

### Why it happens
The plan is scattered: `PLAN.md` (design), `flowcharts/00_overview` (layer roadmap),
`SYSTEM_MAP.md` (structure), `BACKLOG.md` (deferrals), many `research/*`. I follow the LOCAL
backlog thread of whatever I'm in (Rule K), which is great for not dropping sub-items but has
no force pulling me back to whole-plan altitude. Result: 20 slices deep in one area, the rest
of the plan out of view.

### Design — one master tracker + an altitude RULE + a memory + a per-sign-off habit
1. **`docs/MASTER_PROGRESS.md`** — ONE page holding the ENTIRE plan at high altitude: Layers
   1–11, the §53 replay tiers, the ADVANCED slices, multi-broker, dashboard, open blockers,
   paused items — each a single status line. It is an INDEX over PLAN/SYSTEM_MAP/BACKLOG, not a
   copy. This is the "complete plan" in one glance. Kept current every sign-off (like
   SYSTEM_MAP/BACKLOG).
2. **Rule M — Plan Altitude (anti-fixation)** (added to the project `CLAUDE.md`):
   - **Session start:** read `MASTER_PROGRESS.md` first (alongside BACKLOG) and state where we
     are in the WHOLE plan.
   - **Every sign-off:** after the per-feature backlog list (Rule K), add a one-line
     **whole-plan altitude check** — where this slice sits in the master plan + the top 2–3
     remaining big-rocks across the ENTIRE plan (not just this feature).
   - **Anti-tunnel trigger:** after ~3 consecutive slices in one feature-area, or before
     starting a new area, explicitly re-pick the next work by WHOLE-PLAN priority from
     MASTER_PROGRESS — not by whatever is locally adjacent.
   - **Keep MASTER_PROGRESS current** every sign-off (add to the Rule H/K update ritual).
3. **Auto-memory (feedback):** persist the directive + the mechanism so it survives across
   sessions (a fresh agent reads it and behaves the same).
4. **Reuses existing muscles:** Rule A (sign off before advancing) and Rule K (surface open
   items) already fire every slice — Rule M just adds the ZOOM-OUT step to that same ritual, so
   it costs one extra paragraph per sign-off, not a new workflow.

### Why a rule + doc + memory (all three), not one
- The **doc** (MASTER_PROGRESS) is the artifact that holds the whole plan.
- The **rule** (Rule M in CLAUDE.md) forces me to READ and UPDATE it — always-active, so I
  can't quietly skip it.
- The **memory** carries the intent across sessions so a fresh context re-establishes the
  habit even before reading CLAUDE.md.
Together they make forgetting the plan structurally hard, the same way BACKLOG+Rule K made
forgetting a deferral hard.

---

## What I'll establish NOW (this turn) vs BUILD later
- **NOW (durable anchors, cheap):** create `MASTER_PROGRESS.md`; add **Rule M** to the project
  `CLAUDE.md`; write the anti-fixation memory. These are the "rule/memory" the user asked for.
- **NEXT as #13 (a build slice, needs dataviz + code):** the dashboard feature-surface registry
  + generic renderer + coverage panel + audit + registering the invisible features.
- **#14** (incremental high-fidelity replay prebuild) follows, per the user's ordering.

## Rule check
- **Rule D:** this design is persisted here before any build.
- **dataviz:** Problem-1 panel code is DEFERRED to the #13 build, where the dataviz skill is
  read first (no chart/panel code written in this design turn).
- **Rule H/K/M:** MASTER_PROGRESS joins SYSTEM_MAP + BACKLOG in the per-sign-off update ritual.
