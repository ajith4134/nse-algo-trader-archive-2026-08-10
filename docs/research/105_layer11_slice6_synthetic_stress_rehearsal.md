# Layer 11 Slice 6 — Synthetic stress rehearsal (LLM stress scenarios; ties to Layer 7.5)

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 11 slice 6 (BACKLOG). The LAST
generative Layer-11 slice. Reuses the slice-1 `StrategyLlmClient` seam + memory read-model.
Advisory this slice; the rehearsal-EXECUTION consumer is the Layer-7.5 control-arms lab (queued).

## 1. Goal (BACKLOG / MASTER_PROGRESS)
> "Slice 6 — synthetic stress rehearsal (LLM stress scenarios; ties to Layer 7.5)."

Grounded in the bot's REAL weaknesses, the LLM generates concrete adversarial STRESS SCENARIOS —
"what market condition would break this, and how" — each targeting a real vulnerable mechanism,
naming the predicted failure mode and a mitigation. This is the red-team generator; Layer 7.5
(control-arms lab, built next) is what RUNS the scenarios as control arms / rehearsal backtests.

## 2. Why an LLM
Enumerating plausible, mechanism-specific adversarial scenarios ("a gap-down that fakes an ORB
breakout then reverts in a trending-turned-choppy tape") from heterogeneous weakness signals is
generative synthesis, not a fixed rule. Grounded so it targets the bot's ACTUAL failure surface
(its over-confident, negative-edge, clustering mechanisms), not generic market lore.

## 3. Component (Rule C)
`llm_strategy/synthetic_stress_rehearsal.py`:
- `StressScenario(scenario_label, market_condition, targeted_mechanism, predicted_failure_mode,
  mitigation, severity)` — severity ∈ [0,1], clamped on parse.
- `SyntheticStressRehearsal(generated, served_by, scenarios: tuple[...], grounding_facts, note)`.
- `SyntheticStressScenarioGenerator(llm_client, experience_memory)`:
  - `build_grounding_facts()` — the REAL weakness surface: over-confident + negative-edge
    calibration-board rows, VIOLATED assumptions (`evaluate_trading_assumptions`), temporal
    clustering (`outcome_sequence_dependence`), and weak per-regime cohorts.
  - `build_request(facts)` — forces the scenario JSON schema.
  - `generate()` — one grounded LLM call → `SyntheticStressRehearsal` (non-generated on pool
    exhaustion — surfaced as blocked, never a crash).

## 4. Wiring (Rule G) + cadence
- Service `_maybe_run_synthetic_stress_rehearsal(now)` on the daily cadence (after the council),
  caching `_latest_stress_rehearsal`. Best-effort.
- Dashboard surface `synthetic_stress_rehearsal` (Rule N): scenario count, the highest-severity
  scenario's condition + targeted mechanism + severity, served-by.

## 5. Advisory → rehearsal-execution (QUEUED → Layer 7.5, Rule K)
The scenarios are DISPLAY-ONLY this slice. The consumer that RUNS each scenario — replaying the
synthetic condition against the current champion configs and scoring the realised failure vs the
predicted one — is the **Layer 7.5 control-arms lab** (research/95, "build AFTER Layer 11"), which
is not built yet. This slice is the generator; Layer 7.5 is the executor. Explicit hand-off.

## 6. Verification
- Hermetic (Rule J): fake LLM + memory stub → grounding carries the real weakness numbers
  (violated assumption + clustering + negative-edge), schema forced, scenarios parse + severity
  clamps, pool-exhaustion → non-generated.
- Real-data (Rule F): run `generate()` over the REAL 340-experience memory through the real pool →
  real stress scenarios targeting real vulnerable mechanisms.
  `scripts/verify_layer11_stress_rehearsal_realdata.py`.

## 7. Open items (Rule K)
- 🔵 Rehearsal-EXECUTION consumer = **Layer 7.5 control-arms lab** (research/95): replay each
  synthetic scenario against the champion configs, score predicted-vs-realised failure, feed a
  world-model scoreboard. The generator (this slice) hands scenarios to it.
