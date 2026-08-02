"""Rule-F verification for Trunk II — market breadth + cross-market context (research/137). Computes
REAL market breadth over the latest stored cash bhavcopy (thousands of EQ symbols) and the
cross-market confirmation read.

Run:  python scripts/verify_market_breadth_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.market_data.market_breadth import (
    SymbolReturn,
    assess_cross_market_context,
    compute_market_breadth,
)
from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore


def main() -> int:
    store = MarketDataSqliteStore()
    trade_date = store.latest_cash_bhavcopy_trade_date()
    print(f"Latest stored cash bhavcopy trade date: {trade_date}")
    if trade_date is None:
        print("RESULT: SKIP — no stored cash bhavcopy.")
        return 0
    returns = [SymbolReturn(s, r) for s, r in store.cash_bhavcopy_symbol_returns(trade_date)]
    store.close()
    print(f"Real EQ symbols with a return: {len(returns)}")

    mb = compute_market_breadth(returns)
    cx = assess_cross_market_context(returns)
    print("\nMARKET BREADTH over REAL bhavcopy:")
    print(f"  {mb.summary}")
    print("\nCROSS-MARKET CONTEXT:")
    print(f"  {cx.summary}")

    assert mb.total == len(returns) and 0.0 <= mb.breadth_pct <= 1.0
    print(f"\nRESULT: PASS — real market-internals sensed over {mb.total} real EQ symbols "
          f"({mb.breadth_pct:.0%} advancing, {'BROAD' if mb.is_broad else 'narrow'}; "
          f"cross-market {'DIVERGENCE' if cx.divergence else 'confirmed'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
