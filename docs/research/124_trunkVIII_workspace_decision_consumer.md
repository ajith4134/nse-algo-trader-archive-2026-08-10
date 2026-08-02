# VIII — Global Workspace decision-consumer (slice 2)  ·  research/124

**Trunk VIII SENTIENCE — the integrator ACTS.** Design doc (Rule D). Clears the Rule-K primary
consumer queued by slice 1 (research/123): the broadcast was advisory; this makes the dominant
global context actually bias decisions — the "one mind" acting, not just observing.

## The idea → concrete target
When the Global Workspace ignites a dominant broadcast, that global context should influence the
whole system's behaviour (GWT: ignition → global ACCESS). Concretely: when the integrated dominant
focus is a SAFETY or RISK concern, entries are trimmed (trade smaller while the mind's focus is
cautionary); a non-cautionary focus never changes sizing. **Safety-first + tighten-only.**

**Target:** `LiveUniversePaperState.workspace_caution_multiplier() -> float` in [0,1], applied at all
4 entry sites (like `debate_risk_size_multiplier`). **Success test:** over the real memory, where the
dominant broadcast is the `goal_integrity` safety concern, the multiplier trims size (<1.0) and the
count increments; with no ignited cautionary broadcast, it is 1.0 (no change).

## Design decision — tighten-only, safe-by-construction (no calibration gate)
The slice-1 backlog note said "calibration-gated (reuse the debate-risk earn harness)". On reflection
the correct, safer design is **tighten-only**: the consumer can only REDUCE size on a cautionary
dominant signal, never increase it. That is conservative by construction (trimming risk can't make
the system less safe), so — like the opponent-ledger defer and the constitution gate (both un-gated,
verified signals), and UNLIKE the LLM advisories (debate/allocator/council, which are calibration-
gated because they could loosen behaviour) — it is safe to be active without an earn-harness. The
inputs are the already-verified VII safety detectors, not opinions.
- **Deviation from slice-1's note, recorded (Rule K):** a future OPPORTUNITY-LOOSENING variant (a
  dominant high-conviction opportunity RELAXING sizing) WOULD need the calibration gate; that stays
  queued. Only the tightening half ships now.

## Multiplier (kind-based, interpretable)
- dominant broadcast is `None` or not `ignited` → **1.0** (nothing dominant).
- ignited & `kind == "safety"` & `is_critical`-content → **0.0** (defer; belt-and-suspenders with
  the off-switch, which a critical safety signal also engages).
- ignited & `kind == "safety"` → **0.75** (trade at 75% while a safety concern is the global focus).
- ignited & `kind == "risk"` → **0.90** (mild trim on a risk-flavoured dominant focus).
- else (opportunity/info) → **1.0** (never loosen).

## Wiring (Rule G/N — wired-into-DECISIONS, the whole point)
- Service pushes `_latest_workspace_broadcast` onto `state.workspace_broadcast` each pass (after the
  workspace cycle, before scans).
- `workspace_caution_multiplier()` reads it; multiplies `clamped_quantity`/`lots` at ALL 4 entry
  sites (2 cash + 2 option), after the existing gates; counts applications + total size-downs.
- Dashboard `global_workspace` surface extends to show the live caution multiplier + how many
  entries it has trimmed — so the integrator's ACTION is visible (Rule N).

## Sourcing (Rule I / option-3 — honestly recorded)
This is project-specific decision wiring (multiply the order size by an integrated caution factor at
our own entry sites), exactly like the existing `debate_risk_size_multiplier` / opponent-ledger
consumers. No OSS applies — there is no third-party "bias my order size by my own global-workspace
broadcast" library; `sourcing-oss-parts` is N/A for bespoke internal glue. Reuses the project's own
entry-gate + multiplier idiom.

## Verification
- Hermetic (Rule J): a state with an ignited safety broadcast → multiplier 0.75 (0.0 if critical),
  risk → 0.90, none/opportunity → 1.0; counters increment; the entry-site integer clamp trims size.
- Real-data (Rule F): the real offline service — its workspace broadcasts `goal_integrity` (safety);
  assert `workspace_caution_multiplier()` < 1.0 on the real state (the integrator actually trims).

## Atlas impact
No NEW branch (the 4 VIII branches are already 🟢) — this CLEARS slice-1's Rule-K primary consumer,
turning the integrator from advisory into wired-into-decisions. Honest grade: VIII slice 1 becomes
fully done (integrator built AND acting); the opportunity-loosening + coalition refinements stay queued.
