# B1 — unstick the cash scanner: always advance, and scan only intraday-tradable equities

**Sourcing note (Rule I / sourcing gate, explicit not silent):** no OSS sourcing pass applies. The
authoritative classification of which NSE scrips are intraday-tradable is the exchange's own bhavcopy
`series` column, which this repo **already ingests daily** into `cash_bhavcopy_delivery` (9,767 rows,
`daily_nse_reports_ingestion_job`). Sourcing an external instrument-master library would be strictly
worse than the exchange's own data already on disk. Logged in `docs/BACKLOG.md`.

## The defect (two independent bugs, both required for the fix)

### 1 · The scan pointer can never advance past a bar-less instrument

`live_universe_paper_loop.py:1127-1144`:

```python
for instrument in cash_universe:
    if newly_seeded >= max_new_cash_seeds_per_pass: break     # 30/pass
    if instrument.instrument_token in state.seeded_cash_tokens: continue
    recent_bars = live_universe_feed.recent_intraday_bars(...)  # paced 0.34 s/call
    newly_seeded += 1
    if not recent_bars:
        continue            # <-- token NEVER marked seeded
    opened = _seed_cash_instrument_from_orb(...)   # seeded_cash_tokens.add() is at :932, INSIDE here
```

`seeded_cash_tokens.add()` is the first statement of `_seed_cash_instrument_from_orb` — reached only
when bars came back. **A bar-less instrument is therefore never marked, so the next pass retries the
same one, forever.** Measured live: `seeded_count` frozen at **231 / 9,292** for an entire session
while the loop ran every ~15 s. ~10 s of every pass was spent re-fetching the same dead scrips.

This is a robustness bug independent of *which* universe is scanned: any instrument that returns no
bars re-deadlocks the scanner.

### 2 · The scanned universe is ~75% debt paper, not equities

The live service scans `universe.cash_equity_instruments` raw (9,292). Kite's instrument dump marks
NSE-listed **bonds/NCDs as `instrument_type == "EQ"`**, so they are classified as cash equity
(`kite_instrument_master_loader.py:48`). The only existing filter,
`is_mainboard_cash_trading_symbol`, strips just `-SM`/`-ST` (SME) and therefore returns all 9,292.
From index ~215 onward the list is `0ABCL31-N0`, `1003IIFL29-NC`, … — probed live, these return
**0 bars**.

## Ground truth: the exchange's own series classification

From the stored bhavcopy for 2026-07-24 (`cash_bhavcopy_delivery.series`):

| series | count | meaning | intraday-tradable? |
|---|---|---|---|
| **EQ** | **2,389** | rolling settlement, normal market | **YES** |
| BE | 300 | **trade-for-trade** — compulsory delivery | **NO** |
| SM | 292 | SME platform | NO |
| ST | 143 | SME trade-for-trade | NO |
| GS | 45 | government securities | NO |
| GB | 44 | government bonds | NO |
| BZ | 26 | surveillance / restricted | NO |
| IV, RR, E1, SZ, MF | 20 | misc (institutional, rights, MF) | NO |

**`EQ` is the intraday universe — 2,389 names.** Excluding `BE`/`BZ` is a *correctness* requirement,
not an optimisation: trade-for-trade scrips settle on compulsory delivery with no intraday netting, so
an intraday-only bot that opens a BE position cannot square it off before close — it would violate the
project's single hardest non-negotiable ("every position auto-squares-off before close").

## The change

**A · New module `universe_registry/intraday_tradable_cash_universe.py`** — the one place this policy
lives:
- `INTRADAY_TRADABLE_NSE_SERIES = frozenset({"EQ"})` with the exclusion rationale documented per series.
- `select_intraday_tradable_cash_equities(instruments, series_by_symbol)` — pure, testable, no I/O.
- Returns a result object carrying the kept instruments **and the excluded count by series**, so the
  filtering is visible on the dashboard rather than a silent 9,292 → 2,389 drop (Rule O.3).
- **Unknown-symbol policy:** a symbol absent from the bhavcopy is EXCLUDED, and counted separately.
  Absence means the exchange did not report it trading on the last session — the safe reading for an
  intraday bot. Counted so a stale/partial bhavcopy is visible instead of silently shrinking the
  universe.

**B · Wire it in** at `live_paper_trading_service.py:554` where `_cash_universe` is built, using the
already-present `latest_cash_bhavcopy_trade_date()` + `load_cash_bhavcopy_delivery_rows()`.
**Fallback:** if no bhavcopy is stored, keep the unfiltered universe (the deadlock fix below makes
that safe) and record an explicit blocker — never silently scan bonds, never silently scan nothing.

**C · Deadlock fix** in `live_universe_paper_loop.py`: mark the token as attempted in the scan loop
itself, immediately after the fetch, so the pointer always advances whatever the fetch returned. Add
a counter for attempted-but-bar-less so the condition is visible instead of invisible.

## Acceptance criteria

1. A bar-less instrument is marked attempted and is **not** retried on the next pass.
2. `seeded_count` climbs past 231 across a live session (it was frozen all of 2026-07-27).
3. The scanned universe is the ~2,389 `EQ` names; `BE`/`BZ`/`SM`/`ST`/`GS`/`GB` are excluded.
4. Exclusions are **counted and surfaced by series**, not silent.
5. No bhavcopy stored → unfiltered universe + a logged blocker; the scanner still advances (never
   deadlocks) because of criterion 1.
6. Tighten-only on scope: the filter can only ever REMOVE instruments, never invent one.
7. Rule-F: on the live server, `seeded_count` rises and new cash names open positions.

## Verification plan

- Unit tests over criteria 1, 3, 4, 5, 6 using the REAL series codes above (not invented ones).
- Rule F: deploy to the live open market and watch `seeded_count` climb past 231 and cash open
  positions appear in names outside the original 231.

## Explicitly NOT in this slice (Rule K)

- **B8** (options seeded once per process, no retry) — separate slice, next.
- Liquidity/turnover ranking of the 2,389 already exists (`_liquidity_ranked_cash_universe`) and is
  untouched here.
- The 0.34 s/call single-broker fetch ceiling (**B5**, multi-broker fleet not wired) still caps how
  fast 2,389 names can be swept — this slice removes the deadlock and the wasted 75%, it does not
  raise the fetch rate.
