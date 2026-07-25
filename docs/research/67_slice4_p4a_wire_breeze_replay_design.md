# Research/67 — §53 Slice 4 P4a-wire: Breeze 1-second into the replay loop (design)

**Rule D design doc.** P4a built + real-data-verified the Breeze 1-second
`HistoricalBarSource`. This slice makes the **replay loop actually consume it** —
P4a's PRIMARY consumer (Rule K), so the fidelity climb reaches trading decisions,
not just a shelf.

## Current replay path (read from code)
`live_paper_trading_service._build_replay_feed_from_store` loads **5-minute** bars
per token from `MarketDataSqliteStore`, filters to the survivorship-free
point-in-time universe, and builds a `ReplayUniverseFeed(bars_by_token, …)`. The
feed is the seam the market-closed loop runs on. So "wire Breeze 1s in" = let that
`bars_by_token` be sourced from a `HistoricalBarSource` at `SECOND_1` instead of
the store at `MINUTE_5`.

## Constraints that shape the scope (do NOT ignore — Rule I honesty)
- **Rate limit:** Breeze allows 100 calls/min, **5000/day**. A 1-second full-day
  pull is ~23 chunked calls PER instrument, so the ~2000-name cash universe = ~46k
  calls/day — **infeasible**. 1-second replay is therefore for a **bounded focus
  set** (the names actively traded/watched, or a configured list) and/or a single
  session — never the whole universe daily.
- **Session:** Breeze needs a daily manual-login token (task #6). An always-on
  service cannot auto-refresh it yet, so autonomous Breeze-replay is **gated on #6**.

## The build (P4a-wire) — a safe, injectable seam (defaults OFF)
1. `paper_trading/historical_source_replay_feed_builder.py`:
   `build_replay_bars_by_token_from_source(historical_bar_source, instruments,
   bar_interval, from_timestamp, to_timestamp) -> dict[int, list[PriceBar]]` —
   calls `fetch_historical_bars` per instrument, drops empties. Generic over ANY
   `HistoricalBarSource` (so it also works for Kite minute), reused for Breeze 1s.
2. `HighFidelityReplayConfig(bar_source, instruments, session_date,
   bar_interval=SECOND_1)` — a single optional DI param on the service.
3. `LivePaperTradingService(..., high_fidelity_replay=None)`. In
   `_build_replay_feed_from_store`: **if** a `high_fidelity_replay` is injected,
   build `bars_by_token` from it (the focus instruments, that session, 09:15–15:30
   IST) and build the `ReplayUniverseFeed` from that (provenance REPLAY_FAITHFUL /
   BAR_ONLY — 1-second is still bar-only fidelity, just finer). **Else** the
   existing store-5m path, unchanged (no regression — the default is None).

## Verification
- **Hermetic (Rule J):** inject a fake `HistoricalBarSource` → the builder yields
  `bars_by_token` → a `ReplayUniverseFeed` serves those 1s bars; the service branch
  picks the injected source when present and falls back to the store when absent.
- **Real data (Rule F):** a script builds `bars_by_token` from the REAL Breeze 1s
  source for ITC on a real session and asserts the `ReplayUniverseFeed` serves
  real 1-second bars (time-ordered). (Uses the same daily session token as P4a.)

## Scope & backlog (Rule K)
- **This slice:** the builder + the injectable seam + verification — replay CAN run
  on Breeze 1s.
- **Queued (needs task #6 + a rate-limit-aware focus scheduler):** the always-on
  service AUTONOMOUSLY selecting a focus set + session + auto-refreshing the Breeze
  session to run 1s replay unattended. Until then the seam is exercised by the
  real-data script / an explicit injection, not the unattended loop.
