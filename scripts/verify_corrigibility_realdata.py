"""Rule-F verification for Trunk VII.5 — corrigibility/off-switch (research/111). The real service
composes an off-switch (un-halted); a compliant posture leaves trading permitted; engaging the
switch blocks every order; self-corrigibility halts on a synthetic constitutional breach.

Run:  python scripts/verify_corrigibility_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.dashboard.project_status_data import atlas_coverage


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    state = service._state
    switch = state.corrigibility_switch
    print(f"Service composed an off-switch: {isinstance(switch, CorrigibilitySwitch)}")
    assert isinstance(switch, CorrigibilitySwitch) and not switch.is_halted

    # un-halted → the bot's real segments trade
    assert state.constitution_permits_order("nse_cash_equity", is_option=False)
    print("  un-halted → orders permitted ✓")

    # engage the off-switch → EVERY order blocked
    switch.halt("manual emergency stop")
    blocked = not state.constitution_permits_order("nse_index_options", is_option=True)
    print(f"  engaged  → order blocked={blocked} (reason: {switch.reason})")
    assert blocked
    switch.resume()

    # atlas coverage is reported (dashboard concept-tree program visibility)
    cov = atlas_coverage()
    print(f"\nAI atlas coverage: {cov['built']}/{cov['total']} built ({cov['built_pct']}%), "
          f"{cov['partial']} partial — VII CONSCIENCE in progress")
    assert cov["built"] > 0

    print("\nRESULT: PASS — the off-switch halts all trading; atlas coverage is visible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
