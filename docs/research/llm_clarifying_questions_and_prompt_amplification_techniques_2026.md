# LLM interrogation (clarifying-question) patterns and automatic prompt amplification/optimization — evidence review

Research date: 2026-07-26. Multi-source web research (WebSearch + WebFetch on real pages, five parallel
research sweeps + one retry). All claims graded A (primary/official/peer-reviewed), B (reputable
secondary — blogs, practitioner writeups, docs), or C (forum/anecdote/marketing), and dated where
relevant. Complements the sibling docs already in this folder:
`llm_production_grade_code_prompting_techniques_2026.md` (why LLMs default to shallow code + the
verification-loop fix) and `agentic_coding_workflows_claude_code_multiagent_2026.md` — this doc covers
the *upstream* half of the pipeline: getting the SPEC right before generation, and amplifying it into a
strong build prompt.

## Bottom line

The field splits cleanly into two halves with very different evidence quality. **Getting an LLM to ask
good clarifying questions is a real, active 2023–2026 research area, but the single most important
finding is a negative one**: models do not spontaneously interview you — left alone they "overwhelmingly
default to direct answers" even when they can recognize a query is ambiguous (arXiv:2605.25284, May
2026); clarifying behavior has to be forced via an explicit instruction, a training-time incentive, or a
structured tool, and even then a rigorous 2024 benchmark (CLAMBER) found current LLMs have only "limited
practical utility" at it. **Structured, multiple-choice ("wizard") elicitation is better evidenced than
open-ended clarifying questions** — Claude Code's `AskUserQuestion` tool and GitHub's `spec-kit`
`/speckit.clarify` command are real, shipped implementations, and the one direct head-to-head study found
(arXiv:2602.04210, Feb 2026) reports up to 54% relative alignment-score improvement for structured vs.
open-ended elicitation. On the amplification side, **automatic prompt-optimization frameworks (DSPy,
EvoPrompt, PromptWizard, TextGrad, OPRO) all have real A-grade benchmark gains**, but only **TextGrad**
has a direct code-generation benchmark (+20% relative on LeetCode-Hard); the rest were built and proven
on classification/QA/math-reasoning, not code. Meanwhile the most heavily marketed "instant prompt
amplifier" (PromptPerfect) has **no independent evidence at all** behind it. For raw code-quality prompting
techniques, the strongest evidence converges on **execution-grounded self-correction** (Reflexion: 91.0%
vs. 80.1% pass@1 on HumanEval) and **execution-based consensus** (CodeT: 65.8% pass@1, +18.8pp) — both of
which route through an external checker (test execution), not pure self-critique. A 2023 paper explicitly
shows *pure* self-critique without an external verifier can make things worse ("LLMs Cannot Self-Correct
Reasoning Yet," arXiv:2310.01798) — this is the load-bearing caveat for the whole self-refine/self-critique
category.

---

## 1. Clarifying-question / "interview the user" prompting for requirements elicitation

**Academic (Grade A):**
- **CLAMBER** — ACL 2024 benchmark, 12K instances, taxonomy of ambiguity types (arxiv.org/abs/2405.12063).
  Finding: current LLMs have "limited practical utility" identifying/clarifying ambiguous queries; CoT and
  few-shot prompting give only marginal gains and can induce overconfidence.
- **"Knowing but Not Showing"** (Su & Cardie, arXiv:2605.25284, May 2026) — the key negative finding:
  models CAN judge a query ambiguous when asked directly, but in normal use they default to answering
  anyway; retrieval context makes this worse. The premise that models spontaneously interview the user is
  largely false — it must be forced.
- **"Modeling Future Conversation Turns to Teach LLMs to Ask Clarifying Questions"** (arXiv:2410.13788) —
  trains models to ask by simulating the payoff across possible user interpretations; a training-time fix,
  not a prompt trick.
- **LLMREI** (arXiv:2507.02564, IEEE 2025) — GPT-4o interview chatbot for software requirements
  elicitation, evaluated on 33 simulated stakeholder interviews. Concrete numbers: fully captured up to
  60.94% of requirements, +12.76% partially (73.7% total); longer/least-to-most prompting reduced
  interviewer errors in 64.23% of assessments vs. 59.1% for a short prompt.
- Adjacent 2025–2026 papers confirming this is an active field, not one-off: ClarifyMT-Bench
  (arXiv:2512.21120), ReqElicitGym (arXiv:2602.18306), ClarifySTL (arXiv:2605.01209), diffusion-inspired
  preference-elicitation question generation (arXiv:2510.12015).

**Adjacent-but-distinct techniques (often conflated with "ask clarifying questions"):**
- **Self-Ask** (Press et al., ofir.io/Self-ask-prompting) — model asks *itself* sub-questions, no human
  interviewed. Real gains on compositional reasoning, but irrelevant to human-in-the-loop clarification.
- **Active Prompting** (Diao et al., arXiv:2302.12246, ACL 2024; github.com/shizhediao/active-prompt, 249
  stars) — uses model uncertainty to choose which *training exemplars* need human annotation (67.9%→74.9%
  over self-consistency). Human is consulted for few-shot curation, not end-task requirements.
- **Rephrase and Respond (RaR)** (Deng et al., arXiv:2311.04205) — model rephrases the question itself,
  no user interaction (GPT-4 avg 64.95%→89.77% across 10 tasks). Strong numbers, but not human interview.

**Practitioner signal (Grade C):** widespread "ask up to 3 clarifying questions before writing code" prompt
clauses on GitHub and in OpenAI/Reddit/HN community threads — but no rigorous head-to-head measurement of
output quality was found anywhere; this entire practitioner layer is anecdotal.

**Verdict:** real, active research area; the rigorous evidence is thinner and more cautionary than the
practitioner lore suggests. Strongest actionable takeaway: an explicit "ask before assuming" directive is
necessary (models won't do it on their own), and structured/constrained question formats outperform
open-ended ones (see §4).

---

## 2. Meta-prompting / prompt amplification tools

**Anthropic's own tooling (Grade A):** No standalone "Prompt Improver" product page currently exists (old
URLs redirect into the generic best-practices docs). The real artifact is the **metaprompt recipe**:
`github.com/anthropics/claude-cookbooks/blob/main/misc/metaprompt.ipynb`, linked from
`platform.claude.com/docs/.../prompt-engineering/overview` ("Don't have a first draft prompt? Generate one
with the metaprompt recipe"). Technique: a fixed template with six multi-shot examples is filled with the
task description; Claude generates a full instruction set inside `<Instructions>` XML tags; variable
placeholders are auto-detected by regex. **No benchmark or before/after quality evidence is published** —
described technique, not a proven one.

**PromptPerfect (Grade C, marketing only):** promptperfect.jina.ai discloses no methodology. All
discoverable "reviews" are SEO listicles with no testing methodology; Jina's own blog no longer even
features it. Real independent signal is a 2023 HN "Show HN" thread (126 pts, 55 comments) leaning
skeptical: "modern equivalent of selling shovels during a gold rush"; "the optimized prompt was not better
for my use case." **Verdict: unverified vendor marketing — flag as overhyped relative to its visibility.**

**GitHub prompt-expander/optimizer tools (Grade A/B, READMEs read directly):**

| Tool | Stars | Activity | Technique |
|---|---|---|---|
| linshenkx/prompt-optimizer | 32.7k | Active | Iterative LLM refine loop, multi-platform |
| mshumer/gpt-prompt-engineer | 9.7k | Cooling (~9mo stale) | Generates variants, ranks by ELO |
| microsoft/PromptWizard | 3.9k | Active | Mutate→critique→refine chain; published paper arXiv:2405.18369, benchmarked (GSM8K etc.) |
| Eladlev/AutoPrompt | 3.0k | Active | Synthetic test generation + calibration loop |
| keirp/automatic_prompt_engineer (APE) | 1.4k | Dead (2+ yrs) | Foundational academic root; now superseded |
| aws-samples/claude-prompt-generator | 1.3k | **Archived** | Closest fit to "short idea→long structured Claude prompt," but abandoned |

Real adoption clusters around iterative test-score-refine loops, not naive single-shot expansion — pure
"expand a vague idea" tools are niche/toy or abandoned.

**Academic "meta-prompting" — term collision (Grade A, arXiv:2401.12954, Suzgun & Kalai, Jan 2024):** This
is **not** single-task prompt amplification — it's multi-agent orchestration: one LM "conductor" spawns
specialized expert instances (communicating only through the conductor) plus tool use. On GPT-4 across 8
tasks it beat standard prompting by 17.1pp, dynamic-expert prompting by 17.3pp, multi-persona prompting by
15.2pp (Game of 24: 3.0%→67.0%). OpenAI's Cookbook separately uses "meta-prompting" for the looser
"stronger model rewrites the prompt a weaker model executes" sense — a genuine, confirmed term collision
worth flagging so it isn't conflated with prompt amplification.

**Sentiment (Grade C, real threads):** Practitioner consensus leans toward "have the LLM ask clarifying
questions before writing the prompt" over "blind one-shot expand my idea" — several 2025–2026 threads
report blind expansion wastes tokens/hedges answers.

---

## 3. Automatic prompt optimization frameworks — DSPy, APE, EvoPrompt, TextGrad, OPRO

All five have real A-grade benchmark gains. **Code-generation validation is thin: only TextGrad has a
direct, published code-task benchmark.**

| Framework | What it optimizes | Benchmark evidence (A-grade) | Code-gen evidence | Adoption |
|---|---|---|---|---|
| **DSPy** (arXiv:2310.03714) | Compiles declarative LM pipelines → optimized prompts + few-shot demos (+ optional weights) | GPT-3.5 beats few-shot by >25%, expert demos by 5–46%; llama2-13b beats few-shot by 65% | None in own paper; used for agents/retrieval/QA in practice, not code-gen specifically | 36.4k★, very active, follow-on "GEPA" paper (Jul 2025) |
| **APE** (arXiv:2211.01910) | Generates+selects instructions via search | Matches/beats human instructions on 19/24 BIG-Bench Instruction Induction tasks | None found | 1.4k★, dead repo — used only as a baseline in later papers, considered superseded |
| **EvoPrompt** (arXiv:2309.08532, ICLR 2024) | Evolutionary/genetic-algorithm discrete prompt search | Up to 25% gain over human/APE baselines across 31 datasets (BBH, GPT-3.5, Alpaca) | None found | 250★, modest, Microsoft-affiliated |
| **TextGrad** (arXiv:2406.07496, Nature Mar 2025) | "Textual gradients" — LLM feedback iteratively improves any pipeline component | GDM QA 51%→55% (GPT-4o); molecule design; radiotherapy planning | **+20% relative on LeetCode-Hard — the only direct code-gen benchmark of the five** | 3.7k★, 294 forks, Nature-published |
| **OPRO** (arXiv:2309.03409, ICLR 2024) | LLM proposes new prompts conditioned on a trajectory of prior prompt+score pairs | Discovered "Take a deep breath and work on this problem step-by-step": 80.2% GSM8K vs. 71.8% ("let's think step by step") vs. 34.0% (empty); up to 50% gain on BBH | None found | 768★, low activity — largely a research curiosity, not production-adopted |

**Practitioner/production signal:** DSPy has real tooling activity (SuperOptiX orchestration, a
self-published "2 years of production DSPy" account, though undisclosed/unquantified). No practitioner
source found using any of these five specifically for code-generation beyond TextGrad's own number — flag
this as the main gap if planning to use APO for a coding-prompt pipeline.

---

## 4. CoT, self-consistency, plan-and-solve, ReAct, Reflexion, self-refine — CODE quality specifically

| Technique | Original paper's code coverage | Code-specific evidence found | Verdict |
|---|---|---|---|
| **Chain-of-Thought** (arXiv:2201.11903) | None — arithmetic/commonsense/symbolic only | Follow-up arXiv:2512.09679 (Dec 2025, 6 models 7B–480B): structured/guided CoT +5–12% pass@1 avg, but **naive zero-shot CoT can degrade performance** ("overthinking" on simple tasks), echoed in arXiv:2512.14048 and arXiv:2503.15341 | **Mixed/contested** — helps when structured, can hurt when applied blindly |
| **Self-Consistency** (arXiv:2203.11171) | None — same reasoning-task list as CoT | Code-analog is a *distinct*, execution-based method: **CodeT** (arXiv:2207.10397) dual execution-agreement voting → 65.8% pass@1 HumanEval (+18.8pp); **Coder-Reviewer Reranking** (arXiv:2211.16490) → up to +17pp | **Strong, but only via adapted execution-based variants** — vanilla text-majority-vote was never tested on code |
| **Plan-and-Solve** (arXiv:2305.04091) | None — 10 reasoning datasets only | Not found | **No evidence either way for code** |
| **ReAct** (arXiv:2210.03629) | None — HotpotQA/FEVER/ALFWorld/WebShop only | Not a code-gen method — it's agent scaffolding. Downstream: RUSTFORGER (arXiv:2602.22764) ReAct-style agents resolve up to 21.2% of Rust issues; CP-Agent (arXiv:2508.07468) ReAct + persistent kernel → perfect accuracy on 101-problem constraint-programming set | **Architecture for coding agents, not a code-gen prompting technique per se** |
| **Reflexion** (arXiv:2303.11366) | **91.0% pass@1 HumanEval** vs. GPT-4 baseline 80.1%, vs. prior SOTA CodeT+GPT-3.5 65.8%; Rust 68.0 vs. 60.0 | Confirmed directly from paper Table 1 | **Strong** — but driven by *test-execution feedback*, not pure self-critique |
| **Self-Refine** (arXiv:2303.17651) | Code Optimization: 27.3%→36.0% (+8.7pp); Code Readability: 27.4%→56.2% (+28.8pp), GPT-4 | Confirmed directly | **Moderate-to-strong on these two sub-tasks, but self-judged (no ground truth)** — see counter-evidence below |

**Counter-evidence (Grade A, load-bearing caveat):** "Large Language Models Cannot Self-Correct Reasoning
Yet" (Huang et al., arXiv:2310.01798) — intrinsic self-correction *without* an external signal degraded
performance (GSM8K 75.9%→74.7%, CommonSenseQA 75.8%→41.8%); explicitly excepts cases with an **external
verifier** (code executors/unit tests) — exactly why Reflexion/CodeT work while pure text self-critique on
reasoning doesn't. "Is Self-Repair a Silver Bullet?" (arXiv:2306.09896, ICLR 2024) found self-repair gains
are "often modest… sometimes not present at all" once repair cost is counted.

**Net takeaway:** code-gen improvement from this whole family tracks whether an **external, checkable
signal** (test execution) is in the loop — present and strong in Reflexion/CodeT, partially absent (and
weaker) in Self-Refine's code tasks, entirely absent in CoT/Self-Consistency/Plan-and-Solve/ReAct's
*original* evaluations.

---

## 5. Wizard-style structured-choice frameworks (multiple-choice spec elicitation)

**Bottom line:** young pattern, exactly one flagship production tool, one flagship OSS methodology, and
one piece of rigorous evaluation evidence directly supporting it — everything else is adoption signal.

- **Claude Code — `AskUserQuestion` tool** (Grade A, official): 1–4 questions per call, each with 2–4
  labeled options (label + description, optional preview), `multiSelect` support, free-text only via an
  optional "Other." `code.claude.com/docs/en/agent-sdk/user-input`, `code.claude.com/docs/en/tools-reference`.
  Plan Mode is the *permission mode* (propose-then-approve); `AskUserQuestion` is what renders the actual
  choices inside it.
- **GitHub `spec-kit` `/speckit.clarify`** (formerly `/quizme`) (Grade A): scans a spec across 9 ambiguity
  categories, asks up to 5 questions one at a time, each rendered as a Markdown table of lettered options
  (A/B/C…) with a recommended pick; answers merge back into the spec. 123.9k★ — by far the largest
  real-world adoption signal in this whole review. `github.com/github/spec-kit`.
- **BMAD-METHOD** (Grade A, docs.bmad-method.org/explanation/advanced-elicitation): numbered menu of
  critique techniques (pre-mortem, first-principles, etc.) to refine a drafted spec section. 51.1k★.
- **Amazon Kiro / OpenSpec** (Grade A): despite "spec-driven" branding, both use a single free-text prompt
  auto-expanded into Markdown docs for free-text review — **not** multiple-choice elicitation. Worth
  flagging as a branding/reality mismatch.
- **Cursor / Aider / Windsurf / Copilot Workspace**: no equivalent MCQ feature found — all free-text
  chat/plan summaries (Grade A/B per-tool docs).

**Academic evidence (thin but real):** Zhou et al., "Steering LLMs via Scalable Interactive Oversight"
(arXiv:2602.04210, Feb 2026, Grade B) directly compares closed-form/structured vs. open-ended elicitation
for PRD generation in "vibe coding": **up to 54% relative alignment-score improvement**, +4.7% ablation
effect from closed-form alone, small (n=10) human study. A 74-study systematic review of LLM+requirements-
engineering work (arXiv:2509.11446, Sept 2025) confirms this exact comparison is otherwise absent from the
literature.

**Community sentiment:** HN's highest-engagement relevant thread (128 pts, Oct 2025,
news.ycombinator.com/item?id=45610996) leans skeptical of rigid spec structure ("sledgehammer to crack a
nut," "waterfall with AI, now?"). No real consensus either way — treat as an open design question, not a
settled one.

---

## Ranked: the 9 most adoptable, evidence-backed techniques

### (a) Interrogating an idea into a full spec

1. **Force the "ask, don't assume" directive explicitly** — models default to answering rather than
   clarifying even when they can recognize ambiguity (arXiv:2605.25284); this is table stakes and without
   it every other technique below is moot. Grade A (negative-finding paper), zero adoption cost.
2. **Prefer structured multiple-choice elicitation over open-ended questions** — Claude Code's
   `AskUserQuestion` and GitHub spec-kit's `/speckit.clarify` (123.9k★) are real, shipped implementations;
   the one direct comparison found (arXiv:2602.04210) reports up to 54% relative alignment-score gain for
   structured vs. open-ended. Strongest practical recommendation in this whole review.
3. **Cap it at a small number of rounds (2–5 questions), not an open-ended interview** — LLMREI
   (arXiv:2507.02564) shows ~74% requirement capture at this scale; longer/least-to-most phrasing within
   that cap reduces interviewer error (64.23% vs. 59.1%).
4. **Explicit planning phase before code, separate from the clarification phase** — Anthropic's official
   Explore→Plan→Implement→Commit workflow (`code.claude.com/docs/en/best-practices`), rationale: jumping
   straight to code risks solving the wrong problem. Grade A, official, well-corroborated by practitioner
   threads (Simon Willison, HN).
5. **Treat CLAMBER/"Knowing but Not Showing"-style caution as a design constraint, not just a fact**: don't
   trust an LLM to reliably self-detect when it needs to ask — over-specify triggers ("if X is unclear,
   ask") rather than relying on the model's judgment.

### (b) Amplifying the spec into an institutional-grade build prompt

6. **Iterative mutate→critique→refine prompt optimizers (PromptWizard-style), not naive one-shot
   expanders** — arXiv:2405.18369, 3.9k★, real GSM8K-class benchmark gains. Avoid PromptPerfect-style
   "instant expand" tools — no independent evidence found behind the marketing (Grade C only, flag as
   overhyped relative to visibility).
7. **Externally-verifiable completion gate + Reflexion-style execution-grounded self-critique** — the
   single strongest code-quality result in this whole review (91.0% vs. 80.1% pass@1 HumanEval,
   arXiv:2303.11366), and the anchor finding of the sibling doc
   `llm_production_grade_code_prompting_techniques_2026.md`. Bake "must produce a runnable check that
   passes" into the amplified prompt, not just "write good code."
8. **TextGrad-style textual-gradient refinement for code specifically** — the only APO framework with a
   direct code-gen benchmark (+20% relative, LeetCode-Hard, Nature-published arXiv:2406.07496); best fit
   among the five APO frameworks if the target really is code quality rather than classification/QA.
9. **DSPy-style compiled optimization — but only when there's a real scoring metric to optimize against**
   (25–65% gains across its benchmarks, 36.4k★, most mature/active of the five frameworks); not yet shown
   to help ad-hoc single-shot code-generation prompts specifically — best reserved for repeated/metric-able
   pipelines (retrieval, agents, evaluators), not a one-off "amplify my idea into a prompt" use case.

### Explicitly flagged as overhyped / weak evidence (do not adopt on faith)
- **PromptPerfect** and most "prompt expander" GitHub toys — Grade C/marketing only, no independent
  verification found anywhere.
- **OPRO** — real, celebrated result ("take a deep breath") but 768★, low production adoption; treat as a
  research curiosity, not a tool to integrate.
- **APE** — superseded; only survives as a baseline other papers beat.
- **Vanilla CoT and Self-Consistency for code** — their *original* papers never touch code benchmarks at
  all; naive CoT can actively hurt code tasks (arXiv:2512.09679). What actually works for code
  (CodeT-style execution voting) is a related-but-distinct execution-grounded method, not the vanilla
  text-based technique.
- **Pure self-refine/self-critique without an external verifier** — arXiv:2310.01798 shows this can
  *degrade* performance; only trust self-critique loops that route through a real check (tests, execution),
  matching the Reflexion pattern, not blind "critique your own answer" prompting.
- **Kiro / OpenSpec "spec-driven" branding** — marketed alongside spec-kit/BMAD but actually free-text
  expansion, not structured elicitation; don't assume the branding implies the wizard mechanism.

---

## Sources (primary list; inline citations above have full detail)

Clarifying questions: arxiv.org/abs/2405.12063 (CLAMBER) · arXiv:2605.25284 · arXiv:2410.13788 ·
arxiv.org/abs/2507.02564 (LLMREI) · arXiv:2512.21120 · arXiv:2602.18306 · arXiv:2605.01209 ·
arXiv:2510.12015 · ofir.io/Self-ask-prompting · arxiv.org/abs/2302.12246 (Active Prompting) ·
arxiv.org/abs/2311.04205 (RaR).

Meta-prompting/amplification: github.com/anthropics/claude-cookbooks/blob/main/misc/metaprompt.ipynb ·
promptperfect.jina.ai · github.com/linshenkx/prompt-optimizer · github.com/mshumer/gpt-prompt-engineer ·
github.com/microsoft/PromptWizard (arXiv:2405.18369) · github.com/Eladlev/AutoPrompt ·
github.com/keirp/automatic_prompt_engineer · github.com/aws-samples/claude-prompt-generator ·
arxiv.org/abs/2401.12954 (Suzgun & Kalai Meta-Prompting).

APO frameworks: github.com/stanfordnlp/dspy (arxiv.org/abs/2310.03714) · arxiv.org/abs/2211.01910 (APE) ·
github.com/keirp/automatic_prompt_engineer · arxiv.org/abs/2309.08532 (EvoPrompt) ·
github.com/beeevita/EvoPrompt · github.com/zou-group/textgrad (arxiv.org/abs/2406.07496) ·
arxiv.org/abs/2309.03409 (OPRO) · github.com/google-deepmind/opro.

CoT/ReAct/Reflexion/self-refine for code: arxiv.org/abs/2201.11903 (CoT) · arXiv:2512.09679 ·
arXiv:2512.14048 · arXiv:2503.15341 · arxiv.org/abs/2203.11171 (Self-Consistency) ·
arxiv.org/abs/2207.10397 (CodeT) · arxiv.org/abs/2211.16490 (Coder-Reviewer Reranking) ·
arxiv.org/abs/2305.04091 (Plan-and-Solve) · arxiv.org/abs/2210.03629 (ReAct) · arXiv:2602.22764
(RUSTFORGER) · arxiv.org/abs/2508.07468 (CP-Agent) · arxiv.org/abs/2303.11366 (Reflexion) ·
arxiv.org/abs/2303.17651 (Self-Refine) · arxiv.org/abs/2310.01798 (self-correction limits) ·
arxiv.org/abs/2306.09896 (self-repair silver bullet).

Wizard/structured-choice: code.claude.com/docs/en/agent-sdk/user-input ·
code.claude.com/docs/en/tools-reference · github.com/github/spec-kit ·
docs.bmad-method.org/explanation/advanced-elicitation · kiro.dev/docs/specs ·
github.com/Fission-AI/OpenSpec · arXiv:2602.04210 (Zhou et al., Steering LLMs via Scalable Interactive
Oversight) · arXiv:2509.11446 (systematic review) · news.ycombinator.com/item?id=45610996.

## What this doc did NOT cover
- Could not access Reddit directly in any research pass (fetch blocked in this environment) — all Reddit
  evidence above is secondhand via search-result titles/snippets, graded C and flagged as such.
- Did not benchmark these techniques against each other empirically ourselves — all numbers are as
  reported by the cited papers/docs, not independently reproduced.
- Non-English prompt-engineering communities were not searched.
- Image/diffusion-model prompt expanders (MagicPrompt, Stable Diffusion prompt tools) were explicitly out
  of scope — this review is text/code-LLM-only.
