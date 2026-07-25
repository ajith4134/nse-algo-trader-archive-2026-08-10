"""CLI: fetch the BSE delisted-securities master and store it (§53 task #13).

A runnable entry point (cron-able, like `daily_nse_reports_ingestion_job`) — the
Rule-G wiring for the delisted source/store. Idempotent (INSERT OR REPLACE).

Usage:  python -m nse_algo_trader.market_data.delisted_securities_ingestion_job
"""

from nse_algo_trader.market_data.delisted_securities_source import (
    BseDelistedSecuritiesSource,
)
from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore


def ingest_delisted_securities(delisted_securities_source=None, market_data_store=None) -> int:
    """Fetch the delisted master and persist it. Injectable source/store for tests;
    defaults to the real BSE source + the shared SQLite store."""
    delisted_securities_source = delisted_securities_source or BseDelistedSecuritiesSource()
    delisted = delisted_securities_source.fetch_delisted_securities()
    owns_store = market_data_store is None
    market_data_store = market_data_store or MarketDataSqliteStore()
    try:
        return market_data_store.save_delisted_securities(delisted)
    finally:
        if owns_store:
            market_data_store.close()


if __name__ == "__main__":
    print(f"Stored {ingest_delisted_securities()} delisted securities")
