"""Rule-F verification for Trunk VII — scalable oversight (research/116). Confirms the LIVE service
composes the oversight competence-ceiling gate onto its trading state, the bot's own confident
segments pass, and a low-confidence LEVERAGED (option) decision is DEFERRED as beyond autonomous
competence — over the real service state (not a fake).

Run:  python scripts/verify_scalable_oversight_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    state = service._state

    # A confident cash decision → autonomous (permitted).
    assert state.oversight_permits_autonomous_order(0.68, is_option=False) is True
    # A confident option decision → autonomous (permitted).
    assert state.oversight_permits_autonomous_order(0.66, is_option=True) is True
    # A LOW-confidence LEVERAGED (option) decision → beyond autonomous competence → DEFERRED.
    blocked = not state.oversight_permits_autonomous_order(0.50, is_option=True)
    # A low-confidence cash decision → permitted (lower stakes, panel-review tier).
    permitted_cash = state.oversight_permits_autonomous_order(0.50, is_option=False)

    print("Scalable-oversight gate on the REAL service state:")
    print(f"  confident cash (0.68)        → permitted")
    print(f"  confident option (0.66)      → permitted")
    print(f"  low-conf option (0.50)       → blocked={blocked} (beyond autonomous competence)")
    print(f"  low-conf cash (0.50)         → permitted={permitted_cash} (lower stakes)")
    print(f"  tiers: autonomous={state.oversight_autonomous_count} "
          f"panel={state.oversight_panel_review_count} "
          f"blocked={state.oversight_human_review_blocked_count}")

    assert blocked and permitted_cash
    assert state.oversight_human_review_blocked_count == 1
    print("\nRESULT: PASS — scalable oversight enforces the competence ceiling on the real service: "
          "low-confidence leveraged decisions are escalated/deferred, confident ones act autonomously.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
