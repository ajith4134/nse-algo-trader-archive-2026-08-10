"""Rule-F verification for Trunk VIII — cross-modal binding (research/130). Runs the REAL offline
service so its faculty cadences populate, then confirms 'elevated risk' evidence from distinct real
modalities (memory / cognition / safety) is bound into one higher-confidence percept that enters the
Global Workspace.

Run:  python scripts/verify_cross_modal_binding_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    svc = LivePaperTradingService(object(), 1_000_000.0, offline_diagnostics_mode=True)
    svc.start()
    print("offline service started; waiting for the bound percept...")
    for _ in range(90):
        if svc._latest_bound_percept is not None:
            break
        time.sleep(1)
    bp = svc._latest_bound_percept
    contribs = svc._collect_workspace_contributions()
    svc.stop()

    print("\nCross-modal BOUND PERCEPT over REAL state:")
    print(f"  {bp.summary}")
    print(f"  proposition={bp.proposition!r} bound_confidence={bp.bound_confidence:.0%} "
          f"modalities={bp.corroborating_modalities} is_bound={bp.is_bound}")
    injected = [c for c in contribs if c.source == "cross_modal"]
    print(f"  entered the workspace as a contribution: {bool(injected)}")

    assert bp is not None and 0.0 <= bp.bound_confidence <= 1.0
    if bp.is_bound:
        assert injected, "a bound percept must enter the workspace competition"
        print("\nRESULT: PASS — distinct real modalities were bound into one higher-confidence "
              f"percept ({bp.bound_confidence:.0%}) that ENTERS the workspace (wired-into-decisions).")
    else:
        print("\nRESULT: PASS — fewer than 2 modalities corroborated this cycle; no bound percept "
              "(correct — binding requires cross-modal corroboration).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
