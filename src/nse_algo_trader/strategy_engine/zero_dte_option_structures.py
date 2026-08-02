"""B32 · 0-DTE defined-risk structure builders — turn a router choice into concrete option legs.

Given one underlying's near-expiry option ladder + live premia, each builder returns the legs for its
structure plus the DEFINED max loss per lot (docs/research/174 §2). Every structure is defined-risk —
long premium (loss = premium paid) or a spread (loss = wing width − net credit). A short leg is NEVER
naked: the short-premium structure is an iron fly with bought protective wings, so a 0-DTE fast move
can never produce an unbounded loss.

Builders ABSTAIN (Rule O.3/Q — a reason, never a silent skip or a guessed leg) when a required strike
or its premium is missing, or when a "credit" structure would actually pay no credit.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.strategy_engine.strategy_signal_types import (
    OptionLegAction,
    OptionLegIntent,
)
from nse_algo_trader.strategy_engine.zero_dte_regime_router import ZeroDteStructure
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.universe_registry.instrument_types import Instrument, OptionRight


@dataclass(frozen=True)
class ZeroDteStructureLegs:
    """The concrete legs for a chosen 0-DTE structure, or an abstention with a reason."""

    structure: ZeroDteStructure
    legs: tuple[OptionLegIntent, ...]
    #: worst-case loss for ONE lot of the whole structure, in rupees (always ≥ 0).
    defined_risk_per_lot: float
    abstain_reason: str | None = None


def _abstain(structure: ZeroDteStructure, reason: str) -> ZeroDteStructureLegs:
    return ZeroDteStructureLegs(structure=structure, legs=(), defined_risk_per_lot=0.0,
                                abstain_reason=reason)


def _atm_option(ladder: list[Instrument], spot: float, right: OptionRight) -> Instrument | None:
    candidates = [o for o in ladder if o.option_right is right and o.strike_price is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda o: abs(o.strike_price - spot))  # type: ignore[operator]


def _wing_option(
    ladder: list[Instrument], right: OptionRight, atm_strike: float, wing_steps: int, going_up: bool
) -> Instrument | None:
    """The `wing_steps`-th listed strike OTM from ATM on the given side (up for calls, down for puts)."""
    side = [
        o for o in ladder
        if o.option_right is right and o.strike_price is not None
        and ((o.strike_price > atm_strike) if going_up else (o.strike_price < atm_strike))
    ]
    if len(side) < wing_steps:
        return None
    side.sort(key=lambda o: o.strike_price, reverse=not going_up)  # type: ignore[arg-type,return-value]
    return side[wing_steps - 1]


def build_directional_long_option(
    ladder: list[Instrument], spot: float, direction: SignalDirection,
    premium_by_token: dict[int, float], lots: int = 1,
) -> ZeroDteStructureLegs:
    """S1: BUY one ATM CE (LONG) or PE (SHORT). Defined risk = premium paid."""
    structure = ZeroDteStructure.DIRECTIONAL_LONG_OPTION
    right = OptionRight.CALL if direction is SignalDirection.LONG else OptionRight.PUT
    atm = _atm_option(ladder, spot, right)
    if atm is None:
        return _abstain(structure, f"no ATM {right.value} in the ladder")
    premium = premium_by_token.get(atm.instrument_token)
    if premium is None or premium <= 0.0:
        return _abstain(structure, f"no usable premium for {atm.trading_symbol}")
    return ZeroDteStructureLegs(
        structure=structure,
        legs=(OptionLegIntent(atm, OptionLegAction.BUY, lots),),
        defined_risk_per_lot=premium * atm.lot_size,
    )


def build_long_straddle(
    ladder: list[Instrument], spot: float,
    premium_by_token: dict[int, float], lots: int = 1,
) -> ZeroDteStructureLegs:
    """S2: BUY ATM CE + ATM PE. Defined risk = both premiums paid."""
    structure = ZeroDteStructure.LONG_STRADDLE
    call = _atm_option(ladder, spot, OptionRight.CALL)
    put = _atm_option(ladder, spot, OptionRight.PUT)
    if call is None or put is None:
        return _abstain(structure, "missing ATM call or put")
    call_premium = premium_by_token.get(call.instrument_token)
    put_premium = premium_by_token.get(put.instrument_token)
    if not call_premium or not put_premium or call_premium <= 0 or put_premium <= 0:
        return _abstain(structure, "missing usable premium on a straddle leg")
    return ZeroDteStructureLegs(
        structure=structure,
        legs=(
            OptionLegIntent(call, OptionLegAction.BUY, lots),
            OptionLegIntent(put, OptionLegAction.BUY, lots),
        ),
        defined_risk_per_lot=(call_premium + put_premium) * call.lot_size,
    )


def build_short_premium_iron_fly(
    ladder: list[Instrument], spot: float,
    premium_by_token: dict[int, float], wing_steps: int = 2, lots: int = 1,
) -> ZeroDteStructureLegs:
    """S3: SELL ATM CE + ATM PE, BUY protective wings `wing_steps` OTM each side (iron fly).
    Defined risk = wing width − net credit. Abstains if it would pay no credit (not a credit trade)."""
    structure = ZeroDteStructure.SHORT_PREMIUM_SPREAD
    short_call = _atm_option(ladder, spot, OptionRight.CALL)
    short_put = _atm_option(ladder, spot, OptionRight.PUT)
    if short_call is None or short_put is None:
        return _abstain(structure, "missing ATM call or put for the short legs")
    atm_strike = short_call.strike_price
    if atm_strike is None:
        return _abstain(structure, "ATM short call has no strike")  # invariant; defensive
    long_call = _wing_option(ladder, OptionRight.CALL, atm_strike, wing_steps, going_up=True)
    long_put = _wing_option(ladder, OptionRight.PUT, atm_strike, wing_steps, going_up=False)
    if long_call is None or long_put is None:
        return _abstain(structure, f"no {wing_steps}-step protective wing available")
    long_call_strike = long_call.strike_price
    long_put_strike = long_put.strike_price
    if long_call_strike is None or long_put_strike is None:
        return _abstain(structure, "a wing option has no strike")  # invariant; defensive

    short_call_premium = premium_by_token.get(short_call.instrument_token)
    short_put_premium = premium_by_token.get(short_put.instrument_token)
    long_call_premium = premium_by_token.get(long_call.instrument_token)
    long_put_premium = premium_by_token.get(long_put.instrument_token)
    if any(p is None or p <= 0.0 for p in
           (short_call_premium, short_put_premium, long_call_premium, long_put_premium)):
        return _abstain(structure, "missing usable premium on an iron-fly leg")

    net_credit_per_share = (
        short_call_premium + short_put_premium  # type: ignore[operator]
        - long_call_premium - long_put_premium
    )
    if net_credit_per_share <= 0.0:
        return _abstain(structure, "iron fly would pay no net credit — not a credit structure")

    # Symmetric fly: the worst case is a move to either wing. Loss on a side = (wing distance) − credit.
    call_wing_width = long_call_strike - atm_strike
    put_wing_width = atm_strike - long_put_strike
    worst_wing_width = max(call_wing_width, put_wing_width)
    defined_risk_per_share = max(worst_wing_width - net_credit_per_share, 0.0)
    return ZeroDteStructureLegs(
        structure=structure,
        legs=(
            OptionLegIntent(short_call, OptionLegAction.SELL, lots),
            OptionLegIntent(short_put, OptionLegAction.SELL, lots),
            OptionLegIntent(long_call, OptionLegAction.BUY, lots),
            OptionLegIntent(long_put, OptionLegAction.BUY, lots),
        ),
        defined_risk_per_lot=defined_risk_per_share * short_call.lot_size,
    )
