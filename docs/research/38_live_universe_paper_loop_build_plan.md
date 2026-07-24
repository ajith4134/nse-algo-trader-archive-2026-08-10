# 38 — Live Universe-Wide Paper Loop: Build Plan (2026-07-24)

## Why this document exists
The dashboard the operator was looking at showed **no full-universe trades
and no OPEN trades**. Root cause, confirmed in code + the SQLite store on
2026-07-24 (market open):

1. The dashboard's paper lab is **hardcoded to INFY only**
   (`dashboard_server._load_stored_intraday_bars` loads token `408065`;
   `_current_snapshot` calls `run_config_enforced_orb_paper_lab(..., _INFY, ...)`).
2. It runs a **historical replay** that opens *and closes* every trade
   inside the replay, so at snapshot time everything is already flat —
   nothing is ever "open".
3. The intraday `price_bars` table holds **1 instrument (INFY), 1,650
   5-min bars**. The 2,000+ cash universe and 215 option underlyings have
   **no intraday bars** — only EOD reports (3,318 cash bhavcopy symbols,
   62,696 F&O contract rows).
4. `MarketClockGatedDataSourceRouter` exists but its `_live_bar_source`
   is always `None`, so it **permanently serves replay** and is not wired
   into the dashboard loop.

This conflicts with the standing rule (CLAUDE.md / memory: *full universe,
never sample symbols*; *real-data verification gate*; *no orphaned
features*). The market-clock-gated live handoff (PLAN §1.4, research/26)
was **decided but never built past the router stub** because it was
blocked on an open session. **2026-07-24 the market is open and live Kite
auth works** — so it is now buildable and Rule-F verifiable.

## Decided behavior (PLAN §1.4 + research/26) — the contract we build to
- **Market OPEN (9:15–15:30 IST, Mon–Fri minus holidays):** the router
  drains replay and serves the **live Kite feed**. The paper loop trades
  the **full universe** on live data, opening positions that stay **OPEN
  intraday** and are managed against live price.
- **Market CLOSED:** the router serves the looping `HistoricalReplaySource`
  so paper/learning **never stops** (24/7). No live orders, ever, when
  closed.
- **At 15:15 IST:** Layer 8 (`execute_intraday_square_off`) flattens every
  open paper position — safe-ordered (BUY-cover before SELL-hedge), retry
  to flat, unflattened legs surfaced CRITICAL. No overnight carry, ever.
- **Paper and live are two independent consumers** of the same router,
  each with its own `BrokerClient` + ledger/capital. Paper has no market
  gate (always on); live gates on `MarketClock == open`. **This session
  builds PAPER-on-live-data only — no real-money orders** (operator
  decision 2026-07-24).

## Operator decisions locked (2026-07-24)
- **Order mode:** PAPER trading on the LIVE feed. Simulated fills
  (`SimulatedBrokerClient`), ₹0 real-money risk. Live real-money orders
  are a separate, later, explicitly-gated build.
- **Universe scope:** CASH + OPTIONS together — all liquid NSE cash + the
  215 option underlyings (5 index + 210 stock) with ATM/ITM/OTM ladders.
- **Strategies:** ORB (cash directional) + credit-spread (options).

## Live universe facts (real Kite master, 2026-07-24)
- NSE EQ rows: 9,829 (incl. SME `-SM`, `-BE` etc.; phase-1 tradable cash =
  the liquid mainboard subset — the classifier/liquidity filter decides).
- NFO option contracts: 38,453 across **215 distinct underlyings**.
- Nearest weekly expiry: **2026-07-28**.

## Kite rate-limit strategy (the real constraint)
- `quote()` / `ltp()`: up to ~500 instruments per call, ~1 req/s → the
  whole cash universe priced in a handful of calls per scan interval.
- `historical_data()`: ~3 req/s, one instrument per call → too slow to
  poll thousands each interval. Use it **once** per shortlisted instrument
  to seed today's opening-range / intraday bars, not every tick.
- **Live path design:** an LTP/quote-batch scanner for breadth (all cash
  priced cheaply), historical intraday only for the shortlist that needs
  bar history (ORB opening range), and KiteTicker WebSocket as the later
  scalable streaming upgrade. Bars aggregate from ticks/quotes into the
  same `PriceBar` shape the router already yields.

## Build slices (Rule A — one at a time, Rule F — verify each on live data)
1. **Live universe assembly** — `live_tradable_universe.py`: fetch Kite
   master, reuse `build_phase1_instrument_universe` for cash, add an
   **option-ladder selector** (ATM/ITM/OTM around live spot for the
   current expiry, per underlying). Export the concrete instrument list
   the loop scans. Verify: ~2,000 cash + 215 underlyings’ ladders on real
   data.
2. **Live bar/quote source** — `kite_live_quote_bar_source.py` with a
   `stream_bars()`/snapshot interface; attach it to the router as
   `_live_bar_source` so `current_data_mode` returns LIVE now. Verify:
   real LTPs for a universe batch during the open session.
3. **Universe-wide live paper loop** — `live_universe_paper_loop.py`: each
   interval, price the universe, run ORB (cash) + credit-spread (options),
   size via the risk gate, open **held-open** paper positions, manage
   stop/target on live price, and at 15:15 call Layer 8 to flatten. Two
   consumers (paper always; live stub gated). Wires L8 into the loop
   (Rule G).
4. **Open-positions model + dashboard** — a live open-positions view + the
   §9 CONFIDENT-WIN/LOSS/UNCERTAIN tables populated from the live loop;
   dashboard reads live OPEN positions across the universe. Then sign off
   L8 (now wired) + L9 (open-positions view) on live data.

## Rule G wiring note (important finding)
Before this build, Layer 8's `execute_intraday_square_off` /
`IntradaySquareOffSchedule` were referenced **only by tests and their own
`__init__`** — no runnable loop consumed them; the paper engine did its
own inline single-leg close (`opening_range_breakout_paper_engine.py:115`)
that does NOT do safe multi-leg ordering. Slice 3 wires L8 into the live
loop, closing that orphan. The flowchart note's earlier "consumed by the
paper loop now" was inaccurate and is corrected in `08_session_square_off.md`.

## Verification gates (Rule F)
Each slice signed off only after a check against the **live** Kite feed
during the open session (not replay, not synthetic). The 15:15 square-off
of live-opened paper positions is the capstone L8 real-data check.
