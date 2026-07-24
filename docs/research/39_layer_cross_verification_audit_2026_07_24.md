# 39 — Deep Cross-Verification Audit of Layers 1–9 (2026-07-24)

Market-open, real-data deep check requested by the operator. Six parallel
audit agents each read one layer group's flowchart note + PLAN claims +
EVERY source file + ran that layer's tests, and reported docs-vs-code-vs-
tests discrepancies. Plus a central **live real-data pipeline check** (this
session) exercised L2→L3 on the real open market:
INFY real bars → EMA 1024.6 / RSI 28.1 (oversold) / ATR 3.74 / ADX 37.2
(trending) / session VWAP 1030.5; NIFTY spot 23664 → ATM 23650 CE @149.25
→ BS-inversion IV 13.3% — all sane on real data.

**Headline:** nothing claimed *built* was found fabricated or stubbed — the
code that exists is real and, where checked, mathematically correct
(all 11 indicators, DSR/CPCV/PSR formulas, Brier grading, ledger P&L, the
undefined-risk/naked detector with adversarial coverage all verified sound).
**The dominant issue is Rule-G orphaning: large, correct subsystems are not
wired into the running loop, while the docs/overview describe them as
complete.** Test suite: 262 green.

## Severity-ranked findings

### Fixed this session (2026-07-24)
- **[L9 MED] Dashboard thread-safety race** — request threads read the
  live service's mutating ledger/scoreboard (`dict changed size during
  iteration` reachable). FIXED: the writer thread now publishes finished
  `PaperTradingSummary`/`PredictionTableSummary`; requests read only the
  immutable snapshot. (commit 5f06989)
- **[L9 MED] False all-session "overnight breach" CRITICAL** — fired on any
  open position regardless of time. FIXED: time-gated at 15:15; mid-session
  open positions are INFO. (5f06989)
- **[L8 MED] Square-off report discarded at the wiring** — the loop booked
  every leg closed regardless of Layer 8's outcome (a persistently-rejected
  square-off would be silently booked flat). FIXED: honor `SquareOffReport`;
  unflattened legs are surfaced (`unflattened_square_off_positions`), never
  dropped; new test. (5f06989)

### Open — Rule-G orphans (built + tested, wired nowhere)
- **[HIGH value] Options / credit-spread ENTIRE path is orphaned.**
  `select_credit_spread_legs` (L4), `build_order_intents_for_credit_spread`
  + `execute_multi_leg_order_atomically` (L6), and the L3 options-derived
  IV→ATM-IV→IV-Rank→PCR pipeline have ZERO non-test callers. The live loop
  only trades cash ORB. → task #8 wires this in (un-orphans all of it).
- **[L4 MED] ADX regime gate unwired.** `choose_v1_session_strategy` /
  `classify_adx_market_regime` route nothing at runtime — the loop runs ORB
  unconditionally (never stands aside on INDECISIVE, never routes to credit-
  spread on RANGE_BOUND). The ADX value is computed but used only for §9
  labels. → fold into task #8.
- **[L7 MED] 24/7 replay↔live router orphaned.** `MarketClockGatedDataSource
  Router` is never instantiated; the live service uses the feed directly and
  idles when the market is closed. "Never stops / seamless handoff" is not in
  a runnable path yet. → replay-when-closed is a queued slice.
- **[L7 MED] DSR + CPCV promotion gates orphaned.** No consumer in any
  runnable path; only the §9 lab scores. → wire into a promotion step later.
- **[L3 MED] Most indicators orphaned.** Only ADX + BS-delta are consumed;
  EMA/RSI/ATR/Supertrend/VWAP + the whole options-IV pipeline have their
  (now-built) Layer-4 consumer but it wires in only ADX. → future strategies.
- **[L2 MED] `KiteLiveTickStreamSource` orphaned** — superseded by the
  LTP-polling `KiteLiveUniverseFeed`; no live consumer, never real-verified.

### Open — correctness / risk (not yet fixed)
- **[L7 MED] Slippage bypassed on the LIVE loop.** `live_universe_paper_loop`
  records fills at raw breakout/stop/target prices; its SimulatedBrokerClient
  has no slippage adjuster (only the old replay lab wired
  `make_slippage_fill_adjuster`). Live paper P&L is frictionless. → fix.
- **[L7 LOW-MED] Optimistic gap exits.** Stop/target fill at the exact level
  no matter how far LTP gapped through — flatters loss-side P&L. → fix with
  slippage / gap-aware fill.
- **[L9 MED] `min_capital_per_trade` not enforced on the live path.**
  `clamp_quantity_to_capital_limits` is orphaned; the service only uses the
  risk-budget mapping. → wire the clamp into the loop.
- **[L6 MED] Live naked-leg guarantee overstated.** On the live Kite path a
  leg is "executed" on mere acceptance (OPEN≠filled); no OPEN-state polling /
  unwind. Disclosed as deferred, but the doc's absolute wording overstates
  it. → OPEN-state polling is a live-path slice (needs live orders).
- **[L2 MED] `has_fo_ban_list_for_date()` referenced in a docstring but never
  defined** — the documented way to distinguish never-ingested from
  zero-ban-day does not exist. → add the method.
- **[L2 LOW] `mwpl_utilization_percent` div-by-zero** when MWPL==0. → guard.
- **[L7 LOW] CPCV embargo removes test/OOS indices** (should embargo
  training, not the OOS path). Low impact (feeds DSR variance; min-trades
  gate dominates). → refine.
- **[L7/INFO] Break-even graded as loss** (`realized_pnl > 0`). → treat 0 as
  neutral/scratch.
- **[L9 LOW] Access key compared with `!=` not `compare_digest`; key in URL**
  (lands in logs). Exposure gated (port not opened; real auth required pre-
  live) but harden before any exposure.

### Open — documentation drift (reconcile)
- Overview + several flowcharts describe the options IV pipeline, the 24/7
  router, DSR/CPCV gates, and the ADX-routed strategy as "complete/built"
  when they are orphaned. L2/L3 "nothing consumes this yet" notes are stale.
  L1/L2 file lists omit `live_tradable_universe.py`, `recent_intraday_bars`,
  `fo_bhavcopy_backfill_job.py`. `07_...md` still says "server runs the old
  INFY replay" (false). → a doc-reconciliation sweep marks orphaned pieces
  "built but not yet wired (queued: <slice>)" instead of "complete".

## Disposition
Priority order: (1) wire options credit-spread + regime gate [task #8,
un-orphans the biggest chunk, market-open verifiable]; (2) post-seed
breakout watch [#9]; (3) order types incl. SL/SL-M/GTT [#10]; (4) slippage-
on-live + min-capital clamp; (5) small L2 fixes; (6) doc-reconciliation
sweep. Rule F: each fix verified on real live data during the open session.
