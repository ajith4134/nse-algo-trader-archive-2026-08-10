"""ATM / ITM / OTM moneyness classification for any option strike.

First-class concept usable across the whole universe (index and all
~210 stock-option underlyings): ATM = the strike nearest spot within
half a strike-ladder step; otherwise ITM/OTM by the option right's
payoff side. The ladder step is derived from the actual chain, never
hardcoded, since it differs per underlying (NIFTY 50/100 pts, stocks
anything from 1 to 500+).
"""

from enum import Enum

from nse_algo_trader.universe_registry import OptionRight


class OptionMoneyness(str, Enum):
    AT_THE_MONEY = "ATM"
    IN_THE_MONEY = "ITM"
    OUT_OF_THE_MONEY = "OTM"


def infer_strike_ladder_step(sorted_unique_strikes: list[float]) -> float:
    """Smallest gap between adjacent strikes — the chain's ladder step."""
    if len(sorted_unique_strikes) < 2:
        raise ValueError("need at least two strikes to infer a ladder step")
    return min(
        later - earlier
        for earlier, later in zip(sorted_unique_strikes, sorted_unique_strikes[1:])
        if later > earlier
    )


def classify_option_moneyness(
    strike_price: float,
    spot_price: float,
    option_right: OptionRight,
    strike_ladder_step: float,
) -> OptionMoneyness:
    if abs(strike_price - spot_price) <= strike_ladder_step / 2.0:
        return OptionMoneyness.AT_THE_MONEY
    if option_right is OptionRight.CALL:
        return (
            OptionMoneyness.IN_THE_MONEY
            if strike_price < spot_price
            else OptionMoneyness.OUT_OF_THE_MONEY
        )
    return (
        OptionMoneyness.IN_THE_MONEY
        if strike_price > spot_price
        else OptionMoneyness.OUT_OF_THE_MONEY
    )
