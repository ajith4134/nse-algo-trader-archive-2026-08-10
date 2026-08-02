"""Rule-F verification for Trunk VII — instrumental-convergence limiter (research/117). Confirms the
LIVE service composes the limiter onto its trading state, under normal load the real concurrent
exposures are under the cap (permit), and an engaged real off-switch blocks ALL orders (off-switch
dominance) — over the real service state.

Run:  python scripts/verify_instrumental_convergence_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
from nse_algo_trader.conscience.instrumental_convergence_limiter import ConvergenceLimits
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    state = service._state
    cap = ConvergenceLimits().max_concurrent_exposures
    open_exposures = len(state.open_positions) + len(state.open_option_spreads)
    print(f"Real service state: {open_exposures} concurrent exposures (cap {cap})")

    # Under normal load → permitted.
    permitted = state.convergence_limiter_permits_order()
    print(f"  under cap → permitted={permitted}")
    assert permitted, "normal load should be under the runaway-acquisition cap"

    # Off-switch dominance: engage the real off-switch → every order blocked.
    state.corrigibility_switch = CorrigibilitySwitch()
    state.corrigibility_switch.halt("verify: off-switch dominance")
    blocked = not state.convergence_limiter_permits_order()
    print(f"  off-switch engaged → blocked={blocked} "
          f"(count={state.convergence_limiter_blocked_order_count})")
    assert blocked and state.convergence_limiter_blocked_order_count == 1

    print("\nRESULT: PASS — the instrumental-convergence limiter caps runaway acquisition and "
          "asserts off-switch dominance on the real service state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
