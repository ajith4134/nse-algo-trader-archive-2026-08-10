# Layer 11 Slice 3 — Causal analysis over multi-hop outcome clusters → assumption registry

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 11 slice 3 (BACKLOG).
Builds on slice 1 (`memory_grounded_strategy_analyst`) and reuses the same `StrategyLlmClient`
seam + swappable pool. Advisory this slice (like slice 1); the decision-consumer is QUEUED.

## 1. Goal (BACKLOG / MASTER_PROGRESS)
> "Slice 3 — causal analysis over multi-hop outcome clusters → assumption registry."

The Layer-10 memory already computes STATISTICAL multi-hop reads but not the WHY:
- `outcome_sequence_dependence` — per mechanism, does it win less AFTER a loss than after a win
  (temporal clustering / non-iid)? (`OutcomeSequenceDependence.dependence_gap`, `clusters`).
- `calibration_by_market_regime` — which mechanisms/strategies fail in which regime (cross-regime).
- `calibration_board` — the over-confident mechanisms; `evaluate_trading_assumptions` — which
  calibration/edge assumptions are VIOLATED.
These say WHAT clusters; none says WHY. Slice 3 adds an LLM `CausalClusterAnalyst` that reasons
ACROSS these per-mechanism/per-regime facts to propose **named, falsifiable causal hypotheses**
for the clusters (a suspected COMMON cause behind co-failing mechanisms), registering them as
tracked causal assumptions that extend the statistical assumption registry with explanations.

## 2. Why an LLM here (not another SQL query)
The existing reads are per-mechanism / per-regime. The causal question — "do mechanisms X and Y
fail for the SAME underlying reason (stops too tight in trends? entering into mean-reversion?
event-day gamma?)" — is cross-cluster synthesis over heterogeneous facts, exactly what an LLM
does well and a fixed query does not. Grounding keeps it honest: the prompt is built ONLY from
the real cluster reads, and the system prompt forbids inventing mechanisms/numbers.

## 3. Component (Rule C names)
`llm_strategy/causal_cluster_analyst.py`:
- `CausalHypothesis(cluster_label, implicated_mechanisms: tuple[str,...], suspected_common_cause,
  falsifiable_prediction, confidence: float)` — one causal assumption: which mechanisms cluster,
  the suspected shared cause, and the concrete evidence that would CONFIRM or REFUTE it.
- `CausalClusterAnalysis(generated, served_by, hypotheses: tuple[CausalHypothesis,...],
  grounding_facts, note)`.
- `CausalClusterAnalyst(llm_client, experience_memory)`:
  - `build_grounding_facts()` — pulls the REAL clusters: over-confident calibration-board rows,
    per-regime calibration cohorts, temporal-clustering mechanisms (`outcome_sequence_dependence`
    where `clusters`), and VIOLATED assumptions (`evaluate_trading_assumptions`).
  - `build_request(facts)` — forces the `CausalHypothesis[]` JSON schema.
  - `analyze()` — one grounded LLM call → `CausalClusterAnalysis` (non-generated on pool
    exhaustion, surfaced as blocked, never a crash — same pattern as slice 1).

## 4. Wiring (Rule G) + cadence
- Service `_maybe_run_causal_cluster_analysis(now)` on the daily cadence (after the reflection),
  caching `_latest_causal_cluster_analysis`. Best-effort (no keys/network/thin memory ⇒ untouched).
- Dashboard surface `causal_cluster_analysis` (Rule N): hypothesis count, the top hypothesis'
  cluster + suspected cause + confidence, served-by.

## 5. Advisory → decision-consumer (QUEUED, Rule K)
Like slice 1, this is ADVISORY. The causal hypotheses are EXPLANATORY (they annotate the
assumption registry with WHY) and generate FALSIFIABLE predictions. The decision-consumer — score
each hypothesis' falsifiable_prediction against incoming outcomes and, once a hypothesis EARNS
confirmation, raise a targeted assumption tripwire / strategy-config nudge — is the queued
follow-up (same advisory→gating discipline as slices 1–2c). Persisting hypotheses for that scoring
is part of that queued step; slice 3 caches the latest analysis in memory + surfaces it.

## 6. Verification
- Hermetic (Rule J): fake LLM + in-memory memory stub (extended with a temporal-clustering row)
  → assert the grounding facts contain the real cluster numbers (regime cohorts + clustering gap
  + violated assumption), the schema is forced, the parsed hypotheses surface, and pool exhaustion
  yields a non-generated analysis.
- Real-data (Rule F): run `analyze()` over the REAL 340-experience memory through the real pool
  (Groq/…) → a real causal hypothesis naming real mechanisms/regimes.
  `scripts/verify_layer11_causal_cluster_realdata.py`.

## 7. Open items (Rule K)
- 🔵 Decision-consumer: falsifiable-prediction scoring → confirmed causal hypothesis → targeted
  assumption tripwire / strategy nudge (calibration-gated). Needs a persistent hypothesis registry.
- 🔵 Grounding enhancement: a dedicated cross-mechanism CO-OCCURRENCE query (mechanisms that fail
  on the SAME sessions), to complement the per-mechanism temporal + per-regime facts.
