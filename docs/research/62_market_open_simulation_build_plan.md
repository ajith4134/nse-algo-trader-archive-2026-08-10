# Research/62 — Market-Open Simulation: research-backed BASE-first BUILD PLAN

**Planning doc (Rule D).** Converts the finalized idea (§53 map + §8/§11 additions +
§9/§10 refinements) into a decomposed, sliced, buildable feature, using the completed
sourcing research (§54, §55, §59 [+56–60], §61). Skill: `building-features-from-ideas`
(sourcing step already satisfied by the research pass — cited per part, not re-run).

Nothing here is built yet. This doc is the blueprint; slice 1 starts only on user GO
(Rule A). Every deferral below is mirrored into `docs/BACKLOG.md` + a task (Rule K).

---

## 1. What the research changed vs the idea (the buildable reality)

**Buildable NOW, free, first-party (no license, no blocker):**
- **Point-in-time universe** — daily **bhavcopy 1994+** (which symbols traded that day →
  survivorship-bias-free), `symbolchange.csv` (renames), **F&O bhavcopy 2001+** (which
  names had options that day), `niftyindices.com` press releases 1998+ (index members). (§59, §58)
- **Corporate actions** — NSE `corporates-corporateActions` API via `nselib`, 41,979
  records 1995+ (splits/bonuses/divs/renames), cross-checked vs BSE. (§59, §57)
- **Trading calendar** — `pandas_market_calendars` NSE holidays **1997+** (seed). (§61)
- **Segment inception (verified):** index options **4-Jun-2001**, stock options
  **2-Jul-2001**, index futures 12-Jun-2000. F&O *dissemination archive* starts **Jan
  2003** (a ~2.5y gap vs trading start). (§60)
- **Intraday history we can get cheaply now:** ICICI **Breeze 1-second** historical API
  (cash + options + OI) — the realistic pre-license intraday source; broker 1-min as fallback. (§54)

**Paid (the fidelity ceiling, later):** NSE Data & Analytics license (₹1.1L–31.3L/yr);
true per-order **tick only from ~Dec 2007**, 1995–2007 is trades-only. (§54, §59)

**Permanent blockers (design around, never silently drop — in BACKLOG):**
- True **L3/MBO** live feed — co-location only, impossible for personal use. (§54)
- Historical **order-book DEPTH** — no vendor sells it; **record forward only**. (§54)
- **Intraday participant/FII-DII flow** — EOD-only, forever (→ prev-day context). (§54)
- **Pre-~2010 news at intraday precision** — no archive/API exists; date-level or none. (§61)
- **Rules/calendar point-in-time tables** — no machine-readable dataset; **compile from
  dated NSE/SEBI circulars** (two master-circular anchors give the chain). (§61)

**Consequence:** fidelity is **era-dependent** and highest at *today*, thinning backward
(depth→none pre-record; tick→trades-only pre-2007; news→sparse pre-2010). Every emitted
datum/experience must be **fidelity-tagged** (extends the provenance watermark §8.2), so
calibration trusts a thin 2009 day less than a full 2026 one. This is the spine of the design.

---

## 2. The BASE target (pinned, with a success test) — skill step 1

**Target:** a never-idle **historical-archive replay driver** that walks NSE history
today→inception, and streams any chosen past trading day — at that day's **point-in-time
universe**, through a **leakage-firewalled** causal gate, every datum **provenance +
fidelity tagged** — into the EXISTING paper loop + Layer-10 memory, indistinguishable
from live to the strategy, and turning each step into a **prequential graded prediction**.

**Success test (Rule F, real data):** pick a real past day D (e.g. a 2020 COVID-crash
day). Replay it end-to-end and assert:
1. The universe seen == the symbols that actually traded on D (a since-delisted name
   present if it traded D; a not-yet-listed name absent). *(survivorship test)*
2. At virtual-time T, no datum with timestamp > T is ever observable. *(leakage test)*
3. Every experience written to memory carries `provenance=replay-faithful` + a
   `fidelity_tier`. *(provenance test)*
4. The bot emits a forecast BEFORE each reveal; a log/Brier score accrues into the
   existing scorer over the session. *(prequential test)*
5. Positions open and square off within D; no carry past D's close. *(intraday invariant)*

---

## 3. Decomposition into parts + sourced piece per part — skill steps 2–3

| # | Part (self-describing) | Shape | Sourced piece / verdict |
|---|---|---|---|
| P1 | `historical_trading_day_walker` | today→inception iterator over REAL trading days | `pandas_market_calendars` (BORROW, 1997+) + inception dates §60 |
| P2 | `point_in_time_universe_resolver` | (date)→ set of tradeable symbols+contracts as of that date | BUILD glue over bhavcopy/symbolchange/F&O-bhavcopy/index-press (§58/59) |
| P3 | `corporate_action_adjustment_engine` | keep price continuity across splits/bonuses | `nselib` corporate-actions API (BORROW) + BUILD adjuster (§57/59) |
| P4 | `historical_intraday_replay_source` | stream (ticks/1s bars/OI) for date's universe, as-live | ADAPT existing Layer-2 data seam → ICICI Breeze 1s adapter (§54) |
| P5 | `causal_leakage_firewall` | hard gate: never emit t>virtual-now; rebuild forward | BUILD in Rule-J DI seam; pattern from NautilusTrader clock (§55) |
| P6 | `experience_provenance_and_fidelity_tagger` | tag every datum/experience live/replay + era-fidelity | BUILD thin wrapper (§8.2); feeds info-diet + antibody (§55) |
| P7 | `prequential_forecast_scorer` | predict-then-reveal → log/Brier into existing scorer | River `progressive_val_score` + existing proper-scorer (BORROW, §55) |
| P8 | `never_idle_market_clock` (upgrade of `MarketClockGatedDataSourceRouter`) | one clock: live when open, replay when closed, seamless | ADAPT existing router seam |
| P9 | wire into paper loop + Layer-10 memory + square-off (Rule G) | — | existing loop; BUILD wiring |

Deferred to ADVANCED/ULTRA (behind the depth-record + license dependency), already in map:
hftbacktest queue/fill + market impact (§55), microstructure features frds/tclf/OFI/VPIN
(§55), RL gyms/ABIDES, generative days, purgedcv PBO on the DSR gate, temporal self-play,
deficit curriculum, sleep-consolidation, sim-reality-gap throttle.

---

## 4. Slice sequence (Rule A — one at a time, sign off before next)

- **Slice 1 · Honest clock (P1+P5+P8, thin P6):** walk the calendar, replay ONE real past
  day's *existing* free data (broker 1-min to start) through the router's replay seam
  behind the leakage firewall, tagging provenance. Success test #2,#3,#5. *Smallest real-
  data-verifiable unit; proves the causal spine before adding fidelity or universe depth.*
- **Slice 2 · Point-in-time universe (P2+P3):** the day's real survivorship-free universe,
  corporate-action-correct. Success test #1. *Turns "a day" into "the whole market as it was."*
- **Slice 3 · Prequential learning (P7+P9):** predict-then-reveal scoring into the existing
  §9/Layer-10 calibration; wire fully into the loop. Success test #4. *The learning payoff.*
- **Slice 4 · Fidelity climb:** ICICI Breeze 1-second intraday source (P4 upgrade); then,
  in parallel, START recording our own live depth forward (the only way to ever get L2/L3).
- **Slice 5+ · ADVANCED tier:** microstructure features, queue/impact fills, deficit
  curriculum (unblocks the Layer-10 regime queries), parallel multi-day → champion-challenger.

**Recommended start: Slice 1.** It is real-data-verifiable today on data already in the
project, reuses the existing router, and lays the causal-honesty foundation everything
else stands on.

---

## 4a. Slice 2 · P3 — corporate-action adjustment engine (design)

**Goal (§11.2):** the bot sees the RAW point-in-time price as "now" (what actually
printed that day), but any price *series* spanning a split/bonus ex-date must stay
continuous — a 1:5 split must not read as an 80% crash to indicators/returns.

**Data source (Rule I — acquired):** `nselib.capital_market.corporate_actions_for_equity`
returns real NSE records: `symbol, exDate, faceVal, series, subject` where `subject`
is free text like `"Bonus 10:1"` or `"Face Value Split (Sub-Division) - From Rs 10/-
Per Share To Rs 2/- Per Share"`. Real splits/bonuses exist inside the current stored
window (KRISHANA 10→2 ex-03-Jul-2026, GOLDIAM bonus 1:3 ex-10-Jul-2026).

**Adjustment math (price factor for bars BEFORE ex-date, bringing them onto the
post-action scale):**
- Split face `A`→`B`: factor = `B/A` (10→2 ⇒ 0.2).
- Bonus `X:Y` (X free per Y held): factor = `Y/(X+Y)` (1:1 ⇒ 0.5, 1:3 ⇒ 0.75, 10:1 ⇒ 1/11).
- Dividends / rights / other: factor `1.0` (not adjusted for intraday continuity — a
  known limitation; big fake gaps come from splits/bonuses, which we handle).

**Engine:** `CorporateActionAdjustmentEngine(actions_by_symbol)` →
`cumulative_price_factor(symbol, bar_date, as_of_date)` = product of factors for actions
with `bar_date < exDate <= as_of_date`; `adjust_bars_for_continuity(symbol, bars, as_of)`
scales OHLC by that factor (older bars down to current scale) and volume by `1/factor`
(turnover continuous). A bar on/after the ex-date keeps factor 1 → stays raw.

**Wiring (Rule G):** `ReplayUniverseFeed` gains an optional engine; `recent_intraday_bars`
(the indicator/lookback series) returns continuity-adjusted bars as of the replay clock,
while `latest_price_by_token` stays RAW (the real current print, §11.2). The service
builds the engine from real nselib actions for the replay universe (best-effort — identity
when unavailable, so replay never breaks). Provider behind a DI seam (`nselib` real vs a
fake for hermetic tests).

**Verification:** hermetic unit tests on the real `subject` string forms (parser + factor
math + continuity across an ex-date); a Rule-F real-data pass fetching real actions via
nselib and asserting a real split series is made continuous. Real split *within the stored
liquid-universe price window* may be absent (small-cap ex-dates) → a finer blocker, not a
slice-2 stopper.

## 4b. Slice 3 — prequential learning + provenance memory-drain (design)

**Reality check:** the §9 lab ALREADY does predict-then-see grading on replayed data
(the paper loop runs on the replay feed → predictions → Brier/log grading → Layer-10
memory). What is missing — and what makes 24/7 replay learning *safe* — is that
replay-derived experiences are indistinguishable from live ones in the memory. Slice 1
built the provenance watermark but its CONSUMER was queued; Slice 3 wires it in.

**Slice 3a (this increment) — provenance-tagged, separable memory:**
- `ClosedExperiment` gains `data_provenance` (default `"live"` — back-compatible; the
  213 existing real experiences are all genuinely live).
- `build_closed_experiment(..., data_provenance)` carries it; the service **drain reads
  the ACTIVE feed's provenance** (`ReplayUniverseFeed.provenance_stamp()` in replay,
  `live` otherwise) — the watermark's first real consumer (Rule G/K). A trade opens and
  squares off in one mode, so drain-time provenance == the trade's provenance.
- `SqliteExperienceMemory`: `data_provenance` column + a one-time `ALTER TABLE` migration
  (existing rows default `live`); `experiment_count_by_provenance()`; a `data_provenance`
  filter on `calibration_board` so live vs replay calibration is SEPARABLE.
- Verified on the REAL memory DB (213 experiences → all `live` post-migration) + a
  recorded replay experiment tags `replay_faithful`.

**Slice 3b (tracked next) — provenance INTO decisions (the down-weighting policy):**
recalibration / antibody / information-diet must weight replay below live (§8.2) so a
replay-only lesson never overrides live evidence, and over-reliance on replay trips the
information-diet health WARNING. Slice 3a records + separates provenance; 3b acts on it.
Also tracked: the dense per-step prequential scorer (§8.1) beyond per-trade grading.

## 5. Blockers & deferrals → BACKLOG (Rule K)
The permanent blockers (§1) and the queued slices 2–5 are logged in `docs/BACKLOG.md`
under a new "Market-open simulation (§53)" feature section on build start, each with its
"done =" test. The full-universe rule + point-in-time acceptance criteria (§11) are the
acceptance gates. No slice is "done" until Rule F real-data verified on the day it replays.
