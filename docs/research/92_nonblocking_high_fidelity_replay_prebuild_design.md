# research/92 — Non-blocking high-fidelity replay prebuild (task #14)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD. Restores autonomous high-fidelity replay (Breeze-1s / fleet-1m)
as a DEFAULT without blocking startup — the proper fix behind the 2026-07-25 dashboard
outage (research/91 / SYSTEM_MAP ledger 2026-07-25y).

## Problem
`service.start()` built the high-fidelity replay feed (`_build_high_fidelity_replay_feed`)
SYNCHRONOUSLY — many network fetches for the focus set — before returning. That blocked the
dashboard bind and kept the service unusable for minutes, so autonomous high-fidelity replay
had to be made opt-in (default OFF). We want it back on by default without the stall.

## Design — build fast, upgrade in the background
1. **`start()` always builds the fast store-5m feed first** (`_build_store_5m_replay_feed`,
   the existing else-branch extracted) so the service is live in ~seconds and replay works
   immediately on 5-minute bars.
2. **If a high-fidelity config is active**, spawn a DAEMON builder thread
   (`_high_fidelity_replay_builder`) that does the heavy fetch off the startup path and, when
   done, **atomically swaps** the replay feed to the higher-fidelity one.
3. **Thread-safe swap:** a `threading.Lock` guards the `(_replay_feed, _replay_timestamps,
   _replay_cursor)` triple. The builder assigns all three under the lock (cursor reset to 0);
   `_advance_replay_pass` reads the timestamp + advances the cursor under the same lock. So the
   writer thread never indexes a stale cursor into a swapped-shorter timestamp list.
4. **Best-effort:** any failure in the builder leaves the store-5m feed in place (no regression,
   no crash). The loop keeps publishing on store-5m throughout the build and switches to
   high-fidelity only once it is fully built.
5. **Re-enable by default:** `enable_autonomous_high_fidelity_replay` back to True (Breeze-1s
   activates when a token is stored; the multi-broker fleet stays behind its own
   `enable_multi_broker_fleet_replay`, default off, until its focus is bounded). The dashboard
   bind + live view are unaffected because the build is now off-thread.

## Verification (Rule F/J)
- Hermetic: inject a slow/fake high-fidelity config via the builder seam; assert `start()`
  returns fast, the store-5m feed serves immediately, and after the builder completes the feed
  is swapped (feed identity changes) under the lock — with the loop never raising.
- Real-data: with a stored Breeze token, `start()` returns in ~seconds on store-5m, and the
  1-second feed swaps in once built; `/api/snapshot` stays responsive throughout.

## Files
- `dashboard/live_paper_trading_service.py` (refactor build path + lock + builder thread;
  flip the default).
- `tests/test_dashboard/test_nonblocking_high_fidelity_replay.py`
- extend `scripts/verify_...` or a small real check (market-closed).

## Rule check
- **Rule G:** the high-fidelity feed still drives the loop (now via a background upgrade).
- **Rule F/J:** hermetic swap test + a real market-closed check.
- **Rule M:** update MASTER_PROGRESS (fleet/Breeze replay back to default) + SYSTEM_MAP.
