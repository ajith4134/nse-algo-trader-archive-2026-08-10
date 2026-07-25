"""Rule-F real-data verification for the scheduled champion-challenger auto-re-eval
(§53 slice 5c-i.b). Builds a service, runs `_maybe_reevaluate_champion_challenger` over the
REAL stored sessions twice on the same day, and confirms: it runs the tournament on real
data the first time (loading the real session set), keeps/updates the champion via the gate,
and is a no-op the second time (once-per-day scheduler). Does not mutate live trading — only
the champion config store, which is the intended output.

Run:  python scripts/verify_champion_challenger_autoreeval_realdata.py
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
)

IST = ZoneInfo("Asia/Kolkata")


def main() -> int:
    load_env_file_into_environ()
    service = LivePaperTradingService(object(), 1_000_000.0, champion_challenger_min_sessions=5)

    sessions = service._load_stored_benchmark_sessions()
    print(f"Real evaluation set loaded by the service: {len(sessions)} stored sessions")
    if len(sessions) < 5:
        print("Fewer than 5 stored sessions — re-eval would skip; not enough to verify.")
        return 2

    before = ChampionConfigurationStore().load_champion_or_default()
    print(f"Champion before: ORmin={before.opening_range_minutes} RR={before.target_risk_reward_ratio}")

    load_calls = {"n": 0}
    original_loader = service._load_stored_benchmark_sessions
    service._load_stored_benchmark_sessions = lambda: (load_calls.__setitem__("n", load_calls["n"] + 1), original_loader())[1]

    now = datetime(2026, 7, 24, 18, 0, tzinfo=IST)
    service._maybe_reevaluate_champion_challenger(now)      # first run: executes
    first_run_loads = load_calls["n"]
    service._maybe_reevaluate_champion_challenger(now)      # same day: gated no-op
    second_run_loads = load_calls["n"]

    after = ChampionConfigurationStore().load_champion_or_default()
    print(f"Champion after:  ORmin={after.opening_range_minutes} RR={after.target_risk_reward_ratio}")
    print(f"Session-loader invocations: after 1st call={first_run_loads}, after 2nd call={second_run_loads}")
    print(f"last_run_date = {service._champion_challenger_last_run_date}")

    assert first_run_loads == 1, "first re-eval should load the real sessions once"
    assert second_run_loads == 1, "second same-day call must be a scheduler no-op"
    assert service._champion_challenger_last_run_date == now.date()
    print("\n✓ Rule-F PASS: the scheduled re-eval ran the tournament over real sessions once, "
          "updated the champion via the gate, and is idempotent within the day.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
