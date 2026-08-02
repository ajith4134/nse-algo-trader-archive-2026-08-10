# VIII — higher-order monitoring + indicator scoreboard (🟡→🟢)  ·  research/131

**Trunk VIII SENTIENCE — completes the trunk (13/13).** Design doc (Rule D). Sourcing: research/125 →
higher-order monitoring anchors on **`pybreaker`'s state machine** (closed/open/half-open — reference
the pattern, don't vendor a circuit-breaker for HTTP); indicator scoreboard flagged **`river`**
rolling-metric, but on fit-review river is a heavy streaming-ML framework — our need is a rolling
count/salience per faculty, so BUILD the small primitive referencing river's rolling idea + Elo/
TrueSkill. Both branches → BUILD thin glue over OUR OWN workspace operation.

## The ideas (metacognition — the mind watching itself)
- **Higher-order monitoring** (🟡 `information_diet` → 🟢): monitor the Global Workspace's OWN
  operation — is it igniting too often (no discrimination), too rarely (not functioning), or is it
  starved of faculties? A health state over recent cycles (referencing pybreaker's healthy/degraded
  states).
- **Indicator scoreboard** (🟡 `dashboard_feature_surface` → 🟢): a unified scoreboard scoring each
  faculty's CURRENT contribution (salience) + how often it has been the dominant broadcast — the
  workspace's own dashboard of its specialists, ranked.

## Targets
- `assess_metacognition(cycle_log) -> MetacognitionReport` where `cycle_log` = recent
  `(ignited, faculty_count)` — ignition-rate + a health state. Success test: an all-ignited log →
  "over-igniting"; a never-ignited log → "under-igniting"; a no-faculty log → "starved"; a mix →
  "healthy".
- `build_indicator_scoreboard(contributions, broadcast_history) -> ScoreboardReport` — per-faculty
  current salience + dominance count, ranked. Success test: the most-dominant faculty leads.

## Component parts
- `sentience/workspace_metacognition.py` — `MetacognitionReport`(ignition_rate, cycles_observed,
  mean_faculty_count, health_state, summary) + `assess_metacognition`.
- `sentience/indicator_scoreboard.py` — `IndicatorScore`(source, kind, current_salience,
  times_dominant) + `ScoreboardReport`(scores ranked, leader, summary) + `build_indicator_scoreboard`.

## Wiring (Rule G/N)
The service keeps a small `_workspace_cycle_log` deque of `(ignited, faculty_count)`, appended each
`_maybe_run_global_workspace`. Metacognition reads it; the scoreboard reads the current contributions
+ the broadcast history. Both cached; two dashboard surfaces `higher_order_monitoring` +
`indicator_scoreboard` (Rule N). READ-ONLY metacognitive diagnostics.

## Verification
- Hermetic (Rule J): the health-state classifier (over/under-igniting/starved/healthy); scoreboard
  ranking + dominance counting.
- Real-data (Rule F): over the real offline service, metacognition reports the real ignition
  rate/health and the scoreboard ranks the real faculties (goal_integrity leading).

## Atlas impact
higher-order monitoring + indicator scoreboard 🟡→🟢. **VIII 11🟢→13🟢 — TRUNK VIII COMPLETE.**
Overall built 52→54/197 (27.4%), partial 58→56.
