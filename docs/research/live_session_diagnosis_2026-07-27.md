# Live-session diagnosis — 2026-07-27 (market OPEN)

Investigation of the operator's report: *"not seeing single option trades, very few trades,
0 index-option and stock-option trades, is data flowing, are all features influencing open
trades, trades not following min/max capital per trade, Confident WIN table 0 open."*

All findings below are **CONFIRMED against the live running server** (dashboard PID 135746,
`/api/snapshot`, the real Kite session, and the real SQLite stores) unless marked SUSPECTED.
Nothing was mutated: no orders placed, no DB/config writes, no restart.

---

## 0 · Live facts at the time of diagnosis (09:48–10:05 IST)

| Fact | Value |
|---|---|
| Loop alive | YES — `last_pass_at` advancing every ~15 s; `fill_count` 241 → 243 |
| Kite auth | VALID (token refreshed 08:05 IST, valid to 2026-07-28 06:00 IST) |
| Market open | YES |
| Cash universe fetched | 9,292 instruments |
| **Seeded (ever scanned)** | **221 — FROZEN all session** |
| Open positions | 43–45, **100% `cash`**, **100% `short`** |
| Index-option / stock-option open | **0 / 0** |
| Closed trades | 376 · realized P&L **−4,995** |
| Prediction tables | confident_win **0** · confident_loss 95 · uncertain 3 |
| Bars stored today | 09:15 → 213 tokens · 09:20 → 4 · 09:25 → 1 · **nothing after** |

**"Offline diagnostics mode" in `/home/opc/dashboard.log` is a RED HERRING** — that log's mtime
is 02:23 GMT but the live process started 03:27 GMT. The line is from an earlier run. The current
process is fully authenticated and live.

---

## 1 · ROOT CAUSE — the scanner is deadlocked on BONDS (explains "very few trades")

**This is the single highest-impact defect.**

`dashboard/live_paper_trading_service.py:551-560` builds the scan list from
`universe.cash_equity_instruments` **raw** — 9,292 instruments — sorted option-underlyings-first.
That list is not mainboard equities: from index ~215 onward it is **NCDs / bonds / debt paper**:

```
index 210+ : 0ABCL31-N0, 0HFL28-N0, 0IRFC35-N0, 1003IIFL29-NC, 1003SCFL31-Z4, ...
6,077 of the 9,077 tail entries are bond-shaped (digit-leading or -Nx/-Zx/-BW/-NC suffix)
```

Probed read-only against the live Kite session — these return **0 bars**, because they barely trade.

Now the seeding loop, `paper_trading/live_universe_paper_loop.py:1127-1144`:

```python
for instrument in cash_universe:
    if newly_seeded >= max_new_cash_seeds_per_pass: break     # cap = 30/pass
    if instrument.instrument_token in state.seeded_cash_tokens: continue
    ...
    recent_bars = live_universe_feed.recent_intraday_bars(...)  # paced 0.34 s/call
    newly_seeded += 1
    if not recent_bars:
        continue            # <-- token is NEVER marked seeded
    opened = _seed_cash_instrument_from_orb(...)   # seeded_cash_tokens.add() lives at :932, INSIDE here
```

`seeded_cash_tokens.add()` is the **first statement of `_seed_cash_instrument_from_orb` (`:932`)** —
so it is only ever reached for instruments that returned bars. **A bar-less instrument is never
marked seeded, so the very next pass retries the same instrument.**

**Consequence:** the pointer advanced through the 215 option underlyings (213 got bars, 7 missed),
reached the bond tail, and has been re-probing the *same ~30 dead bonds* every pass ever since.
At 0.34 s/call that is ~10 s of every 15 s pass spent fetching nothing.

- `seeded_count` frozen at **221** for the entire session — the smoking gun.
- The ~2,000 real mainboard equities beyond the bonds are **structurally unreachable**. The scanner
  will never get to them, today or any day.
- `select_mainboard_cash_equities()` exists in `universe_registry` but **is not called by the live
  service** — and in its current form returns all 9,292 anyway, so it does not filter bonds either.

**Why the bar pipeline "died" at 09:25:** it did not die. Every pass after the option underlyings
were done spends its whole budget on bond fetches that persist nothing.

---

## 2 · ROOT CAUSE — min/max capital-per-trade is enforced, then silently undone

Config: `min_capital_per_trade = 40,000` · `max_capital_per_trade = 100,000` · capital ₹10 cr.
Observed: **43/43 open positions below the floor.** min ₹2,521 · median ₹7,107 · max ₹14,257.

The floor **is** read and applied (`live_paper_trading_service.py:4866-4871` →
`live_universe_paper_loop.py:607-622 capital_clamped_quantity`) — but at the **wrong point**.
Both cash entry sites check the floor and *then* apply six size-down multipliers with **no re-check**:

```python
# live_universe_paper_loop.py:950   floor enforced here — qty 291, notional Rs 99,971 -> PASSES
clamped_quantity = state.capital_clamped_quantity(...)
if clamped_quantity <= 0: return False
...
clamped_quantity = int(                                   # :969  shrinks ~13x, NO re-check
    clamped_quantity * state.debate_risk_size_multiplier(...)
    * state.news_event_size_multiplier(...)
    * state.win_probability_size_multiplier(...)
    * state.capital_allocation_size_multiplier(...)
    * state.world_model_size_multiplier(...)
    * state.organism_vitality_multiplier())
clamped_quantity = state.apply_workspace_caution(clamped_quantity)   # :980
if clamped_quantity <= 0: return False                    # :983  only checks > 0, never the min notional
_open_position_from_signal(state, signal, clamped_quantity, ...)     # :997  opens at Rs 4,810
```

Same defect at the second cash site (`:869-873` floor, `:885-898` multipliers).

**Live multiplier values (measured):**

| Lever | Value | Source |
|---|---|---|
| ML win-probability (fractional Kelly) | **×0.25** (floor; negative edge at 19% win rate) | `predictive_core/win_probability_engine.py:36,54-60` |
| Organism vitality (homeostat) | **×0.25** (vitality 0.344, 19 degraded components) | `autopoiesis/organism_vitality_gate.py:52-57` |
| Global-workspace caution | ×0.90 | `live_universe_paper_loop.py:569-570` |
| World-model planning | ×0.92 on shorts | `:256-273` |
| Capital-allocation (CVXPY) | ×1.00 — identity, not earned | `:229-246` |
| Debate-risk / news | ×1.00 — not earned | `:354-389` |

Product ≈ **0.0518** → ₹100,000 collapses to ≈ ₹5,000. **Maximum reachable notional today is
₹22,500 — structurally below the ₹40,000 floor**, which is why 100% of positions violate it.

Exact reproduction (read-only, real config, real positions):
```
NATIONALUM entry 343.54 stop 346.05 -> risk-sized 798,082 | margin-limited 291
  capital_clamped -> 291  (Rs 99,971, passes the 40k floor)
  x0.05175 -> qty 14, Rs 4,810   <-- EXACT match to the live position
MANKIND    -> capital_clamped 39 (Rs 98,304 passes) -> x0.05175 -> qty 1, Rs 2,521  <-- EXACT match
```

**Secondary:** `max_risk_per_trade_fraction` (2%) is **inert** — at ₹10 cr the risk-limited qty is
always far above the margin-limited qty, so `max_capital_per_trade` always binds.
**The options paths never call `capital_clamped_quantity` at all**
(`option_credit_spread_live_path.py:226-231, :344-346`) — neither min nor max applies to option lots.
`clamp_quantity_to_capital_limits` (`config_enforced_paper_run.py:57-70`) is a dead duplicate
(Rule-G orphan, referenced only by a test).

---

## 3 · ROOT CAUSE — 100% short book (explains the losses and poisons the memory)

Not a sign error. The ORB detector, stop/target management, and ledger P&L math are all
symmetric and correct (verified).

`positioning_permits_entry` (`live_universe_paper_loop.py:324-338`) →
`participant_positioning/market_positioning_bias.py:12-41`. The live opponent-ledger reading is
`directional_lean: "bearish"`, `retail_on_other_side: true`, conviction "normal" — every early-return
escape is false, so **every LONG entry is vetoed, all day**. `positioning_deferred_count = 145`.

One **daily, market-wide NSE index-futures** report is applied as a **binary all-or-nothing veto to
every individual cash equity**. No size-down tier, no per-symbol relevance test, no cap on how
one-sided the book may get.

2026-07-24 was a **rising** day (153 up / 72 down of 225 tokens, median +0.575%) — the system took
282 shorts vs 82 longs. Outcome across the whole memory:

| direction | n | win rate | P&L |
|---|---|---|---|
| long | 82 | **0.500** | **+10,282** |
| short | 294 | **0.095** | **−45,033** |

**The entire loss is the forced short book.** The long book is profitable.

---

## 4 · ROOT CAUSE — `confident_win` is mathematically unreachable

Bands (`prediction_lab/mechanism_recalibration.py:25-26`): p ≥ 0.60 → confident_win,
p ≤ 0.40 → confident_loss. Model is a bare logistic on ADX:
`p = sigmoid(0.18 * (ADX − 22.5))` (`adx_confidence_prediction.py:33-40`).

**4a — the recalibration offset caps the only win-capable mechanism below the threshold.**
`learn_mechanism_recalibrations` (`memory_reflection/assumption_registry.py:246-275`) computes
`offset = actual − predicted` over the last 40 experiments. Current learned offsets:

| mechanism | n | predicted | actual | offset |
|---|---|---|---|---|
| post-breakout trend continuation (ADX trending) | 40 | 0.8124 | 0.1750 | **−0.6374** |
| long ATM option riding the spot's ORB breakout | 40 | 0.7973 | 0.4500 | −0.3473 |
| indeterminate regime | 27 | 0.4841 | 0.4074 | −0.0767 |
| false breakout into range-bound chop | 50 | 0.2059 | 0.2600 | +0.0541 |

Reproduced end-to-end: **max attainable recalibrated p on the only win-capable mechanism = 0.3626**,
against a 0.60 threshold. A raw probability of 1.2374 would be required. `confident_win = 0` is a
hard impossibility, not bad luck. DB timeline confirms the switch-on:
`2026-07-24: confident_win 115` → `2026-07-25: 0` → `2026-07-27: 0`.

**4b — monotonicity inversion.** `mechanism_name` is chosen from the **raw** band while the offset is
keyed on that mechanism, so recalibrated p is discontinuous and non-monotonic in ADX: crossing
ADX 24.75 makes p jump **down** from 0.4435 to 0.0100. The system rates a *strong* trend as its
single worst setup.

**4c — ADX unwarmed for 38% of entries.** `_regime_adx_warmed_at` (`:641-653`) returns **0.0** when
fewer than 28 bars exist. **144 of 376** records sit at p ≈ 0.0712 — graded with no ADX signal at all
and auto-filed confident_loss. (Directly caused by §1: bar history is starved.)

**4d — both win-capable mechanisms are also in the antibody veto set**, independently guaranteeing
confident_win = 0. Each of 4a and 4d alone is sufficient.

**4e — the offset is frozen.** Recency window is 40 and the mechanism is vetoed, so no new rows
accrue and the −0.6374 correction can never decay. (SUSPECTED — structurally implied.)

**Entering confident_loss trades is BY DESIGN** (`prediction_record.py:1-8` — a falsification lab
that deliberately tests losing predictions). **The bug is that nothing caps the confident_loss share
of a live book**: `assigned_table` appears **nowhere** in the entry path. A design meant for cheap
offline experiments was wired to the live loop unbounded.

`promoted=False` / `reject_deflated_sharpe_too_low` is **display-only** — it never gates entries
(`_strategy_readiness_summaries` is called only by the snapshot builder). Defensible for paper, but
there is **no circuit breaker** for a strategy that is rejected, calibration-violated, and bleeding.

---

## 5 · Data flow — is it reaching the features?

**Yes for the base pipeline, no for breadth.** Kite is authenticated and quotes/bars flow. But:

- Only **213 of 9,292** names ever get bars (§1) — every downstream engine is fed a 2.3% slice.
- The live feed is **Kite-only**: `KiteLiveUniverseFeed(authenticated_kite_client, ...)`
  (`live_paper_trading_service.py:485`). `MultiBrokerHistoricalBarSource` — the Upstox / Angel One /
  Breeze / Kite fleet — **exists (`:5342`) but is NOT injected into the live universe feed**. The
  0.34 s/call single-broker pacing is the throughput ceiling; the other three broker APIs are idle.
- `_advance_one_pass` (`:947`) runs **inside the same try block** as ~45 downstream feature stages
  (`:948-994`). Any exception in the scan pass **skips every remaining feature that pass**. Errors
  print to stdout, which is a socket — **not captured to any file**, so failures are invisible.
- `_persist_todays_session_bars` swallows all exceptions (`kite_live_universe_feed.py:141-142`,
  `except: pass`) — a Rule-O violation; silent persistence loss is undetectable.

---

## 6 · Ranked fix order

1. **Filter the scan universe to real mainboard equities** and **mark bar-less tokens as seeded** so
   the pointer always advances. Fixes "very few trades" and feeds every downstream engine. (§1)
2. **Fix the long veto** — make the opponent ledger a size-down tier, not a 100% one-side block, and
   cap book one-sidedness. Stops the bleeding. (§3)
3. **Move the min/max capital gate to the last step** before opening, at all four entry sites; skip
   the trade rather than open a token position. (§2)
4. **Cap the confident_loss share** of the live book; make recalibration monotonic; do not grade a
   trade when ADX is unwarmed. (§4)
5. **Inject the multi-broker bar fleet** into the live feed to lift the fetch ceiling. (§5)
6. **Capture the loop's stdout to a file** and isolate `_advance_one_pass` from the feature stages so
   one bad pass cannot skip 45 features silently. (§5)

---

*Diagnosis only — no code changed. Rule-F real-data pass: performed live against the open market.*

---

## 7 · ROOT CAUSE — why there is not a single option trade

**Nothing is wrong with option data, the chain, expiry, lot size, quotes, liquidity, or config.**
Verified by re-running the real assembly read-only: 39,070 NFO rows → 38,430 phase-1 contracts →
215 underlyings → ladder of **2,917 instruments, all 5 indices present**, expiry 2026-07-28, and a
batched quote call returned **2,917/2,917 prices**. Spot LTP resolved 215/215.

### 7a — `int(1 × 0.90) == 0`: the workspace caution multiplier zeroes every option order

Both option entry sites start from **`lots = 1`** and then `int()`-truncate after fractional levers:

```python
# option_credit_spread_live_path.py:206, :226-233   (directional twin at :344-350)
lots = 1
lots = int(lots * state.debate_risk_size_multiplier(...)
           * state.index_level_size_multiplier(...)
           * state.organism_vitality_multiplier())
lots = state.apply_workspace_caution(lots)   # :231 -> live_universe_paper_loop.py:583 int(size*mult)
if lots <= 0:
    return False                              # :232-233
```

`workspace_caution_multiplier` (`live_universe_paper_loop.py:555-571`) returns **0.90** whenever the
dominant ignited broadcast is `kind == "risk"`. Live surface confirms it:
`dominant: "cross_modal (risk)" · entry-size caution ×0.90 (live)` and
`RUMINATING on cross_modal (risk) — 10/10 of recent broadcasts (100%)`.

**`int(1 * 0.90) = 0` → every option entry returns False.** Cash is untouched because its quantity is
in the hundreds, so ×0.90 merely trims it. **Only the options path, hard-coded to a base of 1 lot, is
zeroed.** Any lever below 1.0 does this — `organism_vitality_multiplier()` would zero it independently.

This is the single reason there are zero index-option trades. It is a **unit bug**: fractional
multipliers designed for share quantities were applied to a lot count of 1 with no `max(1, ...)`
floor and no "round up or skip" policy.

### 7b — option underlyings are seeded ONCE per process, never reset, with no retry

`option_credit_spread_live_path.py:169` adds the underlying to `seeded_option_underlyings`
**unconditionally at the top of the function, before any gate**; `:499` then skips it forever.
`seeded_option_underlyings` (`live_universe_paper_loop.py:593`) is **never cleared anywhere** — the
only reset (`live_paper_trading_service.py:1098-1100`) is the replay path and clears cash only.

At 25 seeds/pass and ~46 s/pass, **all 215 underlyings are consumed in ~9 passes ≈ 7 minutes after
the open** — exactly the window where no ORB breakout can exist yet. The cash path has
`check_watched_names_for_live_breakout` re-checking every pass (`:802`, called at `:1105`); **the
options path has no equivalent at all.** One look per day, taken at the worst possible moment.

Reconstructed funnel over all 215 underlyings at the real seeding instants (real Kite bars):

| gate | 09:20 | 09:25 | 09:45 | now |
|---|---|---|---|---|
| stand-aside (20<ADX<25) | 72 | 65 | 25 | 20 |
| directional: no ORB breakout yet | 92 | 119 | 106 | 85 |
| directional: memory antibody veto | 0 | 0 | 56 | 80 |
| credit spread: leg-selector None | 18 | 10 | 9 | 14 |
| credit spread: risk-gate reject | 7 | 5 | 2 | 2 |
| **reaches the order** | **26** | **15** | **17** | **14** |

**~26 valid credit spreads existed** at the 09:20 seeding instant — 15 killed by the bearish
positioning veto (§3, applies to options too via `:222-225`/`:340-343`), the surviving ~10 killed by
the `int(1×0.90)=0` truncation.

### 7c — why stock options are near-zero historically (6 trades ever)

`live_tradable_universe.py:211` takes a **single global** `nearest_expiry_date(all_options)` and
`:168-169` drops every contract not on that exact date. Real expiries pulled today:

```
INDEX_OPTION : 2026-07-28, 08-04, 08-11, 08-18, 08-25 ...  (weekly)
STOCK_OPTION : 2026-07-28, 08-25, 09-29                    (monthly only)
```

Today is monthly-expiry week so both coincide. **In the other ~3 weeks of every month the global
minimum is a NIFTY weekly, so all ~210 stock-option underlyings are silently dropped from the ladder
entirely** — a Rule-L full-universe violation, and the exact explanation for "only 6 stock-option
trades ever."

### 7d — the whole directional-option arm is antibody-vetoed

Every directional option uses one hard-coded mechanism name
(`prediction_lab/option_prediction_records.py:74`), and that mechanism is in the veto set with a
−0.347 offset. Only 1-in-8 shadow probes survive (`_SHADOW_PROBE_EVERY = 8`). Additionally
`oversight_permits_autonomous_order(..., is_option=True)` treats **all** options as high-stakes
(`conscience/scalable_oversight.py:26-27, 39-44`), blocking low-confidence option entries outright
(cash gets PANEL_REVIEW + permit=True instead).

### 7e — no dashboard visibility

`seeded_count = 221` on the dashboard is the **cash** counter only
(`live_paper_trading_service.py:4967`). **There is no option-seeding surface at all** — a Rule-N gap
that is why this was invisible.

---

## 8 · CORRECTION — the vitality "hard veto" is NOT confirmed

An earlier analysis in this session claimed the autopoiesis vitality gate was hard-vetoing every
entry (`permits_order=False`). **My own checks do not support that**, and it is recorded here as
REFUTED-AS-STATED so it is not carried forward as fact:

- `_acute_veto_reason` (`organism_vitality_gate.py:248-258`) fires only when the **worst** component
  is **VITAL** and in FAILING/FAILED. The five components with `observed_failure=1` in the homeostat
  store are `thread.win_probability_trainer`, `thread.news_acquisition`,
  `thread.hi_fidelity_replay_builder`, `thread.exchange_filings`, `session.breeze` — **all
  SUPPORTING, none VITAL** (verified against the real registry: 13 VITAL ids, none of them these).
- The decisive empirical test: if entries were reaching the chain and being zeroed, `entries trimmed`
  would keep climbing. Polled 5× over 2.5 minutes of open market: **`entries trimmed` frozen at 180**,
  `orders today` frozen at 46/3000, `fills` frozen at 244, `open` 42. Nothing is reaching the trim
  stage at all.

**What is confirmed:** organism vitality is genuinely low and *falling* (0.344 → 0.307 → 0.295 over
~20 min), 19/36 components degraded, and it contributes a real **×0.25 size lever** to the §2
haircut. What is **not** confirmed is a hard order veto.

**The actual reason no new positions are opening** is §1 + §7b: the cash scan is livelocked on bonds
so no new cash signal is ever generated, and the options path already burned its one-shot seeding
pass in the first 7 minutes. The system is not being vetoed — it is **starved of candidates**.

---

## 9 · Feature wiring — how much of the project actually reaches a trade

Only **4 files** can alter an order: `live_universe_paper_loop.py`,
`option_credit_spread_live_path.py`, `pre_trade_risk_gate.py`, `trading_control_config.py`.
Everything else acts only by writing a field on `LiveUniversePaperState` that one of those reads.

Of 25 packages, **8 currently change an order**: memory_reflection (strongest — 87% of decisions),
participant_positioning (38.5% deferrals), sentience (×0.90, 180 entries trimmed), predictive_core
(win-prob + world-model), conscience, autopoiesis (×0.25), risk_management, indicators (ADX only).

**Wired but returning identity every cycle:** `capital_allocation` (`acted=False`),
`llm_strategy` debate-risk (`earned=False`, 0 observations).

**Display-only (no decision consumes them):** `epistemics`, `society`, `will`, `axiology`,
`intrinsic_motivation`, `market_breadth`, plus `control_arm_*`, `skill_vs_luck_court`,
`per_trade_pre_mortem`, `profit_provenance`, `world_model_scoreboard`, `memory_consolidation`,
`semantic_memory`, `red_team`, `ethics_law`, `incident_post_mortem`.

**Inert by construction — the entire `news_sentiment` trunk (11 surfaces):**
`news_event_calibration_earned` and `index_level_calibration_earned` are declared
(`live_universe_paper_loop.py:191,198`) and read (`:383,402`) but **no code path anywhere sets either
to True**. 58 symbols carry event risk; 0 deferred, 0 sized-down.

**Broken wiring:** `service:4185` reads `getattr(self, "_last_ensemble_disagreement", 0.0)` — that
attribute is **never assigned anywhere**; `surprise_spike` is never passed
(`world_model_planning_engine.py:113`). The dashboard simultaneously shows κ=1.00, surprise
"SPIKE: YES" and disagreement "±33% HIGH" — the spike-kill is dead code.

**Dead indicators (6):** EMA, RSI, VWAP, Supertrend, PCR, EOD-ATM-IV — referenced only by
`indicators/__init__.py`.

**`information_diet` is a broken meter, not evidence.** `information_diet.py:87-93` hard-codes exactly
5 sources and hard-codes ADX to 1.0. It structurally cannot show the ~8 other levers that *are* live.
"Only 5 sources influence decisions" is the meter's limit, not the system's.

**22 engines run once per day at process start and then freeze** — all `_maybe_run_*` are guarded by
`if self._X_last_run_date == today: return` (`service:2902…3669`). The process started ~08:58 IST, so
goal-integrity, interpretability, tripwires, surprise, ensemble, breadth, epistemics, society,
red-team and ethics/law were all computed **pre-open** and never refresh intraday. This is the direct
answer to "many features need an open market to start working": they ran while the market was closed
and will not recompute today.

**70 `except Exception` in `live_paper_trading_service.py`**, most bare `pass` — including the memory
drain + antibody/recalibration refresh (`:4776`) and the whole global-workspace cycle (`:4543`), the
two mechanisms that actually move trades. Rule-O.3 violation.

---

## 10 · Revised fix order

1. **B1 — bond deadlock** (§1): filter to real mainboard equities + mark bar-less tokens seeded.
2. **B7 — `int(1 × 0.90) = 0`** (§7a): floor option lots at 1, or skip explicitly. **One-line-class
   fix that unblocks 100% of option trading.**
3. **B8 — option re-seeding** (§7b): give options a watch-and-retry equivalent to cash; reset
   `seeded_option_underlyings` daily.
4. **B2 — long veto** (§3): graded size-down, not a 100% one-side block.
5. **B3 — capital gate last** (§2).
6. **B9 — per-segment expiry** (§7c): stop dropping all stock options 3 weeks of every month.
7. **B4 — confident_win reachability** (§4).
8. **B10 — intraday refresh** (§9): the 22 once-per-day engines must recompute during market hours.
9. **B5 — multi-broker fleet**, **B6 — logging/isolation** (§5).
