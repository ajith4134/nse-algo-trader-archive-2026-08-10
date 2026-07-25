# Research/79 — Delisted-securities master (BSE) design (task #13)

**Rule D design doc.** Adds a free delisted-securities master to help the §53
survivorship-free universe work distinguish **delisted (permanently gone)** from
**suspended / merely-untraded** names — the open §53 blocker G2/G3 (research/58/59).

## Source (verified live 2026-07-25)
NSE's own delisted list is bot-blocked (research/75). **BSE's is free + open:**
`https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?segment=Equity&status=Delisted`
returns a JSON list — **4,612 delisted rows**, each with `SCRIP_CD`, `Scrip_Name`,
`ISIN_NUMBER`, `scrip_id`, `Status`, `GROUP`, `FACE_VALUE`. **ISIN is present** — so
it keys to our ISIN-keyed reference data. Needs a browser User-Agent + BSE Referer
(anti-bot), 404/empty tolerated. BSE ≠ NSE, so it is a **corroborating cross-source**
for delisting, not an NSE authority — combined with the bhavcopy-presence-gap signal.

## The build
1. `market_data/delisted_securities_source.py`: `DelistedSecurity(scrip_code, name,
   isin, scrip_id, source)` · `DelistedSecuritiesSource` protocol
   (`fetch_delisted_securities() -> list[DelistedSecurity]`) · `BseDelistedSecuritiesSource`
   (real adapter — browser UA, parse; network at call, not import → hermetic).
2. `MarketDataSqliteStore`: `delisted_securities` table + `save_delisted_securities`
   / `load_delisted_securities` (keyed by source+isin/scrip_code).
3. `market_data/delisted_securities_ingestion_job.py`: a CLI entry point (cron-able,
   like `daily_nse_reports_ingestion_job`) that fetches BSE + stores — the Rule-G
   wiring (runnable entry point).
4. `DelistedSecuritiesMaster` (from the store): `is_delisted_isin(isin)` /
   `is_delisted_symbol(name/scrip_id)` lookup for consumers.

## Wiring (Rule G) & consumer
The ingestion job is the runnable entry point (Rule G (a)). Named consumer of the
master lookup: the §53 **suspension-vs-delisting bhavcopy test (G3)** and the
point-in-time universe cross-check (a bhavcopy gap + a delisted-master hit =
confirmed delisted; gap without a hit = possibly suspended) — the survivorship
correctness use, tracked as the next step (Rule K: master built + stored + queryable
now; the resolver-side consumption is the named next slice).

## Verification
- **Hermetic (Rule J):** `BseDelistedSecuritiesSource` parses a real-shaped BSE JSON
  sample → typed records; store round-trip; master lookup by ISIN/symbol.
- **Real data (Rule F):** env-gated live fetch of the BSE API asserts >1000 delisted
  rows with ISINs, stored + reloaded, a known delisted ISIN found. (Env-gated so the
  suite stays offline.)

## Backlog (Rule K)
- 🔵 Kaggle CC-BY-4.0 survivorship-free delisted set as a 2nd cross-source (needs a
  Kaggle API token — deferred).
- 🔴 Resolver-side consumption: suspension-vs-delisting test (G3) + universe-gap
  classification using the master.
