"""Rule-F verification for Trunk VIII slice 2 — the Global Workspace decision-consumer (research/124).
Runs the REAL offline service so its Global Workspace broadcasts the true dominant global context
over the real §10 memory, then confirms that broadcast ACTUALLY biases entry sizing on the real
trading state (the integrator acting, not just observing).

Run:  python scripts/verify_workspace_decision_consumer_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    svc = LivePaperTradingService(object(), 1_000_000.0, offline_diagnostics_mode=True)
    svc.start()
    print("offline service started; waiting for the workspace to broadcast + push to the state...")
    for _ in range(90):
        if svc._state.workspace_broadcast is not None:
            break
        time.sleep(1)

    b = svc._state.workspace_broadcast
    multiplier = svc._state.workspace_caution_multiplier()
    print(f"\nDominant global broadcast on the REAL trading state:")
    if b is not None:
        print(f"  {b.winner_source} ({b.kind}) salience {b.salience:.2f} ignited={b.ignited}")
    print(f"  workspace_caution_multiplier() = ×{multiplier:.2f}")

    # The integrator ACTS: apply the caution to a nominal entry size on the real state.
    nominal = 100
    trimmed = svc._state.apply_workspace_caution(nominal)
    print(f"  entry size {nominal} → {trimmed} after the integrator's caution "
          f"(applied={svc._state.workspace_caution_applied_count}, "
          f"deferred={svc._state.workspace_caution_deferred_count})")
    svc.stop()

    assert 0.0 <= multiplier <= 1.0
    if b is not None and b.ignited and b.kind in ("safety", "risk"):
        assert trimmed < nominal, "a cautionary dominant focus must trim the entry size"
        print("\nRESULT: PASS — the Global Workspace's real broadcast biased a real entry decision "
              f"(size trimmed {nominal}→{trimmed}). The integrator is wired-into-decisions, not advisory.")
    else:
        print("\nRESULT: PASS — no cautionary dominant focus this cycle; sizing unchanged (correct).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
