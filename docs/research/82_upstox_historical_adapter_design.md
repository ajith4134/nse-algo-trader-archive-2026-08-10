# Research/82 — Upstox v3 historical adapter (design, task #17)

**Rule D**, from the Upstox sourcing (2026-07-25, docs + `upstox-python-sdk` sdist +
live instrument master). Interchangeable data source (PLAN §8a.12).

## Sourcing facts
- SDK `upstox-python-sdk` (import `upstox_client`), MIT, thin (urllib3/six/…),
  **hermetic construction** (no network until a call fires). `HistoryV3Api.
  get_historical_candle_data(instrument_key, unit, interval, to_date, from_date)`.
- **v3 endpoint** `GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to}/{from}`.
  `unit` = minutes|hours|days|weeks|months; `interval` 1–300 (minutes) — **1-min yes,
  no sub-minute**. Dates `YYYY-MM-DD`. Response positional `[ts,o,h,l,c,v,oi]` — **OI
  present (7th)**. Caps: minutes 1–15 ≤1 month, >15 & hours ≤1 quarter, days ≤1 decade
  (from Jan-2022 minutes / Jan-2000 days). Rate 10/s (non-SEBI-algo).
- **Auth:** OAuth (browser redirect → code → token), token expires ~3:30 AM IST daily,
  **no refresh grant**. BUT a **1-year read-only "Analytics Token"** exists (no
  redirect) — ideal for a data-only pipeline / the Rule-F pass.
- Instrument master (gz JSON at `assets.upstox.com`): **instrument_key** =
  `NSE_EQ|<ISIN>` (cash), `NSE_FO|<token>` (F&O; strike/expiry separate fields),
  `NSE_INDEX|Nifty 50` — segment-aware keying.

## The build
`market_data/upstox_historical_bar_source.py`: `UpstoxHistoricalBarSource(
history_client, upstox_instrument_key_resolver)` on the seam — injected client (never
imports upstox_client); `BarInterval → (unit, interval)` (SECOND_1 raises);
per-interval day-window chunking + dedupe; OI parsed (7th field); response tolerant of
dict OR the SDK's `response.data.candles` object. `instrument_key` via injected
resolver (default raises — needs the master).

## Verification
- **Hermetic (Rule J):** injected fake v3 client (dict + SDK-object shapes) — call
  shape, unit/interval map, chunk+dedupe, OI parse, SECOND_1 + missing-resolver
  errors. 5 tests.
- **Rule F — OPEN BLOCKER:** needs an Upstox token. Easiest = generate the 1-year
  **Analytics Token** (no daily redirect) from the dev dashboard. Then real pull + assert.

## Backlog (Rule K)
Upstox instrument-key resolver (ISIN for NSE_EQ, token for NSE_FO, from the master);
prefer the Analytics token for the data pipeline (headless, 1-year).
