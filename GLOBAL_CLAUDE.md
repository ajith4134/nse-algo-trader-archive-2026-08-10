# Skill Routing Rule (always active)

Before answering any prompt, classify it and route to the right skill. Do this silently — don't announce the classification, just invoke the skill and follow it.

## Decision procedure

Ask these questions IN ORDER about the user's prompt:

**1. Does answering require facts from outside this machine or my memory?**
Signals: "research", "find out", "look up", "search", "compare X vs Y", "what's the best/latest", "current price/version/news", any topic that changes over time, any claim I'd otherwise answer from memory that could be stale or wrong.
→ Invoke the `deep-research` skill.

**2. Is the user describing an idea with examples and wanting the FULL space, not just their examples?**
Signals: "all X", "everything like this", "similar ideas", "combine these", "advanced/ultra version", "what else is there", "what am I missing", "like A and B" (where A and B are clearly a sample), brainstorming, planning a project/feature, "let's discuss", vague ideas needing exploration.
→ Invoke the `expand-idea` skill.

**3. Does the prompt need BOTH?** (an idea to expand AND real-world facts to expand it with)
Signals: "research ideas for...", "find all the ways people do X and suggest better ones", planning something that depends on current tools/markets/tech.
→ Invoke `expand-idea` as the outer frame, and use `deep-research` inside it to build the taxonomy from verified sources instead of memory.

**4. Is the user asking to BUILD a feature/idea/branch in an engine-grade project (e.g. nse-algo-trader), but the ask is under-specified?**
Signals: "add X", "build a Y", "make it do Z", "I want a …", "implement …", "what about …" — a short/fuzzy feature request where the design has materially-undetermined axes (the decision it changes, inputs, algorithm class, scope, acceptance metric).
→ Invoke the `idea-to-institutional-spec` skill (forced MCQ clarify → research → institutional spec → hand off to `building-engine-grade-features`). It composes `deep-research`/`sourcing-oss-parts`; if the idea is a sample of a bigger space, run `expand-idea` first, then spec the chosen slice.

**5. Neither?** (already-specified small edit, direct coding task, file edit, quick factual question I'm certain about, running commands)
→ No skill; answer directly.

## Tie-breakers & hard rules

- When in doubt between "answer from memory" and `deep-research`: choose `deep-research`. Stale confident answers are worse than a short delay.
- When the user gives 1–3 examples and says "like", "such as", "for example", or "etc" — that is NEVER a complete list. Treat it as an `expand-idea` trigger: the examples mark the category, not its boundary.
- Explicit `/deep-research` or `/expand-idea` always wins over this rule.
- If the user says "quick" / "just tell me" / "no research", skip the skills and answer directly — but flag anything that might be stale.
- A prompt can escalate mid-conversation: if a direct answer reveals the user actually wants breadth or verified facts, switch to the right skill then.
