# Layer 7.5 Slice 2 — SHADOW-REJECTED arm + Skill-vs-Luck Court (research/95 follow-on)

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 7.5 slice 2 (BACKLOG). Builds on
slice 1's `control_arm_comparison` (RANDOM-CONTROL). Read-only diagnostic; the learning-consumer
(train only on the skill diagonal) stays queued.

## 1. Goal (research/95 queued list)
Two of the control-arm-lab pieces:
- **SHADOW-REJECTED arm** — "what the gate REFUSED would have done." If the refused trades would
  have lost, the gate adds skill; if they would have won, the gate is over-rejecting.
- **Skill-vs-Luck Court** — the verdict pipeline over BOTH arms (random-control + shadow-rejected):
  is the edge directional skill? Is the gate's rejection skillful? What should learning trust?

## 2. The data insight (no new capture needed)
The gate REFUSES entries on VETOED mechanisms (the Layer-10 antibody). Those mechanisms' real
outcomes are ALREADY in memory — the pre-veto experiences plus the Layer-10 shadow-probe trickle
(1-in-N vetoed entries opened for recovery evidence). So the SHADOW-REJECTED arm = the aggregate
real performance of the VETOED mechanisms, and the TAKEN arm = the NON-vetoed mechanisms — both
read straight from the calibration board split by `vetoed_mechanisms(memory)`. Real data, no new
per-session mechanism threading.

## 3. Components (Rule C)
`paper_trading/shadow_rejected_arm.py` (PURE):
- `ArmPerformance(arm_name, mechanisms, experiments, win_rate, mean_return)`.
- `ShadowRejectedAnalysis(taken, shadow_rejected, rejection_adds_skill: bool | None, detail)`.
- `analyze_shadow_rejected_arm(experience_memory, vetoed) -> ShadowRejectedAnalysis` — split the
  calibration board by the veto set, experiment-weight each group's win-rate + mean-return.
  `rejection_adds_skill = shadow_rejected.mean_return < taken.mean_return` (the gate refused the
  worse trades); None when nothing is vetoed yet.

`paper_trading/skill_vs_luck_court.py` (PURE):
- `SkillVsLuckVerdict(directional_skill, directional_detail, rejection_skill, rejection_detail,
  overall_verdict, skill_diagonal_note)`.
- `convene_skill_vs_luck_court(control_arm_comparison, shadow_rejected_analysis) ->
  SkillVsLuckVerdict` — `directional_skill` = the RANDOM-CONTROL edge verdict (real beats random);
  `rejection_skill` = the shadow-rejected verdict (refused-worse); `overall` = skill when
  directional holds and rejection is not counter-productive. The **skill-diagonal note** states
  what learning should train on: taken-and-won + rejected-and-would-lose (the skill diagonal);
  distrust taken-and-lost + rejected-and-would-win.

## 4. Wiring (Rule G) + cadence
- Service `_maybe_run_skill_vs_luck_court(now)` (daily, after the control-arm comparison): compute
  `vetoed_mechanisms(memory)` → `analyze_shadow_rejected_arm` → `convene_skill_vs_luck_court`
  (reusing the cached slice-1 comparison), caching `_latest_skill_vs_luck_verdict`. Best-effort.
- Dashboard surface `skill_vs_luck_court` (Rule N): directional-skill + rejection-skill verdicts +
  the overall + the skill-diagonal note.

## 5. Advisory → learning-consumer (QUEUED, Rule K)
The court is READ-ONLY. The consumer that makes the memory TRAIN only on the skill diagonal
(down-weight taken-and-lost / rejected-and-would-win rows) is the queued follow-up, calibration-
gated — same discipline as the Layer-11 advisory→gating slices.

## 6. Verification
- Hermetic (Rule J): memory stub with a vetoed + a non-vetoed mechanism → assert the arm split +
  weighted aggregates + `rejection_adds_skill`; court combines the two verdicts correctly
  (skill/no-skill/gathering permutations).
- Real-data (Rule F): over the REAL memory + real veto set → the shadow-rejected split + the court
  verdict. `scripts/verify_skill_vs_luck_court_realdata.py`.

## 7. Open items (Rule K)
- 🔵 Learning-consumer: train the memory on the skill diagonal only (down-weight the off-diagonal).
- 🔵 Slice 3 (per-trade pre-mortem) + slice 4 (world-model scoreboard + profit provenance).
