"""Parser for NSE's daily Market Wide Position Limit (MWPL) file.

Source file: `combineoi_DDMMYYYY.zip` → `combineoi_DDMMYYYY.csv`
(nsearchives/archives.nseindia.com). One row per F&O underlying with its
MWPL, current aggregate open interest, and the position limit for the
next day — which is the literal string "No Fresh Positions" when the
stock is in the ban period. MWPL utilization % (OI/MWPL) is the input
for the 95% ban / 80% unban / 60% early-warning thresholds
(`docs/research/13` §3).
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class MwplPositionLimitRow:
    trade_date: date
    isin: str
    scrip_name: str
    underlying_symbol: str
    market_wide_position_limit: int
    aggregate_open_interest: int
    future_equivalent_open_interest: float
    next_day_fresh_position_limit: int | None  # None == "No Fresh Positions" (banned)

    @property
    def is_in_ban_period(self) -> bool:
        return self.next_day_fresh_position_limit is None

    @property
    def mwpl_utilization_percent(self) -> float:
        return 100.0 * self.aggregate_open_interest / self.market_wide_position_limit


def parse_mwpl_position_limits(
    combineoi_csv_text: str,
) -> list[MwplPositionLimitRow]:
    csv_reader = csv.DictReader(io.StringIO(combineoi_csv_text))
    csv_reader.fieldnames = [name.strip() for name in csv_reader.fieldnames]
    parsed_rows: list[MwplPositionLimitRow] = []
    for raw_row in csv_reader:
        stripped_row = {key: value.strip() for key, value in raw_row.items() if key}
        raw_next_day_limit = stripped_row["Limit for Next Day"]
        parsed_rows.append(
            MwplPositionLimitRow(
                trade_date=datetime.strptime(
                    stripped_row["Date"].upper(), "%d-%b-%Y"
                ).date(),
                isin=stripped_row["ISIN"],
                scrip_name=stripped_row["Scrip Name"],
                underlying_symbol=stripped_row["NSE Symbol"],
                market_wide_position_limit=int(stripped_row["MWPL"]),
                aggregate_open_interest=int(stripped_row["Open Interest"]),
                future_equivalent_open_interest=float(
                    stripped_row["Future Equivalent Open Interest"]
                ),
                next_day_fresh_position_limit=(
                    None
                    if raw_next_day_limit.lower() == "no fresh positions"
                    else int(raw_next_day_limit)
                ),
            )
        )
    return parsed_rows
