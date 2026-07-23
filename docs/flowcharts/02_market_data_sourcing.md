# 02 — Market Data (Layer 2): Broker-Neutral Sourcing + NSE Official Reports

**Status:** first feature-set built and tested (broker-neutral data model,
swappable source protocols, Kite adapters, all five NSE official-report
ingests). Awaiting user verification sign-off. Remaining Layer 2 work
listed at the bottom.

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
