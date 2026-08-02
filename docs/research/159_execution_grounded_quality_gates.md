# research/159 — Execution-grounded quality gates (evidence-backed depth levers, item "c")

**Purpose:** add the PROVEN, execution-grounded quality mechanisms (research/158) to the build loop —
static analysis, property-based tests, and a fresh-context reviewer pass — so future engine builds are
verifiably deep, not prose-deep. These are the levers the evidence ranked highest (static-analysis loops
cut defects 40-80%→~12%; property tests find edge bugs example tests miss; execution-grounded review
helps where pure self-critique hurts).

## Sourcing (Rule I / P.3) — integrate the standard tools, verified installed
- **ruff 0.16** (astral-sh/ruff) — CHOSEN: the modern Rust-fast linter that subsumes flake8/isort/pyflakes/
  pycodestyle/bugbear in one tool; considered flake8+plugins (slower, fragmented) + pylint (slow) → rejected.
- **mypy 2.3** — CHOSEN reference static type checker; pyright considered (Node dep, editor-oriented) → mypy fits a Python CLI gate.
- **hypothesis 6.16** — CHOSEN: the de-facto Python property-based-testing library (no real alternative).
All three pip-installed + version-verified. No bespoke reimplementation (these ARE the real tools).

## Components
1. **Static-analysis gate** — `ruff` (lint + bug patterns) + `mypy` (types) via `scripts/quality_gate.py`.
   Scoped to TARGET paths (the code being built) by default, with a `--full` repo option — so it applies
   rigor to new engines without demanding a boil-the-ocean cleanup of 233 pre-existing modules (which
   would just add noise + get ignored — the bloat-decay failure mode). ruff configured to a solid,
   pragmatic ruleset; mypy in a lenient-but-real mode (catches real type errors, not annotation zealotry).
2. **Property-based tests** — `hypothesis`: invariants for numeric/engine code (e.g. calibrated
   probabilities ∈ [0,1]; size multipliers ∈ [floor,1] + monotone; Kelly sign; utility decomposition
   sums to total; arbitration Pareto-consistency). Complements example tests (edge coverage).
3. **Fresh-context reviewer pass** — a documented build step: after an engine is built + its own tests
   pass, a FRESH-CONTEXT reviewer (a subagent, or a clean re-read) RUNS `quality_gate.py` + the real-data
   verify + adversarially checks the Rule-P checklist, and reports defects. Execution-grounded (it runs
   things), because pure text self-critique plateaus/hurts (research/158). Wired into the engine skill.

## `scripts/quality_gate.py` contract
`python scripts/quality_gate.py [paths...] [--full] [--no-tests]` → runs ruff → mypy → pytest (targeted
or full), prints a consolidated PASS/FAIL with per-tool findings + counts; non-zero exit on failure so it
can back a hook (item "a") and a CI step. Errors surfaced, never swallowed (Rule O.3).

## Config (pyproject.toml)
- `[tool.ruff]` — target py312, a curated rule set (pyflakes/pycodestyle/bugbear/comprehensions/simplify),
  line-length aligned to the codebase, per-file ignores for tests.
- `[tool.mypy]` — pragmatic: `ignore_missing_imports`, no `disallow_untyped_defs` globally (would drown in
  the existing 233 modules); real error checking on targeted engine modules.

## Verification (Rule F)
Run the gate on the just-built win-probability engine (`predictive_core/win_probability_*`) — fix what it
flags — and add + run the new property tests. Show real gate output (ruff/mypy/pytest pass) by eye.

## Rule K
Baseline the pre-existing repo-wide lint/type debt as a tracked follow-up (don't block new work on it);
the gate defaults to targeted scope so new engines are clean while the debt is paid down incrementally.
The reviewer-pass automation (a standing reviewer subagent) is wired via the engine skill in item "a/b".
