# Layer 11 Slice 5 — Prediction-market council weighting (research/96)

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 11 slice 5 (BACKLOG).
Reuses the slice-1 `StrategyLlmClient` seam + swappable pool + memory read-model, and the
prequential-accrual + earn-then-act discipline of slice 2c. Advisory this slice.

## 1. Goal (BACKLOG / MASTER_PROGRESS)
> "Slice 5 — prediction-market council weighting (multiple roles, track-record-weighted)."

A COUNCIL of distinct forecasting roles each produce a PROBABILITY forecast on a resolvable
proposition, and the council's aggregate is a TRACK-RECORD-WEIGHTED average — roles that have
forecast more accurately in the past carry more weight (a prediction market where each member has
a reputation). This adds diverse, reputation-weighted probabilistic judgment on top of the single
analyst (slice 1) and the adversarial debate (slice 2).

## 2. Components (Rule C)
`llm_strategy/prediction_council.py`:
- `CouncilRole(name, system_instruction)` — distinct lenses: MOMENTUM optimist, MEAN-REVERSION
  skeptic, REGIME realist, RISK-averse. Each forecasts independently (its own LLM call).
- `CouncilMemberForecast(role, probability, rationale)` — probability clamped [0,1] on parse.
- `CouncilForecast(proposition_label, member_forecasts, weight_by_role, weighted_probability,
  simple_mean_probability, generated, served_by, grounding_facts, note)`.
- `PredictionCouncil(llm_client, experience_memory, track_record_store=None)`:
  - `build_grounding_facts()` — the real memory context (over-confident mechanisms, per-regime
    calibration, recent record) each role reasons from.
  - `forecast(proposition_label, proposition_question)` — every role forecasts P(true)
    independently; aggregate = Σ weightᵢ·pᵢ, weights from the track-record store (equal when no
    record). Also reports the simple mean for comparison. Non-generated on pool exhaustion.
- pure `track_record_weights(log_loss_by_role, roles)` — weight ∝ 1/(loss+ε); a role with NO
  record gets the coin-flip baseline (1.0 bit), so unproven roles are neutral, proven-accurate
  roles gain weight, proven-bad lose it. Normalised to sum 1.

`paper_trading/council_track_record_store.py` — per-role prequential accrual: rows
`(role, probability, is_true)`; `role_log_loss()` returns each role's mean log-loss (bits) over
its RESOLVED forecasts — the reputation the weighting reads. Own small `.sqlite3`, DI path seam.

## 3. Wiring (Rule G) + cadence
- Service `_maybe_run_prediction_council(now)` on the daily cadence (after the allocator), caching
  `_latest_council_forecast`. The council forecasts a resolvable proposition — "the current most-
  active mechanism wins its next trade" (grounded in that mechanism's calibration). Best-effort.
- Dashboard surface `prediction_council` (Rule N): weighted vs simple-mean probability, member
  spread, whether weights are reputation-tilted yet, served-by.

## 4. Advisory → resolution/accrual (QUEUED, market-gated — Rule K)
Like slice 2c, the track record accrues PREQUENTIALLY at runtime: when the proposition RESOLVES
(the mechanism's next live trade closes), each member's `(probability, outcome)` is recorded and
the reputations update. Until enough resolved forecasts accrue, weights are equal (weighted ==
simple mean) — the council is a plain ensemble that becomes reputation-weighted as skill is
proven. The resolution-recording consumer + any decision use of the council probability are the
queued follow-ups (market-gated).

## 5. Verification
- Hermetic (Rule J): role-scripted fake LLM → assert each role forecasts independently + carries
  the grounding, probabilities clamp, aggregate = weighted mean, pure weight function (equal with
  no record, tilts toward the low-log-loss role, unproven role = baseline), store round-trip,
  pool-exhaustion → non-generated.
- Real-data (Rule F): run `forecast()` over the REAL memory through the real pool → a real
  council forecast; with an empty track-record store the weighted probability equals the simple
  mean (honest un-tilted state). `scripts/verify_layer11_prediction_council_realdata.py`.

## 6. Open items (Rule K)
- 🔵 Resolution/accrual consumer (market-gated): record each member's `(probability, outcome)`
  when the proposition resolves → reputations tilt the weights over live sessions.
- 🔵 Decision-consumer: use the council's weighted probability as a sizing/veto input,
  calibration-gated (shared earn-harness discipline).
