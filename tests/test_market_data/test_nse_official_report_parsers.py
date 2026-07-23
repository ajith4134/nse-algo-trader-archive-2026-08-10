from datetime import date

import pytest

from nse_algo_trader.market_data.nse_official_reports import (
    FoContractType,
    parse_bulk_or_block_deals,
    parse_cash_bhavcopy_with_delivery,
    parse_fo_ban_list,
    parse_fo_bhavcopy_contract_rows,
    parse_mwpl_position_limits,
)
from tests.fixtures.sample_nse_official_report_texts import (
    SAMPLE_BLOCK_DEALS_NO_RECORDS_CSV,
    SAMPLE_BULK_DEALS_CSV,
    SAMPLE_CASH_BHAVCOPY_WITH_DELIVERY_CSV,
    SAMPLE_FO_BAN_LIST_CSV,
    SAMPLE_FO_BHAVCOPY_CSV,
    SAMPLE_MWPL_POSITION_LIMIT_CSV,
)


class TestCashBhavcopyDeliveryParser:
    def test_parses_equity_row_with_delivery_fields(self):
        rows = parse_cash_bhavcopy_with_delivery(
            SAMPLE_CASH_BHAVCOPY_WITH_DELIVERY_CSV
        )
        equity_row = rows[0]
        assert equity_row.symbol == "20MICRONS"
        assert equity_row.series == "EQ"
        assert equity_row.trade_date == date(2026, 7, 22)
        assert equity_row.close_price == 211.15
        assert equity_row.total_traded_quantity == 201717
        assert equity_row.delivered_quantity == 89309
        assert equity_row.delivered_percent == 44.27

    def test_dash_delivery_fields_become_none_not_zero(self):
        rows = parse_cash_bhavcopy_with_delivery(
            SAMPLE_CASH_BHAVCOPY_WITH_DELIVERY_CSV
        )
        no_delivery_row = next(row for row in rows if row.symbol == "AAREYDRUGS")
        assert no_delivery_row.delivered_quantity is None
        assert no_delivery_row.delivered_percent is None


class TestFoBhavcopyOpenInterestParser:
    def test_parses_all_four_contract_types_and_skips_blank_lines(self):
        rows = parse_fo_bhavcopy_contract_rows(SAMPLE_FO_BHAVCOPY_CSV)
        assert [row.contract_type for row in rows] == [
            FoContractType.STOCK_OPTION,
            FoContractType.INDEX_OPTION,
            FoContractType.INDEX_FUTURE,
            FoContractType.STOCK_FUTURE,
        ]

    def test_stock_option_row_carries_strike_right_and_open_interest(self):
        stock_option_row = parse_fo_bhavcopy_contract_rows(SAMPLE_FO_BHAVCOPY_CSV)[0]
        assert stock_option_row.underlying_symbol == "ABCAPITAL"
        assert stock_option_row.strike_price == 350.0
        assert stock_option_row.option_right_code == "PE"
        assert stock_option_row.expiry_date == date(2026, 8, 25)
        assert stock_option_row.open_interest == 93000
        assert stock_option_row.change_in_open_interest == 18600

    def test_future_row_has_no_strike_or_option_right(self):
        future_rows = [
            row
            for row in parse_fo_bhavcopy_contract_rows(SAMPLE_FO_BHAVCOPY_CSV)
            if row.contract_type
            in (FoContractType.INDEX_FUTURE, FoContractType.STOCK_FUTURE)
        ]
        assert len(future_rows) == 2
        for future_row in future_rows:
            assert future_row.strike_price is None
            assert future_row.option_right_code is None
        banknifty_future_row = future_rows[0]
        assert banknifty_future_row.underlying_symbol == "BANKNIFTY"
        assert banknifty_future_row.open_interest == 619980


class TestFoBanListParser:
    def test_parses_trade_date_and_banned_symbols(self):
        ban_report = parse_fo_ban_list(SAMPLE_FO_BAN_LIST_CSV)
        assert ban_report.ban_trade_date == date(2026, 7, 23)
        assert ban_report.banned_underlying_symbols == ("KAYNES",)

    def test_unrecognizable_header_raises(self):
        with pytest.raises(ValueError):
            parse_fo_ban_list("<!DOCTYPE html><html>nope</html>")


class TestBulkBlockDealsParser:
    def test_parses_buy_and_sell_deals(self):
        deals = parse_bulk_or_block_deals(SAMPLE_BULK_DEALS_CSV)
        assert len(deals) == 2
        assert deals[0].symbol == "AASTHA"
        assert deals[0].is_buy is True
        assert deals[0].quantity_traded == 160009
        assert deals[0].weighted_average_price == 118.96
        assert deals[0].remarks is None  # "-" means no remark
        assert deals[1].is_buy is False

    def test_no_records_day_yields_empty_list(self):
        assert parse_bulk_or_block_deals(SAMPLE_BLOCK_DEALS_NO_RECORDS_CSV) == []


class TestMwplPositionLimitParser:
    def test_banned_stock_has_none_limit_and_ban_flag(self):
        rows = parse_mwpl_position_limits(SAMPLE_MWPL_POSITION_LIMIT_CSV)
        banned_row = rows[0]
        assert banned_row.underlying_symbol == "KAYNES"
        assert banned_row.next_day_fresh_position_limit is None
        assert banned_row.is_in_ban_period is True
        assert banned_row.mwpl_utilization_percent > 95.0

    def test_normal_stock_has_numeric_limit_and_utilization(self):
        rows = parse_mwpl_position_limits(SAMPLE_MWPL_POSITION_LIMIT_CSV)
        normal_row = rows[1]
        assert normal_row.underlying_symbol == "360ONE"
        assert normal_row.next_day_fresh_position_limit == 43193102
        assert normal_row.is_in_ban_period is False
        assert 0.0 < normal_row.mwpl_utilization_percent < 60.0
