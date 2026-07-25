# research/84 — Multi-broker historical-source failover & aggregation (task #20)

**Date:** 2026-07-25
**Status:** DESIGN (slice 1 = FAILOVER, built this turn; slice 2 = gap-fill
aggregation, queued).
**PLAN ref:** §8a.12 (data sourcing is multi-broker; Layer-2 sources are swappable).

## Problem
We now have six `HistoricalBarSource` adapters on one seam
(`broker_data_source_protocols.HistoricalBarSource`): Kite, Breeze (1-second),
Fyers, Upstox, Angel One, Groww. Individually each is a single point of failure —
a broker can be rate-limited, mid-outage, missing a symbol in its master, or (Groww
today) un-entitled. The replay/fidelity path (`build_replay_bars_by_token_from_source`,
`HighFidelityReplayConfig.bar_source`) consumes exactly ONE source. We want a single
resilient source that transparently draws from several, so no one broker's failure
blocks a replay.

## Why this is buildable + REAL-DATA verifiable now
Two adapters (Upstox, Angel One) have completed Rule-F real-data passes this session,
returning bit-for-bit cross-consistent OHLC for the same instrument. So failover can
be verified on REAL data (not just hermetic): point the aggregator at
[broken-source, Angel] and confirm it serves real Angel bars; point it at
[Upstox, Angel] and confirm the primary (Upstox) serves. This satisfies Rule F for
the failover behavior itself.

## Design — `MultiBrokerHistoricalBarSource` (implements `HistoricalBarSource`)
Because it implements the same protocol, it plugs into every existing consumer with
zero changes (Rule G — the wire-in point already exists).

### Slice 1 — FAILOVER (this turn)
- Ctor takes an **ordered** `list[NamedHistoricalBarSource]` (name + source). Order =
  priority; the composition root decides it (e.g. Fyers deep-history → Upstox → Angel
  → Breeze → Kite). Ordering is where Rule L / user preference is applied — this class
  does not hard-code any broker.
- `fetch_historical_bars(instrument, interval, from, to)`:
  1. Try each source in order.
  2. A source that **raises** (broker outage, rate-limit, or its resolver `KeyError`
     because the symbol isn't in that broker's master) → recorded as `error`, failover
     to next. *(Resolver-KeyError-as-failover is a feature: a name absent from Angel's
     master but present in Upstox's is served by whichever has it.)*
  3. A source that returns **empty** → recorded as `empty`, failover to next (an empty
     from the primary must not mask data a secondary has).
  4. First source returning **non-empty** bars → return them (recorded `served`).
  5. All sources exhausted → return `[]` (consistent with the builder's "omit the
     instrument" contract — never a hard crash).
- **Observability (keeps it wired into decisions, not silent):** an optional
  `on_source_attempt: Callable[[SourceAttempt], None]` fires once per attempt with
  `(source_name, instrument_symbol, outcome, bar_count, error_repr)`. Lets the service
  log which broker actually served each instrument and which failed/why.

### Slice 2 — GAP-FILL AGGREGATION (QUEUED, next slice)
Instead of first-non-empty-wins, take the primary's bars and **fill missing
timestamps** in the window from lower-priority sources (each bar stays wholly from one
feed, so it is internally consistent; only adjacent bars may differ slightly between
feeds — acceptable for replay coverage). Needs its own real-data pass (e.g. a session
where one broker has a mid-day gap the other covers) → deferred to keep this slice
clean (Rule A). Tracked in BACKLOG.

## Files
- `src/nse_algo_trader/market_data/multi_broker_historical_bar_source.py` — the class +
  `NamedHistoricalBarSource` + `SourceAttempt`.
- `tests/test_market_data/test_multi_broker_historical_bar_source.py` — hermetic
  (injected fakes: served / empty→failover / raise→failover / all-fail→[] / order /
  observer callback).
- `scripts/verify_multi_broker_failover_realdata.py` — Rule-F: real failover across
  the live Upstox + Angel adapters.

## Rule check
- **Rule G:** implements `HistoricalBarSource` → drops into the existing replay
  consumers; no orphan. Composition-root wiring into the autonomous replay path is the
  purpose-consumer — tracked as the follow-up (does not block the primitive).
- **Rule F/J:** hermetic tests for all branches + a REAL failover pass on two live
  brokers.
- **Rule L:** priority order is injected, never hard-coded; the caller orders by
  segment/preference.
- **Rule K:** slice-2 aggregation + composition-root autonomous wiring are queued in
  BACKLOG, not silently skipped.
