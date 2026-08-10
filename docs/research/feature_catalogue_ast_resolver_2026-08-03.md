# SPEC — Feature-Catalogue AST resolver + live freshness (Rule R hardening)

**Rev:** 2026-08-03 · closes the 4 open items on the Feature Catalogue (`docs/BACKLOG.md`).

## Problem
The first prober resolved a row→module by a cited-path/name heuristic over the note text. That left 38
rows `unverified`, could not tell wired code from an orphan (Rule G), missed 3 atlas branches whose code
exists but whose tracker prose is stale, and had no freshness mechanism for new modules.

## Fix (one engine: `feature_catalogue_ast_resolver.py`)
1. **Real import graph** — `ast`-parse every `src/nse_algo_trader/**.py`; edges = internal imports (incl.
   package `__init__` re-exports). Same ground truth as the SYSTEM_MAP extractor (Rule H).
2. **Reachability / orphan detection (Rule G)** — BFS from the real runnable entry points
   (`dashboard_server`, `live_universe_paper_loop`, the ingestion/backfill/token cron jobs,
   `autopoiesis_orchestrator`, `config_enforced_paper_run`). A module reached = wired; never reached =
   `orphan`. Wiring becomes a measured status, not a guess.
3. **Row→module resolution** — (a) explicit `pkg/module` path in the note/sources, (b) module-stem token
   in the text, (c) feature-name tokens → best module-stem match. Returns module + present + reachable.
4. **Live auto-discovery (freshness, #4)** — any real non-test, non-`__init__` module referenced by NO
   catalogue row is surfaced as an auto-discovered row ("Undocumented modules" section), so new code
   appears on the board the moment it lands — the catalogue can never silently fall behind the code again.
   Status is still measured live on every request; this closes the authored-set staleness gap.

## Reconciliation
- **#2 unverified** — the AST resolver resolves by real import presence, not note prose → the genuinely-
  built rows flip to `built`; any that remain `unverified` are truly code-absent and stay surfaced.
- **#3 atlas 84 vs 87** — the 3 branches (world-model planning, curiosity-engine components) whose modules
  exist resolve to real modules → measured `built`; code wins over stale 🔴 prose (Rule R).

## Acceptance
- [ ] Import graph built from real AST; entry-reachability computed; orphans flagged.
- [ ] Unverified count drops (only true code-absent rows remain); atlas built count reconciles up.
- [ ] Undocumented real modules auto-surface; page shows an orphan/undocumented signal.
- [ ] Live-verified + screenshot; ruff+mypy clean; SYSTEM_MAP + BACKLOG updated.

## Sourcing
No new OSS — Python stdlib `ast`/`os` only, same approach as the in-repo SYSTEM_MAP extractor.
