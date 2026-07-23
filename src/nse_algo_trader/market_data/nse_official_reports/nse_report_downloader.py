"""Downloads NSE's public daily report files (verified live 2026-07-23).

Quirks this module exists to absorb (all observed against the real site):
- A browser-like User-Agent is required; the default python UA is blocked.
- NSE serves HTML error pages with HTTP 200 ("soft 404s") — every
  download validates content shape, never just the status code.
- Files propagate to `nsearchives.nseindia.com` with delay; the older
  `archives.nseindia.com` host sometimes has a file first, so dated
  downloads try both hosts in order.
- Zipped reports (F&O bhavcopy, MWPL) contain the CSV alongside other
  formats — the CSV member is selected by extension, not by position.
"""

import io
import time
import zipfile
from datetime import date

import requests

_PRIMARY_ARCHIVE_HOST = "https://nsearchives.nseindia.com"
_FALLBACK_ARCHIVE_HOST = "https://archives.nseindia.com"

_BROWSER_LIKE_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

_DOWNLOAD_ATTEMPTS_PER_URL = 3
_RETRY_BACKOFF_SECONDS = 2.0
_REQUEST_TIMEOUT_SECONDS = 30


class NseReportDownloadError(Exception):
    """Raised when a report is unavailable or came back malformed on every attempt."""


def build_cash_bhavcopy_with_delivery_url(trade_date: date, archive_host: str) -> str:
    return (
        f"{archive_host}/products/content/"
        f"sec_bhavdata_full_{trade_date.strftime('%d%m%Y')}.csv"
    )


def build_fo_bhavcopy_zip_url(trade_date: date, archive_host: str) -> str:
    return (
        f"{archive_host}/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{trade_date.strftime('%Y%m%d')}_F_0000.csv.zip"
    )


def build_mwpl_position_limit_zip_url(trade_date: date, archive_host: str) -> str:
    return (
        f"{archive_host}/archives/nsccl/mwpl/"
        f"combineoi_{trade_date.strftime('%d%m%Y')}.zip"
    )


def build_current_fo_ban_list_url(archive_host: str) -> str:
    return f"{archive_host}/content/fo/fo_secban.csv"


def build_current_bulk_deals_url(archive_host: str) -> str:
    return f"{archive_host}/content/equities/bulk.csv"


def build_current_block_deals_url(archive_host: str) -> str:
    return f"{archive_host}/content/equities/block.csv"


def _looks_like_html_error_page(response_body: bytes) -> bool:
    body_head = response_body[:200].lstrip().lower()
    return body_head.startswith((b"<!doctype", b"<html"))


class NseReportDownloader:
    """Fetches and unwraps each daily NSE report into plain CSV text.

    The HTTP session is injectable for tests; the default is a plain
    `requests.Session` with browser-like headers.
    """

    def __init__(self, http_session: requests.Session | None = None) -> None:
        self._http_session = http_session or requests.Session()
        self._http_session.headers.update(_BROWSER_LIKE_REQUEST_HEADERS)

    def download_cash_bhavcopy_with_delivery(self, trade_date: date) -> str:
        return self._download_first_available(
            [
                build_cash_bhavcopy_with_delivery_url(trade_date, host)
                for host in (_PRIMARY_ARCHIVE_HOST, _FALLBACK_ARCHIVE_HOST)
            ]
        ).decode()

    def download_fo_bhavcopy(self, trade_date: date) -> str:
        zip_bytes = self._download_first_available(
            [
                build_fo_bhavcopy_zip_url(trade_date, host)
                for host in (_PRIMARY_ARCHIVE_HOST, _FALLBACK_ARCHIVE_HOST)
            ]
        )
        return _extract_single_csv_from_zip(zip_bytes)

    def download_mwpl_position_limits(self, trade_date: date) -> str:
        zip_bytes = self._download_first_available(
            [
                build_mwpl_position_limit_zip_url(trade_date, host)
                for host in (_PRIMARY_ARCHIVE_HOST, _FALLBACK_ARCHIVE_HOST)
            ]
        )
        return _extract_single_csv_from_zip(zip_bytes)

    def download_current_fo_ban_list(self) -> str:
        return self._download_first_available(
            [build_current_fo_ban_list_url(_PRIMARY_ARCHIVE_HOST)]
        ).decode()

    def download_current_bulk_deals(self) -> str:
        return self._download_first_available(
            [build_current_bulk_deals_url(_PRIMARY_ARCHIVE_HOST)]
        ).decode()

    def download_current_block_deals(self) -> str:
        return self._download_first_available(
            [build_current_block_deals_url(_PRIMARY_ARCHIVE_HOST)]
        ).decode()

    def _download_first_available(self, candidate_urls: list[str]) -> bytes:
        failure_notes: list[str] = []
        for candidate_url in candidate_urls:
            for attempt_number in range(1, _DOWNLOAD_ATTEMPTS_PER_URL + 1):
                try:
                    response = self._http_session.get(
                        candidate_url, timeout=_REQUEST_TIMEOUT_SECONDS
                    )
                except requests.RequestException as request_error:
                    failure_notes.append(f"{candidate_url}: {request_error}")
                    time.sleep(_RETRY_BACKOFF_SECONDS * attempt_number)
                    continue
                if response.status_code == 200 and not _looks_like_html_error_page(
                    response.content
                ):
                    return response.content
                failure_notes.append(
                    f"{candidate_url}: HTTP {response.status_code}"
                    + (" (html error page)" if response.status_code == 200 else "")
                )
                break  # 404/soft-404 won't heal by retrying; try next host
        raise NseReportDownloadError(
            "NSE report unavailable on all hosts: " + "; ".join(failure_notes)
        )


def _extract_single_csv_from_zip(report_zip_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(report_zip_bytes)) as report_zip:
        csv_member_names = [
            name for name in report_zip.namelist() if name.lower().endswith(".csv")
        ]
        if len(csv_member_names) != 1:
            raise NseReportDownloadError(
                f"expected exactly one CSV inside report zip, found {csv_member_names}"
            )
        return report_zip.read(csv_member_names[0]).decode()
