"""Selects the two concrete option legs of a v1 credit spread.

Bull put (bullish bias): SELL an OTM put near the target delta, BUY a
put `width` strike-steps further OTM. Bear call mirrors with calls.
Strike selection is delta-based using Black-Scholes with the day's ATM
IV as the volatility estimate for every strike — a deliberate v1
simplification (no skew model yet; documented limitation).
"""

from dataclasses import dataclass
from datetime import date

from nse_algo_trader.indicators import (
    OptionRightForPricing,
    compute_black_scholes_delta,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    CreditSpreadBias,
    CreditSpreadSignal,
    OptionLegAction,
    OptionLegIntent,
)
from nse_algo_trader.universe_registry import Instrument, InstrumentKind, OptionRight

_CALENDAR_DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class CreditSpreadSelectionConfig:
    short_leg_delta_target: float = 0.25  # absolute delta of the sold option
    hedge_width_strike_steps: int = 2  # how many ladder steps further OTM
    minimum_calendar_days_to_expiry: int = 1  # never open on expiry day itself
    lots: int = 1


def select_credit_spread_legs(
    option_instruments: list[Instrument],
    underlying_symbol: str,
    spot_price: float,
    atm_implied_volatility: float,
    bias: CreditSpreadBias,
    trade_date: date,
    config: CreditSpreadSelectionConfig = CreditSpreadSelectionConfig(),
) -> CreditSpreadSignal | None:
    """None when no expiry/strike ladder can satisfy the config."""
    required_right = (
        OptionRight.PUT
        if bias is CreditSpreadBias.BULLISH_SELL_PUT_SPREAD
        else OptionRight.CALL
    )
    candidate_options = [
        instrument
        for instrument in option_instruments
        if instrument.underlying_symbol == underlying_symbol
        and instrument.kind
        in (InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION)
        and instrument.option_right is required_right
        and instrument.expiry_date is not None
        and (instrument.expiry_date - trade_date).days
        >= config.minimum_calendar_days_to_expiry
    ]
    if not candidate_options:
        return None

    nearest_expiry = min(instrument.expiry_date for instrument in candidate_options)
    expiry_ladder = [
        instrument
        for instrument in candidate_options
        if instrument.expiry_date == nearest_expiry
    ]
    time_to_expiry_years = (nearest_expiry - trade_date).days / _CALENDAR_DAYS_PER_YEAR

    # Out-of-the-money strikes only: puts below spot, calls above.
    if required_right is OptionRight.PUT:
        otm_ladder = [i for i in expiry_ladder if i.strike_price < spot_price]
        otm_ladder.sort(key=lambda i: i.strike_price, reverse=True)  # OTM-ward
        pricing_right = OptionRightForPricing.PUT
    else:
        otm_ladder = [i for i in expiry_ladder if i.strike_price > spot_price]
        otm_ladder.sort(key=lambda i: i.strike_price)  # OTM-ward
        pricing_right = OptionRightForPricing.CALL
    if not otm_ladder:
        return None

    def _absolute_delta_of(instrument: Instrument) -> float:
        return abs(
            compute_black_scholes_delta(
                spot_price,
                instrument.strike_price,
                time_to_expiry_years,
                atm_implied_volatility,
                pricing_right,
            )
        )

    short_leg_position_in_ladder = min(
        range(len(otm_ladder)),
        key=lambda ladder_index: abs(
            _absolute_delta_of(otm_ladder[ladder_index]) - config.short_leg_delta_target
        ),
    )
    hedge_leg_position_in_ladder = (
        short_leg_position_in_ladder + config.hedge_width_strike_steps
    )
    if hedge_leg_position_in_ladder >= len(otm_ladder):
        return None  # ladder too short for the hedge width — never sell naked

    short_instrument = otm_ladder[short_leg_position_in_ladder]
    return CreditSpreadSignal(
        underlying_symbol=underlying_symbol,
        bias=bias,
        short_leg=OptionLegIntent(
            short_instrument, OptionLegAction.SELL, config.lots
        ),
        hedge_leg=OptionLegIntent(
            otm_ladder[hedge_leg_position_in_ladder], OptionLegAction.BUY, config.lots
        ),
        short_leg_estimated_delta=_absolute_delta_of(short_instrument),
    )
