# Why the bot makes no profit — evidence-based diagnosis (2026-08-01)

Source: `~/.nse_algo_trader/experience_memory.sqlite3` — 2,790 real closed
experiences across 7 sessions (2026-07-22 → 07-31). Numbers are the ground truth,
not the architecture docs.

## Headline
- **Net P&L: −₹190,428** over 2,790 trades.
- **Gross P&L (before fees): −₹55,976.** Fees: **−₹134,453**.
  → Even with ZERO fees the system still loses. There is **no positive edge** in
  the dominant strategy, and fees then multiply the loss ~3.4×.

## Finding 1 — The dominant strategy (cash ORB) has negative expectancy
- Cash equity = **2,545 of 2,790 trades (91%)**, P&L **−₹206,078** (live+replay).
- Win/loss asymmetry (cash): 885 wins avg **+₹198**, 1,660 losses avg **−₹230**.
  → Loses *more often* AND *more per loss*. Negative on both axes.
- By mechanism (all ORB arms lose):
  - false-breakout in range chop: 1,381 trades, **−₹98,004**
  - post-breakout trend continuation: 743 trades, **−₹67,374**
  - indeterminate regime: 421 trades, **−₹40,700**
- ORB fires on ~646 distinct names/session (≈1.07 trades/name) — a **shotgun over
  the whole cash universe with no selection**, not a targeted edge.

## Finding 2 — Fees dwarf the signal
- Avg cash trade: fee **₹49.2** vs avg |P&L move| **₹218.8** → **fees are 22.5% of
  the gross move**. A strategy whose true edge is ≈0 cannot survive a 22.5% tax.
- Worst day 07-28: 689 cash trades, **−₹63,733**, **₹37,686 fees**.

## Finding 3 — The mix is INVERTED vs. where the edge actually is
The only profitable things barely trade:
| segment/strategy | trades | P&L | avg return |
|---|---|---|---|
| credit_spread_v1 (options) | 95 | **+₹21,461** | **+2.66%/trade** |
| index_option (all) | 7 | **+₹18,285** | — |
| stock_option | 238 | −₹2,635 | — |
| cash ORB | 2,545 | **−₹206,078** | −0.4%/trade |

→ Credit spreads are the **one real edge** (+2.66%/trade) and index options are
net positive, but together they are **~3.6% of all trades**. The system churns the
losing segment thousands of times and starves the winning one. Violates Rule L
(three segments equal).

## Finding 4 — WHY index/option trades barely fire (user's complaint)
Config is fine (`trading_control_config.json`: all 3 segments + both strategies
enabled). The starvation is structural in `option_credit_spread_live_path.py`:
1. **ADX warmup gate** (`try_open_option_position_for_underlying`, line 309):
   `if len(spot_bars) < 28: return False` — needs 28× 5-min bars ≈ **2h20m into
   the session** before an underlying is even eligible. Options are blind until
   ~11:45 IST.
2. **`regime_unmeasured` abstain** (line 315–321): if ADX hasn't warmed, skip.
3. **Regime hard-constrains the arm**: credit spread needs non-trending tape,
   directional needs trending; INDECISIVE → stand aside.
4. **Round-robin look budget** across ~215 option underlyings (least-recently-
   looked-first) — each underlying is examined rarely per session, so few clear
   all gates in the ~4h window that remains after warmup.
5. Historic bugs (now fixed, per code comments) where the compounded advisory
   size-down levers **rounded option lots to zero** and "blocked 100% of option
   entry" — the residue is a very tight funnel. Current `capital_allocation_state`
   weights are ~1e-9 for most option keys.

Net: index options got **0–3 fills/day**, stock options 8–74/day, cash 232–689/day.

## Finding 5 — Architecture/alpha imbalance (the root cause)
50k LOC / 289 modules / "16 trunks" of conscience·sentience·autopoiesis·will·
axiology sit on top of a signal core that is just **ORB + credit-spread + ADX
gate**. All the meta-machinery can only *gate or size-down* existing signals —
**none of it creates alpha**. The system is over-built on governance and
under-built on edge.

## Prioritised fixes (highest P&L leverage first)
1. **Stop trading cash ORB as-is.** It is −₹206k with negative expectancy on both
   axes. Either disable `nse_cash_equity` until ORB clears a real out-of-sample
   edge gate, or gate entries hard (only high-ADX + confirmation + min expected
   move ≥ N× round-trip cost).
2. **Make entries fee-aware.** Require expected edge per trade ≥ a multiple of the
   round-trip cost (`estimate_round_trip_cost` already exists) — kills the 22.5%
   fee-tax trades before they're placed.
3. **Rebalance toward the real edge.** Credit spreads (+2.66%/trade) and index
   options are profitable — remove the structural starvation: shorten the ADX
   warmup for options (use a faster regime proxy or 1-min bars for warmup),
   raise the per-pass option look budget, and enforce Rule-L segment parity.
4. **Selectivity, not breadth.** Rank cash candidates and take the top-K by edge
   instead of firing on all ~650 names that break their range.
5. **Validate edge before governance.** No amount of conscience/sentience/
   autopoiesis fixes a signal with no edge.

## What is NOT the problem
- Not the config (segments/strategies enabled).
- Not a fee-model bug (₹49/round-trip on ₹40–100k intraday equity is realistic).
- Not "needs more AI trunks" — the profitable strategies already exist and win;
  they are starved, and the losing one is over-fired.
