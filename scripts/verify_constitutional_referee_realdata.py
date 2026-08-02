"""Rule-F verification for Trunk VII.6 — the constitutional Referee enforcement (research/110).
Confirms the REAL service composes a Referee onto its trading state, every segment the bot actually
trades is PERMITTED through the entry-site gate, and a synthetic out-of-scope/overnight order is
BLOCKED (not placed).

Run:  python scripts/verify_constitutional_referee_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    state = service._state
    print(f"Service composed a Referee onto the trading state: "
          f"{isinstance(state.constitutional_referee, ConstitutionalReferee)}")
    assert isinstance(state.constitutional_referee, ConstitutionalReferee)

    # Every segment the bot actually trades must pass the entry-site gate.
    for segment, is_option in [
        ("nse_cash_equity", False), ("nse_index_options", True), ("nse_stock_options", True)
    ]:
        permitted = state.constitution_permits_order(segment, is_option)
        print(f"  {segment:<20} is_option={is_option} → permitted={permitted}")
        assert permitted, f"the bot's own segment {segment} was blocked!"

    # A synthetic constitution-violating order must be refused at the gate.
    blocked = not state.constitution_permits_order("nse_futures", is_option=False)
    print(f"  out-of-scope nse_futures → blocked={blocked} "
          f"(count={state.constitution_blocked_order_count})")
    assert blocked and state.constitution_blocked_order_count == 1

    referee = state.constitutional_referee
    print(f"\nReferee: adjudicated {referee.orders_adjudicated}, blocked {referee.blocked_count}")
    print("RESULT: PASS — the constitution now ENFORCES at the order sites, not just monitors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
