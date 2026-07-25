"""Rule-F real-data verification for the deficit-driven replay curriculum (§53 slice 5a).

Classifies the REAL stored sessions (the market-regime benchmark = the most-recorded
instrument) into their ADX market regimes, shows the distribution (regime VARIETY is the
whole point), then proves the deficit selector picks a session of the least-covered
regime given a coverage ledger. No creds / no network — reads the local bar store.

Run:  python scripts/verify_replay_curriculum_realdata.py
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.paper_trading.deficit_driven_replay_session_selector import (
    select_deficit_replay_session,
)
from nse_algo_trader.paper_trading.historical_session_market_regime_classifier import (
    classify_session_market_regime,
    latest_session_adx,
)

IST = ZoneInfo("Asia/Kolkata")


def main() -> int:
    store = MarketDataSqliteStore()
    try:
        row = store._connection.execute(
            "SELECT instrument_token, COUNT(*) n FROM price_bars WHERE bar_interval='5m' "
            "GROUP BY instrument_token ORDER BY n DESC LIMIT 1"
        ).fetchone()
        if row is None:
            print("No 5m bars stored — cannot verify.")
            return 2
        benchmark_token = row[0]
        dates = [
            datetime.fromisoformat(r[0]).date()
            for r in store._connection.execute(
                "SELECT DISTINCT date(bar_timestamp) FROM price_bars "
                "WHERE bar_interval='5m' AND instrument_token=? ORDER BY 1",
                (benchmark_token,),
            )
        ]
        print(f"Benchmark token {benchmark_token}: {len(dates)} real stored sessions "
              f"({dates[0]} … {dates[-1]})")

        classified = []
        for session_date in dates:
            day_start = datetime(session_date.year, session_date.month, session_date.day, tzinfo=IST)
            bars = store.load_price_bars(
                benchmark_token, BarInterval.MINUTE_5, day_start, day_start + timedelta(days=1)
            )
            regime = classify_session_market_regime(bars)
            adx = latest_session_adx(bars)
            classified.append((session_date, regime))
            print(f"  {session_date}  bars={len(bars):3d}  ADX={adx!s:>6.6}  → {regime.value}")
    finally:
        store.close()

    distribution: dict[str, int] = {}
    for _, regime in classified:
        distribution[regime.value] = distribution.get(regime.value, 0) + 1
    print(f"\nRegime distribution across real sessions: {distribution}")

    assert classified, "no sessions classified"
    assert len(distribution) >= 2, (
        "expected market-regime VARIETY across the real sessions (the curriculum's "
        f"reason to exist); got only {distribution}"
    )

    # With trending already 'covered', the selector must pick a non-trending (deficit) day.
    covered = {"trending": 99}
    chosen = select_deficit_replay_session(classified, covered)
    chosen_regime = next(r.value for d, r in classified if d == chosen)
    print(f"\nGiven trending is saturated (covered=99), curriculum picks: {chosen} "
          f"({chosen_regime})")
    assert chosen_regime != "trending", "deficit selector should avoid the saturated regime"

    print("\n✓ Rule-F PASS: real sessions classify into multiple market regimes and the "
          "deficit-driven curriculum selects an under-covered regime's session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
