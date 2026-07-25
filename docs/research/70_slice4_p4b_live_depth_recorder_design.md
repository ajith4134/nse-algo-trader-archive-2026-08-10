# Research/70 — §53 Slice 4 P4b: live order-book depth recorder (design)

**Rule D design doc.** Historical L2/L3 order-book DEPTH is a permanent blocker —
no vendor sells it (research/62 §1); the ONLY way to ever have it is to **record
our own forward** during live sessions. This slice builds that recorder so depth
history starts accumulating now, for future microstructure features.

## What Kite gives us
`KiteConnect.quote(instruments)` returns, per instrument, a 5-level book:
`depth: {buy: [{price, quantity, orders} ×5], sell: [×5]}` (verified in the SDK).
Polling `quote()` for a bounded focus set each live pass is the snapshot source
(≤500 instruments/call, ~1 req/s — fine for a capped watch set).

## The build (behind DI seams, hermetic — Rule J)
1. `market_data/market_depth_types.py`: `MarketDepthLevel(price, quantity, orders)`,
   `MarketDepthSnapshot(instrument_token, captured_at, bids, asks)` (bids = buy side
   best-first, asks = sell side).
2. `broker_data_source_protocols.MarketDepthSource` (new seam):
   `fetch_market_depth(instrument_tokens) -> dict[int, MarketDepthSnapshot]`.
3. `market_data/kite_market_depth_source.py`: `KiteMarketDepthSource` — injected
   Kite client, `quote()` → parse `depth` → snapshots (real adapter).
4. `market_data/market_depth_snapshot_store.py`: `MarketDepthSnapshotStore` — its
   OWN SQLite file (`~/.nse_algo_trader/market_depth.sqlite3`; depth is high-volume,
   kept off the bars store). `save_snapshots` / `load_snapshots(token, from, to)`
   (bids/asks as JSON per (token, captured_at) row).
5. `paper_trading/live_market_depth_recorder.py`: `LiveMarketDepthRecorder(
   depth_source, depth_store)` — `record_once(instrument_tokens) -> int` fetches +
   persists a snapshot batch; best-effort.

## Wiring (Rule G)
Service constructor flag `record_live_market_depth=False` (default OFF → no
behaviour/load change). When True, it builds `KiteMarketDepthSource(kite_client)` +
`MarketDepthSnapshotStore` + the recorder, and `_run_forever` calls
`record_once(focus)` right after each MARKET-OPEN `_advance_one_pass` (focus = a
capped cash-universe watch set), best-effort so depth never disturbs trading.

## Verification
- **Hermetic (Rule J):** a fake `MarketDepthSource` → recorder → store → readback
  round-trips snapshots; the Kite adapter parses a real-shaped `quote()` depth dict;
  the service records when the flag is on and skips when off.
- **Rule F (OPEN BLOCKER):** real depth needs an OPEN market + a live Kite session
  (both unavailable now — Sat, no token). Recorded as a blocker; run during a live
  session: enable the flag, confirm real 5-level snapshots persist.

## Scope & backlog (Rule K)
- **This slice:** the recorder pipeline + flag-gated live-pass wiring, hermetic.
- **Open (task, Rule F):** real-session depth-capture verification.
- **Open (task):** ENABLE the flag in the deployed service to actually accumulate
  depth forward (the feature is inert until turned on).
- **Queued (task):** depth-CONSUMING features (microstructure signals, depth replay)
  — the recorded depth's eventual purpose-consumer. Until then P4b is "recorder
  built + wired to capture; downstream consumer queued".
