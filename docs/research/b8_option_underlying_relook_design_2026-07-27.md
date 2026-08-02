# B8 — options get ONE look per process; give them a fair, repeating re-look

**Sourcing note (Rule I / sourcing gate, explicit not silent):** no OSS sourcing pass applies. This is
a scheduling defect in this repo's own scan loop — the correct behaviour is already demonstrated by
the CASH path in the same file family (`check_watched_names_for_live_breakout`, re-checked every
pass). There is no external library for "when should I re-examine my own watchlist". Logged in
`docs/BACKLOG.md`.

## The defect

`option_credit_spread_live_path.py`:

```python
def try_open_option_position_for_underlying(...):
    state.seeded_option_underlyings.add(underlying_symbol)   # :172 — unconditional, BEFORE any gate
    ...
# and in the pass loop:
    if underlying_symbol in state.seeded_option_underlyings:  # :541
        continue                                             # permanent skip, forever
```

`seeded_option_underlyings` is **never cleared anywhere** — the only reset in the codebase
(`live_paper_trading_service.py`, replay path) clears `seeded_cash_tokens` and
`watched_opening_ranges` only. So:

- Each underlying is examined **exactly once per process lifetime**.
- The mark happens at the TOP of the function, before every gate, so an underlying that bailed
  instantly (fewer than 28 bars, STAND_ASIDE regime, no ORB breakout yet) burns its only look.
- At 25 seeds/pass and ~46 s/pass, all 215 underlyings are consumed in ~9 passes ≈ **7 minutes after
  the open** — precisely the window in which no opening-range breakout can exist yet.

The cash path does not have this problem: it caches the opening range and re-checks it against live
LTP **every pass** (`check_watched_names_for_live_breakout`). **The options path has no equivalent.**

Measured consequence today: 0 index-option positions all session; the per-index funnel at 11:00 IST
showed NIFTY/NIFTYNXT50/MIDCPNIFTY in a TRENDING regime with live ORB breakouts present — hours
after their single look had already been spent.

## Two design faults, not one

1. **One-shot instead of repeating.** A market condition that does not exist at 09:20 may exist at
   11:00. Looking once is looking at the wrong time.
2. **Alphabetical ordering is unfair under any repeat scheme.** `sorted(spot_by_underlying)` means
   ADANIENT is always considered before ZYDUSLIFE. With a per-pass budget of 25 out of 215, a naive
   re-look would keep re-examining the A-names and starve the tail — the same starvation shape as B1,
   in a different disguise.

## The change

**A · Replace the permanent skip with a RE-LOOK COOLDOWN.** New state field
`last_option_look_at_by_underlying: dict[str, datetime]`. An underlying is eligible again once
`now - last_look >= OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS` (default **300 s**). Rationale: a full
sweep of 215 underlyings takes ~7 min at 25/pass, so a 5-minute cooldown yields continuous,
non-overlapping re-looking — roughly **10+ looks per underlying across a 6.25-hour session** instead
of 1, each at a different market state.

**B · Order by LEAST-RECENTLY-LOOKED, not alphabetically.** This makes the sweep round-robin: every
underlying is examined once before any is examined twice. Fixes fault 2 and makes Rule-L breadth real
rather than nominal. Ties broken alphabetically for determinism.

**C · Record the look in the PASS LOOP, not inside the entry function.** Exactly the B1 lesson: a
mark buried inside a function that early-returns is a mark that does not happen. Recording it in the
loop means the timestamp is always written, whatever the outcome.

**D · Keep `seeded_option_underlyings`** as "looked at least once today" — it is still the honest
coverage measure and is worth surfacing; it simply stops being the *skip* decision.

**E · Reset both on a new session/day**, alongside the existing cash reset, so a new trading day
starts genuinely fresh rather than relying on cooldown arithmetic across a date boundary.

## Acceptance criteria

1. An underlying examined at T is examined again at T + cooldown (not skipped forever).
2. An underlying examined at T is NOT re-examined before T + cooldown (the rate limit is respected).
3. Selection order is least-recently-looked first; with a budget smaller than the universe, every
   underlying is looked at once before any is looked at twice.
4. An underlying with an OPEN position is never re-seeded (unchanged).
5. The look timestamp is recorded even when the entry function returns False or raises.
6. A new session clears both the look-times and the looked-once set.
7. Rule-F: across a live session, option underlyings are examined repeatedly — the look count rises
   well past 215 — and index options become reachable outside the first 7 minutes.

## Verification plan

- Unit tests over criteria 1-6 with an injected clock (pure scheduling logic, no I/O).
- Rule F: deploy live and confirm the look counter climbs past the 215-underlying universe size, and
  that option entries occur outside the opening window.

## Explicitly NOT in this slice (Rule K)

- **B16** — why INDEX options specifically stay at 0 (BANKNIFTY in the 20-25 ADX dead band,
  positioning veto on longs, high-stakes oversight gate). B8 gives them repeated *chances*; it does
  not change any gate.
- **B9** — stock options still vanish from the ladder outside monthly-expiry week.
- **B3 (option half)** — the min/max capital clamp is still not applied to option lots.
- The 0.34 s/call single-broker fetch ceiling (**B5**) still bounds sweep speed.
