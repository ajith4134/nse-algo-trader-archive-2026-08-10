"""Parser for NSE's daily F&O security ban list.

Source file: `fo_secban.csv` (nsearchives.nseindia.com) — released daily
after ~6 PM for the *next* trade date. Format observed live 2026-07-23:

    Securities in Ban For Trade Date 23-JUL-2026:
    1,KAYNES

A symbol on this list has crossed 95% of its Market Wide Position Limit —
only position unwinding is allowed, no fresh F&O positions
(`docs/research/13` §3).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class FoBanListReport:
    ban_trade_date: date
    banned_underlying_symbols: tuple[str, ...]


_BAN_HEADER_DATE_PATTERN = re.compile(
    r"Trade\s+Date\s+(\d{2}-[A-Za-z]{3}-\d{4})", re.IGNORECASE
)


def parse_fo_ban_list(fo_secban_csv_text: str) -> FoBanListReport:
    header_date_match = _BAN_HEADER_DATE_PATTERN.search(fo_secban_csv_text)
    if header_date_match is None:
        raise ValueError(
            "fo_secban.csv header did not contain a recognizable trade date: "
            f"{fo_secban_csv_text[:120]!r}"
        )
    ban_trade_date = datetime.strptime(
        header_date_match.group(1).upper(), "%d-%b-%Y"
    ).date()

    banned_symbols: list[str] = []
    for line in fo_secban_csv_text.splitlines():
        serial_and_symbol = line.strip().split(",")
        if len(serial_and_symbol) == 2 and serial_and_symbol[0].isdigit():
            banned_symbols.append(serial_and_symbol[1].strip())
    return FoBanListReport(
        ban_trade_date=ban_trade_date,
        banned_underlying_symbols=tuple(banned_symbols),
    )
