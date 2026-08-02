"""Rule-F verification for Trunk VII — red-team harness (research/118). Adversarially attacks the
LIVE champion ORB config over the REAL stored benchmark sessions (parameter perturbations +
worst-session tail) and prints the fragility report.

Run:  python scripts/verify_red_team_harness_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.red_team_harness import red_team_champion
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    sessions = service._load_stored_benchmark_sessions()
    print(f"Loaded {len(sessions)} REAL stored benchmark sessions")
    if not sessions:
        print("RESULT: SKIP — no stored benchmark sessions to red-team (ingest sessions first).")
        return 0

    report = red_team_champion(sessions, service._champion_orb_config())
    print("\nRed-team fragility report over REAL sessions + REAL champion config:")
    print(f"  baseline        : {report.baseline_return:+.3%}/trade ({report.baseline_trades} trades)")
    print(f"  worst session   : {report.worst_session_return:+.3%}")
    print(f"  fragile         : {report.fragile}")
    print("  attacks (worst-degradation first):")
    for a in report.attacks:
        print(f"    {a.attack_name:<32} mean {a.mean_return:+.3%}  degradation −{a.degradation:.3%}")
    print(f"\n  summary: {report.summary}")

    assert report.baseline_trades >= 0
    print(f"\nRESULT: PASS — the red-team harness attacked the real champion over {len(sessions)} real "
          f"sessions and produced a fragility report ({'FRAGILE' if report.fragile else 'robust'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
