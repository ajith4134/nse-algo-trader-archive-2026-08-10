# Research/80 — Groww historical HistoricalBarSource adapter (design, task #19)

**Rule D design doc**, grounded in the Groww API sourcing (2026-07-25, read from the
`growwapi-1.5.0` sdist source + official docs). Adds Groww as an interchangeable
market-data source (PLAN §8a.12).

## Sourcing facts that shape the design
- **SDK `growwapi` (MIT)** but HEAVY deps (pandas, protobuf, aiohttp, nats-py,
  google) and **`GrowwAPI(token)` construction does an unguarded network call**
  (`_get_changelog`) + stdout spam → NOT hermetic. Import itself is hermetic.
- **Auth is a plain Bearer token** (`Authorization: Bearer <token>` + `x-*` headers).
  The SDK's `get_access_token(api_key, secret=…/totp=…)` mints it via SHA256 checksum;
  docs say the token **expires daily ~6 AM** — CONFLICTS with the user's "long-lived"
  (their JWT `exp` is year 2051). The real-data pass resolves this.
- **Method:** `get_historical_candles(exchange, segment, groww_symbol, start_time,
  end_time, candle_interval, timeout)` → `{"candles": [[ts,o,h,l,c,v,oi], …]}` (OI
  null for non-FNO). Deprecated `get_historical_candle_data` — avoid.
- **Intervals:** `1minute…30minute, 1hour, 4hour, 1day, …` — **NO sub-minute** (so
  Groww is a MINUTE source; `SECOND_1` raises). Per-call range caps: 1–5min ≤30d,
  10–30min ≤90d, 1h+ ≤180d. History back to **2020** (~5–6y).
- **Symbols:** Groww's own `groww_symbol` (cash `NSE-WIPRO`; F&O
  `NSE-BANKNIFTY-24Dec25-27000-PE`) from the instrument CSV
  `growwapi-assets.groww.in/instruments/instrument.csv` (≠ exchange trading symbol).

## The build
`market_data/groww_historical_bar_source.py`:
- `GrowwHistoricalBarSource(groww_client, groww_symbol_resolver=default_groww_symbol)`
  implements `HistoricalBarSource.fetch_historical_bars`. Injected client (duck-typed
  on `.get_historical_candles(...)`) — **never imports `growwapi`** (heavy + non-
  hermetic construction). Interval map (minute+day; `SECOND_1` raises); per-interval
  chunk windows (30/90/180 days); `groww_symbol` cash `NSE-{sym}` (options raise
  until a CSV-backed resolver is injected); parse positional candles → `PriceBar`
  (timestamp epoch-or-`yyyy-MM-dd HH:mm:ss` IST; OI when present).
- `GrowwRestHistoricalClient(access_token)` — a THIN REST client (`requests`, already
  a dep) exposing `get_historical_candles(...)` via a direct Bearer call, so we avoid
  installing the heavy SDK. Used at the composition root / real-data pass.

## Verification
- **Hermetic (Rule J):** injected fake client returning a real-shaped
  `{"candles": [...]}` — interval map, cash symbol, segment (CASH/FNO), chunk
  windows + dedupe, OHLCV+OI parse, `SECOND_1`/option errors, empty envelope.
- **Real data (Rule F) — token in hand:** `GrowwRestHistoricalClient(GROWW_API_KEY)`
  pulls real 1-minute RELIANCE bars for a recent trading day; assert non-empty,
  ordered, OHLC-sane. If the token 401s (daily-expiry), wire the checksum refresh
  (`get_access_token` with the secret) — tracked.

## Wiring (Rule G) & backlog
Same `HistoricalBarSource` seam → plugs into `build_replay_bars_by_token_from_source`.
Queued: Groww options symbol resolver (from the instrument CSV); token daily-refresh
(checksum with GROWW_API_SECRET) if the real-data pass shows daily expiry.
