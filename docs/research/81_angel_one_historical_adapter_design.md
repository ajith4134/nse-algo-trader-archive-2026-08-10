# Research/81 — Angel One SmartAPI historical adapter (design, task #18)

**Rule D**, from the Angel SmartAPI sourcing (2026-07-25, docs + `smartapi-python`
source + live OpenAPIScripMaster). Interchangeable data source (PLAN §8a.12).

## Sourcing facts
- SDK `smartapi-python` (import `from SmartApi import SmartConnect`), **light deps**
  (requests/six/python-dateutil), **hermetic construction** (no network at `__init__`).
  No LICENSE file (all-rights-reserved; fine for personal use, Rule E).
- **Auth needs client code + PIN + TOTP** — `generateSession(clientCode, pin, totp)`.
  api_key + TOTP secret ALONE are **not sufficient**. Session resets at midnight.
- **`getCandleData({exchange, symboltoken, interval, fromdate, todate})`** →
  `{"status":true,"data":[[ts,o,h,l,c,v], …]}` — **6 fields, NO historical OI**.
  Intervals `ONE_MINUTE…ONE_DAY` (no sub-minute). `fromdate/todate` = `yyyy-MM-dd HH:mm`.
  Per-call caps: 1m ≤30d, 3m ≤60d, 5/10m ≤100d, 15/30m ≤200d, 1h ≤400d, 1d ≤2000d.
  Rate 3/s. Depth floor per symbol not documented (empirical).
- Instruments via `OpenAPIScripMaster.json` (token/symbol/name/expiry/strike/
  instrumenttype/exch_seg); Angel addresses by numeric **symboltoken** (≠ our Kite token).

## The build
`market_data/angel_one_historical_bar_source.py`: `AngelOneHistoricalBarSource(
smartapi_client, angel_symbol_token_resolver)` on the `HistoricalBarSource` seam —
injected client (never imports SmartApi); interval map (SECOND_1 raises); per-interval
day-window chunking + dedupe; exchange NSE/NFO by kind; `open_interest=None`
(historical has none). `symboltoken` via an injected resolver (default raises — needs
the scrip master).

## Verification
- **Hermetic (Rule J):** injected fake SmartConnect (`getCandleData` → real-shaped
  data) — call shape, interval map, chunk+dedupe, parse, SECOND_1 + missing-resolver
  errors. 5 tests.
- **Rule F — OPEN BLOCKER:** needs client code + PIN (+ TOTP from the stored secret);
  user has only api_key + TOTP secret. Then `getCandleData` real pull + assert.

## Backlog (Rule K)
Angel symboltoken resolver (from OpenAPIScripMaster); session builder
(generateSession via pyotp) once client code + PIN are supplied; historical-OI is
unavailable from Angel (use another source for OI).
