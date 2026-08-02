# VIII — coalition formation  ·  research/127

**Trunk VIII SENTIENCE.** Design doc (Rule D). Sourcing: research/125 → BUILD (the only prior art was
the AIOps alert-correlation *pattern* — group co-occurring alerts; no library fits combining our own
concurrent workspace signals). Reference that pattern; build the primitive.

## The idea & upgrade
Slice 1 broadcast a SINGLE winner (with a coalition list computed but unused for ignition). Real GWT
ignition is a COALITION crossing threshold together. Upgrade: when several near-salience contributions
of the SAME kind are co-active, they form a corroborated coalition whose COMBINED salience is
amplified — co-active signals reinforce and ignite more readily (e.g. goal-integrity + red-team +
wireheading all firing = a stronger safety coalition than any alone).

## Component parts (`sentience/coalition_formation.py`, pure)
- **`Coalition`** (frozen) — `members` (sources within ε of the top), `kind` (the winner's kind),
  `base_salience`, `combined_salience`, `corroborating_count` (same-kind members), `is_corroborated`.
- **`form_coalition(scored, epsilon, per_member_bonus=0.05, cap=0.20) -> Coalition`** — `scored` =
  `[(contribution, salience)]` desc; members within ε of the top; `combined_salience = base +
  min(cap, per_member_bonus·(corroborating_count−1))`, clamped ≤1.0. A lone winner → combined == base.

## Wiring (Rule G/N)
`GlobalWorkspace.run_cycle` uses `form_coalition` instead of the inline coalition list: the broadcast
carries the coalition members AND its ignition test uses `combined_salience` (a corroborated coalition
ignites more easily). `WorkspaceBroadcast.salience` becomes the combined salience; `coalition` the
members. The dashboard already shows the coalition; it now reflects amplification. No new surface.

## Verification
- Hermetic (Rule J): two same-kind near-salience contributions → corroborated, combined > base, and
  a coalition that individually sub-threshold ignites once amplified; a lone winner → combined==base;
  amplification capped + clamped ≤1.0; different-kind near contributions don't corroborate.
- Real-data (Rule F): the real workspace still broadcasts goal_integrity; on the real data the safety
  coalition is a single member (goal_integrity) so combined==base (no false amplification) — honest.

## Atlas impact
coalition formation 🔴→🟢. VIII 6🟢→7🟢. Overall 47→48/197 (24.4%).
