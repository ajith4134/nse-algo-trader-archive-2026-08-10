# Layer 11 Slice 2 — Debate-as-Risk-Check (design, research/96 slice 2)

Date: 2026-07-25. Status: DESIGN (build follows in the same turn). Owner task: #2.
Builds on slice 1 (`memory_grounded_strategy_analyst`, research/96) and reuses the same
`StrategyLlmClient` seam + swappable free-tier pool. Advisory this slice; the entry-GATE
consumer is calibration-gated and QUEUED (Rule K), exactly like slice 1's gate-consumer.

## 1. Goal (from BACKLOG / MASTER_PROGRESS)
> "bull/bear/risk roles debate a thesis → disagreement score = risk signal wired into the
> entry gate (advisory→gating after calibration)."

Turn a proposed TRADE THESIS (e.g. "keep trading mechanism `post_breakout_trend` — it's
sound") into an independent three-role LLM debate, and distill the debate into a numeric
**risk signal** the entry gate can eventually consume to defer / size-down high-risk entries
(like the opponent-ledger defer, Layer 10 §10).

## 2. Why independent roles, not one call
A single LLM asked to "give bull, bear and risk views" produces CORRELATED positions (one
model, one context). A real debate needs three INDEPENDENT `generate_structured` calls, each
with its own role system-prompt, over the same thesis + the same real grounding facts:
- **BULL** — argue the thesis is sound; strongest supporting evidence.
- **BEAR** — argue it is NOT sound; strongest disconfirming evidence.
- **RISK OFFICER** — ignore upside; judge downside / risk-of-ruin / how bad the tail is.
Each returns a structured `{soundness ∈ [0,1], key_points[], main_risk}` where `soundness`
= "probability this thesis actually works, from my lens." Independence also lets the swappable
pool serve each call (natural failover) and makes the disagreement meaningful.

## 3. The risk math (pure, deterministic, unit-tested — no LLM)
Given the three soundness values `s_bull, s_bear, s_risk ∈ [0,1]`:
- `disagreement_score = max(s) - min(s)` — the debate SPREAD, bounded [0,1]. This is the
  headline "disagreement" number from the backlog. High = the roles fundamentally disagree.
- `adverse_conviction = 1 - mean(s)` — collective skepticism. High = all three lean negative
  (the case pure disagreement MISSES: unanimous "this is bad" is low-disagreement, high-risk).
- `risk_score = clamp(0.5 * disagreement_score + 0.5 * adverse_conviction, 0, 1)` — the
  gate-relevant blend the queued consumer will threshold. Both terms ∈ [0,1] ⇒ blend ∈ [0,1].
Surfacing BOTH is deliberate: `disagreement_score` is the interpretable debate signal;
`risk_score` is what a gate should actually act on. Weights (0.5/0.5) are a documented default,
overridable; they are NOT tuned yet (that tuning is part of earning calibration — §6).

## 4. Grounding (the whole point, same as slice 1)
Each role prompt carries REAL memory facts about the thesis's mechanism, pulled from the
`ExperienceMemory` read-model — the mechanism's calibration row (predicted vs actual win-rate,
over-confidence gap, mean Brier, n) + overall regime context — so the debate is about THIS
bot's real track record, not generic trading talk. The system prompt forbids inventing numbers.
The hermetic test asserts the grounding facts literally appear in each role's request.

## 5. Cadence & architecture — offline debate, cached risk map, fast gate lookup
LLM calls CANNOT run in the intraday hot path (3 calls × N theses, rate-limited free tier) —
that would stall entries across the full universe. So:
- **Offline (daily cadence, alongside the reflection):** the service debates the currently
  ACTIVE theses — the top mechanisms on the calibration board (bounded N, default 3) — and
  caches a `thesis_risk_map: {mechanism_name -> DebateRiskAssessment}`.
- **Advisory NOW:** the map is surfaced on the dashboard (Rule N). No decision consumes it.
- **Gate consumer (QUEUED, calibration-gated — Rule K):** the 4 entry sites do a FAST cache
  lookup of `risk_score` for the candidate's mechanism; a high score (with earned calibration)
  defers / sizes-down. No LLM call in the hot path — the debate is precomputed offline. This
  mirrors how the strategic reflection is daily, not per-tick.

## 6. Advisory → gating discipline (why the gate is not wired this slice)
Same rule as slice 1: an LLM opinion must EARN calibration before it moves real money. The
debate's `risk_score` has to be shown to correlate with worse realized outcomes (high-risk-
scored theses actually underperform) before it can defer entries. Until then it is advisory /
display-only. "Earning calibration" = accumulate `(risk_score, realized_outcome)` pairs over
replayed/live sessions and score whether risk_score separates winners from losers (a §9-style
check). This is the queued follow-up; slice 2 delivers the debate + score + surface.

## 7. Files (Rule C self-describing; Rule G wiring)
- NEW `llm_strategy/thesis_debate_risk_panel.py`:
  - `TradeThesis` (mechanism_name, strategy_tag, claim, stated_win_probability).
  - `RoleVerdict` (role, soundness, key_points, main_risk).
  - `DebateRiskAssessment` (thesis, verdicts, disagreement_score, adverse_conviction,
    risk_score, generated, served_by, grounding_facts, note).
  - `ThesisDebateRiskPanel(llm_client, experience_memory)` with `debate(thesis)` and
    `debate_active_theses(limit=3) -> tuple[DebateRiskAssessment, ...]` (derives theses from
    the calibration board — the bounded active set).
  - pure helpers `compute_disagreement`, `compute_adverse_conviction`, `compute_risk_score`.
- WIRE `dashboard/live_paper_trading_service.py`: `_maybe_run_thesis_debate_risk_check(now)`
  on the daily cadence (right after `_maybe_run_strategic_reflection`), caching
  `_latest_thesis_risk_assessments`; best-effort (no keys/network/empty memory ⇒ untouched).
- SURFACE `dashboard` feature registry: `thesis_debate_risk_panel` surface (per-thesis
  disagreement / risk / served-by) + coverage manifest entry + audit (Rule N).
- TESTS: hermetic (fake LLM canned soundness ⇒ assert math + grounding present + pool-exhaustion
  path) + `scripts/verify_layer11_debate_risk_realdata.py` real-data pass over real memory.

## 8. Verification plan
- Hermetic (Rule J): fake `StrategyLlmClient` returns scripted per-role soundness; assert
  `disagreement_score`/`adverse_conviction`/`risk_score` math, that each role request contains
  the real grounding facts + its distinct role instruction, and that whole-pool exhaustion
  yields a non-generated assessment (dashboard 'blocked', never a crash).
- Real-data (Rule F): run `debate_active_theses()` over the REAL experience memory through the
  real swappable pool (OVHcloud/Groq/…); assert a real three-role debate with a bounded
  risk_score comes back and names a real mechanism from memory.

## 9. Open items tracked to BACKLOG (Rule K)
- Entry-GATE consumer (PRIMARY purpose) — cached-risk lookup + defer/size-down at the 4 entry
  sites, calibration-gated. QUEUED. Slice 2 is "functionally built, purpose-consumer QUEUED."
- Earn-calibration harness — accumulate (risk_score, outcome), score separation, then unlock
  the gate + tune the 0.5/0.5 blend weights.
