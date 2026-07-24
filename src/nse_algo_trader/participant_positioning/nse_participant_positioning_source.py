"""The real production adapter: fetches NSE's archived participant-wise OI CSV.

Provenance: the download URL pattern is adapted from nsepython's
`get_fao_participant_oi` (github.com/aeron7/nsepython, MIT). What we changed
vs that reference (verified against live NSE bytes on 2026-07-24, see
docs/research/47): (1) it did a bare `pd.read_csv(url)` whose default urllib
User-Agent is now blocked by NSE's Akamai bot manager (503) — we send a real
browser UA, which is sufficient (no cookie/OTP handshake needed for the
archives host); (2) we treat HTTP 404 as "no report for this date"
(holiday / not yet published) and return None instead of raising; (3) we parse
into typed `ParticipantOpenInterestRow` records (not a DataFrame), mapping by
trimmed header name because several NSE headers carry trailing spaces; (4) we
assert the market-clearing checksum (TOTAL long == short) to catch a corrupt
or format-changed file early.

This is the ONLY module that talks to the network for this feature; everything
else depends on the pure `participant_positioning_source` seam.
"""

import csv
import io
import urllib.error
import urllib.request
from datetime import date

from nse_algo_trader.participant_positioning.participant_positioning_source import (
    ParticipantCategory,
    ParticipantOpenInterestRow,
    ParticipantPositioningSnapshot,
)

_NSE_PARTICIPANT_REPORT_URL = (
    "https://nsearchives.nseindia.com/content/nsccl/"
    "fao_participant_{kind}_{ddmmyyyy}.csv"
)  # kind: "oi" (open interest) | "vol" (trading volume) — identical schema
# A real browser UA is the whole anti-bot handshake for the archives host.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# The 14 numeric columns after `Client Type`, in NSE's exact header order.
_NUMERIC_COLUMN_ORDER = (
    "Future Index Long",
    "Future Index Short",
    "Future Stock Long",
    "Future Stock Short",
    "Option Index Call Long",
    "Option Index Put Long",
    "Option Index Call Short",
    "Option Index Put Short",
    "Option Stock Call Long",
    "Option Stock Put Long",
    "Option Stock Call Short",
    "Option Stock Put Short",
    "Total Long Contracts",
    "Total Short Contracts",
)


def _nse_archive_date_token(trade_date: date) -> str:
    return trade_date.strftime("%d%m%Y")


def _download_participant_csv_text(
    kind: str, trade_date: date, timeout_seconds: float
):
    """Return the raw CSV text for the OI ('oi') or volume ('vol') report, or
    None on HTTP 404 (no report that day)."""
    url = _NSE_PARTICIPANT_REPORT_URL.format(
        kind=kind, ddmmyyyy=_nse_archive_date_token(trade_date)
    )
    request = urllib.request.Request(url, headers={"User-Agent": _BROWSER_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as http_error:
        if http_error.code == 404:
            return None
        raise


def parse_participant_report_csv(
    csv_text: str, report_date: date
) -> ParticipantPositioningSnapshot:
    """Parse the real NSE participant CSV bytes (OI or volume — identical
    schema) into a typed snapshot.

    Layout (verified): row 1 is a single preamble line, row 2 is the header
    (some columns have trailing spaces), rows 3-7 are Client/DII/FII/Pro/TOTAL.
    Split out so the real bytes can be parsed in tests without a network call
    (Rule F real-sample verification)."""
    reader = csv.reader(io.StringIO(csv_text))
    all_rows = [row for row in reader if any(cell.strip() for cell in row)]
    # Drop the single preamble line; the next row is the header.
    header = [cell.strip() for cell in all_rows[1]]
    column_index = {name: position for position, name in enumerate(header)}
    for required in ("Client Type", *_NUMERIC_COLUMN_ORDER):
        if required not in column_index:
            raise ValueError(
                f"NSE participant header missing column {required!r}; "
                f"got {header!r} — file format may have changed."
            )

    def _cell(data_row, name):
        return int(data_row[column_index[name]].strip().replace(",", ""))

    rows_by_category: dict[str, ParticipantOpenInterestRow] = {}
    for data_row in all_rows[2:]:
        client_type = data_row[column_index["Client Type"]].strip()
        rows_by_category[client_type] = ParticipantOpenInterestRow(
            client_type=client_type,
            future_index_long=_cell(data_row, "Future Index Long"),
            future_index_short=_cell(data_row, "Future Index Short"),
            future_stock_long=_cell(data_row, "Future Stock Long"),
            future_stock_short=_cell(data_row, "Future Stock Short"),
            option_index_call_long=_cell(data_row, "Option Index Call Long"),
            option_index_put_long=_cell(data_row, "Option Index Put Long"),
            option_index_call_short=_cell(data_row, "Option Index Call Short"),
            option_index_put_short=_cell(data_row, "Option Index Put Short"),
            option_stock_call_long=_cell(data_row, "Option Stock Call Long"),
            option_stock_put_long=_cell(data_row, "Option Stock Put Long"),
            option_stock_call_short=_cell(data_row, "Option Stock Call Short"),
            option_stock_put_short=_cell(data_row, "Option Stock Put Short"),
            total_long_contracts=_cell(data_row, "Total Long Contracts"),
            total_short_contracts=_cell(data_row, "Total Short Contracts"),
        )

    total_row = rows_by_category.get(ParticipantCategory.TOTAL)
    if total_row is not None and (
        total_row.total_long_contracts != total_row.total_short_contracts
    ):
        raise ValueError(
            "NSE participant checksum failed: TOTAL long "
            f"{total_row.total_long_contracts} != short "
            f"{total_row.total_short_contracts} — corrupt or changed file."
        )
    return ParticipantPositioningSnapshot(report_date, rows_by_category)


class NseParticipantPositioningSource:
    """Production `ParticipantPositioningSource`: fetches and parses the NSE
    archived participant-wise open-interest ('oi') and trading-volume ('vol')
    reports for a date. Returns None on a holiday / not-yet-published date
    (HTTP 404)."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout_seconds = timeout_seconds

    def _fetch(self, kind: str, trade_date: date):
        csv_text = _download_participant_csv_text(
            kind, trade_date, self._timeout_seconds
        )
        if csv_text is None:
            return None
        return parse_participant_report_csv(csv_text, trade_date)

    def positioning_on(
        self, trade_date: date
    ) -> ParticipantPositioningSnapshot | None:
        return self._fetch("oi", trade_date)

    def volume_on(
        self, trade_date: date
    ) -> ParticipantPositioningSnapshot | None:
        return self._fetch("vol", trade_date)
