# research/93 — Show PERSISTED closed trades on the dashboard (not the ephemeral ledger)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD. Fixes the user-reported "yesterday's 200+ trades not in Closed
trades." Priority BEFORE VPIN (verify the 24/7 sim is visibly complete first).

## Verification finding (the 24/7 sim WORKS)
Real evidence from the live system: **102 positions open now** (replay actively trading),
**340 graded closed trades persisted** in `experience_memory.sqlite3` — **220 live**
(2026-07-24 real session) + **120 replay_faithful** (the 24/7 loop) — real win/loss + P&L,
all squared off by 15:15. All 5 §53 success criteria hold. The sim is not broken.

## The bug
The "Closed trades" panel is fed by `LivePaperTradingService._recent_closed_trades()`, which
reads `self._state.closed_trades` — the **in-memory, per-process ledger**. That resets on
every service restart (so after many restarts today it shows ~3) and NEVER reads the
persisted 340-trade memory. So the durable trades (yesterday's 220 live + today's replay)
are invisible in the panel even though they exist (they DO drive the Reflection "340
experiences").

## Design — source the panel from the PERSISTED memory
1. **`ExperienceMemory.recent_closed_experiences(limit)`** (sqlite) — the most recent closed
   trades from `experience_nodes`: `(occurred_at, session_date, instrument_token,
   instrument_kind, strategy_tag, direction, actual_outcome, realized_pnl, data_provenance)`,
   newest first. Each row IS a closed+graded trade.
2. **`_recent_closed_trades()` reads memory** (durable, near-real-time — the drain records
   each closed trade within one ~5s pass) instead of the ephemeral ledger. Resolve
   `instrument_token → trading_symbol` via a cached map from the tradable universe (cash +
   option ladder); fall back to `#<token>` when unknown. Segment from `instrument_kind`.
   Tag each with `provenance` (live / replay_faithful) so yesterday's LIVE trades are
   distinguishable from today's REPLAY trades. Falls back to the in-memory ledger if the
   memory read fails (no regression).
3. **`ClosedTradeView` gains `provenance`** and the panel shows it + the date, and the count
   reflects the persisted total (not the since-restart ledger). Panel header stays "Closed
   trades" (drop the "today" framing — it now shows persisted history).

## Verification (Rule F)
On the live dashboard: the Closed-trades panel shows the real persisted trades — yesterday's
220 live + today's replay — with symbols, P&L, outcome, live/replay tag. Screenshot.

## Files
- `memory_reflection/experience_memory.py` (+ `sqlite_experience_memory.py`): the query.
- `dashboard/live_paper_trading_service.py`: `_recent_closed_trades` from memory + token→symbol
  map + `ClosedTradeView.provenance` + count.
- `dashboard/render_dashboard_html.py`: show provenance + date in the closed-trades table.
- tests + a live screenshot.

## Rule check
- **Rule F:** verified against the real persisted 340-trade memory + a live screenshot.
- **Rule N:** closed-trades visibility is part of "the sim is visibly complete."
- **Rule G:** the panel now consumes the durable memory (the real source of truth), not a
  process-local ledger.
