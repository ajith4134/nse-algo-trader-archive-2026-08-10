"""Parser for NSE's daily bulk-deal and block-deal disclosure files.

Source files: `bulk.csv` / `block.csv` (nsearchives.nseindia.com),
current trade day only. Bulk deal = single client crossing ≥0.5% of
listed equity in a day; block deal = negotiated trade in the separate
block window (`docs/research/13` §2). Formats observed live 2026-07-23
are identical except `block.csv` omits the trailing `Remarks` column,
and an empty day is a single `NO RECORDS` row.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class BulkOrBlockDealRow:
    trade_date: date
    symbol: str
    security_name: str
    client_name: str
    is_buy: bool
    quantity_traded: int
    weighted_average_price: float
    remarks: str | None


def parse_bulk_or_block_deals(
    deals_csv_text: str,
) -> list[BulkOrBlockDealRow]:
    csv_reader = csv.DictReader(io.StringIO(deals_csv_text))
    parsed_rows: list[BulkOrBlockDealRow] = []
    for raw_row in csv_reader:
        if raw_row["Date"].strip().upper() == "NO RECORDS":
            continue
        remarks_value = (raw_row.get("Remarks") or "").strip()
        parsed_rows.append(
            BulkOrBlockDealRow(
                trade_date=datetime.strptime(
                    raw_row["Date"].strip().upper(), "%d-%b-%Y"
                ).date(),
                symbol=raw_row["Symbol"].strip(),
                security_name=raw_row["Security Name"].strip(),
                client_name=raw_row["Client Name"].strip(),
                is_buy=raw_row["Buy/Sell"].strip().upper() == "BUY",
                quantity_traded=int(raw_row["Quantity Traded"].replace(",", "")),
                weighted_average_price=float(
                    raw_row["Trade Price / Wght. Avg. Price"].replace(",", "")
                ),
                remarks=remarks_value if remarks_value not in ("", "-") else None,
            )
        )
    return parsed_rows
