# 167 — L0 bitemporal truth: availability-time on the bar store (structural look-ahead prevention)

**Date:** 2026-08-03 · **Redesign layer:** L0 (build order #3) · **Skill:** building-engine-grade-features
**North-star (redesign §3 L0):** *"One point-in-time data path shared by backtest + live … bitemporal
(event/ingestion/availability time), snapshot-on-ingest, frozen tradable-universe per date. Kills
look-ahead leakage structurally."*

## 1. Read-first — what exists
- **Point-in-time UNIVERSE:** `paper_trading/point_in_time_universe_resolver.py` + `corporate_action_adjustment.py`
  already resolve the tradable universe as-of a date (§53 slice 2 🟢). REUSE — not rebuilt here.
- **Bar store:** `market_data/market_data_sqlite_store.py::price_bars` is EVENT-TIME ONLY —
  `(instrument_token, bar_interval, bar_timestamp, ohlcv, oi)`. `grep` confirms `bitemporal/availability/
  ingestion_time/point_in_time/look_ahead = 0`. **This is the L0 gap.**

## 2. The defect
A backtest/replay reads `load_price_bars(token, interval, from, to)` with NO notion of when a bar became
KNOWABLE. A bar timestamped 09:15 (a 5-min bar) only closes — and is only actionable — at 09:20, yet the
store lets a replay at 09:15 read it. Worse, a bar ingested late (a gap-fill written after the fact) is
indistinguishable from one available in real time. Both are silent look-ahead — the single most common way
a backtest lies. L2's holdout + L1's effective-dated costs are point-in-time; the bar store must be too, or
the whole point-in-time chain has a hole.

## 3. The fix — a second temporal axis: availability_time
- Add `availability_time TEXT` to `price_bars`. For a completed bar, availability = its CLOSE time =
  `bar_timestamp + interval_duration` (a 5-min 09:15 bar is available 09:20). This is the honest earliest
  moment the bot could have acted on it.
- **Write:** `save_price_bars` records `availability_time` per bar (default = close time; a live feed may
  pass a later real receipt time, never earlier).
- **Read:** `load_price_bars(..., as_of: datetime | None = None)` adds `AND availability_time <= as_of` —
  so a replay at clock T sees ONLY bars that had already closed by T. `as_of=None` preserves current
  behaviour (live path, which is already real-time).
- **Migration (existing DBs):** on init, if the column is absent, `ALTER TABLE ADD COLUMN` +
  backfill every existing row's availability_time = `bar_timestamp + interval_duration` (computed in
  Python per interval; idempotent — only NULLs). No data loss; the store self-upgrades on next open.

## 4. Wiring (Rule G — no orphan)
`paper_trading/historical_bar_replay_source.py` (the replay bar source) passes `as_of = replay_clock` so
the replay engine is structurally look-ahead-free. Live/feature-plane reads keep `as_of=None`
(they are already real-time). Other `load_price_bars` callers unchanged (default preserves behaviour).

## 5. Depth justification
Not a scalar: a genuine second temporal axis on the persistent store + a migration that self-upgrades real
data + an as-of query that changes what a backtest can SEE (removes look-ahead trades). SOTA analog: a
bitemporal time-series store (event time + knowledge/availability time) — the arctic/kdb+ pattern, and
López de Prado's "point-in-time" data mandate. Output changes real backtest decisions (a bar not yet
available is not tradable).

## 6. Sourcing (Rule O.1) — candidates evaluated on mechanical facts
- **man-group/ArcticDB** (bitemporal time-series store) — REJECT tier-1 (wrong deployment shape): a
  separate storage engine (LMDB/S3/Mongo-backed), not a column on the repo's single embedded SQLite file;
  adopting it means replacing the whole `market_data_sqlite_store`, out of scope for a look-ahead fix.
- **SQL `temporal_tables` / system-versioned tables** — REJECT tier-1 (wrong engine): a Postgres/MariaDB
  extension; SQLite has no system-versioning, so it cannot apply here.
- **sqlite-utils / plain `ALTER TABLE ADD COLUMN`** — the mechanism actually used (stdlib `sqlite3`); no
  dependency needed — the "part" is a schema predicate, not a library.
- **pandas `asof`/`merge_asof`** — REJECT tier-1 (wrong layer): an in-memory join helper, not a persistent
  availability-time axis on the store; would not prevent a look-ahead READ at the source.
Conclusion: bespoke `availability_time` column + as-of predicate on the existing SQLite store is the correct,
minimal fit. No vendor.

## 7. Verification
Unit + property (as_of before a bar's close excludes it; at/after includes it; write records close time;
migration backfills only NULLs, idempotent) + adversarial (mixed intervals, 1s vs 1d, tz-aware timestamps)
+ Rule-F on the REAL store DB (open it → migration adds+backfills the column → an as_of query on a real
token excludes future bars).
