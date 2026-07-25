# research/85 — Wiring the multi-broker fleet into the autonomous replay loop (task #20)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD (this turn). Purpose-consumer for the failover source
(research/84) — Rule K: failover isn't "in the loop" until this lands.
**PLAN ref:** §8a.12 (multi-broker data sourcing); §1.4 (replay when market closed).

## Problem
`MultiBrokerHistoricalBarSource` (research/84) is built + real-data-verified but
nothing WIRES an ordered real fleet into the running service. Today the market-closed
replay precedence in `LivePaperTradingService.start()` is:
1. explicit injected `high_fidelity_replay`, else
2. `_maybe_activate_autonomous_breeze_replay()` — Breeze **1-second** (needs a manual
   daily Breeze token; rate-limited to a tiny focus), else
3. `_build_replay_feed_from_store()` — the stored **5-minute** bars.

So when there is no Breeze token (the common unattended case), replay drops straight
to coarse stored 5m — even though Upstox + Angel can serve **real 1-minute** bars for
a broad universe with no manual step (Upstox Analytics Token = no daily login; Angel =
automatic generateSession). That deep, resilient minute tier is exactly what the
fleet provides.

## Design — a new autonomous tier BETWEEN Breeze-1s and store-5m
Insert `_maybe_activate_autonomous_multi_broker_replay()` so precedence becomes:
1. explicit inject → 2. Breeze 1s (if token) → **3. multi-broker minute fleet (if any
broker creds)** → 4. store 5m.

It mirrors the proven `_maybe_activate_autonomous_breeze_replay` shape exactly:
- Runs in `start()` only if `high_fidelity_replay` is still None after the Breeze try.
- Builds the fleet via an injected `multi_broker_replay_source_builder` seam (default =
  `_build_available_broker_fleet_source`, a module-level real builder — same precedent
  as `_build_authenticated_breeze_historical_source`, so heavy imports/network/creds
  live in ONE lazily-called function and tests inject a fake).
- Fleet None (no broker creds) → return, stay on the store path (never breaks startup).
- Focus = `_rule_l_prioritized_focus_candidates()` (index opts → stock opts → cash)
  truncated to `multi_broker_replay_focus_size` (minute bars aren't Breeze-1s-rate-
  limited, so a broader bound — default 200). Rule L is applied by the ordering, so
  truncation drops cash first.
- Session date = day-walker most-recent-trading-day ≤ yesterday (same as Breeze path).
- Emits `HighFidelityReplayConfig(bar_source=fleet, bar_interval=MINUTE_1, …)` — the
  fleet plugs into the SAME `_build_high_fidelity_replay_feed()` /
  `build_replay_bars_by_token_from_source` path with zero change (the fleet IS a
  `HistoricalBarSource`).
- Whole method wrapped in try/except → None (best-effort; the always-on service must
  always start).

## `_build_available_broker_fleet_source(environ) -> MultiBrokerHistoricalBarSource | None`
Best-effort assembles the broker adapters whose creds are present, in a reliability
priority order, each wrapped so one missing/broken broker never blocks the others:
- **Upstox** (first): if `UPSTOX_ANALYTICS_TOKEN`/`_ACCESS_TOKEN` present → thin REST
  client + instrument-key resolver (downloads the real NSE master). No daily login, OI.
- **Angel One** (second): if `ANGEL_ONE_{API_KEY,CLIENT_CODE,PIN,TOTP_SECRET}` present
  → generateSession + symboltoken resolver (downloads OpenAPIScripMaster).
- (Fyers / Kite / Groww join here as their creds/entitlements land — future.)
Returns `MultiBrokerHistoricalBarSource(ordered)` or None if none built. Order is the
Rule-L-adjacent reliability preference (deep-history, no-daily-login first), injected —
not hard-coded policy inside the failover class.

## Files
- `dashboard/live_paper_trading_service.py` — new `__init__` seams
  (`multi_broker_replay_source_builder`, `multi_broker_replay_focus_size`), the
  `_maybe_activate_autonomous_multi_broker_replay()` method, the `start()` call, and
  the module-level `_build_available_broker_fleet_source()` builder. **No new
  cross-feature edge** (all imports are dashboard→market_data/broker_sessions/
  credentials, which `dashboard←everything` already has).
- `tests/test_dashboard/test_multi_broker_replay_activation.py` — hermetic: inject a
  fake builder → assert a MINUTE_1 `HighFidelityReplayConfig` on the fleet is set;
  None builder → stays None (store path); Breeze-token path still wins if present.
- `scripts/verify_multi_broker_replay_wiring_realdata.py` — Rule-F: the REAL
  `_build_available_broker_fleet_source` yields a fleet that builds a real
  `bars_by_token` (minute bars) via the same builder the loop uses.

## Rule check
- **Rule G / K:** this IS the purpose-consumer — the fleet now drives the market-closed
  replay source, not display-only. After this, #20's "resilient loop" promise is met.
- **Rule F/J:** hermetic activation test + a real fleet-build pass on live brokers.
- **Rule L:** focus candidates ordered index→stock→cash, truncation drops cash first.
- **Rule A:** one slice (autonomous minute-fleet tier). Gap-fill aggregation stays a
  separate queued slice (research/84).
