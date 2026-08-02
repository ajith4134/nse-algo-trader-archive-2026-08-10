# Agentic Coding Workflows for Building Large, High-Quality Software with LLMs

Research date: 2026-07-26. Meta/process research (not a project feature branch) — covers how to work
*with* Claude Code and comparable agentic coding tools to build institutional-grade software at scale.

**Note on the Rule I / sourcing-gate hook:** this doc is not a design doc for a new trading-system
engine/component, so the "search GitHub/PyPI, vendor-or-reject" OSS-sourcing gate does not apply — there
is no feature here to source parts for. It surveys existing external *tools and methodologies*
(Claude Code, Cursor, Aider, etc.) via web research, which is what Sections 1-4 below document. Nothing
is deferred as a result, so no docs/BACKLOG.md entry is needed. Stating this explicitly per the
no-silent-skip rule rather than leaving the hook's applicability ambiguous.
Compiled from 4 parallel Sonnet research passes, each doing multi-angle web search + WebFetch of primary
sources (official docs, GitHub, arXiv, company blogs, HN, Simon Willison). Grades: A = primary/official,
B = reputable secondary, C = forum/vendor/anecdotal.

## Bottom line

There is no evidence that "more agents" is inherently better. The single strongest real-world data point —
the SWE-bench Verified leaderboard, where actual code-fixing ability on real GitHub issues is measured —
is dominated top-to-bottom by **single agents with tools**, not orchestrated multi-agent pipelines,
and at least one architecture-taxonomy paper concludes single-agent designs currently *outperform*
multi-agent ones there, attributing it to lower coordination overhead. Where multi-agent/multi-role
splitting *does* have real evidence behind it: (1) **execution-grounded feedback loops** — generator writes
code, a test/compiler runs it, a debugger iterates on the real pass/fail signal — reliably beat pure
text self-critique; (2) **reviewer ensembles** genuinely catch a wider *union* of distinct bugs than any
one reviewer, because different tools/agents catch different things, even though no single one gets
close to human-level; and (3) narrow **writer/reviewer with a fresh, unbiased context** (not the same
context reviewing itself) is Anthropic's own recommended pattern. Multi-agent orchestration has a real,
measured cost: 2-10x more tokens (2-3x after adjusting for retries), and its most common failure mode is
parallel agents independently resolving ambiguity into locally-coherent but globally-incompatible code.
The practical synthesis: **use a single strong agent as the default engine, and add a second agent/role
only where it exploits a concrete asymmetry** (fresh eyes for review, real test execution for debugging,
independent verification for high-stakes changes, or genuinely parallelizable/decomposable subtasks) —
not by default, and not as a blanket "team of agents beats one" strategy.

---

## 1. Claude Code — CLAUDE.md, Skills, subagents, plan mode, hooks, commands

**CLAUDE.md (official, code.claude.com/docs/en/best-practices):** loads every session — keep it lean;
for each line ask "would removing this cause a mistake?" A bloated file causes Claude to *ignore* real
instructions. Include non-guessable bash commands, non-default style rules, test/lint prefs, gotchas.
Exclude anything inferable from code or standard conventions. Supports `@path/to/file` imports and
hierarchical placement (user, project root, `CLAUDE.local.md` gitignored, per-subdirectory for monorepos).
For **large codebases** specifically (Anthropic blog, "How Claude Code works in large codebases"):
root CLAUDE.md = pointers/critical gotchas only; subdirectory CLAUDE.md files add local convention as
Claude navigates in. Initialize inside subdirectories for monorepos, scope test/lint commands per
subdirectory, use `.claudeignore`, prefer LSP symbol search over grep, and re-tune every 3-6 months.
Community convergence (HN item 48144494, 2026): keep it under ~50 lines, record specific regressions
rather than architectural essays. Reported pain points (anecdotal): instruction non-compliance,
redundant exploration, AI-authored codebases accumulating duplicated logic without strong guardrails.

**Skills (code.claude.com/docs/en/skills):** a directory with `SKILL.md`, loads on-demand
("progressive disclosure") rather than sitting in every session like CLAUDE.md. Custom slash commands
have merged into skills as the current recommended form (legacy `.claude/commands/*.md` still works).
Shipped ~Oct 2025 per community sources, format open-sourced as the Agent Skills spec ~Dec 2025 and
subsequently adopted by OpenAI for Codex. Real example: `ysyecust/everything-claude-code`'s
`skills/coding-standards/SKILL.md` encodes naming/KISS/DRY/error-handling/test-structure rules with
explicit PASS/FAIL pairs, deferring framework specifics to companion skills — a clean illustration of
encoding team standards as a loadable skill instead of bloating CLAUDE.md.
(github.com/anthropics/skills is the official examples repo.)

**Subagents (code.claude.com/docs/en/sub-agents):** each gets its own context window, system prompt,
tool allowlist, model choice — keeps verbose exploration out of the main conversation. Anthropic's own
recommended pattern is **Writer/Reviewer**: one session implements, a second reviews in a fresh context
with only the diff, avoiding the bias of a model reviewing its own work, plus an adversarial review step
before calling work done. Community write-ups (PubNub blog) describe a three-stage pipeline
(spec-writer → architect-reviewer → implementer-tester) with hook-based handoffs and explicit
"definition of done" checklists. A concrete practitioner report (hamy.xyz, Feb 2026) documents a
9-parallel-subagent `/code-review` command (test runner, linter, security reviewer, style, performance,
dependency-safety, simplification, etc.) where tuning raised useful-suggestion rate from <50% to ~75%.

**Plan Mode:** research-and-propose without editing; official best-practice loop is
Explore → Plan → Implement → Commit, with an explicit caution that plan mode "adds overhead" — skip it
for changes you could describe in one sentence.

**Hooks (code.claude.com/docs/en/hooks):** the *only deterministic* enforcement mechanism — unlike
CLAUDE.md instructions, which are advisory. Lifecycle events include PreToolUse (can block),
PostToolUse, Stop/SubagentStop, SessionStart/End. Official example: PostToolUse lint-check on
Edit|Write. A Stop hook can block turn-completion until a check script passes (force-overrides after 8
consecutive blocks). Community guidance: run heavy checks (full test suite) at SessionEnd/CI, not per-edit.

**Real large-scale examples (all Anthropic-published customer case studies — credible as named/quoted,
but vendor-selected, so treat outcome numbers as company-reported, not independently audited):**
- **Wiz**: migrated a 50k-line Python PDF library to 18.4k-line Go in ~20 hours; a 20k-line C++
  classification library to 5.4k-line Go in 2 days, 100% validation-test pass. 90%+ daily adoption.
- **LG CNS**: modernized a 20-year-old system — 2,913 APIs (99.1% converted), 1,340 UI screens off a
  proprietary platform to React, 200 engineers in 5-7 person pods, 7 months vs. a conventional 14+,
  ~50% cost reduction.
- **Rakuten**: one engineer had Claude Code run 7 hours of sustained autonomous work on a 12.5M-line
  multi-language codebase (vLLM); reported 79% reduction in feature time-to-market, 97% fewer critical errors.

No independent (non-Anthropic) named case study of a large personal/OSS system built primarily with
Claude Code was found in this pass — a real gap; what surfaced was general best-practices commentary,
not a single attributable "we built X, this large, this way" narrative outside vendor case studies.

## 2. Multi-agent orchestration — does splitting into specialized agents measurably help?

**Real, published multi-agent pipelines exist and are actively researched**, not just hypothetical:
AgentForge (Planner/Coder/Tester/Debugger/Critic, arXiv 2604.13120), MapCoder (retrieval/plan/code/debug,
arXiv 2405.11403, ACL 2024), AgentCoder (programmer/test-designer/test-executor, arXiv 2312.13010),
self-collaboration code generation (analyst/coder/tester, arXiv 2304.07590), MetaGPT (arXiv 2308.00352),
ChatDev (arXiv 2307.07924).

**Author-reported numbers** (not independently replicated — read as claimed-and-plausible):
MapCoder 93.9% HumanEval pass@1; AgentCoder 96.3% HumanEval / 91.8% MBPP vs. cited single-agent SOTA of
90.2%/78.9%, at ~2.5-3x lower token cost; self-collaboration +29.9-47.1% relative pass@1 over plain
ChatGPT; AgentForge 40.0% SWE-bench Lite vs. single-agent GPT-4o's 14.0%. MetaGPT/ChatDev give no
quantitative baseline comparison in their abstracts.

**The clearest counter-evidence — SWE-bench Verified leaderboard** (leaderboard.steel.dev, live):
dominated by single frontier models running one agentic tool-use loop (Claude models across most of the
top 10). "Inside the Scaffold: A Source-Code Taxonomy of Coding Agent Architectures" (arXiv 2604.03515)
explicitly concludes single-agent architectures currently outperform multi-agent ones on this benchmark,
attributing it to lower coordination overhead. Cognition (Devin) has publicly argued multi-agent
architectures are "fragile" from lack of shared global context; OpenHands uses single-agent design by
philosophy. (Counter-example: Lingxi is a multi-agent SWE-bench entrant built specifically to avoid
single-agent "context dilution" — not unanimous.)

**Adversarial/ensemble reviewers — the one place splitting clearly helps, with real numbers:**
c-CRAB (arXiv 2603.23448) found individual automated review tools (PR-Agent, Devin Review, Claude Code,
Codex) each pass only 20.1-32.1% of tests derived from real human review feedback vs. 100% for humans;
combining all four only lifts coverage to 41.5% — ensembling helps but nowhere near human-level, with
massive non-overlap between what each tool catches. A separate informal 146-PR/679-finding study found
93.4% of distinct flagged issues were caught by exactly one of four reviewer tools — genuine evidence
that reviewers are complementary, not redundant, though no single critic is close to catching everything.

**Skepticism with real numbers:** Augment Code ("When Multi-Agent Is Overkill", Apr 2026) reports
2-10x token overhead for multi-agent vs. single-agent (2-3x after adjusting for retries); cites a 37%
token reduction from better single-agent architecture alone (no added agents); identifies the dominant
failure mode as parallel agents resolving ambiguous specs into locally-coherent but globally-incompatible
code that still passes review. Addy Osmani's "Code Agent Orchestra" (Mar 2026) states plainly that no
quantitative benchmark compares single- vs multi-agent performance in his own survey, and cites ETH
Zurich research (Gloaguen et al.) that LLM-authored agent-instruction files can provide no benefit or
even reduce success ~3% while raising cost 20% — a caution against over-engineering orchestration without
evidence.

**Verdict:** proven — pipelines exist, reviewer ensembles genuinely widen bug-catch coverage, and
multi-agent has real, measurable cost overhead. Claimed-not-verified — the specific superiority numbers
in MapCoder/AgentCoder/AgentForge (author-benchmarked, not third-party replicated). Actively contradicted
by the best real-world benchmark — SWE-bench's top performers are single-agent, and a dedicated taxonomy
paper says single-agent currently wins there.

## 3. Comparable tools

**Cursor:** `.cursorrules`/`.cursor/rules` for per-project agent governance; Composer/agent mode;
background agents. Jan 2026 Cursor research post (via Simon Willison) claims hundreds of concurrent
agents wrote 1M+ lines building a from-scratch Rust browser using hierarchical planner/sub-planner/worker
structure — impressive but self-reported. Aug 2025: security researchers documented "lethal trifecta"
prompt-injection/exfiltration via Cursor's MCP integrations — a real, independently documented risk.
May 2025 "vibe coding" retrospective (Alberto Fortin, via Willison): fast unsupervised Cursor use produced
"no consistency, no overarching plan," resembling "10 junior-mid developers" without coordination — the
clearest community caution about scaling Cursor to large/messy codebases. (Reddit/r/cursor was
unfetchable in this pass — a coverage gap.)

**Windsurf (Cascade):** docs.windsurf.com now redirects to docs.devin.ai — Windsurf's docs have been
folded into Cognition's stack following Cognition's acquisition of Windsurf (Jul 2025, $82M ARR, 350+
enterprise customers inherited). Cascade uses global rules (≤6,000 chars), workspace rules in `.devin/rules/`
(≤12,000 chars, glob/model-decision/manual triggers), and ephemeral local memories explicitly *not*
meant for durable knowledge (docs say put durable knowledge in a Rule or AGENTS.md instead).

**Aider — architect+editor mode, real benchmarked numbers (aider.chat, official):** at launch (Sept 2024)
splitting "propose solution" and "convert to file edits" into separate models gave real, measured gains:
o1-preview solo 79.7% → o1-preview+Sonnet 82.7%; Claude 3.5 Sonnet solo 77.4% → Sonnet+Sonnet 80.5%;
best combo (o1-preview + DeepSeek/o1-mini editor) hit 85%, a new SOTA at the time. By the current
leaderboard snapshot, frontier solo models (gpt-5 high, 88.0%) beat the best listed architect combo
(78.2%) — but this is partly confounded by nobody having paired gpt-5 itself as an architect model yet,
not a fully controlled comparison. Honest read: architect+editor split helped when reasoning models were
much better at reasoning than at precise diff formatting; once frontier models got good at both, the
gap closed or reversed on this specific leaderboard.

**Devin (Cognition):** launch claim (Mar 2024) of 13.86% SWE-bench resolve rate, "far exceeding" then-SOTA
1.96%. Independent scrutiny (per Wikipedia, triangulated): YouTube critics "Internet of Bugs" and
"Computer Vision Project" challenged the flagship Upwork demo, alleging it involved work irrelevant to
the actual request — the well-known Devin demo-skepticism episode. 2025 self-reported update: 67%
PR-merge rate (up from 34%), deployed at Goldman Sachs, Santander, Nubank among others — company-published,
not independently audited.

**OpenHands (formerly OpenDevin):** repositioned as a self-hosted control center that can run its own
agent or Claude Code/Codex/Gemini/any ACP-compatible agent. CodeAct 2.1 (Nov 2024) claimed 53%
SWE-bench Verified / 41.7% Lite — self-reported SOTA at the time, now over a year stale. HN reception
(Show HN, May 2025) framed it as strong for narrow wins (merge-conflict fixes, linting) rather than
wholesale autonomous rewrites — a more modest, practitioner-calibrated take than Devin's marketing.

**OpenAI Codex CLI:** lightweight terminal agent + IDE extensions + cloud "Codex Web." Adopted skills
support (Dec 2025) explicitly following Anthropic's Skills implementation. Per Simon Willison: GPT-5.2-Codex
handles long-horizon work via context compaction; a `/goal` loop-until-complete feature (Feb 2026) echoes
the community "Ralph loop" pattern; a GPT-5.6 file-deletion bug was found running Codex unsandboxed
(Feb 2026) — a concrete safety caveat for full-autonomy modes across all these tools.

## 4. Self-improving / self-refining loops

**Reflexion (Shinn et al., arXiv 2303.11366):** verbal self-reflection stored in episodic memory,
conditioning the next attempt. Headline: 91% pass@1 HumanEval vs. 80% GPT-4 zero-shot. Important caveat:
this relies on the model generating its own unit tests as the pass/fail oracle — later work (Olausson et
al.) frames this as smuggling in execution feedback under the "self-reflection" label; the mechanism
doing the work is closer to execution-grounded feedback than pure introspection.

**Self-Refine (Madaan et al., arXiv 2303.17651):** same LLM as generator/critic/refiner, ~20% average
improvement across seven tasks (aggregate, not code-specific in the abstract).

**Self-Debug (Chen et al., arXiv 2304.05128):** uses actual execution results (not text self-critique):
Spider +2-3% (9% on hardest subset), TransCoder/MBPP up to +12%, matching baselines that sample 10x more
candidates.

**CodeT (Microsoft, arXiv 2207.10397):** generates its own tests to rank samples via dual execution
agreement — 65.8% HumanEval pass@1, +18.8 pts over prior SOTA.

**The key skeptical counterweight — "Is Self-Repair a Silver Bullet for Code Generation?" (Olausson et
al., arXiv 2306.09896):** once repair cost is priced in, gains are "modest, vary a lot, and are sometimes
not present at all." Self-repair is bottlenecked by the model's own ability to generate useful feedback —
when a *stronger* model supplies the feedback instead, gains jump substantially. This is the central
finding undercutting "self-critique alone" hype.

**"Large Language Models Cannot Self-Correct Reasoning Yet" (Huang et al., DeepMind, arXiv 2310.01798,
ICLR 2024):** without external feedback, LLMs struggle to self-correct and performance sometimes
*degrades* after self-correction — a general-purpose, heavily cited confirmation of the same pattern.

**Execution-feedback agentic coding (2024-2025), where the real gains are:** SWE-agent (arXiv 2405.15793,
12.5% SWE-bench via a better agent-computer execution interface); Agentless (arXiv 2407.01489, a
deliberately non-agentic fixed localize→repair→validate pipeline hitting 32.0% SWE-bench Lite at
$0.70/issue, beating more complex self-critique agents of the time); SWE-Gym (arXiv 2412.21139, agent +
execution-trained verifier, 32.0% Verified / 26.0% Lite, SOTA among open-weight systems in 2025).

**Production code-review tools** (CodeRabbit, Greptile, Qodo, Cursor Bugbot) — all vendor self-reported,
no independent audits. Bugbot's "70%+ resolution rate, >50% of flagged bugs actually fixed" is the most
falsifiable claim found (outcome-based, not just flagged-count).

**Verdict:** execution-grounded generator→run-tests→refine loops are proven and load-bearing at the
unit/function level. Pure text self-critique without execution or an external/stronger verifier is the
weak link — two independently strong sources (Olausson et al.; Huang et al./DeepMind, ICLR 2024) show it
plateaus or actively hurts. At whole-repository, real-world scale the ceiling is still low across the
board (SWE-bench baseline <2%, best 2024-25 pipelines ~30-32%), and no production review tool has
published independently audited precision/recall.

## Most effective workflow for turning ideas into institutional-grade code at scale

Synthesizing all four passes, the evidence supports a specific, non-symmetric answer rather than a
blanket "multi-agent beats single-agent":

1. **Default engine = one strong agent with real tool/execution access** (Claude Code, SWE-agent-style
   agent-computer interface, or equivalent) — this is what actually wins on the most realistic benchmark
   (SWE-bench Verified) and what the taxonomy literature says is currently ahead of multi-agent
   orchestration for tightly-coupled, sequential engineering work.
2. **Add a second role only where a concrete asymmetry justifies it, not by default:**
   - **Fresh-context reviewer** (Anthropic's own recommended Writer/Reviewer pattern) for the specific
     reason a model is structurally bad at judging its own output (self-enhancement bias, per Zheng et
     al.'s LLM-as-judge study) — one implementer session, one reviewer session with only the diff.
   - **Ensemble of independent reviewers/linters/security scanners** for coverage, since the evidence
     (c-CRAB, the 146-PR study) shows different tools/agents catch different bugs with heavy non-overlap —
     but expect a firm ceiling well under 100%, and treat it as widening the union, not approaching
     completeness.
   - **A real test/build/compile loop as the refine signal**, never pure prose self-critique — this is
     the best-evidenced lever in the entire research set (CodeT, Self-Debug, SWE-agent, Agentless,
     SWE-Gym all converge on this).
   - **Genuine parallel decomposition** for independently-shippable subtasks (Cursor's/Rakuten's/LG CNS's
     large-scale examples all parallelize across files/modules that don't share tight coupling, not
     across roles reasoning about the same code).
3. **Enforce standards deterministically, not just advisorially** — CLAUDE.md/rules files are read as
   guidance and get ignored under load; hooks (PreToolUse/PostToolUse/Stop) are the only mechanism that
   actually blocks bad output, per Anthropic's own framing.
4. **Budget for the real cost of any added agent** — 2-3x+ tokens minimum, and watch for the dominant
   multi-agent failure mode (parallel agents resolving ambiguity into locally-coherent, globally-incompatible
   code) — mitigate with contract-first / shared-spec planning before parallelizing, which Augment Code's
   analysis found mattered more than agent count.

## What this did not fully cover (gaps, stated explicitly)

- Independent (non-Anthropic-published) named case studies of large personal/OSS systems built primarily
  with Claude Code — not found; only vendor case studies (Wiz, LG CNS, Rakuten) and general best-practices
  commentary surfaced.
- Raw Reddit/Discord community sentiment for Cursor, Windsurf, OpenHands — largely unfetchable in this
  pass (site blocks / empty results); leaned on Simon Willison and Hacker News instead.
- Full quantitative tables for "Refute-or-Promote" (adversarial review paper) and "Dissecting the
  SWE-Bench Leaderboards" — PDF extraction limits; findings from these two are directional only.
- Live, current-day SWE-bench Verified numbers for OpenHands/Windsurf-Devin/Codex side-by-side — the
  official leaderboard table didn't render through the fetch tool; only historical (Nov 2024) OpenHands
  numbers were confirmed.
- MetaGPT/ChatDev's actual head-to-head numeric comparisons against single-agent baselines — abstracts
  gave qualitative claims only.

## Sources (representative; grade noted)

- code.claude.com/docs/en/best-practices, /skills, /sub-agents, /permission-modes, /hooks (A, official)
- claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start (A)
- claude.com/customers/wiz, /lg-cns, /rakuten (A/vendor-selected)
- github.com/anthropics/skills; github.com/ysyecust/everything-claude-code (A/B)
- news.ycombinator.com/item?id=48144494 (C, anecdotal)
- pubnub.com/blog/best-practices-for-claude-code-sub-agents (B)
- hamy.xyz/blog/2026-02_code-reviews-claude-subagents (C, practitioner)
- arxiv.org/abs/2303.11366 (Reflexion), 2303.17651 (Self-Refine), 2304.05128 (Self-Debug),
  2207.10397 (CodeT), 2306.09896 (Olausson, self-repair skepticism), 2310.01798 (DeepMind,
  self-correct skepticism, ICLR 2024), 2312.13010 (AgentCoder), 2310.06770 (SWE-bench),
  2405.15793 (SWE-agent), 2407.01489 (Agentless), 2412.21139 (SWE-Gym), 2405.11403 (MapCoder),
  2604.13120 (AgentForge), 2603.23448 (c-CRAB), 2604.03515 (agent architecture taxonomy) — all A, primary
- leaderboard.steel.dev/leaderboards/swe-bench-verified (A, live data)
- aider.chat/2024/09/26/architect.html, aider.chat/docs/leaderboards (A, official)
- cognition.com/blog/introducing-devin, /devin-annual-performance-review-2025, /windsurf (A/vendor)
- en.wikipedia.org/wiki/Devin_AI (B, secondary, triangulated)
- github.com/All-Hands-AI/OpenHands; openhands.dev/blog/openhands-codeact-21 (A)
- github.com/openai/codex; simonwillison.net/tags/cursor, /codex (A/B)
- augmentcode.com/guides/when-multi-agent-ai-is-overkill; addyosmani.com/blog/code-agent-orchestra (B)
- coderabbit.ai, greptile.com, qodo.ai, cursor.com/en/bugbot (C, vendor self-report)
