# Layer 11 Slice 2c — LLM-risk entry-GATE consumer + earn-calibration harness (research/96)

Date: 2026-07-25. Status: DESIGN → build this turn. Tasks: #3 (gate), #4 (harness, blocks #3).
The PRIMARY purpose of Layer 11 slices 1–2: turn the debate `risk_score` (research/100) from
advisory/display-only into a real ENTRY-GATE decision — safely, only after it earns calibration.

## 1. The honesty problem, and the intraday insight that solves it
An LLM risk signal must NOT move real money until it is shown to predict worse outcomes
OUT-OF-SAMPLE. Pairing a mechanism's risk_score with the SAME historical outcomes the debate was
grounded in is circular (the debate read those calibration facts). The only sound test is
**prequential**: risk_score computed at time T, outcomes observed AFTER T.

Key insight — the bot is **intraday-only, every position squared off same day** (CLAUDE.md
non-negotiable), and the debate runs **once/day from memory-up-to-yesterday**. Therefore a LIVE
trade that opens and closes TODAY is scored against a risk_score the debate computed this morning
from data that does NOT include today's trade. Pairing (today's risk_score for mechanism M,
today's live outcome of an M trade) is genuinely prequential and non-circular — no per-record
stamping or experience-schema migration required. **Replay trades are EXCLUDED** (their outcomes
are historical and were in the memory the debate saw → circular).

## 2. Earn-calibration harness (pure, deterministic — no LLM)
`llm_strategy/debate_risk_calibration_harness.py`:
- `RiskOutcomeObservation(risk_score, is_win)` — one prequential pair.
- `score_risk_calibration(observations, min_observations, min_cohort, min_separation, split_threshold)`
  → `RiskCalibrationVerdict(earned, observation_count, high_cohort_win_rate, low_cohort_win_rate,
  separation, split_threshold, note)`.
- Split observations into HIGH-risk (`risk_score ≥ split_threshold`) vs LOW-risk cohorts;
  `separation = low_cohort_win_rate − high_cohort_win_rate` (positive ⇒ risk_score correctly
  flags worse trades). `earned` iff `observation_count ≥ min_observations` AND both cohorts
  `≥ min_cohort` AND `separation ≥ min_separation`. Defaults: 40 / 15 / 0.05, split 0.5.
- Conservative by construction: too little data, or a one-sided risk distribution (no HIGH or no
  LOW cohort), ⇒ NOT earned ⇒ the gate stays inert.

## 3. Prequential observation accrual (no experience-schema change)
`paper_trading/debate_risk_prequential_observation_store.py` — a dedicated tiny SQLite store
(`~/.nse_algo_trader/debate_risk_observations.sqlite3`; DI path seam for tests), rows
`(recorded_at, mechanism_name, risk_score, is_win)`.
- WRITE: in the service's drain loop, for each newly-closed experiment whose `data_provenance ==
  'live'` AND whose mechanism has a risk_score in today's debate risk-map, append
  `(mechanism, risk_score, outcome=='win')`. (Replay/unknown-mechanism ⇒ skipped.)
- READ: `all_observations()` feeds the harness.

## 4. The entry-GATE consumer (all 4 entry sites)
On `LiveUniversePaperState`:
- fields: `debate_risk_score_by_mechanism: dict` (set by the daily debate),
  `debate_risk_calibration_earned: bool` (set from the harness verdict), counters
  `debate_risk_deferred_count`, `debate_risk_sized_down_count`.
- `debate_risk_size_multiplier(mechanism_name) -> float`: the single position-size lever.
  - risk_score absent for this mechanism → `1.0` (no thesis debated).
  - `not calibration_earned` → `1.0` (ADVISORY until earned — safety default).
  - earned AND `risk_score ≥ DEFER_THRESHOLD` (0.75) → `0.0` (full defer; count).
  - earned AND `risk_score ≥ SIZEDOWN_THRESHOLD` (0.55) → `SIZEDOWN_MULTIPLIER` (0.5; count).
  - else → `1.0`.
- WIRED at all 4 sites (2 ORB cash `live_universe_paper_loop`, 2 option
  `option_credit_spread_live_path`), AFTER recalibration+veto+opponent-defer, mirroring their
  pattern: `q = int(q * state.debate_risk_size_multiplier(mech)); if q <= 0: return False`.

## 5. Service wiring
- `_maybe_run_thesis_debate_risk_check`: after debating, set
  `self._state.debate_risk_score_by_mechanism = {a.thesis.mechanism_name: a.risk_score …}` and
  run the harness over the observation store → `self._state.debate_risk_calibration_earned`;
  cache the verdict for the dashboard.
- drain loop: record the live prequential observations (§3).

## 6. Dashboard (Rule N) — decision-visibility, not just presence
Extend the `thesis_debate_risk_panel` surface with the GATE state: `calibration` (earned/learning),
`observations` (accrued prequential count), and `deferred / sized-down` counts — so "is the LLM
actually affecting trades yet?" is answerable at a glance. This is the Rule-K proof that the
consumer is wired into DECISIONS, not display-only.

## 7. Verification
- Hermetic (Rule J): harness cohort math + earned/not thresholds; `debate_risk_size_multiplier`
  branches (absent / not-earned / defer / size-down); store round-trip; a drain-records-live-only
  test (replay/unknown skipped).
- Real-data (Rule F): over the REAL memory + REAL (currently empty) observation store, the
  harness returns NOT earned (insufficient data) and the gate multiplier is 1.0 for every
  mechanism — i.e. the LLM signal is safely inert today; the end-to-end service path runs clean.
  `scripts/verify_layer11_debate_gate_realdata.py`.

## 8. Honest grading + open items (Rule K)
- The gate IS wired into the decision path at all 4 entry sites (NOT display-only) — but is
  correctly INERT until LIVE prequential separation is demonstrated. Grade: "primary consumer
  WIRED + calibration-gated; earns at runtime as live (risk_score, outcome) pairs accrue."
- OPEN (runtime-accrual, market-gated): live sessions must run for the store to fill and the
  harness to earn — like the slice-5b variety accrual / shadow-arm live pass. Tracked (task #3/#4).
- FUTURE: provenance/recency-weighted observations; tune DEFER/SIZEDOWN thresholds + the harness
  min-separation once real accrual exists; per-mechanism (not just global) earned flags.
