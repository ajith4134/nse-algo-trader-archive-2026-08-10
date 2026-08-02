"""Rule-F real-data verification for Layer 7.5 slice 3 — the per-trade pre-mortem Monte Carlo
(research/107). Extracts REAL post-trigger intraday paths from the stored sessions and runs an
entry-time Monte Carlo on a canonical trade at the champion RR, printing the outcome distribution
+ the CVaR tail.

Run:  python scripts/verify_per_trade_pre_mortem_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
)
from nse_algo_trader.paper_trading.per_trade_pre_mortem import (
    extract_post_trigger_return_paths,
    run_entry_pre_mortem,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection

# Reuse the slice-1 real session loader.
from verify_control_arms_realdata import _load_stored_sessions  # type: ignore


def main() -> int:
    sessions = _load_stored_sessions()
    print(f"Real stored sessions: {len(sessions)}")
    if not sessions:
        print("BLOCKER: no stored sessions.")
        return 2

    champion = ChampionConfigurationStore().load_champion_or_default()
    paths = extract_post_trigger_return_paths(sessions, champion)
    print(f"Extracted post-trigger paths: {len(paths)} "
          f"(mean length {sum(len(p) for p in paths) / max(1, len(paths)):.1f} bars)")
    if not paths:
        print("BLOCKER: no post-trigger paths extracted.")
        return 2

    risk = 1.0
    forecast = run_entry_pre_mortem(
        entry_price=100.0, stop_loss_price=100.0 - risk,
        target_price=100.0 + champion.target_risk_reward_ratio * risk,
        direction=SignalDirection.LONG, return_paths=paths,
    )
    print(f"\nCanonical LONG pre-mortem (entry 100, stop 99, target "
          f"{100 + champion.target_risk_reward_ratio:.0f}, RR{champion.target_risk_reward_ratio}):")
    print(f"  P(target)  = {forecast.probability_target:.0%}")
    print(f"  P(stop)    = {forecast.probability_stop:.0%}")
    print(f"  P(timeout) = {forecast.probability_timeout:.0%}")
    print(f"  expected   = {forecast.mean_return:+.2%}")
    print(f"  CVaR-5%    = {forecast.conditional_value_at_risk_5pct:+.2%}")
    print(f"  worst case = {forecast.worst_case_return:+.1%}")
    print(f"  verdict: {forecast.verdict}")

    total = (forecast.probability_target + forecast.probability_stop
             + forecast.probability_timeout)
    assert abs(total - 1.0) < 1e-6, f"probabilities must sum to 1 (got {total})"
    assert forecast.conditional_value_at_risk_5pct <= forecast.mean_return
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
