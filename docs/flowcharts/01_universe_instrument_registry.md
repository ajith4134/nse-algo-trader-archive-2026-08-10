# 01 — Universe & Instrument Registry

**Status:** built, tested, awaiting user verification before Layer 2 starts.

## What this layer does
Takes a raw Kite Connect instrument-master dump (one dict per tradable
symbol) and turns it into a clean, typed catalogue of exactly the phase-1
universe: NSE cash equities, NSE index options, and NSE stock options.
Everything else (futures, currency, commodities, other exchanges) is
recognized and dropped, not silently mishandled.

## Whole-pipeline data flow so far

```
                         ┌──────────────────────────────┐
                         │  Kite Connect instrument dump │
                         │  (list[dict], one row per     │
                         │   tradable symbol, from       │
                         │   kite.instruments())         │
                         └───────────────┬───────────────┘
                                         │
                                         ▼
                  kite_instrument_master_loader.py
                  ┌──────────────────────────────────────┐
                  │ classify_kite_instrument_row(row)     │
                  │   -> Instrument | None                │
                  │                                        │
                  │ build_phase1_instrument_universe(rows) │
                  │   -> list[Instrument]                  │
                  └───────────────┬────────────────────────┘
                                  │  uses
                                  ▼
        nse_index_options_reference.py
        NSE_INDEX_OPTION_UNDERLYING_SYMBOLS  (5 fixed symbols)
        -> used only to decide INDEX_OPTION vs STOCK_OPTION
                                  │
                                  ▼
                    instrument_types.py
                    Instrument (frozen dataclass)
                    ExchangeSegment / InstrumentKind / OptionRight (enums)
                                  │
                                  ▼
                   list[Instrument]  <-- exported to whatever
                                        Layer 2 (Market Data) is built next
                                        (nothing consumes this yet)
```

Nothing downstream exists yet — this is the first layer. Layer 2 (Market
Data) will be the first consumer of `list[Instrument]`.

## Files belonging to this layer

```
src/nse_algo_trader/universe_registry/
├── __init__.py                      # re-exports the public API listed below
├── instrument_types.py              # data model
├── nse_index_options_reference.py   # fixed NSE index-underlying symbol list
└── kite_instrument_master_loader.py # raw dump -> list[Instrument]

tests/test_universe_registry/
├── __init__.py
├── test_instrument_types.py
└── test_kite_instrument_master_loader.py

tests/fixtures/
├── __init__.py
└── sample_kite_instrument_rows.py   # fake Kite dump rows used only in tests
```

## Every function/class, its imports, and what it exports

### `instrument_types.py`
- **Imports:** `dataclasses.dataclass`, `datetime.date`, `enum.Enum` (stdlib only).
- **Exports:**
  - `ExchangeSegment(str, Enum)` — `NSE_CASH`, `NSE_FO`.
  - `InstrumentKind(str, Enum)` — `CASH_EQUITY`, `INDEX_OPTION`, `STOCK_OPTION`.
  - `OptionRight(str, Enum)` — `CALL` (`"CE"`), `PUT` (`"PE"`).
  - `Instrument` — frozen dataclass. Fields: `instrument_token: int`,
    `trading_symbol: str`, `exchange_segment: ExchangeSegment`,
    `kind: InstrumentKind`, `lot_size: int`, `tick_size: float`,
    `underlying_symbol: str | None`, `strike_price: float | None`,
    `option_right: OptionRight | None`, `expiry_date: date | None`.
    `__post_init__` raises `ValueError` if `kind` is an option kind but any
    of the four option-only fields is `None`.

### `nse_index_options_reference.py`
- **Imports:** none (pure data).
- **Exports:**
  - `NSE_INDEX_OPTION_UNDERLYING_SYMBOLS: tuple[str, ...]` — `("NIFTY",
    "NIFTYNXT50", "FINNIFTY", "MIDCPNIFTY", "BANKNIFTY")`.
  - `BSE_INDEX_OPTION_UNDERLYING_SYMBOLS_DEFERRED: tuple[str, ...]` —
    `("SENSEX", "BANKEX")` — documented as out of scope, not used by any
    function yet.

### `kite_instrument_master_loader.py`
- **Imports:** `datetime.datetime` (stdlib); `ExchangeSegment`, `Instrument`,
  `InstrumentKind`, `OptionRight` from `instrument_types`;
  `NSE_INDEX_OPTION_UNDERLYING_SYMBOLS` from `nse_index_options_reference`.
- **Exports:**
  - `classify_kite_instrument_row(row: dict) -> Instrument | None` — one raw
    dump row in, one `Instrument` out, or `None` if out of phase-1 scope.
  - `build_phase1_instrument_universe(raw_kite_instrument_rows: list[dict]) -> list[Instrument]`
    — runs `classify_kite_instrument_row` over the whole dump and keeps
    only the non-`None` results.

### `universe_registry/__init__.py`
- Re-exports everything above as the package's public surface, so callers
  do `from nse_algo_trader.universe_registry import Instrument, ...` instead
  of reaching into the submodules directly.

## How it was verified
`pytest` — 8 tests, all passing, covering: cash-equity construction without
option fields, option construction rejected when option fields are missing,
option construction accepted when complete, full-universe filtering (5
fixture rows in -> 3 out, futures and MCX dropped), index-option vs
stock-option classification by underlying symbol name.

## Known limitations / explicitly deferred
- No live network call to Kite yet — `build_phase1_instrument_universe`
  takes rows you already have (from `kite.instruments()`); wiring up the
  authenticated Kite client call itself belongs in the Broker Integration
  layer (Layer 6), not here.
- No liquidity filtering of the cash universe (e.g. down to Nifty 500) —
  that needs turnover/volume data, which doesn't exist until Layer 2
  (Market Data) is built. Deliberately not stubbed out with fake logic.
- Stock-option list membership (~185-208 names) is derived live from
  whatever the dump contains — not hardcoded, since NSE reviews this list
  quarterly/semi-annually and a hardcoded list would silently go stale.
