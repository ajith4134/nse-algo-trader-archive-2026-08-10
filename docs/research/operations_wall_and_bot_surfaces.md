# Operations Wall (/wall) + segment-bot / directional-AI dashboard surfaces

**User ask (2026-08-04).** "Make every feature on this server visible on the dashboard like a TV that
shows all the features working — the 3 AI bots, their 2 directional AI features, and everything else.
Make it a RULE, and let future features appear too." Answered scoping MCQ:
- Location: BOTH a new `/wall` page AND surface on the main `/` dashboard.
- Scope: the operational surface manifest + the 3 segment bots + directional AI — **manifest-driven so any
  future feature auto-appears** the moment it registers a surface.
- Signal: MEASURED build/wiring status now (works today, no live feed) **+** a live heartbeat that lights
  once the pod live-loop publishes (honest degradation per Rule R — never defaulted to healthy).

## Why the bots aren't already surfaced

The dashboard snapshot is built by `live_paper_trading_service._build_feature_surfaces` — but the 3
segment bots run in `portfolio_supervisor/pod_runner`, a DIFFERENT process the dashboard's live service
does not hold. Their live state is therefore unreachable from the snapshot today (blocked behind the known
"production data adapters + live-loop tick" blocker — the pod runs on empty-universe adapters). So they had
no surface and no manifest key → invisible, a Rule-N gap I created wiring slices 2–4.

## Design — measured now, heartbeat later (Rule R honest)

### A. `dashboard/segment_bot_surface_prober.py` (new)
Measures each bot's status FROM THE CODE + persisted stores (never hand-typed — Rule R):
- module present + wired into `pod_runner` (AST import-graph reachability),
- `DirectionalSideBrain` wired into the bot (import present),
- competency store on disk → closed-trade count → `gathering` vs `active` on the maturity ladder (Rule Q),
- per-underlying directional engines earned-count from the brain store dir.
Optional live heartbeat: if the pod publishes a state file, read `last_pass_at`; else the metric reads
`NOT-INSTRUMENTED` (never green). Emits `DashboardFeatureSurface` rows:
- `index_option_bot`, `stock_option_bot`, `cash_intraday_bot` (the 3 bots),
- `directional_ai_bull` (P↑ → call/long side), `directional_ai_bear` (P↓ → put/short side) — the 2
  directional AI features the user named.
Injected in `dashboard_read_model.build_dashboard_snapshot` (always-on, with or without live auth), so it
shows on the existing `/` coverage panel AND the new `/wall`.

### B. `dashboard/render_operations_wall_html.py` (new) → route `/wall`
A TV-optimized live wall: every operational surface as a large status tile, grouped by subsystem, each tile
= status light (reserved status palette good/warning/serious/neutral + ICON + LABEL, never colour-alone —
dataviz status-tile rule) · headline metrics · a live-pulse dot (heartbeat). Renders
`FEATURE_SURFACE_MANIFEST` in full via `rows_in_manifest_order()` so a not-yet-built feature shows a
"▲ not yet surfaced" tile and any FUTURE feature appears automatically once added to the manifest — that is
the enforced RULE. Reuses the house design tokens from `render_feature_catalogue_html` (light+dark,
theme-aware). Auto-refresh polling `/api/snapshot` for the live pulse.

### C. Main `/` page + nav
Add a `/wall` nav link and a compact "3 bots + directional AI" strip on `/` (the coverage panel already
consumes `feature_surfaces`; the new rows join it automatically).

## Sourcing (Rule I)
N/A — internal surfacing/instrumentation over the project's own code + existing dashboard framework
(FastAPI + the DashboardFeatureSurface registry). No external OSS part. Charting is hand-built HTML/CSS
status tiles per the dataviz skill (status palette), no library. Logged, not silently skipped.

## Verification (Rule F / N)
Restart `nse-dashboard` (systemd) → `curl` `/` (200), `/wall` (200), `/api/snapshot` (bot surfaces present
+ populated), then `scripts/screenshot_dashboard.py --expect` the bot titles on `/wall`. Unit tests: prober
returns the 5 rows with correct measured status on a temp store; wall renderer contains every manifest key.

## Backlog (Rule K)
- Live heartbeat is `NOT-INSTRUMENTED` until the pod publishes a bot-state file → depends on the live-loop
  blocker. Track as an open blocker; the measured build/wiring status is live now.
- OHLC-bars / retrain-cadence / full-universe perf (carried from the directional-wiring slice).
