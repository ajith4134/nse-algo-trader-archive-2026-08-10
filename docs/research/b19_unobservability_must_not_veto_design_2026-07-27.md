# B19 — an observability gap must never HARD-VETO trading (design, 2026-07-27)

**Sourcing note (Rule I / sourcing gate, explicit not silent):** no OSS sourcing pass applies. This is
a defect in this repo's own safety-gate doctrine — the correct behaviour is already stated in
`organism_vitality_gate.py`'s own module comment and simply is not enforced for this signal class.
There is no external library that decides "may my self-health monitor halt my trading". Logged in
`docs/BACKLOG.md`.

## The live outage

All new entries stopped in BOTH segments. Confirmed via the B7 `option_lot_sizing` surface:
`composed size-down = ×0.000` while workspace caution is ×0.90 and debate-risk ×1.0 — by elimination
the organism-vitality lever is 0.0, so `homeostat_permits_order()` is False at all four entry sites.

## Root cause — the gate is vetoing on BLINDNESS, not on failure

Live telemetry for the 13 VITAL components (read from `autopoiesis_homeostat.sqlite3`):

| VITAL component | driving signal | its ACTUAL failure signal |
|---|---|---|
| `thread.live_paper_loop` | `observability_gap:thread_heartbeat = 1.0` | **`thread_not_alive = 0.0`** — the thread IS alive |
| `adapter.multi_broker_historical_bars` | `observability_gap:operational_observation = 1.0` | — |
| `engine.autopoiesis_homeostat` | `observability_gap:operational_observation = 1.0` | — |
| `engine.incident_post_mortem` | `observability_gap:operational_observation = 1.0` | — |
| `session.kite` | — | `broker_token_expired = 0.0` |
| `store.market_data` / `experience_memory` / `safety_incidents` | — | `sqlite_integrity_check_failure = 0.0` |
| `artifact.*` | — | `artifact_load_failure = 0.0` |

**Nothing has failed.** Every declared failure signal reads 0.0. The components are degraded purely
because the system cannot *observe* them — there is no heartbeat instrumentation emitting for the
loop thread, and no operational-observation hook for those engines/adapters.

Sustained `observability_gap:*` readings (charged at `unreadable_signal_severity = 0.5`, the DEGRADED
tier) accumulate through the EWMA long window until `health_index` falls below
`failing_health_index_floor = 0.20`… into the FAILING band, at which point `_acute_veto_reason`
(`organism_vitality_gate.py:248-258`) fires because the worst binding component is VITAL and FAILING
→ `size_multiplier = 0.0`, `permits_order = False`. Live vitality: 0.307 and falling (0.344 → 0.307 →
0.295 observed over ~20 min), `health model armed 0/36`.

## Why this is a defect, by the module's own doctrine

`organism_vitality_gate.py:65-76` already states the exact principle, for the closure-violation case:

> A CRITICAL closure violation prices risk DOWN; it must never veto… gating vetoes on a chronic
> structural fact **halts trading forever**, because the fact stays true until a human changes the
> architecture.

An observability gap is precisely such a chronic structural fact: no heartbeat instrumentation exists
for these components, so the gap stays true until someone builds it. The doctrine was applied to
closure violations and **not** to observability gaps — which is the bug. The comment even records that
this class of error is only visible on real data, which is exactly how it surfaced here.

Corroborating: `component_health_index.py` already documents the intended severity semantics —
*"Unreadable telemetry is a genuine loss of observability, not a healthy reading — but it is **not
proof of failure either**, so it is charged at the DEGRADED tier rather than the FAILED tier."* The
severity charge honours this; the **veto decision does not**.

## The change

In `organism_vitality_gate.py`, an ACUTE veto additionally requires **evidence of actual failure**.
If the worst binding component's degradation is driven *entirely* by `observability_gap:*` signals,
the gate must fall through to the size-down path instead of vetoing.

- New helper `_degradation_is_only_unobservability(assessment)` — True when every contributing signal
  carrying non-zero severity has the `OBSERVABILITY_GAP_SIGNAL_PREFIX` (imported from
  `component_telemetry_collector`, the existing first-class constant — not a re-declared string).
- `_acute_veto_reason` returns `""` in that case, so the verdict becomes
  `permits_order=True` with `DEGRADATION_SIZE_MULTIPLIER[FAILING] = 0.25`.
- A dedicated reason string so the panel says *"blind, not broken"* rather than a generic size-down —
  the operator must be able to tell the two apart at a glance.

**Resulting behaviour:** the organism that cannot see itself trades **smaller** (×0.25), not **never**.
A genuinely acute failure — `thread_not_alive = 1.0`, `broker_token_expired = 1.0`,
`sqlite_integrity_check_failure = 1.0`, `artifact_load_failure = 1.0` — still vetoes exactly as today.
This narrows the veto to real evidence; it does not remove it.

## Acceptance criteria

1. A VITAL component FAILING **only** on `observability_gap:*` → `permits_order=True`,
   `size_multiplier == 0.25`, reason names unobservability. *(the live case)*
2. A VITAL component FAILING on a genuine failure signal → still `permits_order=False`,
   `size_multiplier == 0.0`. **The veto must not be weakened.**
3. Mixed contributions (a real failure signal AND an observability gap) → still vetoes. Blindness
   never *excuses* an accompanying real failure.
4. Tighten-only invariant preserved: the multiplier never exceeds 1.0 on any path.
5. A SUPPORTING component is unaffected (it never vetoed).
6. Rule-F: on the live server, `composed size-down` leaves 0.000 and new entries resume in both
   segments.

## Verification plan

- Unit tests over the four criteria above, constructing `ComponentHealthAssessment` directly with
  real signal names taken from the live telemetry dump (not invented ones).
- Rule F: redeploy and confirm on the live open market that `option_lot_sizing` no longer reads
  ×0.000 and that `fill_count` advances again.

## Explicitly NOT fixed here (Rule K — tracked, not silently skipped)

- **The observability gaps themselves.** The loop thread emits no heartbeat and the engines/adapters
  no operational observation. This fix stops blindness from halting trading; it does **not** make the
  organism observable. That instrumentation is its own slice → **B20**.
- **The unarmed health model** (`armed 0/36`). Whether a PCA layer that has never armed should carry
  hard-veto authority at all is a separate design question → **B21**.
- `OrganismVitalityGate.dashboard_metrics()` is dead code — the orchestrator's metrics are surfaced
  instead, so the gate's own `vetoed_count` / `sized_down_count` are invisible → **B22**.
