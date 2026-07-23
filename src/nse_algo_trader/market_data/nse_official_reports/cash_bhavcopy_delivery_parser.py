"""Parser for NSE's full cash bhavcopy with delivery data.

Source file: `sec_bhavdata_full_DDMMYYYY.csv` (nsearchives.nseindia.com).
This is the file that carries **delivery quantity / delivery %** — data
Kite Connect does not provide at all (`docs/research/13`). Values arrive
with leading spaces, and delivery fields are `-` for series that have no
delivery concept; those become None, not zero.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class CashBhavcopyDeliveryRow:
    symbol: str
    series: str
    trade_date: date
    prev_close: float
    open_price: float
    high_price: float
    low_price: float
    last_price: float
    close_price: float
    average_price: float
    total_traded_quantity: int
    turnover_lakhs: float
    trade_count: int
    delivered_quantity: int | None
    delivered_percent: float | None


def parse_cash_bhavcopy_with_delivery(
    cash_bhavcopy_csv_text: str,
) -> list[CashBhavcopyDeliveryRow]:
    csv_reader = csv.DictReader(io.StringIO(cash_bhavcopy_csv_text))
    csv_reader.fieldnames = [name.strip() for name in csv_reader.fieldnames]
    parsed_rows: list[CashBhavcopyDeliveryRow] = []
    for raw_row in csv_reader:
        stripped_row = {key: value.strip() for key, value in raw_row.items() if key}
        parsed_rows.append(
            CashBhavcopyDeliveryRow(
                symbol=stripped_row["SYMBOL"],
                series=stripped_row["SERIES"],
                trade_date=datetime.strptime(stripped_row["DATE1"], "%d-%b-%Y").date(),
                prev_close=float(stripped_row["PREV_CLOSE"]),
                open_price=float(stripped_row["OPEN_PRICE"]),
                high_price=float(stripped_row["HIGH_PRICE"]),
                low_price=float(stripped_row["LOW_PRICE"]),
                last_price=float(stripped_row["LAST_PRICE"]),
                close_price=float(stripped_row["CLOSE_PRICE"]),
                average_price=float(stripped_row["AVG_PRICE"]),
                total_traded_quantity=int(stripped_row["TTL_TRD_QNTY"]),
                turnover_lakhs=float(stripped_row["TURNOVER_LACS"]),
                trade_count=int(stripped_row["NO_OF_TRADES"]),
                delivered_quantity=(
                    None
                    if stripped_row["DELIV_QTY"] == "-"
                    else int(stripped_row["DELIV_QTY"])
                ),
                delivered_percent=(
                    None
                    if stripped_row["DELIV_PER"] == "-"
                    else float(stripped_row["DELIV_PER"])
                ),
            )
        )
    return parsed_rows
