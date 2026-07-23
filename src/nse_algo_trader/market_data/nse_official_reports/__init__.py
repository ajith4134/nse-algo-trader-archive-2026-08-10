"""Secondary NSE data ingestion — official daily reports Kite doesn't provide.

Decided in `docs/PLAN.md` §8a.6: built now, as part of Layer 2. Covers
delivery % (cash bhavcopy), historical per-contract OI (F&O bhavcopy),
the F&O ban list, MWPL utilization, and bulk/block deals.
"""

from nse_algo_trader.market_data.nse_official_reports.bulk_block_deals_parser import (
    BulkOrBlockDealRow,
    parse_bulk_or_block_deals,
)
from nse_algo_trader.market_data.nse_official_reports.cash_bhavcopy_delivery_parser import (
    CashBhavcopyDeliveryRow,
    parse_cash_bhavcopy_with_delivery,
)
from nse_algo_trader.market_data.nse_official_reports.fo_ban_list_parser import (
    FoBanListReport,
    parse_fo_ban_list,
)
from nse_algo_trader.market_data.nse_official_reports.fo_bhavcopy_open_interest_parser import (
    FoBhavcopyContractRow,
    FoContractType,
    parse_fo_bhavcopy_contract_rows,
)
from nse_algo_trader.market_data.nse_official_reports.mwpl_position_limit_parser import (
    MwplPositionLimitRow,
    parse_mwpl_position_limits,
)
from nse_algo_trader.market_data.nse_official_reports.nse_report_downloader import (
    NseReportDownloader,
    NseReportDownloadError,
)

__all__ = [
    "BulkOrBlockDealRow",
    "CashBhavcopyDeliveryRow",
    "FoBanListReport",
    "FoBhavcopyContractRow",
    "FoContractType",
    "MwplPositionLimitRow",
    "NseReportDownloadError",
    "NseReportDownloader",
    "parse_bulk_or_block_deals",
    "parse_cash_bhavcopy_with_delivery",
    "parse_fo_ban_list",
    "parse_fo_bhavcopy_contract_rows",
    "parse_mwpl_position_limits",
]
