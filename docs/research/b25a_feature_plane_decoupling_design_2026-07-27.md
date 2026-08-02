# B25a — decouple the feature/analytics plane from the trading loop

**Operator requirement (verbatim):** *"the rest of the features and dashboard should not stop working
or depend on this"*, and they must be *"operating and active even after market is closed"*.

**Sourcing note (Rule I, explicit):** no OSS pass applies — this is a threading/lifecycle change to
this repo's own writer loop. `APScheduler` was already evaluated and marked INTEGRATE in an earlier
sourcing pass (research/170 §8) for a general scheduler; it is deliberately NOT used here, because
this needs one extra daemon thread with a fixed interval, and importing a scheduler framework to run
one loop would add a dependency and a failure mode without removing any code. If the cadence layer
later grows real scheduling needs (cron windows, jitter, misfire policy), revisit that verdict.

## The measured defect

`LivePaperTradingService._run_forever` does everything on ONE thread inside ONE `try`:

```python
while self._running:
    try:
        if market_open:  self._advance_one_pass(now)      # TRADING
        ...
        self._maybe_run_strategic_reflection(now)          # ~45 FEATURE STAGES
        ... 44 more ...
        self._publish(now)                                 # publish LAST
    except Exception:  print(...)
    sleep(scan_interval)
```

Three consequences, all observed:

1. **First publish takes ~89 seconds** (measured 2026-07-27). Every stage — including loading a
   FinBERT model — runs before the dashboard shows anything, so a restart blanks the page for ~1.5
   minutes. The operator hit this directly ("why its taking so long").
2. **One bad pass skips ~45 features.** A single exception anywhere jumps to the handler, so every
   later stage AND the publish are skipped. Failures are indistinguishable from "nothing happened".
3. **Features die with trading.** They share the thread, so anything that stalls the scan pass
   stalls the whole analytics plane — the exact coupling the operator asked to remove.

## The change

**Two daemon threads instead of one:**

| thread | does | cadence |
|---|---|---|
| `live-paper-loop` (existing) | scan pass / replay, drain closed experiments, **publish** | `scan_interval_seconds` |
| `feature-plane` (new) | the ~45 `_maybe_run_*` stages, **publish** | its own interval, market-independent |

**Publish early.** The trading thread publishes right after its scan pass, so the trading view is up
in seconds; feature panels fill in behind it as the feature thread completes stages. Publishing is
already guarded by `self._publish_lock`.

**Per-stage isolation.** Stages become a named list run through one helper that catches per stage,
counts failures by name, and continues. A stage that throws no longer silences the other 44.

**Market-independent.** The feature thread never checks market hours — that is what "active even
after market is closed" requires.

## Thread-safety, stated honestly

Feature stages write cached values onto `self._state` / `self._latest_*` that the trading thread
reads as scalars (size multipliers, veto flags). Under the GIL each attribute assignment is atomic,
so a reader sees either the old or the new value — never a corrupted one. What is NOT guaranteed is
that a *multi-field* update is read atomically: a trading pass could read a new multiplier alongside
a stale companion field.

This is acceptable **for these specific consumers** because every such value is an advisory,
tighten-only size lever whose stale-vs-fresh difference is a slightly different position size — not
a correctness violation. It would NOT be acceptable for order state, which stays exclusively on the
trading thread. Recorded here rather than discovered later; if a future feature writes a value that
must be read consistently with another, it needs an explicit snapshot.

The SQLite stores each thread touches are opened `check_same_thread=False` (see the B18 fix) or
per-thread.

## Acceptance criteria

1. First publish in **under ~10s** (from ~89s) — the trading view no longer waits on FinBERT.
2. A stage that raises does NOT prevent later stages from running, nor the publish.
3. Per-stage failures are counted BY NAME and surfaced — never a silent skip.
4. The feature plane keeps running with the market closed and with the trading loop idle.
5. Stopping the service stops both threads.
6. No regression: all existing surfaces still populate.

## Verification

Unit tests for 2/3/5 with an injected exploding stage; a timing assertion for 1; and a live check
that surfaces still populate (Rule N). Market is closed, so this is Rule-J territory — but the
feature plane is *supposed* to run market-closed, which makes this the one slice today whose
real-data pass does NOT need an open market.

## NOT in this slice (Rule K)

The richer multi-panel UI (B25b) — the operator explicitly sequenced it after this. The ~70 bare
`except: pass` blocks elsewhere (B6) are untouched; this slice only fixes the loop's own structure.
