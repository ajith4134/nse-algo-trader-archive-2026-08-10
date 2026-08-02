# VIII — workspace replay / rumination  ·  research/129

**Trunk VIII SENTIENCE.** Design doc (Rule D). Sourcing: research/125 → candidate `cpprb`
`PrioritizedReplayBuffer` (MIT, mature) was flagged "vendor storage primitive", BUT on fit-review it
is a C++/numpy RL replay buffer for batched transition sampling — the wrong shape for "replay a
handful of recent *broadcast objects* to detect a recurring concern", which is a bounded deque + a
Counter. **Verdict: BUILD the small primitive, reference the experience-replay pattern** (a valid
sourcing-oss-parts outcome: found, evaluated, doesn't fit — don't drag a heavy dep for a Counter).

## The idea
Like hippocampal replay / rumination, the workspace revisits its recent broadcast history to
consolidate: if the SAME concern has dominated the workspace across many recent cycles, the mind is
"ruminating" on a persistent, unresolved concern — worth surfacing distinctly from a one-off spike.

## Target
`ruminate(recent_broadcasts, min_history, dominance_fraction) -> RuminationReport` over the service's
existing `_workspace_broadcast_history` (the deque of IGNITED broadcasts fed by the blinker
subscriber). Success test: when goal_integrity has dominated the recent ignited broadcasts, the
report flags `is_ruminating` on goal_integrity with its recurrence fraction.

## Component parts (`sentience/workspace_rumination.py`, pure)
- **`RuminationReport`** (frozen) — `dominant_recurring` (source), `recurrence_count`,
  `recurrence_fraction`, `distinct_concerns`, `is_ruminating`, `dominant_kind`, `summary`.
- **`ruminate(broadcasts, min_history=4, dominance_fraction=0.6)`** — Counter over `winner_source`;
  the modal source is `dominant_recurring`; `is_ruminating` iff history ≥ `min_history` AND its
  fraction ≥ `dominance_fraction` (the workspace keeps returning to it).

## Wiring (Rule G/N)
`_maybe_run_global_workspace` runs `ruminate` over `_workspace_broadcast_history` each pass and caches
the report. Dashboard surface `workspace_rumination` (recurring concern + fraction + is_ruminating).
READ-ONLY diagnostic — the workspace already ACTS each cycle (the caution multiplier); rumination
reports *persistence*, it doesn't need its own actuator (stated at sign-off, Rule K). A future
escalation consumer (persistent safety rumination → stronger caution / forensic note) is a queued
refinement, not owed for this diagnostic.

## Verification
- Hermetic (Rule J): a history dominated by one source → is_ruminating with the right fraction; a
  diverse history → not ruminating; empty/short history → not ruminating.
- Real-data (Rule F): run the offline service long enough to accrue several ignited broadcasts, then
  confirm the report reflects the real recurring concern (goal_integrity dominates → ruminating).

## Atlas impact
workspace replay/rumination 🔴→🟢. VIII 9🟢→10🟢. Overall 50→51/197 (25.9%).
