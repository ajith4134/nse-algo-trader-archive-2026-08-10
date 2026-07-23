"""Put-Call Ratio (open-interest based) for one underlying from F&O bhavcopy rows.

PCR-OI = total put OI / total call OI across all expiries of the
underlying's options. The classic contrarian reading (>~1.3 crowd-short
-> bullish-contrarian, <~0.7 -> bearish-contrarian) is Grade C evidence
(`docs/research/13` §6) — exposed as data, judged by strategies, never
auto-acted-on here.
"""

from dataclasses import dataclass
from datetime import date

from nse_algo_trader.market_data.nse_official_reports import (
    FoBhavcopyContractRow,
    FoContractType,
)

_OPTION_CONTRACT_TYPES = (FoContractType.INDEX_OPTION, FoContractType.STOCK_OPTION)


@dataclass(frozen=True)
class PutCallOpenInterestRatio:
    underlying_symbol: str
    trade_date: date
    total_put_open_interest: int
    total_call_open_interest: int

    @property
    def ratio(self) -> float | None:
        if self.total_call_open_interest == 0:
            return None
        return self.total_put_open_interest / self.total_call_open_interest


def compute_put_call_open_interest_ratio(
    fo_bhavcopy_contract_rows: list[FoBhavcopyContractRow],
    underlying_symbol: str,
) -> PutCallOpenInterestRatio | None:
    """None when the day has no option rows at all for the underlying."""
    option_rows = [
        row
        for row in fo_bhavcopy_contract_rows
        if row.underlying_symbol == underlying_symbol
        and row.contract_type in _OPTION_CONTRACT_TYPES
    ]
    if not option_rows:
        return None
    return PutCallOpenInterestRatio(
        underlying_symbol=underlying_symbol,
        trade_date=option_rows[0].trade_date,
        total_put_open_interest=sum(
            row.open_interest for row in option_rows if row.option_right_code == "PE"
        ),
        total_call_open_interest=sum(
            row.open_interest for row in option_rows if row.option_right_code == "CE"
        ),
    )
