# VIII — self-model + attention schema  ·  research/128

**Trunk VIII SENTIENCE.** Design doc (Rule D). Sourcing: research/125 → BUILD both (self-model:
`metacognition-skill` 12★ unmaintained, no library; attention schema: ZERO linked code anywhere,
even the 2025 paper; no cognitive-arch package ships either). Thin glue over OUR OWN state.

## The ideas
- **Self-model** — the system's explicit model of ITSELF: "what am I right now?" — calibration
  health, which mechanisms it trusts vs distrusts, its safety posture, recent performance. A machine
  that acts autonomously should be able to report its own condition.
- **Attention schema** (Graziano's Attention Schema Theory) — a model of the system's OWN attention:
  what the Global Workspace is currently attending to and how attention is distributed. AST's claim
  is that modelling one's own attention is the substrate of subjective awareness; here it is a
  concrete introspective read over the workspace + attention context.

## Targets
- `build_self_model(facts) -> SelfModel` — from real cached state (interpretability reliable-share,
  vetoed/red-flag mechanisms, constitution + off-switch + goal-integrity posture, realized return).
  Success test: over the real memory it reports the true condition (calibration low, distrusted
  mechanisms named, safety posture, drawdown).
- `build_attention_schema(broadcast, attention_context, contributions) -> AttentionSchema` — what the
  workspace is attending to + the attention distribution by kind. Success test: reflects the real
  dominant focus (goal_integrity/safety) + the real regime/defensive context.

## Component parts (pure)
- `sentience/self_model.py` — `SelfModel`(frozen: `calibration_reliable_share`,
  `trusted_mechanism_count`, `distrusted_mechanisms`, `safety_posture`
  (compliant/breach/halted), `recent_return_fraction`, `summary`, `is_healthy`) + `build_self_model`.
- `sentience/attention_schema.py` — `AttentionSchema`(frozen: `attending_to` (source),
  `attending_kind`, `attention_by_kind` (dict kind→count), `context_regime`, `is_defensive`,
  `summary`) + `build_attention_schema`.

## Wiring (Rule G/N)
`_maybe_run_global_workspace` builds both after the cycle (read-only self-representations over the
already-collected contributions + broadcast + attention context + cached faculty verdicts) and caches
them. Two dashboard surfaces: `self_model` + `attention_schema` (Rule N — each visible).

## Verification
- Hermetic (Rule J): a self-model over injected facts reports the right posture/trust; an
  attention-schema over a safety broadcast + defensive context reports attending=safety, defensive.
- Real-data (Rule F): over the real offline service, `build_self_model` reports the real condition
  (low calibration, real distrusted mechanisms, compliant posture, ~0 return) and the attention
  schema reports attending=goal_integrity(safety), regime=unknown — honest self-representation.

## Atlas impact
self-model + attention schema 🔴→🟢. VIII 7🟢→9🟢. Overall 48→50/197 (25.4%).
