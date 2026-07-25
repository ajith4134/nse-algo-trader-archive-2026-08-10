"""Rule-F real-data verification for the per-market-regime champion (§53 slice 5c-iii).

Classifies the REAL stored sessions by ADX market regime (they span trending/range/
indecisive), runs the champion-challenger tournament INDEPENDENTLY per regime, and prints
each regime's decision + scorecards. On thin per-regime evidence the conservative gate
keeps the incumbent in each regime (coherent, overfitting-safe). No creds/market.

Run:  python scripts/verify_per_regime_champion_realdata.py
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.paper_trading.historical_session_market_regime_classifier import (
    classify_session_market_regime,
)
from nse_algo_trader.paper_trading.per_regime_champion_evaluator import (
    evaluate_per_regime_champions,
    partition_sessions_by_regime,
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
            print("No stored 5m bars — cannot verify.")
            return 2
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
                "WHERE bar_interval='5m' AND instrument_token=? ORDER BY 1", (token,))
        ]
        labelled = []
        for d in dates:
            day_start = datetime(d.year, d.month, d.day, tzinfo=IST)
            bars = store.load_price_bars(token, BarInterval.MINUTE_5, day_start, day_start + timedelta(days=1))
            if bars:
                labelled.append((bars, instrument, classify_session_market_regime(bars).value))
    finally:
        store.close()

    counts = {r: len(s) for r, s in partition_sessions_by_regime(labelled).items()}
    print(f"Real sessions by regime: {counts}\n")
    decisions = evaluate_per_regime_champions(labelled, {}, CHALLENGERS)

    for regime, decision in sorted(decisions.items()):
        c = decision.champion_scorecard
        print(f"[{regime}] champion traded={c.sessions_traded} sharpe={c.sharpe_ratio:+.3f} "
              f"→ replaced={decision.champion_replaced} ({decision.promotion_reason})")

    assert len(counts) >= 2, f"expected the real sessions to span ≥2 regimes; got {counts}"
    assert set(decisions) == set(counts), "a decision per populated regime"
    print("\n✓ Rule-F PASS: per-regime champion-challenger ran independently across the real "
          "market regimes and returned a coherent, gate-checked decision for each.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
