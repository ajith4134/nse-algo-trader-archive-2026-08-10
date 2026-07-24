# 46 — Shadow-Arm Recovery for Vetoed Mechanisms (Layer 10 slice 4 design)

Design note (Rule D) before building. Closes a real gap in the slice-3 antibody.

## The problem the antibody creates
Slice 3's auto-veto HARD-skips a statistically-refuted mechanism's new entries.
But a hard veto is a **permanent lock-out**: the mechanism stops trading → no
new experiences are recorded → its calibration is frozen at "refuted" → it can
NEVER recover, even if the market regime changes and the thesis becomes valid
again. This is the classic exploration-vs-exploitation trap.

## Sourcing (gate)
Considered: multi-armed-bandit libs (epsilon-greedy/UCB) and champion/challenger
/ shadow-deployment patterns. Bandit libs solve probabilistic *action selection*,
not "keep a small sample of a vetoed arm alive + recency-window re-evaluation" —
that is domain glue over our existing memory. Build from scratch; borrow the
*concept* (shadow/challenger arm + recency).

## Design (two coupled parts)
1. **Shadow-probe sampling (keep evidence flowing).** When a mechanism is
   vetoed, do NOT skip 100%. A small deterministic fraction (every Kth vetoed
   entry for that mechanism, `_SHADOW_PROBE_EVERY`) is opened anyway as a
   **shadow probe** — a normal paper trade that runs to a real outcome and is
   recorded as an experiment, but counted separately (`shadow_entry_count`) so
   the operator sees it is a low-conviction probe, not full deployment. The
   remaining entries stay vetoed (`vetoed_entry_count`). Deterministic (per-
   mechanism counter, not RNG) so it is testable.
2. **Recency-window veto (enable recovery).** The veto decision moves from
   all-time calibration to a **recent window** per mechanism (its last
   `_VETO_RECENCY_WINDOW` experiments). A mechanism trips when its RECENT window
   is significantly over-confident; shadow probes refill that window with fresh
   outcomes; if the recent window becomes calibrated again, the significance
   test no longer trips and **the veto lifts automatically**. The Reflection
   panel still shows all-time calibration (full history); only the veto uses the
   recent window.

Result: predict → record → refute → veto (mostly) BUT keep probing → if the
regime changed and the thesis recovers, the recent evidence lifts the veto. No
permanent lock-out; no un-refuted mechanism trades at full size.

## Changes
- `memory_reflection`: add a recency-windowed calibration query (per mechanism,
  last N by `occurred_at`, via a SQLite window function) + `vetoed_mechanisms`
  uses it (window param, default = recency window).
- `live_universe_paper_loop`: state gains `shadow_probe_counter` (per mechanism)
  + `shadow_entry_count`; the veto check becomes "veto UNLESS this is the Kth
  probe → open as shadow." Applies to cash + option paths.
- `dashboard`: tripwire panel shows "probing N to allow recovery" alongside the
  antibody line.

## Verification (Rule J — market closing, real live data ending)
Hermetic sim harness: inject synthetic experiences into a fake/real memory,
drive the loop via `_FakeFeed`, assert: (a) a vetoed mechanism opens ~1/K
shadow probes (deterministic), (b) after enough calibrated recent shadow
outcomes the recency-window veto LIFTS. Fakes stay test-only (Rule J isolation).
**Real-data pass (Rule F) remains an OPEN BLOCKER** until the next open session
shows a real vetoed mechanism probing + recovering.
