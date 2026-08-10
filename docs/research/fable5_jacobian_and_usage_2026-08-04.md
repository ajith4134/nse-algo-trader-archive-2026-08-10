# Fable 5 + the "87-year math problem" — verified (2026-08-04)

Deep-research triangulation of a Varun Mayya (@thevarunmayya) Instagram reel claiming
"Fable 5 solved a maths problem impossible for 87 years."

## 1. The claim — REAL (with nuance)
- **Problem:** the **Jacobian Conjecture**, posed by Ott-Heinrich Keller, **1939** (→ 87 yrs in 2026). One of Smale's problems.
- **What happened:** Harvard mathematician **Levent Alpöge**, with Anthropic's **Claude Fable 5** as collaborator (problem suggested by Akhil Mathew), found an explicit **counterexample** — a polynomial map ℂ³→ℂ³, constant Jacobian det = −2, **not injective**. 216 chars, fit in one X post, hand-verifiable in ~a day.
- **So "solved" = DISPROVED for dimensions n≥3.** The original 2-D conjecture stays OPEN (per Tao).
- **Human+AI, not autonomous:** AI did the needle-in-haystack search; the human framed it + verified.
- **Disclosure:** informal **X post by Alpöge, ~July 19–21 2026** (NOT an Anthropic blog / arXiv paper). Anthropic's own Fable-5 launch page (2026-06-09) never mentions it.
- **Verification:** **Terence Tao** wrote a public digest (terrytao.wordpress.com, 2026-07-21) treating it as established; Gowers + Lichtman engaged positively. Skeptic Andrew Blumberg: "reveals almost nothing" vs a full proof — caution, not debunk.
- **Do NOT conflate** with the separate OpenAI GPT-5.x disproof of Erdős's ~80-yr unit-distance conjecture (also 2026, different problem/company).
- Sources: Tao blog (A), Secret Blogging Seminar (A-), The Conversation (B+), TheNextWeb/NewsBytes (B), Anthropic launch page (A, silent). Crypto blogs (C, hype packaging).

## 2. The "prompt" — there is no magic one-shot prompt
Every real 2025-26 open-problem AI result used a **multi-stage harness**, not a single prompt:
generate at max reasoning effort → **verify** (Lean/Coq formal, or Python exec, or evolutionary scoring) → refine → **human expert sign-off** (mandatory, every case).
- AlphaEvolve (Tao/DeepMind, arXiv 2511.02864): LLM writes Python → exploit-proof verifier scores → genetic loop over generations.
- AlphaProof (Nature 2025): LM proposes Lean tactics → AlphaZero RL search → every step machine-checked.
- Erdős #728 (Jan 2026): online instance formalizes the prompt → **offline** 2nd instance generates proof (suppress hallucinated recall) → Harmonic **Aristotle** auto-formalizes+verifies in Lean → Tao reviews.
- Reported field trick: "gaslight the model into thinking the problem is tractable" so it attempts instead of refusing.
- **The Oct-2025 embarrassment:** Kevin Weil's "GPT-5 solved 10 Erdős problems" was **literature search**, not new math (Bloom's correction). Canonical cautionary tale.
- Tao's honest aggregate: true AI success rate across 1000+ Erdős problems ≈ "a point or two" %.

## 3. Best-practice prompting for hard reasoning (Anthropic + OpenAI converge)
- Extended/max thinking > manual "think step by step" (drop the latter — redundant, can hurt).
- **Don't over-constrain**: state GOAL + CONSTRAINTS + an explicit **verification contract** ("what counts as done + how to verify"), don't script every step. Over-prescribing narrows the model's own search.
- Don't over-role-play ("world-renowned expert who never errs" hurts). Give permission to express uncertainty.
- Re-tune prompts per new model generation from a minimal base; don't reuse wholesale.

## 4. Using Fable 5 in practice (all Grade-A, live docs)
- **Model id:** `claude-fable-5` (sibling `claude-mythos-5`, invite-only). GA **2026-06-09**.
- **Access:** Claude API `POST /v1/messages`, Bedrock, Vertex, Microsoft Foundry; selectable here as Agent `model: "fable"`.
- **Positioning:** "most capable widely-released; highest ceiling for long-horizon agentic + demanding reasoning." Slowest + priciest. Default heavy model is Opus 5; reach for Fable only when you need the ceiling.
- **Pricing:** **$10 / MTok in, $50 / MTok out** (~2× Opus). 1M context, 128K output.
- **Reasoning effort:** `output_config.effort` ∈ `low|medium|high(default)|xhigh|max`. Thinking ALWAYS on (omit `thinking`; `disabled`/fixed-budget → 400). Max it with `{"effort":"max"}` for hardest tasks; docs note low-effort Fable often beats prior-gen xhigh — sweep on your eval.
- **Gotchas:** `max_tokens` covers thinking+text (budget 64K+ at high effort); check `stop_reason == "refusal"` (HTTP 200, category in stop_details); opt into `betas=["server-side-fallback-2026-06-01"] + fallbacks=[{model:"claude-opus-5"}]`; no temperature/top_p knobs, no assistant prefill; 30-day retention required (no ZDR); a single request can run ~15 min. Hold effort constant within a cached convo (changing it busts the cache).
- Export-control incident (Jun 12 → restored Jul 1 2026) → aggressive refusal classifier on security/cyber work; hence the fallback subsystem.

### Minimal call
```python
import anthropic
client = anthropic.Anthropic()
r = client.beta.messages.create(
    model="claude-fable-5",
    max_tokens=64000,
    output_config={"effort": "max"},
    betas=["server-side-fallback-2026-06-01"],
    fallbacks=[{"model": "claude-opus-5"}],
    messages=[{"role":"user","content":"<goal + constraints + verification contract>"}],
)
```

## Relevance to nse-algo-trader
The verify-and-refine harness pattern = exactly this project's edge philosophy (proof, not blind). For an LLM
strategy/research feature, Fable-5-at-max only for the hardest reasoning step, gated behind the LLM cost-routing
ladder (local → free cloud → paid last); most calls stay on cheaper tiers. See [[feedback_llm_cost_routing_ladder]].
