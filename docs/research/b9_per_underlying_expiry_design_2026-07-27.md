# B9 — expiry must be chosen PER UNDERLYING, not once globally

**Sourcing note (Rule I, explicit):** no OSS pass applies — this is a one-line-class logic error in
this repo's own ladder assembly. The *facts* it depends on (which indices still have weeklies, and
when that changed) came from the B18 research pass already recorded in
`b18_index_options_ensemble_research_2026-07-27.md`; no library knows NSE's expiry calendar for us.

## The defect

`universe_registry/live_tradable_universe.py`:

```python
expiry_date = nearest_expiry_date(all_options)   # ONE global min across EVERY option
...
for option in option_instruments:
    if option.expiry_date != expiry_date:
        continue                                  # everything on another expiry is DROPPED
```

## Why this silently deletes most of the tradable universe

Per SEBI's Oct-2024 framework (one weekly-expiry index per exchange) and NSE's Sept-2025 rollout:

| underlying | expiry cadence |
|---|---|
| **NIFTY** | **weekly + monthly** — the only NSE index with weeklies |
| BANKNIFTY · FINNIFTY · MIDCPNIFTY · NIFTYNXT50 | monthly only (weeklies ended 2024-11-20) |
| ~210 stock options | monthly only |

So the global minimum is a **NIFTY weekly** in roughly three weeks out of every four. In those weeks
the filter drops **all ~210 stock-option underlyings AND the other four indices** — the ladder
collapses to NIFTY alone.

**Why it looked fine today:** 2026-07-28 is the monthly expiry (last Tuesday of July), so this week
every underlying's nearest expiry *coincides* with the global minimum and the bug is invisible. That
is exactly what made it survive: it is correct one week in four. It also explains the observed
"only 6 stock-option trades ever" — those trades could only ever happen during monthly-expiry week.

This is a **Rule-L violation** (the full universe must be covered, not a sample) and, per the B18
research, a **prerequisite** for the index-options ensemble: an engine cannot select among five
indices when four of them vanish from its universe most of the month.

## The change

- New `nearest_expiry_date_by_underlying(option_instruments) -> dict[str, date]` — the soonest
  expiry **for each underlying independently**.
- `select_near_expiry_option_ladder` takes that mapping instead of a single date, so NIFTY can ladder
  its weekly while every other underlying ladders its own monthly, in the same pass.
- `nearest_expiry_date()` is KEPT (it is still the honest answer to "what is the soonest expiry
  anywhere", used for display) but is no longer the filter.
- `TradableUniverse.near_expiry_date` keeps its meaning for display; the ladder no longer depends
  on it.

## Acceptance criteria

1. Given NIFTY with a weekly expiry earlier than everything else, the ladder still contains the
   other four indices and the stock options — each on **its own** nearest expiry.
2. Each underlying appears on exactly ONE expiry (its own nearest) — never mixed across expiries,
   which would silently compare different contracts.
3. An underlying with no spot price is still skipped (unchanged).
4. Strike-ladder behaviour around ATM is unchanged.
5. In monthly-expiry week (all expiries coincide) the output is identical to the old behaviour — the
   fix is a strict superset, never a regression.
6. Rule-F: on the live chain the ladder covers all five indices plus stock options, and the number of
   distinct expiries in the ladder is ≥ 1 (and > 1 outside monthly week).

## Verification plan

- Unit tests for 1-5 using the REAL cadence shape (NIFTY weekly + others monthly).
- Rule F today: the live ladder still assembles and covers all 215 underlyings.
- **Open blocker (Rule K):** today is monthly-expiry week, so the live market CANNOT distinguish
  fixed from broken. The decisive real-data check is the first NON-monthly week — the ladder must
  still contain ~215 underlyings across multiple expiries rather than collapsing to NIFTY. Logged.
