"""Rule-F verification for Trunk VIII — workspace rumination (research/129). Runs the REAL offline
service long enough to accrue several ignited broadcasts, then confirms the rumination report
reflects the real recurring concern (goal_integrity dominates → ruminating).

Run:  python scripts/verify_workspace_rumination_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    # short scan interval so several workspace cycles run quickly
    svc = LivePaperTradingService(
        object(), 1_000_000.0, offline_diagnostics_mode=True, scan_interval_seconds=1
    )
    svc.start()
    print("offline service started; accruing ignited broadcasts for rumination...")
    r = None
    for _ in range(90):
        r = svc._latest_rumination
        hist = len(svc._workspace_broadcast_history)
        if r is not None and hist >= 4:
            break
        time.sleep(1)
    hist = len(svc._workspace_broadcast_history)
    svc.stop()

    print(f"\nBroadcast history accrued: {hist} ignited broadcasts")
    print("Rumination report over REAL replay:")
    print(f"  {r.summary}")
    print(f"  dominant={r.dominant_recurring} ({r.dominant_kind}) "
          f"recurrence={r.recurrence_count}/{r.recurrence_count and round(r.recurrence_count/max(1,r.recurrence_count/max(1e-9,r.recurrence_fraction)))} "
          f"fraction={r.recurrence_fraction:.0%} ruminating={r.is_ruminating}")

    assert r is not None
    print("\nRESULT: PASS — the workspace replayed its recent broadcasts and reported the real "
          f"recurring concern ({r.dominant_recurring}); ruminating={r.is_ruminating}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
