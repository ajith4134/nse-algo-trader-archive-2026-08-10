# research/160 — Slim CLAUDE.md + deterministic hook enforcement (item (a) of the c,a,b plan)

**Date:** 2026-07-26
**Depends on:** research/159 (execution-grounded quality gates — the evidence base).
**User directive:** "I go in your order c,a,b" — (a) = "slim CLAUDE.md + move hard rules to hooks."

## The problem (evidence, research/159)
1. **Rules-file bloat decays adherence.** A long always-present prose wall is followed *less*
   reliably than a short one — the model's attention over a 400-line rules blob degrades, and
   the marginal 15th rule dilutes the first 14. CLAUDE.md is **407 lines** (Rules A–P, each a
   multi-paragraph elaboration with examples). That length is itself an adherence risk.
2. **Prose ≠ enforcement.** A rule stated in prose is a *hope*; a rule checked by a hook is a
   *guarantee*. Research/159's #1 lever is **verifiable completion gates** — deterministic checks
   that mechanically block "done" until satisfied. Anything mechanically checkable should be a
   hook, not (only) a sentence.

## What is already hook-enforced (audit of ~/.claude/settings.json, 2026-07-26)
The infra is already strong — this item ADDS the one missing hard gate + slims the prose:
- **UserPromptSubmit** — injects a compact operational rule+skill checklist every turn (route to
  skill · design doc before build · acquire don't compromise · real-data/sim verify · wire in ·
  map update · no silent skips). This is the always-present *nudge*; keep it compact.
- **PostToolUse (Write|Edit)** — Rule H map-update reminder (throttled ≤1/15min) + sourcing-gate
  reminder on `docs/research/*.md`.
- **PreToolUse (Write|Edit)** — dataviz-skill gate on dashboard/chart code paths.
- **Stop (3 deterministic blocking gates)** —
  1. **Rule closeout** — blocks if `src/nse_algo_trader` changed but `SYSTEM_MAP.md` didn't.
  2. **Rule N live-page guard** — blocks if dashboard code changed but the live page wasn't
     re-verified (marker `/tmp/claude_dashboard_page_verified`).
  3. **Rule H.1 diagram fidelity** — runs `scripts/check_system_map_diagram_fidelity.py`, blocks
     on drift between the rendered §1 diagram and the code's real package graph.

## The gap → the change
**A1 — ADD a 4th Stop hook: the quality gate.** When `src/nse_algo_trader` changed this turn,
run `scripts/quality_gate.py --no-tests` (ruff + mypy on the default engine packages — fast, ~2-3s)
and **block** on failure. This deterministically prevents shipping the exact class of defect the
gate just caught (17 lint/type errors in news_sentiment). Tests stay a heavier explicit step (the
full suite runs in ~38s; the closeout prose still calls for it) — the hook enforces the fast,
always-cheap static half every turn. `--no-tests` keeps the Stop hook snappy so it never
discourages finishing.

**A2 — Preserve the FULL rules verbatim in `docs/RULES.md`.** Nothing is lost: the complete
current Rule A–P text (the authoritative elaboration, examples, pairings) moves to a reference doc
that is loaded on demand, not injected every turn.

**A3 — Rewrite CLAUDE.md SLIM (~40% of current).** Keep, at full fidelity:
- Project intro + Phase-1 scope + **the binding regulatory constraints** (these are legally
  binding — never abbreviate them) + the intraday/no-secrets non-negotiables.
- A **compact rules index**: each rule = a tight 2–4 line statement (WHAT it requires) + a tag
  saying **how it's enforced** — `[HOOK]` (deterministic) or `[JUDGMENT]` (prose/skill only) —
  and a pointer to `docs/RULES.md#rule-x` for the full text.
The essence of every rule stays *present and concise* in CLAUDE.md (so adherence doesn't drop for
the judgment rules), while the verbose multi-paragraph elaborations move out (so the bloat that
decays adherence is gone). This matches the evidence: it is the *length/verbosity* that decays
adherence, not the mere presence of a rule.

## Hookable vs judgment (the honest split)
**Mechanically enforceable → HOOK (guaranteed):**
- SYSTEM_MAP updated on src change (Rule H) — Stop hook ✅
- §1 diagram fidelity (Rule H.1) — Stop hook ✅
- Dashboard live-page verified (Rule N) — Stop hook ✅
- **Lint/type clean (Rule O.3/O.4 static half, Rule P tests) — Stop hook ← NEW (A1)**
- Design-doc-has-sourcing reminder (Rule I/D) — PostToolUse reminder ✅ (advisory, not a hard block)

**NOT mechanically enforceable → stays JUDGMENT (compact prose + skill):**
- Engine-grade DEPTH not skeletons (Rule P core) — a judgment call; `building-engine-grade-features`
  skill carries the method. (A crude LOC threshold would be breadth-theater; rejected.)
- Real-data-by-eye verification (Rule F) — needs a human/agent to inspect numbers.
- No-orphans reachability (Rule G) — partially checkable (import-graph) but brittle; keep prose.
- Segments-equal (L), license-blind (E), plan-altitude (M), production-grade judgment (O.1/O.2) —
  policy/judgment, stay concise prose.

## Risk & mitigation
- **Risk:** slimming drops adherence on judgment rules. **Mitigation:** keep every rule's essence
  (2–4 lines) in CLAUDE.md — concise, not absent; full text one click away in `docs/RULES.md`.
- **Risk:** editing `~/.claude/settings.json` (complex escaped-shell JSON) breaks existing hooks.
  **Mitigation:** append the 4th Stop hook only; validate the JSON parses + dry-run the new hook
  command before finishing.
- **Risk:** the quality-gate Stop hook blocks legitimately-incomplete turns. **Mitigation:** same
  escape valve as the other Stop gates — if intentionally deferred, log in BACKLOG; the gate is
  scoped to the 4 gate-clean packages so pre-existing debt in the other ~211 modules never trips it.

## Verification plan
1. JSON parses (`python -c json.load`).
2. New hook dry-run: with a clean tree it stays silent; with an injected ruff error it emits a
   `{"decision":"block",...}`.
3. CLAUDE.md still contains every rule letter A–P (grep) + the full regulatory block (no loss).
