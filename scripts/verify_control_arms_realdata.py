"""Rule-F real-data verification for Layer 7.5 slice 1 — the RANDOM-CONTROL skill-vs-luck arm
(research/95). Loads the REAL stored benchmark sessions, scores the real champion ORB arm against
the random-control arm, and prints both arms + the edge verdict. On today's data the real strategy
is losing, so the honest expected verdict is "no demonstrated edge vs random" — which is exactly
the scientific value of the control arm.

Run:  python scripts/verify_control_arms_realdata.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data import BarInterval
from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
)
from nse_algo_trader.paper_trading.control_arm_comparison import compare_control_arms
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _load_stored_sessions():
    """Every stored 5m session for the most-populated cash token — the real evaluation set."""
    store = MarketDataSqliteStore()
    sessions = []
    try:
        row = store._connection.execute(
            "SELECT instrument_token, COUNT(*) n FROM price_bars WHERE bar_interval='5m' "
            "GROUP BY instrument_token ORDER BY n DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return sessions
        token = row[0]
        instrument = Instrument(
            instrument_token=token, trading_symbol="BENCHMARK",
            exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
            lot_size=1, tick_size=0.05,
        )
        dates = [
            datetime.fromisoformat(r[0]).date()
            for r in store._connection.execute(
                "SELECT DISTINCT date(bar_timestamp) FROM price_bars "
                "WHERE bar_interval='5m' AND instrument_token=? ORDER BY 1", (token,)
            ).fetchall()
        ]
        for d in dates:
            day = datetime(d.year, d.month, d.day, tzinfo=IST)
            bars = store.load_price_bars(token, BarInterval.MINUTE_5, day, day + timedelta(days=1))
            if bars:
                sessions.append((bars, instrument))
    finally:
        store.close()
    return sessions


def main() -> int:
    sessions = _load_stored_sessions()
    print(f"Real stored sessions: {len(sessions)}")
    if not sessions:
        print("BLOCKER: no stored 5m sessions to score.")
        return 2

    champion = ChampionConfigurationStore().load_champion_or_default()
    print(f"Champion ORB config: OR{champion.opening_range_minutes}m · "
          f"RR{champion.target_risk_reward_ratio}")

    comparison = compare_control_arms(sessions, champion)
    for arm in (comparison.real, comparison.random_control):
        print(f"  {arm.arm_name:>22}: trades {arm.trades} · hit {arm.hit_rate:.0%} · "
              f"mean {arm.mean_return:+.2%} · total {arm.total_return:+.1%} · Sharpe {arm.sharpe:.2f}")
    print(f"\n  edge? {comparison.has_edge} — {comparison.verdict}")

    # both arms produced valid stats in range; the verdict is honest either way
    assert 0.0 <= comparison.real.hit_rate <= 1.0
    assert 0.0 <= comparison.random_control.hit_rate <= 1.0
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
