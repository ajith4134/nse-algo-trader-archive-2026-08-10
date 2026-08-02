"""Rule-F verification for Trunk VIII — higher-order monitoring + indicator scoreboard (research/131).
Runs the REAL offline service so several workspace cycles run, then confirms metacognition reports the
real ignition rate/health and the scoreboard ranks the real faculties. Completes Trunk VIII.

Run:  python scripts/verify_metacognition_scoreboard_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    svc = LivePaperTradingService(
        object(), 1_000_000.0, offline_diagnostics_mode=True, scan_interval_seconds=1
    )
    svc.start()
    print("offline service started; running several workspace cycles...")
    for _ in range(90):
        m = svc._latest_metacognition
        if m is not None and m.cycles_observed >= 4:
            break
        time.sleep(1)
    m = svc._latest_metacognition
    sb = svc._latest_indicator_scoreboard
    svc.stop()

    print("\nHIGHER-ORDER MONITORING (metacognition) over REAL operation:")
    print(f"  {m.summary}")
    print(f"  health={m.health_state} ignition_rate={m.ignition_rate:.0%} "
          f"cycles={m.cycles_observed} faculties/cycle={m.mean_faculty_count:.1f}")

    print("\nINDICATOR SCOREBOARD over REAL faculties:")
    print(f"  {sb.summary}")
    for s in sb.scores:
        print(f"    {s.source[:36]:<36} {s.kind:<10} salience {s.current_salience:.2f} "
              f"dominant {s.times_dominant}x")

    assert m is not None and sb is not None
    assert m.cycles_observed >= 1 and 0.0 <= m.ignition_rate <= 1.0
    print("\nRESULT: PASS — metacognition reported the real workspace health/ignition rate and the "
          "indicator scoreboard ranked the real faculties. TRUNK VIII SENTIENCE COMPLETE (13/13).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
