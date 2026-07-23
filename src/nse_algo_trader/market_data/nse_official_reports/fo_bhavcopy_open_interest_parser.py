"""Parser for NSE's F&O UDiFF bhavcopy — the historical Open Interest source.

Source file: `BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip`
(nsearchives.nseindia.com). Kite Connect has no historical OI in candle
data (`docs/research/13`), so per-contract end-of-day OI and OI-change
come from this file. One row per derivative contract; instrument types:
IDO/STO (index/stock options — phase-1 scope), IDF/STF (futures — parsed
and tagged so MWPL/OI-buildup analysis can use them, but out of trading
scope).
"""

import csv
import io
from dataclasses import dataclass
from datetime import date
from enum import Enum


class FoContractType(str, Enum):
    INDEX_OPTION = "IDO"
    STOCK_OPTION = "STO"
    INDEX_FUTURE = "IDF"
    STOCK_FUTURE = "STF"


@dataclass(frozen=True)
class FoBhavcopyContractRow:
    trade_date: date
    contract_type: FoContractType
    nse_instrument_id: int
    underlying_symbol: str
    expiry_date: date
    strike_price: float | None
    option_right_code: str | None  # "CE" / "PE"; None for futures
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    settlement_price: float
    underlying_price: float
    open_interest: int
    change_in_open_interest: int
    total_traded_volume: int


def parse_fo_bhavcopy_contract_rows(
    fo_bhavcopy_csv_text: str,
) -> list[FoBhavcopyContractRow]:
    csv_reader = csv.DictReader(io.StringIO(fo_bhavcopy_csv_text))
    parsed_rows: list[FoBhavcopyContractRow] = []
    for raw_row in csv_reader:
        if not raw_row.get("TckrSymb"):
            continue  # the file interleaves blank spacer lines
        contract_type_code = raw_row["FinInstrmTp"]
        if contract_type_code not in FoContractType._value2member_map_:
            continue  # e.g. currency/other segments if ever present
        is_option_row = contract_type_code in (
            FoContractType.INDEX_OPTION.value,
            FoContractType.STOCK_OPTION.value,
        )
        parsed_rows.append(
            FoBhavcopyContractRow(
                trade_date=date.fromisoformat(raw_row["TradDt"]),
                contract_type=FoContractType(contract_type_code),
                nse_instrument_id=int(raw_row["FinInstrmId"]),
                underlying_symbol=raw_row["TckrSymb"],
                expiry_date=date.fromisoformat(raw_row["XpryDt"]),
                strike_price=float(raw_row["StrkPric"]) if is_option_row else None,
                option_right_code=raw_row["OptnTp"] if is_option_row else None,
                open_price=float(raw_row["OpnPric"]),
                high_price=float(raw_row["HghPric"]),
                low_price=float(raw_row["LwPric"]),
                close_price=float(raw_row["ClsPric"]),
                settlement_price=float(raw_row["SttlmPric"]),
                underlying_price=float(raw_row["UndrlygPric"]),
                open_interest=int(raw_row["OpnIntrst"]),
                change_in_open_interest=int(raw_row["ChngInOpnIntrst"]),
                total_traded_volume=int(raw_row["TtlTradgVol"]),
            )
        )
    return parsed_rows
