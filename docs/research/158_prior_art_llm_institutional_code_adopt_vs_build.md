# research/158 — Prior art: LLM → institutional-grade code + idea→spec. Adopt-vs-build synthesis

Consolidates four real research sweeps (2026-07-26; full source docs in this folder:
`llm_production_grade_code_prompting_techniques_2026.md`, `agentic_coding_workflows_claude_code_multiagent_2026.md`,
`llm_clarifying_questions_and_prompt_amplification_techniques_2026.md`, + a direct fetch of GitHub
Spec-Kit) into a decision: for each problem, ADOPT proven prior art or BUILD our own. Purpose: make the
"any idea → institutional-grade code" pipeline rest on evidence, not invention.

## The evidence, distilled (what actually works — convergent across ≥2 independent sweeps)
1. **Depth is a MECHANISM problem, not a wording problem.** Shallow code is structural (RL "looks-solved"
   reward-hacking — METR; long-gen context-rot — Chroma). No prompt phrase reliably fixes it.
2. **#1 lever = an externally VERIFIABLE completion gate** the model must pass (tests/build/real-data),
   not a prose ban. (Anthropic "trust-then-verify"; C-compiler case study; METR.) → we already have this
   (Rule F + verify scripts); it must become a HARD gate, not advisory.
3. **Execution-GROUNDED self-critique / reviewer pass in a fresh context helps; PURE text self-critique
   plateaus or HURTS** (Reflexion 91% vs 80% WITH test feedback; arXiv:2310.01798 counter-evidence). →
   add a reviewer step that RUNS things, not one that just re-reads.
4. **Static-analysis correction loops** cut defects 40-80% → ~12% over rounds (arXiv:2508.14419). →
   adopt lint/type-check as a gate.
5. **Property-based testing** for edge coverage beyond example tests. → adopt (Hypothesis).
6. **Rules files decay with bloat** — the one measured cross-tool finding (Claude Code + Cursor + Aider
   docs all say lean/pruned); **hooks are the only DETERMINISTIC enforcement; CLAUDE.md is advisory and
   ignored under load.** → our Rules A–P file is now too long; SLIM it + move HARD rules to HOOKS.
7. **Forced, STRUCTURED (multiple-choice) clarification beats open-ended, capped at 2–5 questions**
   (arXiv:2602.04210 +54% alignment; arXiv:2605.25284 — models won't self-initiate). → adopt
   `AskUserQuestion`-style MCQ elicitation; separate clarify from plan.
8. **Spec-driven, phase-gated artifacts** (Spec-Kit: constitution→specify→clarify→plan→analyze→tasks→
   implement→converge) — each phase's artifact gates the next. → we already do most of it; add the
   forced CLARIFY + an ANALYZE (cross-artifact consistency) + CONVERGE (post-build gap check).
9. **Multi-agent is NOT inherently better** — single-agent-with-tools dominates SWE-bench; multi-agent
   costs 2-10× tokens + risks globally-incompatible parallel output. It DOES help as (a) parallel
   decomposition + per-unit verification for large scale (only demonstrated 100k-LOC path), and (b)
   fresh-context REVIEWER ensembles (different reviewers catch non-overlapping bugs). → use judiciously.
10. **Overhyped / avoid:** "senior engineer" role-prompting (EMNLP 2024 debunk), PromptPerfect & most
    "prompt-expander" toys (no evidence), naive CoT on code (can degrade), pure self-refine w/o a verifier,
    Kiro/OpenSpec "spec-driven" branding (free-text, not a real wizard), SWE-bench score as quality proof
    (contaminated), and **LOC-as-a-target** (depth is a symptom, never a goal).

## Adopt-vs-build decision (per problem)
| Need | Verdict | Action |
|---|---|---|
| Idea → institutional SPEC (Q&A + choices) | **ADOPT + adapt** | Spec-Kit's phase-gate + `AskUserQuestion` forced MCQ clarify (2-5 Qs), separate from plan. Fold into a lean skill; reuse our existing design-doc as the spec artifact. |
| Verifiable completion gate | **HAVE → HARDEN** | Rule F + verify scripts already exist; make "real-data verify ran + passed" a HOOK-enforced gate, not advisory. |
| Execution-grounded reviewer pass | **BUILD (small)** | A fresh-context reviewer sub-step that RUNS tests/lint and adversarially checks — after build, before sign-off. |
| Static-analysis loop | **ADOPT** | `ruff` + `mypy` as a gate/hook in the build loop. |
| Property-based tests | **ADOPT** | `hypothesis` — invariants for numeric/engine code (complements example tests). |
| Lean rules + deterministic enforcement | **RESTRUCTURE** | Slim CLAUDE.md to short imperative rules; move HARD requirements (real-data marker, map fidelity, dashboard surface, test-pass) into HOOKS; detail lives in SKILLS. |
| Large-scale build | **HAVE → use judiciously** | Workflow multi-agent for genuine decomposition + per-unit verify + reviewer ensembles; default to single-agent+tools+execution-loop otherwise. |
| Prompt amplification | **MINIMAL** | Skip PromptPerfect-class tools; the spec doc IS the amplified prompt. (TextGrad/PromptWizard only if we later add a scored optimizer loop.) |

## Spec-driven tools — the hard caveat (from the 4th sweep, research/158b)
No flagship spec-driven tool (Spec-Kit/Kiro/Tessl/BMAD/OpenSpec) has a rigorous benchmark beating
skilled direct prompting; claims are vendor anecdotes. Real NEGATIVE evidence: a Kiro production outage +
**CVE-2026-10591** (prompt-injection bypassing its approval gate), and Tessl's "spec-as-source" being
non-deterministic ("a prompt with extra steps"). **The single most consistent complaint across ALL of
them is OVER-GENERATION of markdown ceremony** (Spec-Kit: 47 tasks for 3 stories, no tests, app didn't
run). Direct lessons for us: (1) our own doc-per-slice habit risks the same ceremony bloat — keep
artifacts LEAN + SKIP ceremony for small changes; (2) never trust "spec-driven" branding as a proxy for
quality/safety — only the verifiable gate is real; (3) approval gates themselves can be attacked → the
verifiable check must be robust. Only Aider's architect/editor split has a rigorous number (+10.3pp, but
stale). Net: our spine is fine; the wins are the mechanisms below — applied WITHOUT ceremony bloat.

## Honest conclusion
We do NOT need to invent a new prompt framework — the field's evidence says our existing spine (rules +
design docs + real-data verification + Rule K tasks) is already the right shape, and matches Spec-Kit.
The high-value UPGRADES are all evidence-backed and mostly ADOPTION, not invention:
1. **Slim CLAUDE.md + convert hard rules to HOOKS** (fixes the measured bloat-decay problem).
2. **Add a forced STRUCTURED-MCQ clarify step** (idea→spec skill) — your Idea 2, in its evidence-backed form.
3. **Add execution-grounded gates**: static analysis (ruff/mypy), property tests (hypothesis), a
   fresh-context reviewer pass — these are the proven depth levers.
4. Keep Rule P's engine standard; keep multi-agent for decomposition/review only.
This is the pipeline that turns any idea into institutional-grade code, grounded in what's actually proven.
