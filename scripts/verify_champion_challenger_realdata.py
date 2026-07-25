"""Rule-F real-data verification for the champion-challenger ORB tournament (§53 slice
5c-i). Runs the champion (default ORB config) against several challengers over the REAL
stored benchmark sessions, prints each scorecard, and shows the promotion decision. On
thin real evidence the conservative Deflated-Sharpe gate is expected to KEEP the champion
(the overfitting-safety property); promotions become possible as more sessions accrue.

Run:  python scripts/verify_champion_challenger_realdata.py
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.paper_trading.champion_challenger_orb_evaluator import (
    evaluate_champion_vs_challengers,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")

CHAMPION = OpeningRangeBreakoutConfig()  # the incumbent default
CHALLENGERS = [
    OpeningRangeBreakoutConfig(opening_range_minutes=30),
    OpeningRangeBreakoutConfig(target_risk_reward_ratio=1.5),
    OpeningRangeBreakoutConfig(opening_range_minutes=45, target_risk_reward_ratio=3.0),
    OpeningRangeBreakoutConfig(latest_entry_time_ist=time(12, 0)),
]


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
        instrument = Instrument(
            instrument_token=benchmark_token, trading_symbol="BENCHMARK",
            exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
            lot_size=1, tick_size=0.05,
        )
        dates = [
            datetime.fromisoformat(r[0]).date()
            for r in store._connection.execute(
                "SELECT DISTINCT date(bar_timestamp) FROM price_bars "
                "WHERE bar_interval='5m' AND instrument_token=? ORDER BY 1",
                (benchmark_token,),
            )
        ]
        sessions = []
        for d in dates:
            day_start = datetime(d.year, d.month, d.day, tzinfo=IST)
            bars = store.load_price_bars(
                benchmark_token, BarInterval.MINUTE_5, day_start, day_start + timedelta(days=1)
            )
            if bars:
                sessions.append((bars, instrument))
    finally:
        store.close()

    print(f"Real evaluation set: {len(sessions)} stored sessions (benchmark token {benchmark_token})\n")
    decision = evaluate_champion_vs_challengers(CHAMPION, CHALLENGERS, sessions)

    def show(name, card):
        hit = None if card.hit_rate is None else round(card.hit_rate, 3)
        print(f"  {name:26s} traded={card.sessions_traded:2d} hit={hit} "
              f"total_return={card.total_return:+.4f} sharpe={card.sharpe_ratio:+.3f} "
              f"| ORmin={card.config.opening_range_minutes} RR={card.config.target_risk_reward_ratio}")

    show("CHAMPION (default)", decision.champion_scorecard)
    for i, card in enumerate(decision.challenger_scorecards):
        show(f"challenger[{i}]", card)

    print(f"\nDecision: champion_replaced={decision.champion_replaced} "
          f"(DSR={decision.promotion_deflated_sharpe:.3f})")
    print(f"Reason: {decision.promotion_reason}")
    print(f"Winning config: ORmin={decision.winning_config.opening_range_minutes} "
          f"RR={decision.winning_config.target_risk_reward_ratio} "
          f"latest_entry={decision.winning_config.latest_entry_time_ist}")

    assert decision.champion_scorecard.sessions_traded >= 0
    # coherence: a replacement only ever happens toward a challenger, never a phantom config.
    if decision.champion_replaced:
        assert decision.winning_config in CHALLENGERS
    else:
        assert decision.winning_config == CHAMPION
    print("\n✓ Rule-F PASS: the champion-challenger tournament ran over real sessions and "
          "returned a coherent, gate-checked promotion decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
