# BACKLOG — deferred work, tracked so nothing is silently skipped (Rule K)

This is the authoritative standing to-do memory across turns/sessions. Every
"queued / next / named-future-consumer / deferred / open-blocker" promise lands
here the moment it is made, under its owning feature, and is struck through /
moved to **Done** only when actually delivered + verified (or the user drops it).
Reconcile with the live task list at each session start.

Status key: 🔴 not started · 🟡 in progress · 🟢 done (moved to Done) · ⛔ blocked

---

## Broker historical-data API limits research (research/73) — open verification items
Full findings: `docs/research/73_broker_api_intraday_historical_data_limits_2026.md`
(ICICI Breeze, Zerodha Kite, Upstox, Angel One SmartAPI, Dhan, Fyers, Finvasia
Shoonya, Alice Blue, Motilal Oswal, 5paisa, IIFL — Layer 2 swappable
data-source candidates per `docs/PLAN.md` §8a.12). Items below are undocumented
or unreachable via public sources as of 2026-07-25 and need a follow-up pass
before any of these sources are selected/wired as a data source:
- 🔴 **Finvasia Shoonya max 1-minute lookback** — docs SPA never rendered
  (JS-only), FAQ 403'd; only the SDK (`Shoonya-Dev/ShoonyaApi-py`) and interval
  list were confirmed, no lookback-days number found anywhere public.
- 🔴 **Alice Blue ANT / Motilal Oswal / IIFL** — official docs domains returned
  HTTP 402/404 or had no discoverable developer API surface at all; only
  secondary evidence (PyPI wrapper page for Alice Blue, marketing page for
  Motilal Oswal) was obtainable. IIFL may be institutional-only/discontinued
  for retail — unconfirmed.
- 🔴 **Broader "any other free Indian broker/data vendor" sweep** — the
  sub-agent covering this exhausted its WebSearch quota before running the
  open-ended discovery queries; only the named candidates above were checked.
- 🔴 **ICICI Breeze 1-second OI population for options** — no doc/example
  confirms whether the `open_interest` field is actually populated (vs.
  null/placeholder) at 1-second granularity; only 1-minute OI was directly
  evidenced. Also flagged: 2024 GitHub Issues/TradingQnA reports of empty
  responses, duplicate rows, and conflicting OHLC specifically on
  `get_historical_data_v2`/1-second interval — the documented ~3-year window
  is not independently verified as cleanly achievable at scale (1000-row/
  request cap + 100-calls/min rate limit).
- 🔴 **Zerodha Kite Connect request-rate limits (req/sec)** — not verified
  against a primary source in this pass.
- 🔴 **Upstox Plus pricing** (paid tier that unlocks expired F&O contract
  history) — no published price found on any static page; needs an
  in-app/account-level check.

## Free deep-intraday NSE history — open verification items (research/74)
Full findings: `docs/research/74_free_deep_intraday_nse_history_ceiling_2026.md`
(ranked free/legitimate sources for 1-min/1-sec NSE history, cash + F&O + OI).
- 🔴 **ICICI Breeze 3-year (FAQ) vs. community-claimed "10-year" (Nifty/
  BankNifty F&O, TradingQnA) conflict** — needs an empirical probe of
  `get_historical_data_v2` against a pre-2023 date range before planning
  around either number.
- 🔴 **HuggingFace `xxparthparekhxx/indian-stock-market-minute-data`
  provenance/accuracy** — dataset card doesn't disclose source feed; spot-check
  sample rows against known-good bhavcopy closes before using as a production
  seed, and don't represent it externally as licensed NSE data.
- 🔴 **`openchart` (github.com/marketcalls/openchart) real depth** against
  NSE's own `chart-database` endpoint — unanswered upstream (issue #4); worth
  an empirical test since it's free and actively maintained.
- 🔴 **NSE Research Initiative 2.0 academic/non-commercial data-access
  application** (nseri@nse.co.in) — not yet filed; the only found channel to
  potentially genuine tick-level (sub-1-second) NSE history for free. Low
  cost to file, slow/uncertain yield — long-lead item, not a current blocker.

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
  **Re-verified 2026-07-25 (`research/71` tick-focused, `research/72`
  depth-focused, independent 4-angle passes each):** confirmed, with one
  precision fix — NSE itself *does* sell historical order-level data
  (Product B, `research/59`) and two academic grant channels exist (IIM
  Ahmedabad campus licence; NSE-NYU Stern Initiative, new find in
  `research/72` — competitive, $7,500/yr, institutional-PI-gated); none are
  free or realistically eligible for this personal trading project, so
  "record forward only" stands as the practical free-access conclusion.
  No Kaggle/GitHub/HuggingFace/Zenodo/WRDS/LOBSTER alternative exists
  (two independent exhaustive passes, `71` + `72`). No new action taken —
  informational re-confirmation only.
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
- 🟢 **Slice 3b-ii — dense prequential forecast scorer.** DONE (2026-07-25,
  research/65, real-data verified): `ExperienceMemory.prequential_forecast_score`
  (running log-loss bits + Brier over the stored prediction stream, provenance-
  separable) → Reflection panel "Forecast skill" note (live vs replay). Sourcing
  outcome: River's `LogLoss` NOT vendored — a query over the persisted stream (we
  already have the formulas) is stateless, restart-safe, and Rule-F-verifiable now,
  which an in-memory accumulator is not. Rule-F: real 293 predictions → 1.142 bits
  / Brier 0.252; independent Brier recompute matches. 414 tests pass. **⇒ slice 3b
  COMPLETE.** (Per-BAR finer-than-per-trade scoring — the River-accumulator
  use-case — remains a future item only if per-step predictions are ever emitted.)
- **Slice 4 — fidelity climb** (research/66):
  - 🟢 **P4a — Breeze 1-second historical source. DONE (2026-07-25, real-data
    verified).** `market_data/breeze_historical_bar_source.py` behind the
    `HistoricalBarSource` seam (injected client, chunking+de-dup, cash+option
    addressing), `BarInterval.SECOND_1`, `breeze-connect` acquired (MIT). Rule-F:
    fetched 600 real 1-second ITC bars (2026-07-24) via
    `scripts/verify_breeze_1s_realdata.py`. Bug the pass caught + fixed: Breeze v2
    reads from/to as **IST wall-clock**, not UTC. 420 tests pass. *(task #3)*
  - 🟢 **P4a-wire — DONE (2026-07-25, real-data verified).** New
    `historical_source_replay_feed_builder` (`build_replay_bars_by_token_from_source`
    + `HighFidelityReplayConfig`) + a `high_fidelity_replay` DI param on the service:
    when injected, the market-closed `ReplayUniverseFeed` is built from Breeze
    **1-second** bars for a focus set instead of the stored 5-minute bars (default
    None = no change). Rule-F: 600 real Breeze 1s ITC bars built into a real
    `ReplayUniverseFeed`. 422 tests pass. P4a's fidelity now reaches the loop.
  - 🟢 **P4a-wire-autonomous — DONE (2026-07-25, real-data verified).** New
    `breeze_replay_focus_planner` (budget-caps 1s focus to Breeze's 5000/day) + the
    service's `_maybe_activate_autonomous_breeze_replay()`: on start, a valid stored
    Breeze token (#6a) self-builds a rate-limited `HighFidelityReplayConfig` (source
    via #6a client + #6b resolver; session = day-walker most-recent-≤-yesterday);
    best-effort → store-5m path when no token. Rule-F: from a stored real token the
    service self-served **21,952 ITC + 17,193 RELIANCE real 1s bars** unattended. 435
    tests pass. *(task #7)* Set the daily token → the loop runs 1s replay itself.
  - 🟢 **Focus RANKING — DONE (2026-07-25, real-data verified).**
    `rank_instruments_by_liquidity` + `MarketDataSqliteStore.
    latest_cash_bhavcopy_trade_date`; the autonomous activation ranks the cash
    universe by real latest-bhavcopy turnover before budget-capping. Rule-F: on the
    real 2026-07-24 bhavcopy INFY ranks above HDFCBANK; unknown symbols sort last.
    442 tests pass. *(task #8)*
  - 🟡 **P4b — live-depth recorder. BUILT + hermetic-verified (2026-07-25).** Full
    pipeline: `market_depth_types` · `MarketDepthSource` seam · `kite_market_depth_
    source` (Kite `quote()` depth) · `market_depth_snapshot_store` (own
    `market_depth.sqlite3`) · `paper_trading/live_market_depth_recorder`. Wired into
    `_run_forever` behind `record_live_market_depth` (default OFF) — records the
    focus set's book after each market-open pass, best-effort. 440 tests pass.
    - ⛔ **Rule-F real-session capture OPEN** — needs an OPEN market + live Kite
      session (Sat + no token now). Verify real 5-level snapshots persist. *(task #5)*
    - 🔴 **Enable `record_live_market_depth=True` in the deployed service** — the
      recorder is inert until turned on; the whole point is to accumulate depth
      forward. *(task #9)*
    - 🔵 **Depth-CONSUMING features** (microstructure signals / depth replay) — the
      recorded depth's purpose-consumer. *(task #10)*
  - 🟢 **Breeze session store + ICICI stock-code map — DONE (2026-07-25, real-data
    verified).** *6b:* `icici_security_master_stock_code_resolver` parses ICICI's
    real SecurityMaster (NSE symbol→ICICI code); injected as the Breeze adapter's
    `stock_code_resolver`. Rule-F: RELIANCE→`RELIND` → **196 real 1-second RELIANCE
    bars** (previously empty). *6a:* `broker_sessions/breeze_session_token_store`
    (daily token + midnight/24h expiry), `breeze_authenticated_client_builder`
    (injectable factory), `set_breeze_session_token` CLI. 430 tests pass. *(task #6)*
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

## Free-data sourcing — actionable wins (research/77, 2026-07-25)
The "can we get the paid data free?" deep-research (5 parallel legitimacy-filtered
sweeps: research/71 tick · 72 depth · 73/74 intraday · 75 corp-actions/ISIN/delisted
· 76 index membership; consolidated 77) confirmed microstructure (tick + L2/L3
depth) is genuinely not free for an individual → record-forward (done: Breeze 1s +
P4b) or license NSE. Net-new actionable wins now tracked:
- 🟡 **Fyers free History API adapter — BUILT + hermetic-verified (2026-07-25,
  research/78).** `market_data/fyers_historical_bar_source.py` on the
  `HistoricalBarSource` seam (injected client, never imports `fyers_apiv3`; ≤100/366-
  day chunking; cash `NSE:{sym}-EQ`); the deep FREE minute source (cash+F&O+OI, ~9y),
  plugs into `build_replay_bars_by_token_from_source`. 449 tests pass. *(task #11)*
  - ⛔ **Rule-F real-data pass OPEN** — needs the user's Fyers creds (client_id +
    secret + redirect), a daily token, and an ISOLATED `fyers-apiv3` install (its
    pinned deps risk colliding with the suite). Then pull real multi-year RELIANCE
    minute bars + assert. *(task #11)*
  - 🔴 **Fyers options symbol-master resolver** — format option symbols from
    `public.fyers.in/sym_details/NSE_FO` (monthly/weekly month codes); default
    resolver raises for options until injected. *(task #14)*
  - 🔴 **Fyers session-token store** (like Breeze #6a) + isolated dependency group. *(task #15)*
- 🔵 **HuggingFace 2022+ NSE 1-min seed** (MIT) — bulk backfill of the bars store;
  verify provenance first. *(task #12)*
- 🟡 **BSE delisted cross-source — BUILT + real-data verified (2026-07-25,
  research/79).** `delisted_securities_source` (BSE `ListofScripData`, ISIN-carrying,
  free) + `DelistedSecuritiesMaster` + `delisted_securities_ingestion_job` (CLI) +
  store table. Rule-F: live BSE fetch >1,000 real delisted rows, all with ISIN. 454
  tests pass. *(task #13)*
  - 🔵 **Kaggle CC-BY-4.0 survivorship-free set** as a 2nd cross-source — deferred
    (needs a Kaggle API token). *(task #13)*
  - 🔴 **Resolver-side consumption** — suspension-vs-delisting test (§53 G3) +
    universe-gap classification (bhavcopy gap + delisted-master hit = confirmed
    delisted) using `DelistedSecuritiesMaster`. The purpose-consumer (Rule K).
- ⛔ **ISIN-to-ISIN merger lineage** — confirmed no free source (symbolchange.csv
  has no ISIN column); remains an open gap (per-event manual or paid vendor).

## Rule L — segment priority (2026-07-25)
- 🟢 **Rule L retrofit of the replay focus — DONE (real-data verified).**
  `_rule_l_prioritized_focus_candidates` spans index options → stock options → cash
  (was cash-only); budget truncation makes cash yield first under the 1s rate limit.
  Rule-F on the real universe (9,292 cash / 70 index-opt / 2,846 stock-opt): options
  ordered before cash, index before stock. 457 tests pass. *(task #16)*
- 🔴 **Audit remaining focus/build sites for cash-first bias** (Rule L applies
  everywhere a focus/ranking/budget/build-order is chosen, not just the Breeze
  replay focus) — ongoing.

## Multi-broker data adapters (PLAN §8a.12; research/80-83, 2026-07-25)
All three implement the `HistoricalBarSource` seam (injected client, never import the
vendor SDK) — BUILT + hermetic-verified.
- ⛔ **Groww** (`groww_historical_bar_source` + `GrowwRestHistoricalClient`) — minute+,
  OI, cash `NSE-{sym}`. **Rule-F REFINED-BLOCKED (2026-07-25):** with the user's
  session-approved long-lived token, EVERY Groww endpoint (margin, holdings, live-data,
  historical — both param shapes, both approval + TOTP tokens) returns `403 "Access
  forbidden"`; the token authenticates but the account has **no API entitlement**.
  Done = activate the **Groww Trading API subscription (₹499/mo, research/80)**, then
  re-probe + real-data pass. Adapter is built + hermetic; nothing more codeable until
  the subscription is live. *(task #19)*
- 🟢 **Angel One** (`angel_one_historical_bar_source` + `angel_one_symbol_token_resolver`
  + `broker_sessions/angel_one_smartapi_session`) — ONE_MINUTE…ONE_DAY, **no historical
  OI**. **DONE — Rule-F VERIFIED (2026-07-25):** `scripts/verify_angel_one_realdata.py`
  (fully-automatic `generateSession` login: client code + PIN + TOTP) → 375 real
  RELIANCE 1-min bars (symboltoken 2885) + 375 real NIFTY 23700 CE 1-min bars (token
  63925, OI None); resolver built from the real OpenAPIScripMaster (2,433 cash + 38,241
  options) matched symboltoken exactly; OHLC cross-matched Upstox. 484 tests pass.
  *(task #18/#22)*
- 🟢 **Upstox** (`upstox_historical_bar_source` + `UpstoxRestHistoricalClient` +
  `upstox_instrument_key_resolver`) — v3 minute+, OI. **DONE — Rule-F VERIFIED
  (2026-07-25):** 1-year Analytics Token → `scripts/verify_upstox_realdata.py` fetched
  375 real RELIANCE 1-min bars + 375 real NIFTY 23700 CE 1-min bars with OI; resolver
  built from the real NSE master (9,460 cash + 38,241 options) matched instrument_key
  exactly. 477 tests pass. *(task #17/#22)*
- 🔴 **Per-vendor symbol/token resolvers + auth/session builders (remaining):**
  ~~Upstox instrument_key resolver~~ **DONE**. ~~Angel symboltoken resolver
  (OpenAPIScripMaster) + `generateSession` session builder~~ **DONE**. Only Groww
  options resolver (instrument CSV) + subscription/token-refresh left — blocked on the
  Groww API subscription. *(task #22)*
- 🟢 **Multi-broker FAILOVER source — DONE, Rule-F VERIFIED (2026-07-25, research/84).**
  `multi_broker_historical_bar_source.MultiBrokerHistoricalBarSource` (implements
  `HistoricalBarSource`; ordered failover on raise/empty, first-non-empty wins,
  all-fail→[], `on_source_attempt` observer). Real pass across live Upstox+Angel:
  primary serves; broken-primary→Angel serves 375 real bars; reversed order respected.
  491 tests pass. *(task #20)*
  - 🔴 **Slice-2 — gap-fill AGGREGATION (queued):** fill a primary's missing
    timestamps in the window from lower-priority sources (each bar stays wholly from
    one feed). Needs its own real-data pass (a session with a broker-specific gap the
    other covers). Done = gap-filled bars verified across two real sources. *(task #20)*
  - 🔴 **Composition-root autonomous FLEET wiring (queued — purpose-consumer, Rule K):**
    the failover source is built + verified but nothing yet WIRES an ordered real
    fleet (Fyers→Upstox→Angel→Breeze→Kite) into the autonomous replay path
    (`_maybe_activate_autonomous_breeze_replay` / `HighFidelityReplayConfig.bar_source`).
    Until wired, resilience isn't in the loop — display/standalone only, NOT done for
    the "resilient loop" promise. Done = the service's replay source is the multi-broker
    source, order applied per Rule L, verified. *(task #20)*
- 🔴 **Kite (paid) deeper history** — richer Kite historical wiring across intervals. *(task #20)*
