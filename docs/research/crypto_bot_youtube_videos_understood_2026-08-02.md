# crypto-bot's 7 YouTube videos — full content understood

**Read:** 2026-08-02 · **Source:** the `video-notes/` folder of crypto-bot.git (transcripts +
sampled frames already captured with `ytgrab`; YouTube WebFetch returns 0 bytes so these
captures ARE the content). 6 had deep write-ups; the 7th (`vid8-tmp`) was captured but never
reviewed — I processed it here.

These videos are the **source material for how the agent should work** — both crypto-bot's
CLAUDE.md (Rules 0–7) and our own nse-algo-trader rules descend from them.

## Videos 1–5 — Austin Marchese (one channel, a deliberate ladder)

A ladder of abstraction: **prompts → specs → verification → skills → loops.** Each rung needs
the one below.

1. **Karpathy's Method** (7zZy1QTvokM) — Replace prompting with 3 durable layers: **Spec**
   (what/why), **Verifier** (how we know it's right), **Environment** (where it compounds). AI
   is a *robot librarian* — answers only from its library and doesn't know when a book is
   missing, so it confidently invents; emotional levers are no-ops, **verification is the only
   real lever.** Guide vs Rule: a CLAUDE.md line is a *request*; a **PreToolUse hook is a rule**.
   Bucket everything: always-do / ask-first / never-do (never-do enforced by hook, not prose).

2. **How the Creator Starts EVERY Project** (KWrsLqnB6vA) — Boris Cherny's 6 practices:
   **plan mode ~80% of sessions**; **keep CLAUDE.md short (~2k tokens), delete when bloated**;
   verification (same Cherny quote — "feedback loop will 2-3x the quality"); parallel
   partitioned sessions; inner loops → slash-commands/skills; **never bet against the model**
   (Bitter Lesson — scaffolding decays, your information moat doesn't).

3. **Paste This Into Claude** (TP73qyFWDcY) — 6 power-phrases: "launch sub-agents" (Claude
   under-uses them; separate agents don't anchor on each other → diverse perspectives);
   "write me an implementation spec" (**3 steps × 5 options = 125 builds; a spec makes it 1** —
   *"it doesn't know what you don't tell it"*, the strongest limit on "never bet against the
   model"); "interview me"; "verify before you build" (+ human validation zones by cost-of-error,
   *"explain the blast radius"*); "build me a skill from THIS conversation" (never abstractly);
   "automate this" = **the dangerous one** (taste-test + 80/20 filter; every automation is
   operational debt; prefer augmentation).

4. **9 Claude Code Plugins** (sBF3UumkL4Y) — weakest/most commercial (a paid sponsor + the
   presenter's own product, neither in any marketplace). The one gem = **Compound Engineering**:
   *"each unit of work should make the next easier"*, **80% planning+review / 20% execution**,
   loop plan→work→review→compound→repeat. Also: research stack **keyword (native) → semantic
   (Exa) → extraction (Firecrawl)**; mechanical-vs-reasoning tokens (if code can do it
   deterministically, write the script); maintainer-matters; $200/mo Max ≈ $1,800 token value.

5. **Loop Engineering** (YAS4ojuhbW4) — the capstone. Cherny: *"I don't prompt anymore. I have
   loops… my job is to write loops."* **4-Condition Test** (repeats / clear done-rule / can
   afford waste / has verify tools). 4 blocks: trigger (`/loop` local, `/schedule` cloud, or a
   custom orchestration skill) · **execution skills** (*"you don't build a loop without
   battle-tested skills behind it"*) · goal+verification (inseparable; **bridge abstract →
   verifiable** by making a skill emit approved/not-approved or 1–10) · output+**memory**
   (*"the agent forgets, the repo doesn't"*). **Loop Training Mode** = the reusable safety
   pattern: ON by default (pause per step, skip already-passing steps, **cap retries**).

## Video 6 — Dubibubi, different creator (weakest sourced)

**"I Scraped 85,000 Claude Skills"** (1GgyJfCK608) — countdown of the 12 most-installed plugins
(frontend-design, superpowers, context7, code-review, code-simplifier, skill-creator, GitHub
MCP, playwright, claude-md-management, feature-dev, typescript-lsp, security-guidance). Its own
frame f_002 shows the numbers came from a **third-party blog table**, not a scrape — the
`marketplace.json` has no install-count field. Best line: *"a prompt asks Claude to think; a
skill teaches Claude how to work."* Load-bearing rule: **don't install all 12 — 3–5 skills
matched to your workflow** (standing context cost is real). Contains a paid product placement +
"$40,000 in 50 days" claim.

## Video 7 — Eliot Prince, "Haiku vs Sonnet vs Opus vs Fable" (tRi9g3urhyE) — NEWLY PROCESSED

Consumer-level model-selection guide (18:36). ⚠️ Note: crypto-bot's own
`eliot-prince-credibility.md` flags this source, and the video is dated (says Fable free "until
July 19"; pre-dates some current models). Core mental model (cheapest→best, left→right):

| Model | Metaphor | Use for |
|---|---|---|
| **Haiku** | school-age intern / courier | quick instant answers, summaries, grab-and-fetch, scheduled micro-tasks. No real reasoning. |
| **Sonnet** | everyday worker | most knowledge work — research, writing, light analysis, a few multi-steps. 1M-token context ("~a dozen novels"). Where a $20 Pro user should live. |
| **Opus** | senior in-house specialist | deep reasoning + fewer mistakes/hallucinations, follows guardrails; contract/financial analysis, pricing critique. Slower, costs more. |
| **Fable** | Deloitte / outside consulting agency | your **hardest** problems; near-autonomous — give it a *goal not a prompt*, it plans, splits into sub-agents, self-corrects dead ends, executes end-to-end. Expensive; being pulled from included plans. |

Effort tab: **higher effort = more thorough but slower + burns limits faster; max ≠ faster.**
Default **high**; drop to **low** on Sonnet for speed; **Fable+max** only for hardest problems;
leave thinking on so it self-decides. A key anecdote: his fiancée burned her whole Pro usage by
accidentally running general work on **Opus instead of Sonnet** — the whole video's premise.
Practical pattern he uses: **Opus/Fable to plan + reason, then switch to Sonnet to execute** the
laid-out steps cheaply. Version numbers (Opus 4.8, Sonnet 5, Fable 5) are "just release numbers."

## Why this matters for us (relevance, not a build)

- This is the DNA of our own working rules: **verification/real-data (our Rule F)**,
  **self-describing names (Rule C)**, **persist research to files**, **research agents on
  Sonnet**, and the **LLM cost-routing ladder** memory. Video 7 is the consumer-grade version of
  our (stricter) model-routing discipline — our rule already says main thread stays on Opus,
  research fan-out on Sonnet, mechanical on Haiku, Fable only on demonstrated shortfall.
- **Loop Engineering + Loop Training Mode** map directly onto our `/loop` and `/schedule` usage
  and our "earn autonomy incrementally, cap retries" instincts.
- **Compound Engineering's 80/20 planning ratio** and *"a good compound note means the next
  agent doesn't relearn the lesson"* = exactly our persist-to-files + memory practice.
- Consistent caveat across the set: **"10x faster" is unmeasured**, videos 4/6/7 contain
  commercial placements, and several headline numbers are unsourced — treat the *techniques* as
  the signal, the *claims/products* as noise.
