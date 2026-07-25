"""Rule-F real-data verification for VPIN order-flow toxicity (§53 ADVANCED; research/94).
Computes VPIN on the REAL stored benchmark sessions and asserts every reading is a valid
toxicity score in [0, 1]. No creds/market.

Run:  python scripts/verify_vpin_realdata.py
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.market_data.vpin_order_flow_toxicity import compute_vpin

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
        token = row[0]
        dates = [
            datetime.fromisoformat(r[0]).date()
            for r in store._connection.execute(
                "SELECT DISTINCT date(bar_timestamp) FROM price_bars "
                "WHERE bar_interval='5m' AND instrument_token=? ORDER BY 1", (token,))
        ]
        print(f"Benchmark token {token}: {len(dates)} real sessions\n")
        readings = []
        for d in dates:
            day = datetime(d.year, d.month, d.day, tzinfo=IST)
            bars = store.load_price_bars(token, BarInterval.MINUTE_5, day, day + timedelta(days=1))
            r = compute_vpin(bars, bucket_count=10)
            readings.append((d, r))
            print(f"  {d}  bars={len(bars):3d}  buckets={r.bucket_count:2d}  "
                  f"VPIN={'—' if r.vpin is None else f'{r.vpin:.3f}'}")
    finally:
        store.close()

    scored = [r.vpin for _, r in readings if r.vpin is not None]
    assert scored, "no session produced a VPIN reading"
    assert all(0.0 <= v <= 1.0 for v in scored), "VPIN out of [0,1]"
    print(f"\nsessions scored: {len(scored)}/{len(readings)} · "
          f"VPIN range {min(scored):.3f}–{max(scored):.3f} · mean {sum(scored)/len(scored):.3f}")
    print("\n✓ Rule-F PASS: VPIN computes a valid order-flow toxicity score in [0,1] on real bars.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
