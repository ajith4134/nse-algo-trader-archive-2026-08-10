# Dashboard offline visibility — token-expiry resilience  ·  research/122

**Bug + fix design doc (Rule D).** Root cause found by actually loading the running dashboard (the
Rule-N/Rule-F step I had been skipping — verifying the coverage-audit *test* instead of the page).

## Symptom
The user reports "the dashboard is not showing and updating." All 32 feature-surface panels
(including the 13 VII CONSCIENCE safety-organ panels built this session) + the memory-backed panels
are blank; `/api/snapshot` returns `feature_surfaces: []` and `memory_experiment_count: 0` while the
real memory DB has 334 experiences. The static atlas/concept-tree panel DOES update (built 41 /
20.8%) — it reads `project_status_data`, not the live service.

## Root cause (evidence)
- The Kite access token (`~/.nse_algo_trader/kite_access_token.json`, dated Jul-25) is **EXPIRED** —
  `KiteAccessTokenFileStore().load_if_still_valid()` returns None. Kite tokens expire daily.
- `dashboard_server._start_live_paper_trading_service()` returns `None` when there is no valid token
  (`_build_authenticated_kite_client()` is None) → the warmup thread leaves `live_service = None` →
  every handler serves the DEGRADED snapshot (no feature surfaces, no memory panels).
- `LivePaperTradingService.start()` hard-calls `fetch_live_tradable_universe(kite_client)` →
  `kite_client.instruments("NSE")`, so the service cannot start at all without a live broker.
- **Not a regression from the VII work** — 708 tests + 8 real-data verify scripts prove the surfaces
  compute correctly; they are simply never published because the service never starts.

The real defect: panels that only read **stored SQLite** (the VII safety organs over the memory, the
memory-reflection panels, red-team over stored sessions, ethics/law over config) are gated behind a
**live broker token that expires every day** — so the dashboard is useful only for a few hours after
each manual login, then goes dark.

## Fix — offline diagnostics mode (additive, live path unchanged)
Add `LivePaperTradingService(offline_diagnostics_mode: bool = False)`. When True, `start()`:
- SKIPS `fetch_live_tradable_universe` (no broker) — sets an empty tradable universe + empty cash
  universe (no live scanning, no live orders — legitimately needs a broker).
- Still opens the real experience memory, runs the writer loop, executes ALL daily safety/memory
  cadences (`_maybe_run_goal_integrity`, `_maybe_run_mechanistic_interpretability`,
  `_maybe_run_red_team`, `_maybe_run_ethics_law_review`, tripwires, incident post-mortem, constitutional
  audit, lab diagnostics, reflection), and `_publish`es — so **all feature surfaces + memory panels
  populate and update from stored data**.
`dashboard_server._start_live_paper_trading_service`: when no valid token, start the service in
`offline_diagnostics_mode=True` (with a benign no-broker placeholder) instead of returning None. A
small banner/status makes clear live trading is paused pending a token; the intelligence panels are live.

## Sourcing (Rule I / option-3 discipline — honestly recorded)
This is internal glue over existing project machinery — no external OSS applies. Reuses the existing
writer loop, cadence methods, `_publish`, and feature-surface registry; the only change is guarding
the universe fetch. `sourcing-oss-parts` is N/A (no third-party piece screens "run our own service
without our own broker"); the reuse-don't-reinvent principle is satisfied by reusing our own loop.

## Verification (Rule F/N — the REAL check this time)
- Hermetic: construct the service `offline_diagnostics_mode=True`, `start()`, wait for a publish,
  assert `published_snapshot().feature_surfaces` is non-empty and `memory_experiment_count > 0`.
- **Real page-load (the step previously skipped):** restart the dashboard with no token, `curl
  /api/snapshot` → assert `feature_surfaces` length == manifest size AND populated (not all
  "gathering"), `memory_experiment_count == 334`; `curl /` 200 and the feature-coverage panel renders.

## Follow-ups (Rule K)
- 🔵 Full **stored-universe** offline mode (assemble a real tradable universe from stored bhavcopy via
  `point_in_time_universe_resolver`) so even replay TRADING runs without a token — heavier; the
  diagnostics-panel visibility fix ships first.
- 🔵 A structural guard (Stop-hook/checklist): dashboard code changed ⇒ the live page must be loaded
  and surfaces confirmed, not just the coverage-audit test — so Rule-N can't be satisfied by a proxy again.
