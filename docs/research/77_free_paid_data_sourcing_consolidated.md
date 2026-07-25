# Research/77 — "Can we get the paid data for free?" — CONSOLIDATED (2026-07-25)

**Deep-research protocol, 5 parallel legitimacy-filtered sweeps** (record-forward /
free-tier / academic / open-data only — no credential sharing, paywall bypass,
ToS-violating scraping, or piracy). Per-dataset detail:
- `research/71` — historical tick / trade-by-trade
- `research/72` — L2/L3 order-book depth
- `research/73` — broker-API intraday history limits · `research/74` — deep-intraday ceiling
- `research/75` — corporate actions / ISIN-merger / delisted master
- `research/76` — point-in-time index membership / survivorship-free universe

## Bottom line
For the **microstructure tier (tick + L2/L3 depth), there is genuinely no free
route for an individual** — confirmed across independent passes (no free NSE tick;
NSE *does sell* order-level data ₹1.1L–12.5L/yr; no vendor sells historical depth
retail). **"Record forward + eventually license NSE" stands** — which is exactly
what the project already built (Breeze 1s + the P4b depth recorder). For the
**reference/bar tiers (deep intraday bars, corporate actions, delisted master,
survivorship-free universe), free stacking gets us most of the way** — and it
surfaced one genuinely new, actionable win: **Fyers' free History API** (deeper +
free vs Breeze's 3y).

## The map (ranked free ceiling per dataset)
| # | Dataset | Free ceiling | Best free route | Honest verdict |
|---|---|---|---|---|
| 1 | Tick / trade-by-trade | none (historical) | record your own broker websocket forward | **pay NSE or record-forward** (r/71) |
| 2 | L2/L3 order-book depth | none (historical) | record forward (Kite 5-lvl … Dhan 20/200-lvl) | **record-forward only** — P4b does this (r/72) |
| 3 | Deep intraday 1m/1s bars | ~3–4 yrs stitched | **Fyers History API** (cash+F&O+OI, since Jul-2017, FREE) + Breeze 1s (~3y) + HuggingFace 2022+ cash 1-min seed | free-stackable; **Kite no longer free (₹500/mo since May-2025)** (r/73,74) |
| 4a | Corporate actions | deep, free | NSE/BSE corp-action APIs via `nselib`/`bse` (already used) | **free** (r/75) |
| 4b | ISIN→ISIN merger lineage | weak | `symbolchange.csv` (no ISIN col) + manual joins | **unresolved free gap** (r/75) |
| 4c | Delisted-securities master | good (BSE) | **BSE delisted PDF + `ListofScripData` JSON** (`status=delisted`); Kaggle CC-BY-4.0 survivorship-free set (1,209 names) | free cross-checkable; NSE list bot-blocked (r/75) |
| 5 | Point-in-time universe / index membership | reconstructable | **bhavcopy reconstruction** (already built: `point_in_time_universe_resolver`); Wikipedia + `IndexInclExcl.xls` cross-checks | free via reconstruction (r/76) |

## Actionable wins (new, worth building — Rule I)
1. **Fyers History API adapter** (biggest win): free, cash **+ F&O + OI**, ~9 years
   (since Jul-2017) — deeper than Breeze's ~3y and free. Add a `FyersHistoricalBarSource`
   behind the existing `HistoricalBarSource` seam (same pattern as Breeze). → task.
2. **HuggingFace `xxparthparekhxx/indian-stock-market-minute-data`** (MIT, 2022+
   cash 1-min, 2,500+ symbols): a fast bulk SEED to backfill the store. Provenance
   undisclosed → verify before trusting. → task.
3. **Delisted master:** wire BSE `ListofScripData` (`status=delisted`, via `bse`
   lib) + the Kaggle survivorship-free set as the delisted cross-source — helps the
   open "delisted master" blocker. → task.

## Confidence & caveats
- **Solid (triangulated, primary-read):** no free tick/depth for individuals; Fyers
  free History API with OI; bhavcopy reconstruction is the survivorship-free route;
  Kite historical is paid (₹500/mo) and 1-min-capped.
- **Probable / single-sourced:** Breeze 1s "10-year" claim (docs say ~3y — conflict,
  tracked); HuggingFace dataset provenance undisclosed; niftyhistory.in unverified.
- **Confirmed-absent (not just unfound):** free consolidated F&O-eligibility-by-date;
  free ISIN-to-ISIN merger lineage; any free Kaggle/GitHub/HuggingFace/WRDS/LOBSTER
  Indian tick or depth (two exhaustive passes).

## What this did NOT change
This CONFIRMS the existing plan (`research/54`) rather than overturning it — the
microstructure ceiling is real. Net-new is the Fyers free-history channel and the
BSE/Kaggle delisted cross-sources. Open verification items are tracked in BACKLOG.
