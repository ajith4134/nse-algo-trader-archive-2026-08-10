"""Rule-F real-data verification for the market-impact fill model (§53 slice 5c-ii).

Computes a real instrument's average daily quantity (ADQ) from the REAL stored bar
volumes, then shows: (1) impact is MONOTONE in order size, (2) the combined cash fill
price worsens with size, (3) a tiny order ≈ the pure-spread price (impact→0), and (4)
unknown liquidity (ADQ absent) reproduces the old spread-only fill (no regression).

Run:  python scripts/verify_market_impact_fill_realdata.py
"""

from nse_algo_trader.broker_oms import OrderSide
from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.paper_trading.fill_slippage_model import slipped_fill_price
from nse_algo_trader.paper_trading.market_impact_fill_model import (
    estimate_market_impact_bps,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)


def main() -> int:
    store = MarketDataSqliteStore()
    try:
        row = store._connection.execute(
            "SELECT instrument_token, AVG(day_volume) FROM ("
            "  SELECT instrument_token, date(bar_timestamp) d, SUM(volume) AS day_volume"
            "  FROM price_bars WHERE bar_interval='5m' GROUP BY instrument_token, d"
            ") GROUP BY instrument_token ORDER BY AVG(day_volume) DESC LIMIT 1"
        ).fetchone()
    finally:
        store.close()
    if row is None or not row[1]:
        print("No stored volumes — cannot verify.")
        return 2
    token, adq = row[0], float(row[1])
    print(f"Benchmark token {token}: real ADQ = {adq:,.0f} shares/day (from stored bars)")

    instrument = Instrument(
        instrument_token=token, trading_symbol="BENCHMARK",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )
    reference = 1000.0
    spread_only = slipped_fill_price(instrument, OrderSide.BUY, reference, order_quantity=1)

    print(f"\nReference price {reference}; spread-only BUY fill = {spread_only:.4f}")
    print("Order size (as % of ADQ) → impact bps → combined BUY fill:")
    prev_fill = 0.0
    for pct in (0.1, 1.0, 5.0, 25.0, 100.0):
        qty = int(adq * pct / 100.0) or 1
        bps = estimate_market_impact_bps(qty, adq)
        fill = slipped_fill_price(instrument, OrderSide.BUY, reference,
                                  order_quantity=qty, average_daily_quantity=adq)
        print(f"  {pct:6.1f}%  qty={qty:>12,}  impact={bps:6.2f}bps  fill={fill:.4f}")
        assert fill >= prev_fill, "fill must be monotone non-decreasing in order size"
        prev_fill = fill

    tiny = slipped_fill_price(instrument, OrderSide.BUY, reference, order_quantity=1,
                              average_daily_quantity=adq)
    # a 1-share order's impact is negligible (well under one 0.05 tick) → ≈ pure spread.
    assert abs(tiny - spread_only) < 0.01, "a tiny order should ≈ the pure-spread price"
    # unknown liquidity -> spread-only (no regression)
    no_adq = slipped_fill_price(instrument, OrderSide.BUY, reference, order_quantity=10_000)
    assert no_adq == spread_only, "absent ADQ must reproduce the old spread-only fill"

    print("\n✓ Rule-F PASS: market impact from REAL volumes is monotone in size, a tiny "
          "order ≈ pure spread, and absent liquidity reproduces the old fill (no regression).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
