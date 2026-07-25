# Research/66 — §53 Slice 4 P4a: Breeze 1-second historical bar source (design)

**Rule D design doc**, grounded in the sourcing pass (research/63-style sweep,
2026-07-25; findings summarized below). Adds ICICI Direct **Breeze** as a
`HistoricalBarSource` giving **1-second** OHLCV+OI — the fidelity climb above the
BASE bar-only replay (research/62 slice 4). Skill: sourcing-oss-parts (done) +
Rule I (acquire the source).

## Sourcing findings that shape the design (all verified from source/docs)
- **SDK:** `breeze-connect` (PyPI, ICICI official), MIT, deps = `python-socketio[client]`,
  `requests`, `pandas`; active (v1.0.69, Apr 2026). → **DEPEND** on it, don't vendor.
- **1-second is v2-only:** `get_historical_data_v2(interval="1second", from_date,
  to_date, stock_code, exchange_code, product_type, expiry_date, right,
  strike_price)`. v2 intervals = {1second,1minute,5minute,30minute,1day} (NOT
  3m/10m/15m/60m). Response `{"Success":[{datetime,open,high,low,close,volume,
  open_interest}], "Error":…, "Status":200}`.
- **⚠ import-time network I/O:** `import breeze_connect` unconditionally `urlopen`s
  the SecurityMaster.zip AND imports socketio AND writes a `logs/` dir. So the
  adapter module MUST NOT import breeze_connect — it takes an **injected
  authenticated client** (duck-typed on `.get_historical_data_v2(...)`), exactly
  like `KiteHistoricalBarSource`. Construction happens only at the composition
  root / verification script; tests inject a fake. This keeps the adapter
  import-safe and hermetic (Rule J).
- **≤1000 candles/call** → multi-window **chunking** is mandatory for 1s (1000s ≈
  16.7 min/call; a full session ≈ 23 calls/instrument). Rate limit 100/min,
  5000/day — fine when chunked.
- **Session:** daily manual login (TOTP at the login URL) → `session_token`
  (expires 24h/midnight); `BreezeConnect(api_key).generate_session(api_secret,
  session_token)`. Creds via `.env` (`ICICI_BREEZE_API_KEY/_API_SECRET`, already in
  the loader) + a daily session token. Auth/session is a SEPARATE concern from the
  adapter (like Kite's access token).
- **Gotchas:** `Success: []` is ambiguous (bad-request vs empty) — return [] but do
  not treat as authoritative; v1↔v2 timestamp disagreement (use v2); 1s history
  reliably ~3y. from/to are ISO8601 UTC millis (`…T07:00:00.000Z`).

## The build (P4a)
1. `BarInterval.SECOND_1 = "1s"` (new). Guard `KiteHistoricalBarSource` to raise a
   clear error for intervals Kite can't serve (1s), instead of a KeyError.
2. `market_data/breeze_historical_bar_source.py`:
   - `BreezeHistoricalBarSource(authenticated_breeze_client, stock_code_resolver=…)`
     implements `fetch_historical_bars(instrument, bar_interval, from, to) ->
     list[PriceBar]`.
   - `BREEZE_V2_INTERVAL_NAME_BY_BAR_INTERVAL` (the supported subset; unsupported →
     ValueError).
   - Addressing: cash equity → `exchange_code="NSE", product_type="cash"`;
     index/stock option → `exchange_code="NFO", product_type="options",
     expiry_date, right(call/put), strike_price`. `stock_code` via an overridable
     resolver (default = the instrument's underlying symbol; ICICI stock codes can
     differ — the resolver is the seam to inject a SecurityMaster mapping later).
   - **Chunking:** window = 1000 × interval_seconds; iterate [from,to], dedupe by
     timestamp (guards inclusive-boundary double counts), concat → PriceBars.
   - Parse the `Success` envelope → `PriceBar` (ISO datetime, float OHLC, int
     volume, `open_interest` when present).
3. Verification:
   - **Hermetic (Rule J):** inject a fake client returning real-shaped v2 envelopes;
     assert interval mapping, cash+option addressing, chunk windows + dedupe,
     parsing, empty-envelope handling, unsupported-interval error. Fake lives only
     under tests/ (never in src/).
   - **Real data (Rule F) — user has Breeze creds:** a guarded verification script
     constructs the REAL `BreezeConnect`, `generate_session` with `.env` creds + a
     daily session token the user supplies, and pulls real 1s bars for real NSE
     names (RELIANCE, ITC, …) — asserting non-empty, monotonic timestamps, sane
     OHLC. This is the sign-off; until run it is an OPEN BLOCKER.

## Scope & backlog (Rule A right-size, Rule K)
- **P4a = the adapter + real-data verify.** Cash addressing is the clean verified
  path; option addressing is built too but its `expiry_date` FORMAT is confirmed
  only on the real-data pass (flagged, not silently skipped).
- **Queued next (P4a-wire):** wire Breeze in as the replay router's fidelity source
  (bar-only → 1s) so the loop actually consumes it — the adapter's PRIMARY consumer
  (Rule K: until then P4a is "built + verified, purpose-consumer queued").
- **Queued (P4b):** live-depth recorder (record L2 forward — the only path to
  historical depth).
- **Queued:** daily Breeze session-token refresh workflow (auth layer), and an
  ICICI-stock-code ↔ NSE-symbol mapping if the real-data pass shows mismatches.
