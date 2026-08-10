# Runtime state snapshot — 2026-08-10

Contents of `/home/opc/.nse_algo_trader/` on the VPS at reset time. This directory lived
**outside every git repository** — until this commit it had no backup of any kind.

Captured with SQLite's online backup API (`Connection.backup()`) while the dashboard service
was still writing, so every `.sqlite3` here is a transactionally consistent snapshot rather
than a torn file copy. `-wal` / `-shm` sidecars were deliberately not copied; they are folded
into the snapshots.

## Layout

- `databases/` — consistent SQLite snapshots. See `RUNTIME_STATE_MANIFEST.json` for per-table
  row counts recorded at capture time.
- `state/` — JSON state, logs, and the `win_probability_model.joblib` model artifact.
- `RUNTIME_STATE_MANIFEST.json` — kind, byte size, and table row counts for every file.

## Highlights

| File | What it holds |
|---|---|
| `experience_memory.sqlite3` | **3,481 closed trades** — realized P&L, exit cause, predicted vs actual outcome, Brier contribution, MFE/MAE, fees |
| `autopoiesis_homeostat.sqlite3` | 69,620 component telemetry samples + 21,204 lifetime events |
| `news.sqlite3` | 8,548 news items, 397 level records |
| `arm_selection_posterior.sqlite3` | 126 posterior cells, 921 pending-trade arms |
| `debate_risk_observations.sqlite3` | 906 risk-debate observations |
| `strategy_trial_registry.sqlite3` | 20 strategy trials |
| `strategy_family_promotion.sqlite3` | 6 family promotions |

## Not in this directory

**Market data** — `market_data.sqlite3` is 327 MB (659,990 price bars, 1,436,568 F&O
bhavcopy contracts, cash delivery, MWPL limits, bulk/block deals, ATM IV). It exceeds
GitHub's 100 MB per-file limit and this host has no `git-lfs`, so it is attached to the
repository's **release** as a compressed asset instead. See the release page.

**Secrets** — `.env`, `kite_access_token.json`, `breeze_session_token.json` and
`dashboard_access_token.txt` are deliberately **excluded** from this repository. Broker API
keys and the TOTP seed do not belong in remote storage, private or otherwise. They remain on
the server only, at `/home/opc/RESET_KEEP/secrets/` (mode 600). If the server is lost, those
credentials must be reissued from the Zerodha console rather than restored from here.
