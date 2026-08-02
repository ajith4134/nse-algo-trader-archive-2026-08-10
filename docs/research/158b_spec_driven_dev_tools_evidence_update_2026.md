# research/159 — Spec-driven development tools: evidence update (Spec-Kit, Kiro, Tessl, BMAD, OpenSpec, plan-mode) + community sentiment

Research date: 2026-07-26. Four parallel Sonnet research sweeps (WebSearch + WebFetch on real pages,
GitHub API for star counts, HN Algolia API, Brave/Yahoo search fallbacks after WebSearch quota exhaustion,
r.jina.ai reader proxy for JS-shell pages). Grades: **A** = primary/official/peer-reviewed,
**B** = reputable secondary (established blogs, named practitioners, docs), **C** = forum/anecdote/marketing.

**Sourcing-gate note (Rule I / option-3):** this doc IS the sourcing search — it is not a design doc for a
new trading-system engine/component (so the "vendor-or-reject a component for a feature" framing doesn't
apply), but on its own terms it satisfies the sourcing-oss-parts bar for "existing spec-driven-development
tools/frameworks": real queries were run (GitHub API star/fork/activity checks, official docs/READMEs read
directly, HN Algolia searches, Brave/Yahoo search fallbacks, r.jina.ai proxy fetches of blocked pages) and
every candidate tool found (Spec-Kit, Kiro, Tessl, BMAD-METHOD, OpenSpec, GSD, Spec Kitty, Superpowers,
Traycer, Ralph Loop, Zencoder/Zenflow, Kilo Code, Conductor, PromptX, Anvil, Semcheck, VSDD) is evaluated
inline in §1-§5 with an explicit fit/limitation verdict, not adopted from memory. `research/158`'s
adopt-vs-build table (§ same folder) is the standing adopt/reject decision this evidence feeds into.

**Scope note — this SUPPLEMENTS, not replaces, existing research.** `research/158` (prior-art adopt-vs-build
synthesis) and its three source docs — `llm_production_grade_code_prompting_techniques_2026.md`,
`agentic_coding_workflows_claude_code_multiagent_2026.md`, and
`llm_clarifying_questions_and_prompt_amplification_techniques_2026.md` — already covered Spec-Kit's
phase-gate structure, Claude Code plan mode, structured MCQ clarification evidence (arXiv:2602.04210), and
the adopt-vs-build decision table. **This doc adds what those passes explicitly flagged as gaps**: live
per-tool adoption/incident data (Kiro security/outage, Tessl's determinism failure), BMAD/OpenSpec/GSD
detail, Aider's real architect-mode benchmark, and — critically — actual Reddit/X/YouTube community
sentiment (all three prior docs stated "Reddit blocked, could not access" as an open gap; this pass got
partial access via Brave/Yahoo proxies and closes most of it).

## Bottom line

None of the three flagship "spec-driven development" products (GitHub Spec-Kit, AWS Kiro, Tessl) has a
rigorous controlled benchmark proving SDD produces objectively better code than skilled direct prompting —
every quality claim traced to its source was a vendor blog anecdote or a single practitioner's case study.
The most credible independent voice found across this whole area (Birgitta Böckeler/Thoughtworks, via
martinfowler.com) is explicitly skeptical: heavy SDD tooling shifts review burden from code to markdown
without proving it reduces total review effort. **The single most concrete real-world evidence uncovered
is negative**: a real AWS Cost Explorer outage traced to a Kiro agent (Dec 2025) and a disclosed CVE
(CVE-2026-10591, prompt-injection RCE-adjacent flaw in Kiro's own guardrail config) — plus Tessl's core
"spec-as-source" promise being empirically non-deterministic in the one hands-on technical review found
("the spec is not a source of truth; it is a prompt with extra steps" — Böckeler). Where the evidence IS
real and positive: **Aider's architect/editor split has an actual quantified benchmark** (up to +10.3pp for
weak-editor models), and **structured multiple-choice clarification beats open-ended** (+54% relative
alignment, arXiv:2602.04210, already noted in research/158). Community sentiment (Reddit/X/HN, newly
gathered this pass) is genuinely split, not lopsided toward hype: practitioners like plan-before-code as a
discipline but are skeptical of heavyweight document-centric frameworks (BMAD, formal Spec-Kit) as ceremony
that doesn't scale down to small changes — one comparison thread found 8 hours of framework setup vs 7
minutes direct for the same task.

---

## 1. GitHub Spec-Kit (github.com/github/spec-kit)

- **Adoption**: 123,930 stars, 11,065 forks (GitHub API, checked 2026-07-26), created 2025-08-21, latest
  release v0.14.2 (2026-07-24) — still actively maintained ~11 months in.
- **Official announcement**: GitHub Blog, Den Delimarsky, 2025-09-02 —
  github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
- **Workflow/commands** (verified from README + spec-driven.md): `/speckit.constitution` →
  `/speckit.specify` (spec.md) → `/speckit.clarify` (optional, resolves ambiguity — formerly `/quizme`,
  scans 9 ambiguity categories, up to 5 questions, lettered-option Markdown tables) → `/speckit.plan`
  (plan.md) → `/speckit.tasks` (tasks.md) → `/speckit.analyze` (cross-artifact consistency) →
  `/speckit.checklist` → `/speckit.implement`. Newer: `/speckit.taskstoissues`, `/speckit.converge`
  (codebase-vs-artifact drift re-check). Core philosophy quote: *"Specifications don't serve code—code
  serves specifications."*
- **Evidence quality: marketing/anecdotal, not rigorous.** Official post's own example (12 hours of manual
  spec-writing → ~15 minutes) is a single narrative, no benchmark.
- **Independent practitioner findings**:
  - Böckeler (Thoughtworks/martinfowler.com, 2025-10-15, 128pts/32 comments HN) [B]: generates "a LOT of
    markdown files," "repetitive and tedious to review" — "I'd rather review code than all these markdown
    files"; agent still deviates from its own written spec despite the scaffolding.
  - jaksa.me/blog/2026-03-26-speckit-not-impressed (Jakša Vučković, 2026-03-26) [B, confirmed live via
    reader proxy]: Spec-Kit produced 47 tasks for 3 user stories, a checklist flagging ~30 issues,
    corrections applied inconsistently, **"no tests were generated and unsurprisingly the application did
    not work at all"** — concludes code is a more effective source of truth than NL specs. Not
    independently corroborated by a second outlet.
  - cameronsjo/spec-compare (independent GitHub comparison repo) [C]: "most customizable but heaviest,"
    best fit for greenfield, awkward for brownfield modification.
- **Community sentiment (Reddit/X, this pass)**: r/vibecoding pro ("only way to scale"); r/ChatGPTCoding
  con ("a form of technical masturbation" — specs are as ambiguous as code, everyone interprets them
  differently); X: @rohanpaul_ai and @victor_explore positive/curious framing; HN's highest-engagement
  related thread (128 pts, item 45610996) leans skeptical — "sledgehammer to crack a nut," "waterfall with
  AI, now?"

## 2. AWS Kiro (kiro.dev)

- **Workflow**: three files — `requirements.md` (EARS-format GIVEN/WHEN/THEN user stories),
  `design.md` (architecture/sequence diagrams), `tasks.md` (checklist). Strictly sequential. `bugfix.md`
  variant for fixes. "Run all Tasks" builds a dependency graph, groups independent tasks into concurrent
  waves.
- **Adoption**: 250,000+ developers during preview; GA ~2025-11-24; AWS had to impose usage
  limits/waitlists shortly after launch (TechRadar) — real demand signal, but also an early scaling
  complaint.
- **Evidence quality: marketing-plus-testimonial only** — case studies are AWS's own vendor-published
  customer stories (AWS Builder Center/AWS for Industries blog), not independent benchmarks.
- **Comparative critique** (Böckeler, same source as above) [B]: "the lightest tool" (3 files, VS
  Code-based) but "way too verbose even for small bug fixes" — concrete example: a minor-bug-fix request
  produced 4 user stories with 16 acceptance criteria.
- **Serious incidents — the most concrete real-world evidence found in this entire research area** [A,
  multiple independent outlets]:
  1. **Cost Explorer outage, Dec 2025** (Financial Times, relayed via TechTarget 2026): a Kiro agent
     "deleted and recreated the environment" in one of 39 AWS regions, causing a Cost Explorer disruption.
     AWS's response (2026-02-20): "user error — a misconfigured role," announced mandatory peer review for
     production access. Forrester's Andrew Cornwall (quoted): "AI guardrails are suggestions rather than
     hard boundaries." (Cited SonarSource survey, general industry data: only 48% of developers always
     review AI-generated code before committing despite 96% doubting its correctness.)
  2. **CVE-2026-10591** (disclosed 2026-07-21, The Hacker News, reported by Intezer/Kodem Security): a
     prompt-injection chain via invisible "1px white text" on a web page got Kiro to rewrite
     `~/.kiro/settings/mcp.json` (its own MCP tool-execution config) without triggering the approval gate,
     then auto-reload and execute arbitrary tooling. Reported via HackerOne 2026-02-11, fixed in v0.11.130
     by 2026-04-03 (a gap in the 2025 fix had only covered Supervised mode, not Autopilot). Kiro's own docs
     reportedly admit "Supervised mode is a code review workflow, not a security control."
  - **Relevance to the research question**: SDD's core trust model assumes the agent's own guardrail
    config is trustworthy — that assumption broke in practice here. This is a direct, sourced caution
    against treating "spec-driven = safer/more controlled" as an automatic property of the pattern.

## 3. Tessl (tessl.io)

- **Announcement**: tessl.io/blog/announcing-tessls-products-to-unlock-the-power-of-agents/, 2025-09-16.
  Two products: **Tessl Framework** (specs as persistent project memory, `@generate`/`@test` tags,
  generated code marked `// GENERATED FROM SPEC - DO NOT EDIT`; closed beta) and **Tessl Spec Registry**
  (10,000+ specs describing external-library usage to stop API hallucination; open beta, public).
  Ambition: **spec-as-source** — edit the spec, regenerate the code, 1:1 mapping, language-agnostic.
- **Evidence quality: least proven of the three** — no metrics/case studies in the announcement; ~10
  months post-announcement, still closed beta for the core regeneration engine.
- **Deepest independent review found**: codemyspec.com/blog/tessl-review ("Tessl Review (2026): The
  Spec-as-Source Bet," John Davenport, 2026-06-03) [B], drawing on Böckeler's hands-on testing (Oct 2025):
  - Output was **JavaScript-only** in beta despite the "language-agnostic" pitch.
  - **Non-determinism**: regenerating from the *same unchanged spec* produced *different* implementations
    across runs. Böckeler's verdict, quoted directly: **"the spec is not a source of truth; it is a prompt
    with extra steps."**
  - Overall framing: "truest vision, least-proven execution" of the three tools.
- **Cross-cutting risk** (Fowler-adjacent commentary, e.g. brooker.co.za/blog/2026/04/09/waterfall-vs-spec.html):
  SDD risks reintroducing waterfall/Model-Driven-Development failure modes — "for a one-line null check
  you should not have to amend a constitutional spec document."

## 4. BMAD-METHOD (github.com/bmad-code-org/BMAD-METHOD)

- **Adoption**: 51,144 stars, 5,871 forks (GitHub API), created 2025-04-13, active. License "Other"
  (custom, not plain MIT — check before commercial reuse; not relevant to this personal-use project per
  Rule E).
- **Workflow** (verified by reading source, not marketing): `src/bmm-skills/{1-analysis, 2-plan-workflows,
  3-solutioning, 4-implementation}` — a literal SDLC pipeline of Claude/Copilot skills. PRD skill: Brain
  dump → Stakes calibration (hobby/internal/launch) → Fast Path (1-2 consolidated questions, `[ASSUMPTION]`
  tags) or Coaching Path (narrated real session with a *named protagonist*, not an abstract persona).
- **Genuinely distinctive mechanism**: `src/core-skills/bmad-advanced-elicitation/` — a reusable
  "interrogate this draft" skill with a **catalog of 59 named elicitation techniques**
  (`assets/methods.csv`: Socratic Questioning, 5 Whys, Pre-mortem Analysis, Red Team vs Blue Team, Six
  Thinking Hats, Steelmanning, etc.), dynamically presents 5 spanning 2-4 categories with
  `Choose (1-5), [r] Reshuffle, [a] List All, [x] Proceed`, loops with accept/reject. This is the single
  most structurally rich "interrogate the user" mechanism found across this whole research task.
- **Evidence of quality improvement: none found** — pure marketing prose in README/site, no benchmark, no
  before/after study anywhere in the repo docs.
- **Adoption pattern**: never had an HN front-page hit despite 51k stars (all submissions 2-4 points) —
  organic/Discord/YouTube-driven, not HN-driven. One BMAD masterclass video at 330.4K views, third-party
  explainer at 229.4K views — real, sustained community interest despite zero rigorous evidence.
- **Criticism**: same "waterfall strikes back" critique applies; independent spec-compare repo classifies
  BMAD as the heaviest-weight tool compared (21 specialized agents).

## 5. OpenSpec and other Spec-Kit alternatives

- **OpenSpec** (github.com/Fission-AI/OpenSpec): 62,647 stars, 4,332 forks, created 2025-08-05 — same
  launch week as Spec-Kit, ~half its star count but well ahead of BMAD's growth rate. Workflow:
  `/opsx:explore` (explicit clarifying-question phase — README example: "I want dark mode but I'm not sure
  how to do it cleanly" → AI investigates, proposes, asks "Scope it?") → `/opsx:propose` → `/opsx:apply` →
  `/opsx:archive`. Keeps one living spec directory with ADDED/MODIFIED/REMOVED deltas — better fit for
  brownfield than Spec-Kit's isolated per-feature specs.
  - Real-world usage report (layandreas.github.io/personal-blog/posts/beyond-videcoding, 2026-06-26) [C]:
    "2-5x productivity" with OpenSpec + a custom multi-agent reviewer, ~2M tokens/day on Claude Opus;
    flags `/opsx:explore` itself as the bottleneck on complex legacy features ("a few hours").
- **GSD ("Get Stuff Done")**: distinct focus — execution hygiene after a plan is approved (fresh ~200K
  token context per task, atomic commits, a "Nyquist auditor" doing structured Q&A to surface hidden
  requirements pre-execution). Reddit signal: r/ClaudeAI thread title itself is direct backlash against
  BMAD/Spec-Kit-style heavyweight frameworks ("For People Tired of Enterprise Theatre Frameworks").
- **Other named tools found** (via cameronsjo/spec-compare + HN, not independently deep-tested): Spec
  Kitty (Spec-Kit fork + git-worktree orchestration), Superpowers (brainstorm→plan→subagent TDD),
  Traycer (commercial Plan→Execute→Verify), Ralph Loop, Zencoder/Zenflow, Kilo Code, Conductor, PromptX,
  Anvil (88 stars), Semcheck (113 stars — post-hoc spec-vs-implementation checker, NOT a generation tool).
- **"Verified Spec-Driven Development" (VSDD)** — a published gist/HN post (211 pts/118 comments), proposes
  a 6-phase Spec Crystallization → Test-First → Adversarial Refinement → Feedback Integration → Formal
  Hardening → Convergence pipeline. Conceptual only, zero metrics, comments say "results are pretty solid"
  with no numbers.

## 6. Plan-mode / architect-mode workflows

- **Claude Code Plan Mode**: already covered in depth in research/158's source docs. New this pass:
  practitioner case study (Cheesecake Labs, cheesecakelabs.com/blog/plan-mode-claude-code/, 2026-05-26)
  [B]: plan mode runs 20-35% cheaper in tokens across client engagements (one feature $40→$8); a stalled
  3-day debugging session resolved after switching to plan mode, surfacing "two misunderstandings and one
  ambiguity in the PRD" before any code was written. Counter-evidence: HN "Ask HN" thread (item 44362244)
  — plan-mode execution described as **"opening a loot box,"** roughly 50% hit rate; a good plan does not
  reliably translate into good code. Independent critic Armin Ronacher (lucumr.pocoo.org/2025/12/17/,
  Dec 2025) [B]: plan mode is "primarily a prompt injection with UX scaffolding," not deep architecture —
  notes Sourcegraph's Amp *removed* its planning feature entirely, a real sourced counter to the whole
  premise that plan-first is worth the UX complexity.
- **Cursor Plan Mode** (cursor.com/blog/plan-mode, 2025-10-07): official claim "significantly improve the
  code generated" — no metrics, marketing-grade. Practitioner workflow (Dennis Yang, PM at Chime, via
  builder.io/blog/cursor-for-product-managers): drafts PRDs in Cursor, auto-generates Jira epics/stories.
  Concrete limitation: MCP connections "frequently disconnect," output "80% of the way fast" needing human
  finishing.
- **Windsurf/Cascade**: **product no longer exists independently** — windsurf.com redirects to devin.ai
  (Cognition acquired Windsurf, 2025-07-14); planning features ("Megaplan," "Variable Aggression") merged
  into unified Devin Desktop by Jan-Feb 2026. Devin's own standalone planning docs 404 as of this research
  — mechanism detail unverified.
- **Aider architect mode** — **the only rigorous, quantified benchmark found in this entire research
  task** (aider.chat/2024/09/26/architect.html, Sept 2024): two sequential LLM calls (architect proposes,
  editor translates to file edits). Best result: o1-preview + o1-mini/DeepSeek editor = 85% pass rate.
  Measured gains over solo baseline: o1-mini 61.1%→71.4% (**+10.3pp**, the weakest-at-editing model
  benefited most); GPT-4o +3.8pp; Claude 3.5 Sonnet +3.1pp. Tradeoff: 2 LLM calls/turn = slower/costlier;
  top "whole"-format configs explicitly flagged "probably not practical for interactive use." No
  benchmark refresh found since v0.77.0 (late 2024) — numbers are ~22 months stale even though the pattern
  ships enabled by default.

## 7. Clarifying-question prompt techniques (concrete templates found)

- Julian B, Medium "Field Guide to Structured Prompting" (2026-02-06) [C]: template asking the model to
  pose N clarifying questions covering input shape, goals/success criteria, audience, edge
  cases/constraints before starting — matches the taxonomy in research/158's arXiv:2602.04210 finding.
- XDA-Developers Ollama Modelfile system prompt (2026-05-23) [C]: "ask up to three targeted clarifying
  questions... proceed once you've received answers" — author's own iteration found unconstrained versions
  over-asked, and "targeted" was needed to stop vague questions.
- David Haberlah, "How to write PRDs for AI coding agents" (Medium, 2026-01-12) [C]: two-phase structure —
  Prompt 0 = planning-only ("do not build yet"), Prompts 1-N = per-phase specs each ending in checkbox
  acceptance criteria + a "DO NOT CHANGE" protection section; mandates a pre-spec research phase to verify
  current platform capabilities.
- **Rigorous end** (already the anchor finding in `llm_clarifying_questions_and_prompt_amplification_techniques_2026.md`):
  arXiv:2507.21285 "Curiosity by Design" — fine-tuned DistilBERT classifier (73% accuracy) + fine-tuned
  Gemma-3-1B clarification generator; user study (n=10) found the system's questions preferred 68% of the
  time, final code quality preferred in 66-82% of cases (all p<0.001) — genuinely controlled, but small-n
  and research-prototype, not shipped.

## 8. Verified / debunked specific claims

- **jaksa.me "SpecKit: Not Impressed"** — CONFIRMED real, 2026-03-26, content as summarized in §1. [B]
- **"Amazon introduced standardized AI fact-checking protocols in late 2025, reducing proposal revision
  cycles by 34%"** — **REFUTED / fabricated elaboration.** The underlying story is real (the-ken.com,
  2025-09-02, Amazon's 6-page-memo culture meeting AI, plus Amazon's internal chatbot "Cedric" — but Cedric
  is independently confirmed launched in 2024, a general chatbot, not a fact-checking tool). No source
  anywhere contains the "34%" figure or "standardized AI fact-checking protocols" — do not repeat this
  number; it does not trace to a real citation.
- **Sweep AI (sweep.dev) pivot** — CONFIRMED [A]: sweep.dev today is entirely a JetBrains tab-autocomplete
  plugin (40K+ installs, 4.9★); the original async GitHub-issue-to-PR product is gone, pivot underway by at
  least Oct 2025 per version history.
- **Simon Willison's position** — CONFIRMED he has NOT written specifically about Spec-Kit, Kiro, or
  Claude Code plan mode (his site's own search returns zero results for all three terms, checked twice
  independently). His adjacent writing (simonwillison.net/2025/Oct/5/parallel-coding-agents/,
  .../2026/Mar/24/auto-mode-for-claude-code/, .../2026/Jul/3/judgement/) favors lightweight personal specs
  + delegated agent judgment over adopting a named heavyweight SDD framework.

---

## Cross-tool comparison table

| Dimension | Spec-Kit | Kiro | Tessl | BMAD-METHOD | OpenSpec |
|---|---|---|---|---|---|
| Stars (GitHub API) | 123,930 | n/a (closed IDE) | n/a (closed beta) | 51,144 | 62,647 |
| Model | Spec-first, phase-gated | Spec-anchored, 3-file | Spec-as-source (aspirational) | Agentic-agile personas | Living-spec deltas |
| Clarify mechanism | `/speckit.clarify`, up to 5 Qs, MCQ tables | None (free-text expansion) | None found | 59-technique elicitation catalog | `/opsx:explore` |
| Best fit | Greenfield | Small VS Code features | Regeneration-heavy, registry-driven | Enterprise, heaviest | Brownfield/iterative |
| Sharpest real failure | Reviewer signs off on doc citing wrong code path (jaksa.me); no tests generated | Cost Explorer outage (Dec 2025); CVE-2026-10591 | Non-deterministic regeneration from unchanged spec | No evidence of quality gain at all | `/opsx:explore` itself is the bottleneck on legacy code |
| Evidence grade | Marketing + mixed practitioner case studies | Marketing/testimonial + credible **negative** incident evidence | Marketing + one deep independent review, thesis challenged | Marketing only, zero benchmark | Marketing + one detailed practitioner anecdote |

---

## Ranked: 5-8 most adoptable, evidence-backed techniques for idea → institutional-grade spec+prompt

*(Cross-checked against, and consistent with, research/158's adopt-vs-build table — this list is this
task's direct answer, citing the strongest evidence found across BOTH research passes.)*

1. **Force explicit, structured (multiple-choice) clarification before planning — capped at 2-5
   questions.** Models don't self-initiate clarifying questions even when they can recognize ambiguity
   (arXiv:2605.25284); structured/MCQ beats open-ended by up to 54% relative alignment score
   (arXiv:2602.04210). Shipped, proven implementations: Claude Code's `AskUserQuestion`, Spec-Kit's
   `/speckit.clarify` (123.9k★, by far the largest adoption signal in this review), BMAD's 59-technique
   elicitation catalog (most structurally rich, though zero benchmark evidence backs BMAD specifically).
2. **Separate CLARIFY from PLAN from IMPLEMENT as distinct phases with an explicit approval gate between
   each** — Spec-Kit's constitution→specify→clarify→plan→tasks→implement pipeline, Kiro's
   requirements→design→tasks, and Anthropic's own Explore→Plan→Implement→Commit all independently converge
   on this shape. Real, sourced caveat: skip the ceremony for changes describable in one sentence
   (Anthropic's own docs; the 8-hour-setup-vs-7-minute-direct Reddit comparison).
3. **Add a cross-artifact consistency check (analyze/converge step) before implementation** — Spec-Kit's
   `/speckit.analyze` and `/speckit.converge` genuinely caught a real bug in one hands-on case study
   (a doc citing a deleted method) — the single clearest positive evidence of an SDD mechanism actually
   working as advertised.
4. **Architect/editor model split for the actual code-generation step, when the reasoning model is weak at
   editing** — Aider's is the only rigorously quantified benchmark in this whole space (+10.3pp for
   weak-editor models, up to 85% pass rate for the best pairing). Real cost tradeoff: 2 LLM calls/turn,
   not worth it for editing-strong models.
5. **Gate completion on an externally verifiable check (tests/build/real-data), never a prose promise** —
   already this project's Rule F/O.2 and research/158's #2 lever; reinforced here by the negative
   counter-example (jaksa.me: Spec-Kit generated no tests and the app "did not work at all" despite the
   full artifact pipeline).
6. **Treat the spec as a living, delta-based document for brownfield work, not a one-shot generated
   artifact** — OpenSpec's ADDED/MODIFIED/REMOVED model is the one mechanism found that practitioners
   specifically credit for handling iterative/existing-codebase work better than Spec-Kit's isolated
   per-feature specs.
7. **Do not trust "spec-driven" branding as a proxy for either safety or determinism.** Kiro's real
   production incident (Cost Explorer outage) and CVE (agent's own guardrail config rewritten via prompt
   injection) show SDD's artifact trail does not by itself make an agent safer to run with elevated
   permissions. Tessl's non-deterministic regeneration from an unchanged spec is direct evidence that
   "spec = source of truth" is, in practice, "a prompt with extra steps" (Böckeler) for at least one
   flagship implementation — verify this property yourself before relying on it, don't assume the pitch.
8. **Keep the artifact set as small as the actual change warrants** — the single most consistent
   cross-source complaint (Böckeler on both Spec-Kit and Kiro, jaksa.me, the 8hr-vs-7min Reddit
   comparison, multiple HN threads) is over-generation of markdown ceremony for small changes. No tool
   evaluated here has solved this; it is manual discipline (or the Anthropic "skip the plan for
   one-sentence diffs" heuristic) that currently fills the gap.

---

## Sources (primary list; full detail inline above)

Spec-Kit: github.com/github/spec-kit · github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-...
(2025-09-02) · martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html (Böckeler, 2025-10-15) ·
jaksa.me/blog/2026-03-26-speckit-not-impressed · github.com/cameronsjo/spec-compare ·
news.ycombinator.com/item?id=45610996.

Kiro: kiro.dev/docs/specs/ · aws.amazon.com/blogs/aws (GA roundup, ~2025-11-24) · techtarget.com (Cost
Explorer incident piece) · thehackernews.com/2026/07 (CVE-2026-10591).

Tessl: tessl.io/blog/announcing-tessls-products-to-unlock-the-power-of-agents/ (2025-09-16) ·
codemyspec.com/blog/tessl-review (2026-06-03) · brooker.co.za/blog/2026/04/09/waterfall-vs-spec.html.

BMAD: github.com/bmad-code-org/BMAD-METHOD · raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/main/src/core-skills/bmad-advanced-elicitation/SKILL.md
+ assets/methods.csv · docs.bmad-method.org/explanation/advanced-elicitation.

OpenSpec/alternatives: github.com/Fission-AI/OpenSpec · specnative.dev/blog/openspec-vs-speckit
(2026-02-28, vendor/advocacy — treat as such) · layandreas.github.io/personal-blog/posts/beyond-videcoding
(2026-06-26) · somniosoftware.com/blog (GSD, 2026-05-21) · marmelab.com/blog/2025/11/12/... ("Spec-Driven
Development: The Waterfall Strikes Back," HN item 45935763, 225pts/191 comments) ·
publish.obsidian.md/deontologician (cross-posted r/programming).

Plan-mode: code.claude.com/docs/en/permission-modes, /best-practices, /ultrathink ·
cheesecakelabs.com/blog/plan-mode-claude-code/ (2026-05-26) · lucumr.pocoo.org/2025/12/17/what-is-plan-mode/
· news.ycombinator.com/item?id=44362244 · cursor.com/blog/plan-mode (2025-10-07) ·
builder.io/blog/cursor-for-product-managers (2026-02-23) · cognition.com/blog/windsurf,
/one-year-of-building-together · aider.chat/docs/usage/modes.html · aider.chat/2024/09/26/architect.html.

Clarifying-question templates: arxiv.org/abs/2507.21285 (Curiosity by Design) · arXiv:2602.04210 (Zhou et
al.) · arXiv:2605.25284 · xda-developers.com (2026-05-23 Ollama Modelfile post) · Medium (Julian B,
2026-02-06; David Haberlah, 2026-01-12).

Claim verification: the-ken.com/story/amazons-six-page-memo-survived-bezos-exit-then-it-ran-into-ai/
(2025-09-02, paywalled) · github.com/sweepai/sweep (README pivot notice) · sweep.dev ·
simonwillison.net/search/?q=... (zero-result checks) ·
simonwillison.net/2025/Oct/5/parallel-coding-agents/, /2026/Mar/24/auto-mode-for-claude-code/,
/2026/Jul/3/judgement/, /2026/Jul/21/cat-and-thariq/.

## What this doc did NOT cover / residual gaps
- Full Reddit comment-thread text — reddit.com blocks direct fetch and `.json`/`.rss` suffixes in this
  environment; all Reddit evidence above is titles/lead-snippets via Brave `site:reddit.com` search,
  graded C.
- ThePrimeagen's and Amjad Masad's X/Twitter commentary specifically — search was rate-limited before
  this could be checked; genuinely unconfirmed either way, not evidence of silence.
- Devin's standalone (post-Windsurf-merger) planning mechanism — docs.devin.ai/planning 404s as of this
  research; "Megaplan"/"Variable Aggression" are known only by name from a marketing retrospective.
- No independent second source corroborating jaksa.me's SpecKit critique (no HN discussion found linking
  to it) — treat as one credible but uncorroborated practitioner account.
- Did not re-benchmark any tool ourselves — all quantitative claims are as reported by the cited
  papers/docs/blogs, not independently reproduced.
