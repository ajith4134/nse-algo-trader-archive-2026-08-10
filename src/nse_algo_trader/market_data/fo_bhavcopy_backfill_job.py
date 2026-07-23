"""One-shot/backfill job: pull historical F&O bhavcopies into the store.

Seeds the IV/PCR history that `implied_volatility_rank` and PCR trend
reads need. Weekends are skipped outright; a weekday whose file NSE
doesn't serve (holiday) is recorded and skipped; already-stored days are
never re-downloaded, so re-runs only fetch what's missing.

Usage: python -m nse_algo_trader.market_data.fo_bhavcopy_backfill_job
       [--calendar-days-back N]   (default 45)
"""

import argparse
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.market_data.nse_official_reports import (
    NseReportDownloader,
    NseReportDownloadError,
    parse_fo_bhavcopy_contract_rows,
)

_SECONDS_BETWEEN_DOWNLOADS = 1.0  # be polite to NSE's archive hosts


def backfill_fo_bhavcopy_history(
    earliest_trade_date: date,
    latest_trade_date: date,
    report_downloader: NseReportDownloader,
    market_data_store: MarketDataSqliteStore,
) -> dict[date, str]:
    backfill_outcomes: dict[date, str] = {}
    trade_date = earliest_trade_date
    while trade_date <= latest_trade_date:
        if trade_date.weekday() >= 5:
            trade_date += timedelta(days=1)
            continue
        if market_data_store.has_fo_bhavcopy_for_date(trade_date):
            backfill_outcomes[trade_date] = "already stored"
            trade_date += timedelta(days=1)
            continue
        try:
            contract_rows = parse_fo_bhavcopy_contract_rows(
                report_downloader.download_fo_bhavcopy(trade_date)
            )
            market_data_store.save_fo_bhavcopy_contract_rows(contract_rows)
            backfill_outcomes[trade_date] = f"{len(contract_rows)} rows"
        except NseReportDownloadError:
            backfill_outcomes[trade_date] = "unavailable (holiday?)"
        time.sleep(_SECONDS_BETWEEN_DOWNLOADS)
        trade_date += timedelta(days=1)
    return backfill_outcomes


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--calendar-days-back", type=int, default=45)
    parsed_args = argument_parser.parse_args()
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    outcomes = backfill_fo_bhavcopy_history(
        today_ist - timedelta(days=parsed_args.calendar_days_back),
        today_ist - timedelta(days=1),
        NseReportDownloader(),
        MarketDataSqliteStore(),
    )
    stored_count = sum(1 for outcome in outcomes.values() if outcome.endswith("rows"))
    print(f"FO bhavcopy backfill: {stored_count} new days stored")
    for trade_date, outcome in sorted(outcomes.items()):
        print(f"  {trade_date}: {outcome}")
