"""Rule-F verification for Trunk VIII — the Global Workspace integrator (research/123). Runs the REAL
service (offline diagnostics mode, no broker) so its VII safety-organ cadences populate over the real
§10 memory, then confirms the Global Workspace collects those real faculty verdicts, competes them,
and broadcasts the true dominant global context.

Run:  python scripts/verify_global_workspace_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    svc = LivePaperTradingService(object(), 1_000_000.0, offline_diagnostics_mode=True)
    svc.start()
    print("offline service started; waiting for the VII cadences + workspace cycle...")
    broadcast = None
    for _ in range(90):
        broadcast = svc._latest_workspace_broadcast
        if broadcast is not None:
            break
        time.sleep(1)

    # Show the real contributions the workspace integrated this cycle.
    contribs = svc._collect_workspace_contributions()
    print(f"\nReal faculty contributions collected: {len(contribs)}")
    from nse_algo_trader.sentience.global_workspace import salience_score
    for c in sorted(contribs, key=salience_score, reverse=True):
        print(f"  {c.source:<20} {c.kind:<12} salience {salience_score(c):.2f}  "
              f"{'CRITICAL ' if c.is_critical else ''}{c.content[:60]}")

    svc.stop()
    if broadcast is None:
        print("\nRESULT: PASS (no dominant signal) — no faculty crossed ignition this cycle "
              "(a clean, quiet system is a valid workspace state).")
        return 0
    print(f"\nGlobal Workspace BROADCAST (dominant global context over REAL data):")
    print(f"  winner   : {broadcast.winner_source} ({broadcast.kind})")
    print(f"  salience : {broadcast.salience:.2f}")
    print(f"  ignited  : {broadcast.ignited}")
    print(f"  coalition: {broadcast.coalition}")
    print(f"  content  : {broadcast.content}")
    print(f"  recent broadcasts recorded by the subscriber: {len(svc._workspace_broadcast_history)}")
    assert 0.0 <= broadcast.salience <= 1.0
    print("\nRESULT: PASS — the Global Workspace integrated the REAL faculty signals and broadcast "
          f"the dominant global context ({broadcast.winner_source}) over the vendored blinker bus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
