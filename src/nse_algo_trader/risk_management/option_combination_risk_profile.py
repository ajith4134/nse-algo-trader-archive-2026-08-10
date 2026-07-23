"""Structural risk analysis of any option leg combination.

Answers, from payoff structure alone (premiums deliberately excluded —
conservative): can this combination lose without bound, does it contain
a short leg with no protective long pairing, and what is the worst-case
structural loss. Works for any legs on any underlying — spreads,
condors, strangles, ratio spreads (`docs/research/07` §D.3).
"""

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.strategy_engine import OptionLegAction, OptionLegIntent
from nse_algo_trader.universe_registry import OptionRight


class PositionRiskCategory(str, Enum):
    DEFINED_RISK = "defined_risk"
    UNDEFINED_RISK = "undefined_risk"


@dataclass(frozen=True)
class OptionCombinationRiskProfile:
    category: PositionRiskCategory
    worst_case_structural_loss: float | None  # None == unlimited (net short calls)
    has_unlimited_upside_loss: bool  # net short calls: loss grows with spot forever
    has_unpaired_short_leg: bool  # any SELL not covered by an equal-or-more long
    # quantity on the same right & expiry (v1's "never naked" trigger)


def _leg_signed_share_quantity(leg: OptionLegIntent) -> int:
    share_quantity = leg.lots * leg.instrument.lot_size
    return share_quantity if leg.action is OptionLegAction.BUY else -share_quantity


def _expiry_payoff_at_spot(legs: list[OptionLegIntent], spot_at_expiry: float) -> float:
    payoff = 0.0
    for leg in legs:
        if leg.instrument.option_right is OptionRight.CALL:
            intrinsic = max(spot_at_expiry - leg.instrument.strike_price, 0.0)
        else:
            intrinsic = max(leg.instrument.strike_price - spot_at_expiry, 0.0)
        payoff += _leg_signed_share_quantity(leg) * intrinsic
    return payoff


def _combination_has_unpaired_short_leg(legs: list[OptionLegIntent]) -> bool:
    """True when, within any (right, expiry) group, sold quantity exceeds
    bought quantity — some short exposure has no long leg pairing at all."""
    net_quantity_by_right_and_expiry: dict[tuple, int] = {}
    for leg in legs:
        group_key = (leg.instrument.option_right, leg.instrument.expiry_date)
        net_quantity_by_right_and_expiry[group_key] = (
            net_quantity_by_right_and_expiry.get(group_key, 0)
            + _leg_signed_share_quantity(leg)
        )
    return any(net < 0 for net in net_quantity_by_right_and_expiry.values())


def assess_option_combination_risk(
    legs: list[OptionLegIntent],
) -> OptionCombinationRiskProfile:
    if not legs:
        raise ValueError("cannot assess an empty leg combination")

    net_call_share_quantity = sum(
        _leg_signed_share_quantity(leg)
        for leg in legs
        if leg.instrument.option_right is OptionRight.CALL
    )
    has_unlimited_upside_loss = net_call_share_quantity < 0
    has_unpaired_short_leg = _combination_has_unpaired_short_leg(legs)

    if has_unlimited_upside_loss:
        worst_case_structural_loss = None
    else:
        # Payoff at expiry is piecewise linear: extremes occur at spot=0,
        # at each strike, and beyond the highest strike (slope checked above).
        candidate_expiry_spots = {0.0}
        candidate_expiry_spots.update(leg.instrument.strike_price for leg in legs)
        candidate_expiry_spots.add(
            2.0 * max(leg.instrument.strike_price for leg in legs)
        )
        worst_case_structural_loss = max(
            0.0,
            -min(
                _expiry_payoff_at_spot(legs, spot) for spot in candidate_expiry_spots
            ),
        )

    return OptionCombinationRiskProfile(
        category=(
            PositionRiskCategory.UNDEFINED_RISK
            if has_unlimited_upside_loss or has_unpaired_short_leg
            else PositionRiskCategory.DEFINED_RISK
        ),
        worst_case_structural_loss=worst_case_structural_loss,
        has_unlimited_upside_loss=has_unlimited_upside_loss,
        has_unpaired_short_leg=has_unpaired_short_leg,
    )
