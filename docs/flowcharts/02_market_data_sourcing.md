# 02 — Market Data (Layer 2): Broker-Neutral Sourcing + NSE Official Reports

**Status:** complete for v1 (Kite-only per PLAN §8a.13), all feature-sets
live-verified 2026-07-23 — broker-neutral data model, swappable source
protocols, Kite adapters, all five NSE official-report parsers (over six
report files), SQLite store, F&O history backfill, and the daily ingestion
job. Other-broker adapters deferred post-completion.

## What this layer does
Two halves, per `../PLAN.md` §8a.6/.12:

1. **Broker data sources (swappable)** — a broker-neutral data model
   (`PriceBar`, `MarketTick`, `BarInterval`) plus `Protocol` interfaces
   that every broker adapter implements. Kite Connect is the first
   adapter; Upstox / Angel One / ICICI Direct / Groww slot in behind the
   same protocols when the user provides their APIs. Nothing downstream
   ever sees a broker-specific dict.
2. **NSE official-reports ingestion (secondary)** — the daily public NSE
   files carrying data no broker API provides (`../research/13`):
   delivery % (cash bhavcopy), historical per-contract OI (F&O UDiFF
   bhavcopy), F&O ban list, MWPL utilization, bulk/block deals.

## Whole-pipeline data flow so far

```
[Layer 1: Universe & Instrument Registry]
   kite_instrument_master_loader -> list[Instrument]
        │
        │  Instrument (identity: instrument_token)
        ▼
[Layer 2: Market Data]
┌─────────────────────────────────────────────────────────────────┐
│ Broker side (swappable via broker_data_source_protocols)         │
│                                                                  │
│  HistoricalBarSource (Protocol)                                  │
│    └─ KiteHistoricalBarSource(authenticated_kite_client)         │
│         .fetch_historical_bars(instrument, bar_interval,         │
│                                from_datetime, to_datetime)       │
│         -> list[PriceBar]      (oi=True auto for option kinds)   │
│                                                                  │
│  LiveTickStreamSource (Protocol)                                 │
│    └─ KiteLiveTickStreamSource(kite_ticker_client)               │
│         parse_kite_ticker_payload(raw dict) -> MarketTick        │
│         callbacks fire once per parsed MarketTick                │
├─────────────────────────────────────────────────────────────────┤
│ NSE official-reports side (nse_official_reports/)                │
│                                                                  │
│  NseReportDownloader ── download_* ──> csv text ── parse_* ──>   │
│    cash bhavcopy ─> list[CashBhavcopyDeliveryRow]  (delivery %)  │
│    F&O bhavcopy  ─> list[FoBhavcopyContractRow]    (EOD OI)      │
│    fo_secban.csv ─> FoBanListReport                (ban list)    │
│    combineoi zip ─> list[MwplPositionLimitRow]     (MWPL %)      │
│    bulk/block    ─> list[BulkOrBlockDealRow]                     │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   (nothing consumes these yet — Layer 3 Indicators and the Layer 7
    replay store will be the first consumers)
```

## Files belonging to this layer

```
src/nse_algo_trader/market_data/
├── __init__.py                        # public surface re-exports
├── market_data_types.py               # PriceBar / MarketTick / BarInterval
├── broker_data_source_protocols.py    # HistoricalBarSource / LiveTickStreamSource
├── kite_historical_bar_source.py      # Kite candles -> list[PriceBar]
├── kite_live_tick_stream_source.py    # KiteTicker wrapper + payload parser
└── nse_official_reports/
    ├── __init__.py                    # subpackage public surface
    ├── nse_report_downloader.py       # URL builders + validated downloads
    ├── cash_bhavcopy_delivery_parser.py
    ├── fo_bhavcopy_open_interest_parser.py
    ├── fo_ban_list_parser.py
    ├── mwpl_position_limit_parser.py
    └── bulk_block_deals_parser.py

tests/test_market_data/
├── __init__.py
├── test_kite_historical_bar_source.py
├── test_kite_live_tick_stream_source.py
├── test_nse_official_report_parsers.py
└── test_nse_report_downloader.py

tests/fixtures/
└── sample_nse_official_report_texts.py  # real NSE rows, downloaded 2026-07-23
```

## Every function/class, its imports, and what it exports

### `market_data_types.py`
- **Imports:** stdlib only (`dataclasses`, `datetime`, `enum`).
- **Exports:**
  - `BarInterval(str, Enum)` — broker-neutral: `MINUTE_1/3/5/10/15/30/60`,
    `DAY_1` (values `"1m"`…`"1d"`). Broker adapters own the mapping to
    their API's names.
  - `PriceBar` — frozen dataclass: `instrument_token: int`,
    `timestamp: datetime`, `interval: BarInterval`, `open_price`,
    `high_price`, `low_price`, `close_price: float`, `volume: int`,
    `open_interest: int | None` (None for cash / OI-less sources).
  - `MarketTick` — frozen dataclass: `instrument_token: int`,
    `last_price: float`; optional (None when the mode doesn't send them):
    `exchange_timestamp`, `last_traded_quantity`, `cumulative_day_volume`,
    `average_traded_price`, `open_interest`.

### `broker_data_source_protocols.py`
- **Imports:** `typing.Protocol/runtime_checkable`, `collections.abc.Callable`,
  the types above, `Instrument` from `universe_registry`.
- **Exports:**
  - `HistoricalBarSource(Protocol)` —
    `fetch_historical_bars(instrument, bar_interval, from_datetime, to_datetime) -> list[PriceBar]`.
  - `LiveTickStreamSource(Protocol)` — `register_tick_callback(fn)`,
    `subscribe_instrument_tokens(list[int])`, `start_streaming()`,
    `stop_streaming()`. Callbacks fire from the source's own thread.

### `kite_historical_bar_source.py`
- **Imports:** types above + `Instrument`, `InstrumentKind`.
- **Exports:**
  - `KITE_INTERVAL_NAME_BY_BAR_INTERVAL: dict[BarInterval, str]` (e.g.
    `MINUTE_5 -> "5minute"`, `DAY_1 -> "day"`).
  - `KiteHistoricalBarSource(authenticated_kite_client)` — client is
    injected (anything with `.historical_data(...)`); live auth wiring
    stays in Layer 6. Requests `oi=True` automatically when
    `instrument.kind` is an option kind.

### `kite_live_tick_stream_source.py`
- **Imports:** `MarketTick`, `collections.abc.Callable`.
- **Exports:**
  - `parse_kite_ticker_payload(raw_kite_tick: dict) -> MarketTick` —
    handles full/quote/ltp modes; absent fields -> None. Kite key map:
    `volume_traded -> cumulative_day_volume`, `oi -> open_interest`.
  - `KiteLiveTickStreamSource(kite_ticker_client)` — wraps a
    KiteTicker-shaped object (injected); hooks `on_ticks`/`on_connect`,
    queues subscriptions made before connect and replays them on connect.

### `nse_official_reports/nse_report_downloader.py`
- **Imports:** `requests`, stdlib (`io`, `time`, `zipfile`, `datetime.date`).
- **Exports:** `NseReportDownloadError`; `NseReportDownloader(http_session=None)`
  with `download_cash_bhavcopy_with_delivery(trade_date)`,
  `download_fo_bhavcopy(trade_date)`, `download_mwpl_position_limits(trade_date)`,
  `download_current_fo_ban_list()`, `download_current_bulk_deals()`,
  `download_current_block_deals()` — all return CSV text; plus the six
  `build_*_url(trade_date?, archive_host)` URL builders.
- **Hard-won quirks encoded here (all observed live 2026-07-23):**
  browser UA required; NSE serves HTML error pages with **HTTP 200**
  (every download validates content, not status); dated files reach
  `nsearchives.nseindia.com` late — `archives.nseindia.com` is tried as
  fallback host; zips contain CSV + XML members (CSV picked by
  extension); 3 retries with backoff on network errors, no retry on
  404/soft-404.

### The five parsers (each: stdlib `csv` only, pure text -> dataclasses)
- `cash_bhavcopy_delivery_parser.py` —
  `parse_cash_bhavcopy_with_delivery(text) -> list[CashBhavcopyDeliveryRow]`.
  Source `sec_bhavdata_full_DDMMYYYY.csv`. Fields incl.
  `delivered_quantity/delivered_percent: … | None` (`-` -> None, never 0).
  Leading-space headers/values stripped.
- `fo_bhavcopy_open_interest_parser.py` —
  `parse_fo_bhavcopy_contract_rows(text) -> list[FoBhavcopyContractRow]`;
  `FoContractType(str, Enum)`: `INDEX_OPTION("IDO")`, `STOCK_OPTION("STO")`,
  `INDEX_FUTURE("IDF")`, `STOCK_FUTURE("STF")`. Futures rows carry
  `strike_price=None`, `option_right_code=None`. Skips the file's blank
  spacer lines. Row fields: trade/expiry dates, OHLC, settlement,
  underlying price, `open_interest`, `change_in_open_interest`, volume.
- `fo_ban_list_parser.py` — `parse_fo_ban_list(text) -> FoBanListReport`
  (`ban_trade_date`, `banned_underlying_symbols: tuple[str, ...]`).
  Parses the date out of the `Securities in Ban For Trade Date …` header;
  raises `ValueError` on unrecognizable input.
- `mwpl_position_limit_parser.py` —
  `parse_mwpl_position_limits(text) -> list[MwplPositionLimitRow]` with
  `next_day_fresh_position_limit: int | None` (None == "No Fresh
  Positions" == banned), properties `is_in_ban_period` and
  `mwpl_utilization_percent` (feeds the 95/80/60% thresholds).
- `bulk_block_deals_parser.py` —
  `parse_bulk_or_block_deals(text) -> list[BulkOrBlockDealRow]`. One
  parser for both files (`block.csv` merely lacks the Remarks column);
  `NO RECORDS` day -> empty list; `-`/empty remarks -> None.

## How it was verified
- `pytest`: 33 tests total, all passing (25 new for this layer).
- **Live manual check (2026-07-23, trade date 2026-07-22):** all report
  URLs downloaded from this VPS with plain browser headers — no cookie
  handshake needed for the archive hosts. Full-file parses: cash
  bhavcopy 3,261 rows (323 `-`-delivery -> None), F&O bhavcopy 38,343
  contracts (32,589 STO / 5,114 IDO / 625 STF / 15 IDF), bulk deals 128
  rows, block deals NO-RECORDS day -> 0 rows, MWPL 210 underlyings.
  **Cross-check:** MWPL "No Fresh Positions" set == ban-list file set
  (KAYNES) exactly.

## Broker credentials store (added 2026-07-23, serves Layer 2 data adapters + Layer 6 execution)

```
src/nse_algo_trader/broker_credentials/
├── __init__.py                        # public surface re-exports
└── broker_api_credentials_loader.py   # the ONLY module knowing credential env-var names

tests/test_broker_credentials/
└── test_broker_api_credentials_loader.py

.env  (gitignored, never committed)    # actual keys/secrets live here
```

### `broker_api_credentials_loader.py`
- **Imports:** stdlib (`os`, `dataclasses`, `enum`, `pathlib`) + `dotenv`
  (`python-dotenv`, new dependency).
- **Exports:**
  - `BrokerName(str, Enum)` — `ZERODHA_KITE`, `UPSTOX`, `ANGEL_ONE`,
    `ICICI_BREEZE`, `GROWW`.
  - `BrokerApiCredentials` — frozen dataclass: `broker_name`,
    `api_key: str`, `api_secret: str | None`. **`__repr__` masks both
    values** so secrets can never leak via logs/tracebacks.
  - `load_env_file_into_environ(env_file_path=None)` — .env → os.environ,
    existing env vars win.
  - `load_broker_api_credentials(broker_name, environ=None) -> BrokerApiCredentials`
    — raises `MissingBrokerCredentialsError` naming the missing env var.
    Env-var convention: `<BROKER>_API_KEY` / `<BROKER>_API_SECRET`.
- **Verified 2026-07-23:** real `.env` loads for Kite/Upstox/ICICI (key +
  secret) and Angel One (key only); special characters (`$ # ^ ~`) intact
  via single-quoting; `.env` confirmed absent from `git status`.

## Kite daily session automation (added 2026-07-23)

User asked for OpenAlgo-style automatic request-token handling; built the
stronger version — a fully headless TOTP login (no browser, no clicks,
no open ports; this VPS exposes only SSH). Flow verified against current
community implementations before building.

```
src/nse_algo_trader/broker_sessions/
├── __init__.py
├── kite_access_token_store.py      # persist token + 6AM-IST expiry logic
├── kite_totp_auto_login.py         # headless login -> request_token -> access token
└── refresh_kite_access_token.py    # CLI entry for the pre-market cron

src/nse_algo_trader/broker_credentials/
└── kite_login_credentials_loader.py  # user id / password / TOTP secret from .env

tests/test_broker_sessions/           # 11 tests: expiry boundaries, file perms,
                                      # full fake login chain, wrong-password path
```

- `fetch_kite_request_token_via_totp_login(api_key, login_credentials, http_session=None)`
  — seeds cookies on connect/login, POSTs `api/login` (user id+password),
  POSTs `api/twofa` (pyotp TOTP), then follows redirect **headers**
  manually and extracts `request_token` — the registered redirect URL
  (`http://127.0.0.1/kite/callback`) is never visited, so it needs no
  server.
- `generate_and_store_daily_kite_access_token(...)` — exchanges the
  request token via `KiteConnect.generate_session` (injectable) and
  persists a `KiteAccessTokenRecord` to
  `~/.nse_algo_trader/kite_access_token.json` (chmod 600).
- `KiteAccessTokenRecord.expires_at()` — 6:00 AM IST strictly after
  generation; `is_still_valid(now)`; repr masks the token.
- `python -m nse_algo_trader.broker_sessions.refresh_kite_access_token`
  — skips login while the stored token is valid; `--force` overrides.
  To be cron-scheduled pre-market once live-verified.
- New env vars: `ZERODHA_KITE_USER_ID` / `_PASSWORD` / `_TOTP_SECRET`
  (password + TOTP secret pending from user). New dependency: `pyotp`.
- **Not yet live-verified** — blocked on the user adding password + TOTP
  secret to `.env`; first real run is the verification.

### Credentials on hand vs. still missing (as of 2026-07-23)
| Broker | Have | Still needed for a live session |
|---|---|---|
| Zerodha Kite | key + secret | daily `request_token` via login redirect (interactive) |
| Upstox | key + secret | OAuth authorization code via login redirect (interactive) |
| Angel One | key only | API secret, client code, PIN, TOTP secret |
| ICICI Breeze | key + secret | daily session token via login redirect (interactive) |
| Groww | nothing | API key (+ whatever its auth flow needs) |

## Known limitations / explicitly deferred (remaining Layer 2 scope)
- **Other broker data adapters (Upstox / Angel One / ICICI Direct /
  Groww)** — blocked on the user providing those APIs (`PLAN.md` §8a.12);
  the protocols are the ready-made slot.
- **Persistence / replay store** (bars + daily report tables feeding
  Layer 7's `HistoricalReplaySource`) — next Layer 2 feature to build.
- **Historical (dated) ban-list / bulk-deal archives** — only the
  current-day files are wired; NSE's dated archives for these need their
  URL patterns verified before use.
- **Intraday OI polling** (Kite quotes carry live OI; candles don't) —
  belongs with the live-streaming consumer once one exists.
- **No live KiteTicker/auth wiring** — deliberately Layer 6, same as
  Layer 1's deferral of `kite.instruments()`.

## Live verification (2026-07-23, real Kite session)
- Kite TOTP auto-login chain ran against the real endpoints: password ->
  TOTP -> request_token from redirect header -> generate_session ->
  token stored (valid till 6:00 AM IST next day). Redirect URL
  `http://127.0.0.1/kite/callback` confirmed never visited.
- `KiteHistoricalBarSource` real fetches: INFY 5-min 2026-07-22 -> 75
  bars (09:15-15:25, exactly one full session), cash OI=None as designed;
  NIFTY26JUL25000CE -> 75 bars with real OI (13.3M) carried through.
- Still pending for zero-touch daily automation: `ZERODHA_KITE_TOTP_SECRET`
  (user provided a one-time 6-digit code instead; it was used within its
  30s window for this verification).

## Zero-touch daily automation live (2026-07-23)
- `ZERODHA_KITE_TOTP_SECRET` provided; `refresh_kite_access_token --force`
  performed a fully-automatic real login (no human input) and stored a
  fresh token.
- Cron installed (server tz GMT): 02:35 + 03:05 GMT daily (= 08:05/08:35
  IST, pre-market) -> logs to `~/.nse_algo_trader/kite_token_refresh.log`;
  the second run self-skips when the first succeeded. Package installed
  editable so cron needs no PYTHONPATH.

## Persistence store + daily ingestion job (added 2026-07-23)

```
src/nse_algo_trader/market_data/
├── market_data_sqlite_store.py        # bars + all 5 NSE report types, idempotent
└── daily_nse_reports_ingestion_job.py # evening cron: download all -> store

tests/test_market_data/test_market_data_sqlite_store.py  # 8 round-trip tests
```

### `market_data_sqlite_store.py`
- **Imports:** stdlib `sqlite3`/`datetime`/`enum`/`pathlib` + the Layer 2
  types and report-row dataclasses.
- **Exports:** `DealDisclosureKind(str, Enum)` (`BULK_DEAL`/`BLOCK_DEAL`);
  `MarketDataSqliteStore(db_file_path=~/.nse_algo_trader/market_data.sqlite3)`
  with save/load pairs:
  - `save_price_bars` / `load_price_bars(instrument_token, bar_interval,
    from_timestamp=None, to_timestamp=None)` — PK
    (token, interval, timestamp); INSERT OR REPLACE; inclusive range,
    timestamp-ordered; tz-aware ISO strings round-trip exactly.
  - `save/load_cash_bhavcopy_delivery_rows(trade_date)` — PK
    (date, symbol, series).
  - `save/load_fo_bhavcopy_contract_rows(trade_date, underlying_symbol=None)`
    — PK (date, nse_instrument_id) + index on (underlying, date).
  - `save/load_fo_ban_list_report` — delete+insert per date; a
    never-ingested date loads as None.
  - `save/load_mwpl_position_limit_rows(trade_date)` — PK (date, symbol).
  - `save/load_bulk_or_block_deal_rows(trade_date, deal_kind)` — no natural
    PK, so save replaces the whole (date, kind) slice; re-ingest safe.
  - WAL mode; `close()`.

### `daily_nse_reports_ingestion_job.py`
- `ingest_nse_reports_for_trade_date(trade_date, report_downloader,
  market_data_store) -> dict[report_name, outcome]` — six ingests
  (cash bhavcopy, F&O bhavcopy, MWPL for the given date; ban list +
  bulk + block as current-day files), each failure isolated so one
  missing report never blocks the rest.
- `__main__`: `--trade-date YYYY-MM-DD` (default: today IST).
- **Cron (weekdays)**: 14:30 + 16:30 GMT (20:00/22:00 IST) ->
  `~/.nse_algo_trader/nse_reports_ingestion.log`; idempotent re-runs.

### Live verification (2026-07-23)
Real run for trade date 2026-07-22: cash 3,261 / F&O 38,343 / MWPL 210 /
ban 1 (KAYNES) / bulk 128 / block 0 — all read back correctly (1,587
NIFTY contracts via the underlying filter). 75 live INFY 5-min bars
saved and reloaded **identical** through the store. DB size: ~6.2 MB/day.

## Later-layer ingestion additions queued for this layer
- **Participant-wise derivatives OI** (FII/DII/Pro/Client daily
  positions, NSE report) — required by the §10 Opponent Ledger; add as
  a sixth official-report ingest when Layer 10 reaches that feature.

## Live universe feed (added 2026-07-24) — the open-session data source
New file `kite_live_universe_feed.py` (`KiteLiveUniverseFeed`) is the
live-session data source the market-clock-gated router serves when the
market is open (PLAN §1.4). Two access patterns, sized to Kite limits:
- `latest_price_by_token(instruments) -> dict[token, float]` — batched
  `ltp()` (≤400/call) for the WHOLE universe each scan interval. Cash maps
  to `NSE:<sym>`, options to `NFO:<sym>`; missing quotes are absent (never
  zero-filled).
- `todays_session_bars(instrument, as_of, interval) -> list[PriceBar]` —
  today's candles 09:15→now for one instrument (delegates to
  `KiteHistoricalBarSource`), giving ORB the real opening range. Used to
  seed an instrument, not polled universe-wide.
- `stream_bars()` shim so the router can hold it as `_live_bar_source`;
  the universe loop uses the two methods above at universe granularity.

**Rule-F live verification (2026-07-24, open session):** batched LTP priced
**3,714 instruments (800 cash + 2,915 options) in 0.4s**; INFY today's
5-min bars 09:15→10:50 (20 bars), opening range high=1042.6/low=1023.0.
Router confirmed: LIVE when the feed is attached and the market is open,
REPLAY when no feed — the seamless handoff gate (research/26) now works.
4 unit tests (`test_kite_live_universe_feed.py`).

**Named future consumer (Rule G):** the live universe paper loop (slice 3,
research/38) attaches this as the router's live source and consumes it.
