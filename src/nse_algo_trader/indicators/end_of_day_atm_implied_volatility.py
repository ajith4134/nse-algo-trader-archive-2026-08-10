"""End-of-day ATM implied volatility for one underlying from F&O bhavcopy rows.

Selection: nearest expiry strictly after the trade date, strike nearest
the underlying's spot, IV inverted from CE and PE settlement prices
(settlement is populated even for untraded strikes, unlike close) and
averaged. This is the daily point that accumulates into the IV history
`compute_implied_volatility_rank` consumes.
"""

from dataclasses import dataclass
from datetime import date

from nse_algo_trader.indicators.black_scholes_implied_volatility import (
    DEFAULT_RISK_FREE_INTEREST_RATE,
    OptionRightForPricing,
    compute_implied_volatility,
)
from nse_algo_trader.market_data.nse_official_reports import (
    FoBhavcopyContractRow,
    FoContractType,
)

_OPTION_CONTRACT_TYPES = (FoContractType.INDEX_OPTION, FoContractType.STOCK_OPTION)

_CALENDAR_DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class AtmImpliedVolatilitySnapshot:
    underlying_symbol: str
    trade_date: date
    expiry_date: date
    atm_strike_price: float
    underlying_price: float
    call_implied_volatility: float | None
    put_implied_volatility: float | None

    @property
    def atm_implied_volatility(self) -> float | None:
        recovered_ivs = [
            iv
            for iv in (self.call_implied_volatility, self.put_implied_volatility)
            if iv is not None
        ]
        if not recovered_ivs:
            return None
        return sum(recovered_ivs) / len(recovered_ivs)


def compute_end_of_day_atm_implied_volatility(
    fo_bhavcopy_contract_rows: list[FoBhavcopyContractRow],
    underlying_symbol: str,
    risk_free_rate: float = DEFAULT_RISK_FREE_INTEREST_RATE,
) -> AtmImpliedVolatilitySnapshot | None:
    """None when the day has no usable option rows for the underlying."""
    option_rows = [
        row
        for row in fo_bhavcopy_contract_rows
        if row.underlying_symbol == underlying_symbol
        and row.contract_type in _OPTION_CONTRACT_TYPES
        and row.expiry_date > row.trade_date
    ]
    if not option_rows:
        return None

    nearest_expiry = min(row.expiry_date for row in option_rows)
    nearest_expiry_rows = [
        row for row in option_rows if row.expiry_date == nearest_expiry
    ]
    underlying_price = nearest_expiry_rows[0].underlying_price
    atm_strike = min(
        {row.strike_price for row in nearest_expiry_rows},
        key=lambda strike: abs(strike - underlying_price),
    )
    trade_date = nearest_expiry_rows[0].trade_date
    time_to_expiry_years = (nearest_expiry - trade_date).days / _CALENDAR_DAYS_PER_YEAR

    def _invert_iv_for_right(option_right_code: str) -> float | None:
        matching_rows = [
            row
            for row in nearest_expiry_rows
            if row.strike_price == atm_strike
            and row.option_right_code == option_right_code
        ]
        if not matching_rows:
            return None
        return compute_implied_volatility(
            observed_option_price=matching_rows[0].settlement_price,
            underlying_price=underlying_price,
            strike_price=atm_strike,
            time_to_expiry_years=time_to_expiry_years,
            option_right=OptionRightForPricing(option_right_code),
            risk_free_rate=risk_free_rate,
        )

    return AtmImpliedVolatilitySnapshot(
        underlying_symbol=underlying_symbol,
        trade_date=trade_date,
        expiry_date=nearest_expiry,
        atm_strike_price=atm_strike,
        underlying_price=underlying_price,
        call_implied_volatility=_invert_iv_for_right("CE"),
        put_implied_volatility=_invert_iv_for_right("PE"),
    )
