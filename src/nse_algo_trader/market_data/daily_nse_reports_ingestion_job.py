"""Daily job: download all five NSE reports and persist them to the store.

Run by cron every evening after NSE publishes (~6 PM IST). The dated
reports (cash bhavcopy, F&O bhavcopy, MWPL) are fetched for the given
trade date; ban list and bulk/block deals only exist as current-day
files, so they are ingested as-published (their own internal dates win).
Every save is idempotent, so re-runs are safe.

Usage: python -m nse_algo_trader.market_data.daily_nse_reports_ingestion_job
       [--trade-date YYYY-MM-DD]   (default: today IST)
"""

import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_sqlite_store import (
    DealDisclosureKind,
    MarketDataSqliteStore,
)
from nse_algo_trader.market_data.nse_official_reports import (
    NseReportDownloader,
    NseReportDownloadError,
    parse_bulk_or_block_deals,
    parse_cash_bhavcopy_with_delivery,
    parse_fo_ban_list,
    parse_fo_bhavcopy_contract_rows,
    parse_mwpl_position_limits,
)


def ingest_nse_reports_for_trade_date(
    trade_date: date,
    report_downloader: NseReportDownloader,
    market_data_store: MarketDataSqliteStore,
) -> dict[str, str]:
    """Runs all five ingests, isolating failures per report. Returns a
    report-name -> outcome summary ("N rows" or the error message)."""
    ingestion_outcomes: dict[str, str] = {}

    def _run_single_report_ingestion(report_name: str, ingest_one_report) -> None:
        try:
            ingestion_outcomes[report_name] = ingest_one_report()
        except (NseReportDownloadError, ValueError) as ingestion_error:
            ingestion_outcomes[report_name] = f"FAILED: {ingestion_error}"

    def _ingest_cash_bhavcopy() -> str:
        rows = parse_cash_bhavcopy_with_delivery(
            report_downloader.download_cash_bhavcopy_with_delivery(trade_date)
        )
        market_data_store.save_cash_bhavcopy_delivery_rows(rows)
        return f"{len(rows)} rows"

    def _ingest_fo_bhavcopy() -> str:
        rows = parse_fo_bhavcopy_contract_rows(
            report_downloader.download_fo_bhavcopy(trade_date)
        )
        market_data_store.save_fo_bhavcopy_contract_rows(rows)
        return f"{len(rows)} rows"

    def _ingest_mwpl() -> str:
        rows = parse_mwpl_position_limits(
            report_downloader.download_mwpl_position_limits(trade_date)
        )
        market_data_store.save_mwpl_position_limit_rows(rows)
        return f"{len(rows)} rows"

    def _ingest_current_ban_list() -> str:
        ban_report = parse_fo_ban_list(report_downloader.download_current_fo_ban_list())
        market_data_store.save_fo_ban_list_report(ban_report)
        return (
            f"{len(ban_report.banned_underlying_symbols)} symbols "
            f"for {ban_report.ban_trade_date}"
        )

    def _ingest_current_bulk_deals() -> str:
        rows = parse_bulk_or_block_deals(report_downloader.download_current_bulk_deals())
        market_data_store.save_bulk_or_block_deal_rows(rows, DealDisclosureKind.BULK_DEAL)
        return f"{len(rows)} rows"

    def _ingest_current_block_deals() -> str:
        rows = parse_bulk_or_block_deals(report_downloader.download_current_block_deals())
        market_data_store.save_bulk_or_block_deal_rows(rows, DealDisclosureKind.BLOCK_DEAL)
        return f"{len(rows)} rows"

    _run_single_report_ingestion("cash_bhavcopy_delivery", _ingest_cash_bhavcopy)
    _run_single_report_ingestion("fo_bhavcopy_open_interest", _ingest_fo_bhavcopy)
    _run_single_report_ingestion("mwpl_position_limits", _ingest_mwpl)
    _run_single_report_ingestion("fo_ban_list", _ingest_current_ban_list)
    _run_single_report_ingestion("bulk_deals", _ingest_current_bulk_deals)
    _run_single_report_ingestion("block_deals", _ingest_current_block_deals)
    return ingestion_outcomes


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--trade-date", type=date.fromisoformat, default=None)
    parsed_args = argument_parser.parse_args()
    trade_date_to_ingest = parsed_args.trade_date or datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    outcomes = ingest_nse_reports_for_trade_date(
        trade_date_to_ingest, NseReportDownloader(), MarketDataSqliteStore()
    )
    print(f"NSE report ingestion for {trade_date_to_ingest}:")
    for report_name, outcome in outcomes.items():
        print(f"  {report_name}: {outcome}")
