# VIII — selective + state-dependent attention  ·  research/126

**Trunk VIII SENTIENCE.** Design doc (Rule D). Sourcing: research/125 (both parts → BUILD; all OSS
candidates dead/immature — `asmo` BSD dead-since-2016, `empyrical` gives state metrics only; no
cognitive-arch package ships attention codelets). This is thin glue over OUR OWN workspace signals.

## The idea
The Global Workspace has limited capacity — not every faculty signal deserves equal entry to the
competition. Two attention mechanisms modulate a contribution's salience BEFORE it competes:
- **Selective attention** — weight by current CONTEXT relevance (market regime): momentum/opportunity
  signals get more attention in a TRENDING regime, less in INDECISIVE; safety always attended.
- **State-dependent attention** — modulate by the system's INTERNAL state (defensive arousal): after
  a loss streak / in drawdown / with the off-switch near, boost attention to SAFETY & RISK signals
  (attend to danger when hurting), damp opportunity.

## Target
`apply_attention(contributions, context) -> list[WorkspaceContribution]` — returns the contributions
with attention-adjusted urgency/relevance (a per-contribution attention weight folded into its
salience inputs), so `GlobalWorkspace.run_cycle` competes the ATTENDED signals.
**Success test:** in a drawdown/loss-streak state a risk signal's salience is boosted above the same
signal in a calm state; in an indecisive regime an opportunity signal is damped; safety is unchanged.

## Component parts (`sentience/workspace_attention.py`, pure)
- **`AttentionContext`** (frozen) — `market_regime` (trending/range/indecisive/unknown),
  `consecutive_losses` (int), `drawdown_fraction` (float ≥0), `off_switch_engaged` (bool).
- **`attention_weight(contribution, context) -> float`** — a multiplier (≈0.5..1.5) on the
  contribution's salience inputs: safety → always 1.0+ (defensive states push higher); risk →
  boosted by drawdown/losses/halt; opportunity → boosted in trending, damped in indecisive & under
  defensive arousal; info → mild.
- **`apply_attention(contributions, context)`** — returns new `WorkspaceContribution`s with urgency &
  relevance scaled by `attention_weight` (clamped 0..1), leaving `is_critical` intact (critical
  safety still wins).

## Wiring (Rule G/N)
`_maybe_run_global_workspace` builds an `AttentionContext` from the REAL state (current session market
regime; recent closed-trade streak / drawdown from the ledger; off-switch state) and calls
`apply_attention(contributions, context)` before `run_cycle`. Dashboard `global_workspace` surface
shows the live attention context (regime, defensive?). Rule N — the attention shaping is visible.

## Verification
- Hermetic (Rule J): drawdown/loss-streak boosts a risk contribution's salience; indecisive regime
  damps opportunity; safety-critical unaffected; weights clamp to [0,1].
- Real-data (Rule F): over the real offline service, build the context from real state, apply
  attention, and confirm the workspace still broadcasts the real dominant signal (goal_integrity) —
  attention shapes competition without breaking the safety-first ordering.

## Atlas impact
selective attention + state-dependent attention 🔴→🟢. VIII 4🟢→6🟢. Overall 45→47/197 (23.9%).
