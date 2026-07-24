# Research/52 — Information diet (accounting) · §10 institution feature

**Layer 10 · §10 · the last institution feature.** Rule D design doc.
(PLAN §10 order: assumption registry ✓, opponent ledger ✓, **INFORMATION DIET**,
epidemiology→antibody ✓.) "Information-diet-DIRECTED research targeting" is a
separate item parked to Layer 11 — NOT this.

## 1. What it is
Account for WHAT information the bot actually consumes to make each entry decision,
and whether that diet is healthy — so an over-reliance on one source, or (worse) the
whole Layer-10 learning apparatus NOT influencing any trades, is visible. Self-
awareness of the decision inputs, an institution-grade discipline.

## 2. The information sources feeding an entry decision
Each candidate entry is shaped by:
- **ADX regime confidence** — the base §9 win-probability (used by 100% of decisions).
- **Opponent ledger** — participant-wise OI positioning; engages when it DEFERS an
  entry (positioning_deferred_count).
- **Memory antibody** — a refuted mechanism's veto (vetoed_entry_count).
- **Memory recalibration** — a learned bias offset actually moved the win-probability
  (recalibrated_entry_count).
- **Shadow probe** — a vetoed mechanism opened for recovery evidence (shadow_entry_count).

These counters ALREADY flow through the loop/state; information-diet accounting is the
aggregation + a health read over them, plus a denominator.

## 3. Design (Rule C, Rule G, Rule K)
- Loop state: add `entry_decisions_considered` (the denominator), incremented once per
  candidate at the single choke point `apply_recalibration` (called at all 4 entry
  sites right after a prediction record is built).
- `paper_trading/information_diet.py` (pure): `read_information_diet(considered,
  positioning_deferred, antibody_vetoed, memory_recalibrated, shadow_probes) ->
  InformationDiet` — per-source influence counts + shares of `considered`, a
  `memory_influence_share = (vetoed+recalibrated+shadow)/considered`, and a
  `health_status` ∈ {gathering, healthy, warning} with a note.
  - **gathering** below a min sample (20 decisions).
  - **warning** when, after enough decisions, `memory_influence_share == 0` (the bot
    trades purely on the base ADX signal — 213 learned experiences change NOTHING) OR
    the opponent ledger never engages while divergences existed. This is the unhealthy
    "mono-diet / inert-learning" case.
  - **healthy** otherwise.
- **Consumer (Rule K — a decision/alert, not decoration):** `monitoring_alerts` raises
  a WARNING when the diet is unhealthy (surfaced in the alert feed the operator acts
  on — the same channel as the antibody/overnight alerts); plus an "Information diet"
  dashboard panel showing each source's influence share. The alert makes a real
  problem (the learning apparatus not affecting trades) loud.

## 4. Wiring
service publishes the diet (from state counters) → read model → server → panel +
alert. `entry_decisions_considered` is the only new state field; the rest are existing
counters.

## 5. Verify
- Hermetic: `read_information_diet` shares + health verdicts (memory-inert → warning;
  balanced → healthy; small sample → gathering).
- **Rule F:** run the replay-when-closed loop (market closed now) so real entry
  decisions accumulate, and read the real diet from the live state/counters (the
  memory veto/recalibration are active on the real 213-experience memory, so the diet
  reflects real source engagement). Sim harness (Rule J) for the counter aggregation
  where a full replay isn't deterministic.

## 6. After this
This is the last §10 institution feature. With it, Layer 10 is functionally complete;
remaining L10 items are data/market-blocked only (regime-multi data; shadow-arm live
pass). PAUSE per the user before the 24/7 after-hours simulated-live-trading step.
