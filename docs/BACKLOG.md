# BACKLOG — deferred work, tracked so nothing is silently skipped (Rule K)

This is the authoritative standing to-do memory across turns/sessions. Every
"queued / next / named-future-consumer / deferred / open-blocker" promise lands
here the moment it is made, under its owning feature, and is struck through /
moved to **Done** only when actually delivered + verified (or the user drops it).
Reconcile with the live task list at each session start.

Status key: 🔴 not started · 🟡 in progress · 🟢 done (moved to Done) · ⛔ blocked

---

## Opponent ledger (Layer 10 §10)
- 🟢 **Slice 1 — divergence → strategy bias.** DONE (2026-07-24): entries opposed
  by institutional positioning (FII lean + retail-trapped divergence) are deferred
  at all 4 entry sites; real-data verified (real reading defers a LONG). *(task #22)*
- 🟢 **Slice 2 — participant VOLUME file.** DONE (2026-07-24): volume_on() added;
  FII churn (vol/OI) → participation_conviction, wired into the gate (suppress
  defer on "low" conviction); real-data verified (live churn 0.354 → normal). *(task #23)*
- 🟢 **Slice 3 — multi-day FII-net trend.** DONE (2026-07-24): 5-day FII-net
  least-squares trend (confirming/weakening/flat) wired into the gate (weakening
  suppresses the defer); real-data verified (live walk → building short →
  confirming). *(task #24)* — **opponent-ledger feature COMPLETE.**

## §9/§10 grading — proper scoring rules (research/44 borrow)
- 🟢 **Vendor python-prediction-scorer (MIT) proper scores.** DONE (2026-07-24):
  log/quadratic on §9 grading + scoreboard; cohort mean_log_score on the
  calibration board; antibody trips on confidently-wrong log-score. Real-data
  verified over 213 SQLite experiences. *(task #25)*

## Layer 10 — §10 institution features
- 🟢 **Information diet (accounting).** DONE (2026-07-24): per-source influence +
  diet-health read; inert-learning raises a monitoring WARNING; panel wired. Real-data
  verified (real memory → recalibration 100% / veto 47% → healthy). *(task #30)*
  ~~The one §10 institution feature not yet built~~
  (PLAN §10 order: assumption registry ✓, opponent ledger ✓, INFORMATION DIET,
  epidemiology→antibody ✓). Account for WHAT information the bot consumes to decide —
  the sources/signals feeding entries (ADX regime, opponent ledger, memory priors) and
  their diversity/quality/provenance — so an over-reliance or echo-chamber is visible.
  ("information-diet-DIRECTED research targeting" is separately PARKED to Layer 11.)
  Done = a per-decision information-source ledger + a diet-health read, wired + verified.

## Layer 10 memory substrate
- 🟢 **Graph substrate decision + SQLite multi-hop.** DONE (2026-07-24):
  Graphiti/Neo4j REJECTED (LLM-text-extraction KG, server+LLM required, Kùzu
  deprecated — impedance mismatch for structured records; research/50). Delivered
  the multi-hop capability in SQLite: outcome_sequence_dependence (LAG) → non-iid
  clustering feeds the antibody verdict. Real-data verified over 213 experiences.
  *(task #28)*
- 🔴 **Regime-transition fragility + cross-regime co-failure clusters (queued).**
  The LAG/recursive-CTE substrate is built; these need MULTI-REGIME data (real
  data is single-regime "normal" today). Done = fragility/co-failure derived +
  consumed, verified once regimes vary.
- 🟢 **Brier decomposition** (Murphy reliability/resolution/uncertainty). DONE
  (2026-07-24): vendored (briertools rejected — no Murphy fn, 6 deps, no license);
  reliability_decomposition() + diagnosis fed into the antibody's tripwire detail;
  real-data verified over 213 experiences. *(task #26)*
- 🟢 **Auto-recalibration consumer.** DONE (2026-07-24): learn_mechanism_recalibrations
  → per-mechanism bias offset applied to win_probability at all 4 entry sites (demotes
  over-confident theses; re-derives table) + no-edge (resolution≈0) hard-veto.
  Real-data verified (post-breakout-trend −0.72 → 0.84 recalibrates to 0.12).
  *(task #27)*

## 24/7 historical replay simulation — data & universe sourcing (research/53-61)
Idea map + sourcing passes are DONE (research only, no code yet — this is the
Rule-I acquisition research that must precede building §53's replay engine).
Not started = the actual build (queued, no slice scheduled yet). Tracking the
concrete blockers/decisions surfaced so far so they aren't silently dropped
when the build starts:
- 🔴 **License NSE Data & Analytics historical dissemination** (research/59
  §1). Now fully priced (tariff effective Apr-2026): legacy trades-only
  ₹1,10,000/yr each for CM/F&O (from 1995/2003) or full order-level data
  ₹12,50,000/yr each (from ~Dec-2007). Decision needed: commit budget, and
  confirm (a) individual (non-entity) eligibility for the `dotexdata.nseindia.com`
  portal, (b) whether this personal trading project can honestly claim the
  50-80%-off "Student/Researcher" tier (policy defines research as
  non-trading — likely NO). Done = licensed + first historical pull verified.
- 🔴 **ISIN-extinguishing merger/amalgamation swap-ratio + surviving-entity
  records** (research/57, research/59 §3.7/§5 G1). Confirmed hard blocker —
  no free bulk source (MCA/Moneycontrol/NSE UIs all bot-gated). Scope =
  only companies that actually merged, not the full universe. Done = a
  verified paid-vendor source (Trendlyne primary-unverified lead, or Ace
  Equity Nxt ₹125k/yr) or a per-event manual sourcing process for this subset.
- 🔴 **Single bulk NSE/SEBI master list of ALL delisted companies** (research/58,
  research/59 §5 G2). `www1.nseindia.com/content/equities/delisted.xlsx` is an
  unverified lead (SSL-errored on automated fetch). Done = the lead confirmed
  via manual/headless-browser retry, or the bhavcopy-presence-gap fallback
  built and tested instead.
- 🔴 **Suspension-vs-delisting bhavcopy-behavior test** (research/58, research/59
  §5 G3). Unknown whether a suspended-but-not-delisted stock disappears from
  daily bhavcopy the same way a delisted one does. Done = tested empirically
  against a known SEBI-suspension case before the universe-reconstruction
  module ships.
- 🔴 **Rule-F real-data load test: `nselib.corporate_actions_for_equity()` /
  NSE `corporates-corporateActions` API across the full 2,000+-symbol
  universe** (research/57, research/59 §5 G8). Bulk-query depth confirmed
  live (41,979 records, 1995→present) but full-universe per-symbol behavior
  and ISIN-keying correctness not yet load-tested. Done = verified over the
  real full universe, keyed by ISIN not symbol.
- 🔴 **Deep historical tick + L2/L3 depth, intraday participant flow, deep
  historical news** — the original `research/54`/`55`/`61` blockers (true
  L3/MBO co-location-gated — permanent; no vendor sells historical NSE
  depth — record forward only; intraday participant OI — EOD-only,
  permanent; point-in-time news pre-~2010 — hard blocker at intraday
  precision). Carried here for visibility since they were never logged to
  this file when first found. Done = each mitigated per its own
  research-doc recommendation, or accepted as a permanent fidelity ceiling.
- Everything above is a **research-verified acquisition target**. The §53
  build has now STARTED (BASE tier, slice plan in research/62); the items
  above are consumed slice-by-slice below. Re-read `research/53-62` when
  resuming (Rule K step 3).

### §53 BUILD — BASE-first slices (research/62)
- 🟢 **Slice 1 — honest historical-replay clock.** DONE (2026-07-24, functional):
  `historical_trading_day_walker` (P1) · `causal_leakage_firewall` (P5) ·
  `replay_experience_provenance` (P6); `replay_universe_feed` firewalled +
  provenance-stamped, wired in the live service replay path. Day-walker
  Rule-F verified on the REAL XNSE calendar; firewall/provenance hermetic
  (Rule J); 107 paper_trading tests pass. *(task #1)*
  - 🟢 **Slice-1 real-data pass (Rule F) — DONE (2026-07-24)** at BASE (bar-only)
    fidelity: verified over a REAL stored full session (2026-07-24, 225 cash
    instruments, 5m bars) in `~/.nse_algo_trader/market_data.sqlite3` — firewall
    never leaks a future bar across the whole session, a future-moment request
    raises, provenance stamp intact (`test_replay_firewall_real_data.py`). No
    broker login needed (used already-stored real data). *(task #2)*
  - 🔴 **Higher-fidelity real-data pass → slice 4:** tick / ICICI-Breeze 1-second
    intraday replay through the firewall is NOT yet verified (only 5m bars exist
    today). Done = a real tick/1s session replayed causally. Not a slice-1 blocker.
- 🔴 **Slice 1 named consumers (Rule G — not orphans, consumers queued):**
  (a) `historical_trading_day_walker` → **slice-2 archive-walk driver** that
  steps the live service backward through historical sessions (today it is
  built + verified but not yet driving the service's session selection);
  ~~(b) `replay_experience_provenance` stamp → **slice-3 memory-drain** that
  writes the tag onto each replayed experience~~ **DONE (2026-07-25, slice 3a):**
  the drain stamps each experience with the active feed's provenance and the
  memory is now provenance-separable (calibration_board filter + dashboard
  live/replay mix). Making calibration/antibody actually WEIGHT replay below live
  is slice 3b (below).
- 🟢 **Slice 2 — point-in-time universe** (P2+P3): DONE (2026-07-24), real-data
  verified & wired into the loop. Only the low-priority walker-session-stepping
  refinement (task #7) remains under §53.
  - 🟢 **P2 `point_in_time_universe_resolver` — DONE (2026-07-24), real-data
    verified.** Survivorship-free per-date universe from stored cash+F&O
    bhavcopy (EQ names traded that day + option underlyings/contracts =
    F&O-eligibility snapshot). Rule-F verified on real 2026-07-23 bhavcopy
    (~2,387 EQ, 150+ underlyings incl. NIFTY/RELIANCE). *(task #3)*
  - 🟢 **P2 consumer WIRED — DONE (2026-07-24), real-data verified.** New
    `historical_archive_replay_planner` wired into `live_paper_trading_service.
    _build_replay_feed_from_store`: the replay feed now keeps each bar only if
    its instrument was in the REAL cash universe on that bar's OWN date
    (survivorship-free, §11.1), replacing the old "in today's universe" filter;
    unresolved dates pass through. Rule-F verified (RELIANCE kept 2026-07-23,
    non-universe name dropped, pre-ingestion date passes through). *(task #5)*
    The core slice-2 goal (a replayed day shows THAT date's tradeable set) is met.
  - 🔴 **Refinement — full walker-driven backward SESSION stepping (queued):**
    the loop still steps a global timestamp cursor across stored bars, not the
    `HistoricalTradingDayWalker`'s today→inception session order. Wire the walker
    to drive session selection once deep-history bars are ingested. Low priority
    (survivorship correctness already achieved). Done = service replays sessions
    in walker order.
  - 🟢 **P3 corporate-action adjustment engine — DONE (2026-07-24), real-data
    verified.** `nse_corporate_action_source` (real NSE split/bonus via nselib +
    subject→factor parser) + `corporate_action_adjustment.CorporateActionAdjustmentEngine`,
    WIRED into `replay_universe_feed.recent_intraday_bars` (lookback series made
    continuous across ex-dates; current price stays RAW). Rule-F verified LIVE:
    real KRISHANA 10→2 split's fake 80% gap removed (500→100 ⇒ 100→100); real
    bonuses parsed. `nselib` acquired (Rule I). *(task #6)*
  - 🔴 **P3 finer note (not a blocker):** the live end-to-end (a real split
    landing on a STORED liquid-universe symbol within the replay window) isn't
    yet observed — recent splits were small-caps outside the 225 liquid names.
    Engine+wiring verified on real records; full in-loop observation matures with
    deep-history ingestion.
  - Deep-history refinements (delisted master, index-constituent history) still
    tracked in the sourcing items above — bhavcopy already gives correct
    traded-that-day sets for ingested dates without them.
- 🟢 **Slice 3a — provenance-separable memory.** DONE (2026-07-25, real-data
  verified): `calibration_board(data_provenance=...)` filter (protocol + sqlite)
  separates live vs replay calibration; the service publishes
  `experiment_count_by_provenance` → Reflection panel header (live/replay mix) —
  the first dashboard consumer of the slice-1 watermark; drain stamps each
  experience with the active feed's provenance. Rule-F verified on the real
  293-experience DB (all `live` post-migration; injected replay cohort stays
  separated). 403 tests pass. *(task #1)*
- 🟢 **Slice 3b-i — provenance INTO decisions.** DONE (2026-07-25, research/64,
  real-data verified): `provenance_weighted_calibration_board` (live=1.0,
  replay=0.25) drives `vetoed_mechanisms` + `learn_mechanism_recalibrations`, so a
  replay-only lesson can inform but never override live evidence; info-diet gains an
  over-reliance-on-replay WARNING (`replay_experience_share`). Rule-F: on the real
  293-live DB the weighted veto set + offsets are IDENTICAL to pooled (no
  regression); hermetic tests prove the discount + the WARNING. 410 tests pass.
- 🔴 **Slice 3b-ii — dense per-step prequential scorer (queued).** Beyond the
  existing per-trade §9 grading: a running predict-then-reveal log/Brier over the
  replay stream (§8.1). Sourcing verdict (research/63): **vendor River `LogLoss`**
  (`river.metrics.LogLoss` + `river.stats.Mean` + `metrics.base` scaffold, BSD-3,
  ~100 LOC) + a hand-written 15-line `BrierScore` twin; per-cohort = a dict of
  metric instances keyed by group; River's `progressive_val_score` REJECTED
  (model-coupled), depending on the River package REJECTED (numpy + Python≥3.11).
  Done = a running log/Brier accrues over a replay session + surfaced, Rule-F
  verified. *(task #2)*
- 🔴 **Slice 4 — fidelity climb**: ICICI Breeze 1-second source + start
  recording our own live depth forward (the only path to L2/L3).
- 🔴 **Slice 5+ — ADVANCED**: microstructure features, queue/impact fills,
  deficit-driven curriculum (unblocks the Layer-10 regime queries),
  parallel multi-day → champion-challenger.

## Open real-data blockers (Rule F/J — sim-verified, real pass pending)
- ⛔ **Shadow-arm recovery (slice 4) live pass.** Functionally verified via sim
  harness; real-data pass = live shadow-probe counts / a real refute→recover
  cycle over an open market session. Needs market open.

---

## Done
_(move items here with the commit/date when delivered + verified)_
- 🟢 **Opponent ledger core** (fetch NSE participant OI + read model + dashboard
  panel) — real-data verified, committed `e042067` (2026-07-24).
