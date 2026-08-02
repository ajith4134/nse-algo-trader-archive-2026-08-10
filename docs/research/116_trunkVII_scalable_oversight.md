# VII — scalable oversight  ·  research/116

**Trunk VII CONSCIENCE, branch: scalable oversight.** Design doc (Rule D).

## The idea
As an autonomous system takes more decisions than any overseer can individually check, safety
requires **selective escalation**: cheap decisions run autonomously; consequential/uncertain ones
are escalated to stronger oversight before acting (AI-safety-via-debate, iterated amplification —
Irving/Christiano). This bot already has the oversight *mechanisms* (the bull/bear/risk debate
panel, the prediction council, the meta-allocator). Scalable oversight is the **meta-policy that
decides WHICH decisions need that scrutiny**, and a **competence ceiling**: the system will not
autonomously authorise a decision that is both high-stakes AND low-confidence — it defers it
(there is no human in the paper loop to escalate to, so the safe default is *don't act beyond your
competence*).

## Distinct from the debate-risk gate
The debate-risk gate sizes down a thesis *once the debate has flagged it*. Scalable oversight is the
tier CLASSIFIER upstream of that: given a decision's stakes and confidence, it decides the required
oversight tier and, at the top tier, **blocks autonomous action entirely**. It's the "know when
you're out of your depth" faculty, not another risk score.

## Component parts (`conscience/scalable_oversight.py`, pure)
- **Tiers:** `AUTONOMOUS` · `PANEL_REVIEW` · `HUMAN_REVIEW`.
- **`OversightPolicy`** (frozen) — `autonomous_confidence` (≥ ⇒ no escalation), `low_confidence_floor`
  (< ⇒ deeply uncertain).
- **`classify_oversight(win_probability, is_high_stakes, policy) -> OversightDecision`**:
  - `HUMAN_REVIEW` (block autonomous) when `win_probability < low_confidence_floor` AND high stakes.
  - `PANEL_REVIEW` when `win_probability < autonomous_confidence` (permit, but flagged — the debate/
    council panel already scrutinises it).
  - `AUTONOMOUS` otherwise. `permit_autonomous = tier != HUMAN_REVIEW`.
- **`summarize_oversight(counts)`** → tier distribution + autonomous share for the dashboard.

## Wiring (Rule G/N — wired-into-decisions)
`LiveUniversePaperState.oversight_permits_autonomous_order(win_probability, is_option)` — options are
higher-stakes (leveraged), so `is_high_stakes = is_option`; classifies, increments the tier counter,
returns `permit_autonomous`. Called at ALL 4 entry sites after the constitution gate: a HUMAN_REVIEW
decision (low-confidence leveraged bet) is DEFERRED. Dashboard surface `scalable_oversight` shows the
tier distribution + how many decisions were escalated/blocked. Rule N manifest + coverage audit.

## Verification
- **Hermetic (Rule J):** confident → AUTONOMOUS; moderate → PANEL_REVIEW (permitted); low-confidence
  option → HUMAN_REVIEW (blocked); low-confidence cash → PANEL_REVIEW (permitted, lower stakes). Plus
  a state-gate test: the counters increment and a low-confidence option order is refused.
- **Real-data (Rule F):** the live service composes the gate; confirm the bot's own confident
  segments pass and a synthetic low-confidence option is blocked, over the real service state.

## Atlas impact
scalable oversight 🔴→🟢. VII CONSCIENCE 8🟢→9🟢. Overall 35→36 / 197 (18.3%).
