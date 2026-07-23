import io
import zipfile
from datetime import date

import pytest

from nse_algo_trader.market_data.nse_official_reports import (
    NseReportDownloader,
    NseReportDownloadError,
)
from nse_algo_trader.market_data.nse_official_reports.nse_report_downloader import (
    build_cash_bhavcopy_with_delivery_url,
    build_fo_bhavcopy_zip_url,
    build_mwpl_position_limit_zip_url,
)
from tests.fixtures.sample_nse_official_report_texts import (
    SAMPLE_FO_BAN_LIST_CSV,
    SAMPLE_NSE_HTML_ERROR_PAGE,
)

SAMPLE_TRADE_DATE = date(2026, 7, 22)


class FakeHttpResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content


class FakeHttpSessionServingCannedResponses:
    """Stands in for requests.Session; serves a canned response per URL."""

    def __init__(self, canned_responses_by_url: dict):
        self.canned_responses_by_url = canned_responses_by_url
        self.headers = {}
        self.requested_urls = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        return self.canned_responses_by_url.get(
            url, FakeHttpResponse(404, b"<!DOCTYPE html>not found")
        )


def _zip_bytes_containing_csv(csv_member_name: str, csv_text: str) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_writer:
        zip_writer.writestr(csv_member_name, csv_text)
        zip_writer.writestr(csv_member_name.replace(".csv", ".xml"), "<xml/>")
    return zip_buffer.getvalue()


def test_dated_urls_embed_date_in_each_reports_own_format():
    assert build_cash_bhavcopy_with_delivery_url(
        SAMPLE_TRADE_DATE, "https://nsearchives.nseindia.com"
    ).endswith("sec_bhavdata_full_22072026.csv")
    assert build_fo_bhavcopy_zip_url(
        SAMPLE_TRADE_DATE, "https://nsearchives.nseindia.com"
    ).endswith("BhavCopy_NSE_FO_0_0_0_20260722_F_0000.csv.zip")
    assert build_mwpl_position_limit_zip_url(
        SAMPLE_TRADE_DATE, "https://nsearchives.nseindia.com"
    ).endswith("combineoi_22072026.zip")


def test_ban_list_download_returns_csv_text():
    ban_list_url = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"
    fake_session = FakeHttpSessionServingCannedResponses(
        {ban_list_url: FakeHttpResponse(200, SAMPLE_FO_BAN_LIST_CSV.encode())}
    )
    downloaded_text = NseReportDownloader(fake_session).download_current_fo_ban_list()
    assert downloaded_text == SAMPLE_FO_BAN_LIST_CSV


def test_soft_404_html_on_primary_host_falls_back_to_archives_host():
    primary_url = build_mwpl_position_limit_zip_url(
        SAMPLE_TRADE_DATE, "https://nsearchives.nseindia.com"
    )
    fallback_url = build_mwpl_position_limit_zip_url(
        SAMPLE_TRADE_DATE, "https://archives.nseindia.com"
    )
    fake_session = FakeHttpSessionServingCannedResponses(
        {
            primary_url: FakeHttpResponse(200, SAMPLE_NSE_HTML_ERROR_PAGE.encode()),
            fallback_url: FakeHttpResponse(
                200, _zip_bytes_containing_csv("combineoi_22072026.csv", "Date, ISIN\n")
            ),
        }
    )
    downloaded_text = NseReportDownloader(fake_session).download_mwpl_position_limits(
        SAMPLE_TRADE_DATE
    )
    assert downloaded_text == "Date, ISIN\n"
    assert fake_session.requested_urls == [primary_url, fallback_url]


def test_zip_download_extracts_only_the_csv_member():
    fo_bhavcopy_url = build_fo_bhavcopy_zip_url(
        SAMPLE_TRADE_DATE, "https://nsearchives.nseindia.com"
    )
    fake_session = FakeHttpSessionServingCannedResponses(
        {
            fo_bhavcopy_url: FakeHttpResponse(
                200,
                _zip_bytes_containing_csv(
                    "BhavCopy_NSE_FO_0_0_0_20260722_F_0000.csv", "TradDt,BizDt\n"
                ),
            )
        }
    )
    downloaded_text = NseReportDownloader(fake_session).download_fo_bhavcopy(
        SAMPLE_TRADE_DATE
    )
    assert downloaded_text == "TradDt,BizDt\n"


def test_report_missing_everywhere_raises_download_error():
    fake_session = FakeHttpSessionServingCannedResponses({})
    with pytest.raises(NseReportDownloadError):
        NseReportDownloader(fake_session).download_fo_bhavcopy(SAMPLE_TRADE_DATE)
