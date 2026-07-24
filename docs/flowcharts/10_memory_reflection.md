# 10 — Memory & Reflection (Layer 10)

**Status:** slice 1 built + Rule-F verified (2026-07-24). The AI phase begins:
the MEMORY / EPISTEMICS / PREDICTIVE trunks start blooming on the real
prediction-error stream the §9 lab produces. Design + substrate research:
`../research/43`.

## Whole-pipeline data flow so far
```
[L7 live loop] closes a trade
   grade_prediction(record, pnl) -> GradedPrediction  (+ scoreboard, §9 tables)
   emits (graded, ClosedPaperTrade, instrument_kind)  -> state.closed_experiment_events
        │  (a plain tuple — the L7 loop never imports L10)
        ▼
[L9 dashboard service, writer thread]
   _drain_closed_experiments_into_memory():
     build_closed_experiment(graded, trade, kind) -> ClosedExperiment
        │
        ▼
[Layer 10: memory_reflection/]
   ExperienceMemory (swappable substrate boundary)
     SqliteExperienceMemory.record_closed_experiment(ClosedExperiment)
       -> typed experiment node (categorical edges flattened + indexed)
   queries: calibration_for(strategy, regime) · prior_outcomes_for(...) ·
            reflection_diff(recent_window_start)
        │
        ▼
   (-> dashboard "Reflection" surface — next increment)
```

## Files
```
src/nse_algo_trader/memory_reflection/
├── __init__.py
├── experience_memory.py          # ExperienceMemory protocol + ClosedExperiment
│                                  #   + build_closed_experiment + summary types
└── sqlite_experience_memory.py    # SqliteExperienceMemory (v1 backend)
tests/test_memory_reflection/test_experience_memory.py   # 6 tests
```

## Exports / shapes
- `ClosedExperiment` — one memory node: experiment_id, occurred_at (bi-temporal
  recorded_at in store), session_date, and the categorical edges flattened —
  strategy_tag, mechanism_name, regime_context, instrument_token,
  instrument_kind, assigned_table, direction — plus prediction-vs-outcome:
  predicted_outcome, win_probability, actual_outcome, prediction_was_correct,
  brier_contribution, realized_pnl, realized_return_fraction,
  predicted/actual exit cause, kill_criteria.
- `ExperienceMemory` (Protocol): `record_closed_experiment`, `experiment_count`,
  `calibration_for(strategy, regime) -> CalibrationSummary`,
  `prior_outcomes_for(strategy, mechanism, regime, kind) -> PriorOutcomeSummary`,
  `reflection_diff(recent_window_start) -> list[ReflectionDiffRow]`.
- `build_closed_experiment(graded_prediction, closed_trade, instrument_kind)`.
- `SqliteExperienceMemory` (v1) — one `.db` at
  `~/.nse_algo_trader/experience_memory.sqlite3`; indexes on
  (strategy, regime), (strategy, mechanism, regime, kind), (occurred_at).

## Substrate decision (research/43)
Swappable `ExperienceMemory` over **SQLite for v1** — NOT Graphiti/Neo4j yet.
Our §9 data is already structured (Graphiti's LLM entity-extraction from text
is wasted cost + needs a Neo4j server); Kùzu is deprecated; the three query
patterns are categorical aggregations, not multi-hop/semantic. A Graphiti/
Neo4j temporal-KG implementing the SAME protocol is the **named future
consumer** (Rule G) for the semantic / multi-hop-traversal tier.

## Verification (Rule F — real data, 2026-07-24)
Ran the live loop over the real universe; 48 catch-up closes emitted 48 closed
§9 experiment events, all recorded as real memory nodes. The three queries ran
on the real stream and surfaced a genuine calibration signal: the confident-win
**"post-breakout trend continuation"** mechanism ran at **0.05 hit rate** (n=38)
today while the confident-loss **"false breakout into chop"** thesis held at
**0.75** (n=4) — i.e. the memory immediately caught that today's trend-
continuation predictions were miscalibrated. Unit: 6 tests; suite green.

## Remaining slices (queued — Rule G named consumers)
- Record OPTION experiments too (directional + credit-spread closes) — same
  builder, add the option close-paths' graded pairs.
- Dashboard "Reflection" panel: calibration-by-regime board + nightly reflection
  diff (the CONSCIENCE/EPISTEMICS transparency surface).
- Nightly reflection job at session end (writes the diff snapshot).
- Then slice 2: assumption registry + statistical tripwires; slice 3: opponent
  ledger (needs participant-wise OI — per Rule I, acquire that data from the
  NSE participant-wise OI source, don't skip the feature).
- Swap-up path: Graphiti/Neo4j `ExperienceMemory` when semantic/multi-hop
  retrieval is needed.

## Surfacing complete (2026-07-24) — options + Reflection panel
- **Option experiments (Rule I):** options were only display-labeled; now the
  directional-option and credit-spread paths carry real §9 prediction records
  (`prediction_lab/option_prediction_records.py`: directional confidence rises
  WITH ADX, credit-spread confidence rises as ADX FALLS), are graded into the
  scoreboard, and emit closed experiments into memory — so cash AND options
  populate calibration/reflection. Rule-F verified: 14 directional-option
  closes → 14 graded §9 experiments across stock+index options.
- **Reflection panel:** `SqliteExperienceMemory.calibration_board` (per
  strategy×mechanism: predicted vs actual win-rate + Brier, ordered by the
  over-confidence gap) is published by the service and rendered as the
  dashboard "Reflection — mechanism calibration" panel. The EPISTEMICS
  transparency surface — it shows, live, which theses the bot's predictions
  are miscalibrated on (large predicted−actual gap).

## Slice 2 (2026-07-24) — Assumption registry + statistical tripwires
`assumption_registry.py`: `evaluate_trading_assumptions(memory)` gives every
live mechanism two significance-tested assumptions:
- **calibration** — actual win-rate not *significantly* below predicted
  (one-sided normal-approx binomial z; trips on over-confidence), and
- **edge** — mean per-trade return not below a small negative floor.
Only trips with ≥12 trades (never on noise). Wired: the service publishes the
verdicts; the dashboard shows an "Assumption tripwires" panel (VIOLATED first)
and `monitoring_alerts` raises a WARNING per tripped assumption — the bot's own
antibody signal. **Verified:** the trend-continuation mechanism (predicted 85%,
actual 0%, n=18) trips the calibration wire (z≈-9) and raises the alert. 4 unit
tests (`test_assumption_registry.py`).
Next: slice 3 — feed a tripped assumption back to VETO that mechanism's new
entries (epidemiology→antibody automation, PLAN §10); opponent ledger (needs
participant-wise OI — acquire per Rule I).

## Slice 3 (2026-07-24) — Antibody auto-veto (the feedback loop closes)
`assumption_registry.vetoed_mechanisms(memory)` returns the mechanisms whose
calibration assumption is statistically tripped. The service sets
`LiveUniversePaperState.vetoed_mechanisms` each pass; the L7 loop (cash ORB +
option directional/spread) checks `is_mechanism_vetoed(mechanism)` BEFORE
placing any order and skips it (incrementing `vetoed_entry_count`) — so a
refuted thesis stops taking new entries. The memory now feeds back into the
trading gate: predict → record → refute → **veto**. Dashboard shows the active
antibody (mechanisms vetoed · entries blocked) on the tripwire panel.
Verified: a loop pass with the ORB mechanism vetoed opens 0 positions (control
opens 1); `vetoed_mechanisms` lists a tripped thesis and excludes a calibrated
one. 302 suite green.
**Queued next:** a shadow-arm so a small trickle of vetoed-mechanism trades
still record experiences (recovery/exploration, avoids permanent lock-out);
opponent ledger (needs participant-wise OI — acquire per Rule I).

## Slice 4 (2026-07-24) — Shadow-arm recovery (no permanent lock-out)
Slice 3 could veto a mechanism forever: once vetoed it took no entries, so it
could never generate the fresh evidence needed to earn its way back. Slice 4
closes that with two coupled changes.

**(a) Recency-window veto — the veto can lift.**
`experience_memory.calibration_board(..., recency_window: int|None)` now scores
only a mechanism's most-recent N experiments. In SQLite:
`ROW_NUMBER() OVER (PARTITION BY mechanism_name ORDER BY occurred_at DESC) AS rn
... WHERE rn <= ?`. `assumption_registry.vetoed_mechanisms` judges on this
window (`AssumptionConfig.veto_recency_window = 40`), so a mechanism that was
refuted on old trades but has recovered on its recent trades **auto-un-vetoes**
— the all-time board still keeps the full history for display.

**(b) Shadow probes — a trickle of evidence keeps flowing.**
`LiveUniversePaperState.entry_decision_for_mechanism(name) -> "open"|"shadow"|
"veto"`. Not vetoed → `open`. Vetoed → every 8th entry (`_SHADOW_PROBE_EVERY`)
returns `shadow` (a real position opens, counted in `shadow_entry_count`), the
other 7 return `veto` (blocked, `vetoed_entry_count`). So a vetoed mechanism
still records ~1/8 of its would-be experiences, giving the recency window
something to recover on. The 6 veto call sites (4 cash ORB/breakout, 2 option
directional/spread) switched from `is_mechanism_vetoed` to
`entry_decision_for_mechanism(...) == "veto"`.

**Data flow:** predict → record → refute → veto (with 1/8 shadow probes) →
recent evidence recovers → veto lifts. `shadow_entry_count` is published
through the snapshot → read model → server → the antibody note ("N shadow
probes kept alive to allow recovery").

**Files touched:** `memory_reflection/experience_memory.py`,
`memory_reflection/sqlite_experience_memory.py`,
`memory_reflection/assumption_registry.py`,
`paper_trading/live_universe_paper_loop.py`,
`paper_trading/option_credit_spread_live_path.py`,
`dashboard/live_paper_trading_service.py`, `dashboard/dashboard_read_model.py`,
`dashboard/dashboard_server.py`, `dashboard/render_dashboard_html.py`.
Design: `docs/research/46_shadow_arm_recovery_design.md`.

**Verified — functionally (sim harness, Rule J):** 305 suite green, incl.
`entry_decision_for_mechanism` (not-vetoed→open; vetoed→veto ×7 then shadow on
the 8th; probe opens a real position) and recency-window recovery (30 old
losses veto `trend`; 40 recovered recent experiences lift it while the all-time
board keeps the loss history). **Real-data pass is an OPEN BLOCKER** — live
shadow-probe counts / a real refute→recover cycle over a market session need an
open market (Rule F); sim verifies function only, not the real-data sign-off.
**Queued next:** opponent ledger (needs participant-wise OI — acquire per
Rule I); Graphiti/Neo4j substrate swap-up; borrow python-prediction-scorer
proper scoring rules (research/44).

## §10 institution feature — Opponent ledger (2026-07-24, participant-wise OI)
The first §10 "institution feature": read NSE's daily participant-wise open
interest (Client/DII/FII/Pro) as an **opponent ledger** — "who is on the other
side?" A multi-day *confirmation* input, never an intraday trigger.

**Data acquired (Rule I, research/47):** NSE archives
`https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv`
— a browser `User-Agent` header is the entire anti-bot handshake for the
archives host (no cookie/OTP dance); HTTP 404 = holiday/not-yet-published; EOD
~19:00 IST; it is an **archived file fetchable market-closed**, so a real Rule-F
pass is achievable now. File = 1 preamble line, 15 trailing-space-padded header
columns, 5 rows (Client/DII/FII/Pro/TOTAL); TOTAL long==short is a parse
checksum, not a signal.

**Package `participant_positioning/` (new feature, Rule C names):**
- `participant_positioning_source.py` — the **DI seam** (Rule J):
  `ParticipantPositioningSource` Protocol `positioning_on(date) -> Snapshot|None`;
  typed `ParticipantOpenInterestRow` (14 named OI columns + `future_index_net_long`
  / `index_options_net_call_bias` props) and `ParticipantPositioningSnapshot`. No
  network — importable by tests and read models.
- `nse_participant_positioning_source.py` — the **real adapter**: `urllib` GET with
  a browser UA, `parse_participant_oi_csv` (skip 1 preamble, trim headers, map by
  name, checksum), 404→None. Provenance: URL pattern from nsepython (MIT); UA
  fixed (nsepython's bare `pd.read_csv` is Akamai-blocked), `vol` file + typed rows
  added. Only module that touches the network for this feature.
- `opponent_ledger.py` — `read_opponent_ledger(snapshot) -> OpponentLedgerReading`:
  FII index-fut net (Long−Short) & L/S ratio, Client net (contrarian leg),
  FII-vs-Client divergence in index futures & options, coarse `directional_lean`,
  `retail_on_other_side` (the reversal-trap tell), and a human `headline`.

**Data flow (Rule G wiring):** NSE archives → `NseParticipantPositioningSource`
→ `read_opponent_ledger` → `LivePaperTradingService._refresh_opponent_ledger`
(once per trade date, walks back ≤5 days over 404s, best-effort) →
`opponent_ledger` dict on the published snapshot → `dashboard_read_model` →
`dashboard_server` → the **"Opponent ledger — who's on the other side"** panel
(FII vs Client net + divergence, semantic bullish/bearish/⚠-divergence colors
matching the existing tripwire panel). **Named future consumer:** a later slice
feeds the divergence flag into strategy bias / the assumption registry as an
information-diet input.

**Verified — REAL DATA (Rule F pass):** the real adapter fetched live NSE
(walked back over today's 404), parsed the real 23-Jul-2026 EOD file, derived FII
index-fut net −263,082 (bearish, L/S 0.08) vs Client +167,487 → retail on the
other side. Plus 8 tests: a real-sample parse+derive test (Rule F on trimmed real
bytes) and hermetic ledger derivations through an in-memory fake (Rule J, fake
lives only under tests/). 313 suite green. Unlike live ticks, this EOD source has
NO open-blocker — the real-data gate is fully met now.
**Queued next:** participant-VOLUME file; multi-day FII-net trend (history walk);
wire the divergence into strategy bias / assumption registry.
