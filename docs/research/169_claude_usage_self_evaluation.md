# 169 — Self-evaluation vs 4 Claude-Code tutorials (transcripts read 2026-08-03)

Source: 4 YouTube videos (Austin Marchese ch.), transcripts pulled via firecrawl (VPS IP was YouTube-banned;
firecrawl proxy bypassed it). Frames NOT obtained — video download stays cookie-gated; these are
talking-head/screencast tutorials so the transcript carries the full substance (on-screen prompts are spoken).

## What the videos teach (condensed)
- **V1 "6 power phrases":** (1) *launch sub-agents* — parallel Claudes, own context, for multi-perspective /
  scale / speed; Claude under-uses them, force it. (2) *write me an implementation spec* — collapses the
  option space to ~1 before building. (3) *interview me* — Claude asks YOU the questions you didn't know to
  ask, then writes the spec. (4) *verify before you build* — Claude lies "done"; give it a tool to SEE its
  output + 3 layers (CLAUDE.md verify-line · enable verify tools/MCP · human-validation zones for high
  cost-of-error). (5) *based on this conversation, build me a skill* + a **gotchas** section. (6) *automate
  this* (dangerous) — taste-test + 80/20; augment > blind-automate; hooks/schedule/loops.
- **V2 Boris (Claude Code creator):** plan-mode 80% of sessions ("move slow to move fast") · **minimal
  CLAUDE.md**, delete when bloated, add back a bit at a time · verify → 2-3× quality · parallel partitioned
  sessions + fresh context for hard problems · slash-commands/skills for inner loops · **bitter lesson:
  never bet against the model** (don't over-scaffold).
- **V3 Karpathy's 3 layers:** *spec* (uncover the GOAL not the task; agile small specs; be precise) ·
  *verifier* (AI = "robot librarian" — confidently wrong when a book is missing; the ONLY lever is
  verification: set eval criteria up front · 2nd AI as critic · pull external signal) · *environment*
  (CLAUDE.md as repo-map/skills-routing/knowledge-arch/rules · LLM knowledge base = your moat · skills =
  "run water through the hose" · **guard-rails via hooks — enforced at tool level, not prompt level**:
  always-do / ask-first / never-do). "You can outsource thinking, not understanding."
- **V4 9 plugins:** Caveman (condense/save tokens) · Firecrawl+Exa (scrape stack) · Compound-Engineering
  (plan→work→review→compound) · Higgsfield (media) · Anthropic official (skill-creator/legal/frontend-design/
  security) · Codex (multi-model 2nd-opinion; token subsidy reality) · buildpartner.ai · **Morph** (fast-apply
  edits 8×, cuts MECHANICAL token waste) · Code Burn (token dashboard).

## Honest self-evaluation of THIS session
**Already strongly aligned (keep):**
- *Sub-agents / multiply yourself* ✅ — fanned out 3+3 parallel opus agents for L2/L3 (own context, partitioned)
  + research agents as verification lenses.
- *Spec-before-build* ✅ — design doc per engine (research/164-168) before code.
- *Verify before you build / robot-librarian* ✅ — Rule F real-data-by-eye is exactly this; caught the cost-gate
  bug + the index-options root cause; used a research agent as a 2nd critic (found a live rate bug).
- *Environment = CLAUDE.md + hooks as tool-level guard-rails* ✅ — the repo's rules A–Q + Stop/PreToolUse hooks
  ARE Karpathy's "never-do enforced at tool level, not prompt." Human-validation-zone = the live-capital gate.
- *Plugins* ✅ — Caveman/Firecrawl/Exa/Anthropic-official installed + just USED firecrawl to unblock this task.

**Real gaps (fix):**
1. **Interview the user MORE before big builds** (V1#3, V2#1). I proceeded on assumptions too often; only a few
   AskUserQuestion checkpoints. → Ask a short forced-MCQ interview before each big slice.
2. **Token verbosity** (V4 Caveman/Morph/Code-Burn). Drifted verbose despite caveman mode; long sign-offs
   duplicate SYSTEM_MAP/BACKLOG. → 3-line sign-offs; detail lives in the docs.
3. **Mechanical-work waste** (V4 Morph). Lots of edits/greps/polling = mechanical, not reasoning. → recommend
   installing **Morph** (fast-apply) + convert repeated mechanical steps to scripts.
4. **2nd-model adversarial critic** (V3 verifier, V4 Codex). Used same-model agents, not a DIFFERENT model to
   refute. → at L4, run edge-validation through the **Codex plugin** as an independent critic (refute the edge).
5. **CLAUDE.md heaviness vs "minimal"** (V2#2, bitter lesson). The rules are large; Boris says minimal + delete
   bloat. Deliberate here (money-grade guard-rails), but watch for rules fighting a better model over time.

## Concrete changes I'm adopting
- Terse sign-offs (this doc + SYSTEM_MAP hold the detail).
- Short "interview me" MCQ before each big slice.
- Check infra (systemctl) before manual restarts; condition-based waits not poll-loops.
- Recommend installing **Morph** (mechanical-edit token savings) + use **Codex** as a 2nd-model critic at L4.
- Keep the strengths: parallel sub-agents, spec-first, real-data verification, hook guard-rails.
