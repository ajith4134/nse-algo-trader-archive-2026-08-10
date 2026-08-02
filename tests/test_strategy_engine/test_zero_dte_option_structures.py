"""B32: the 0-DTE structure builders emit correct defined-risk legs and abstain on missing data."""

from nse_algo_trader.strategy_engine.strategy_signal_types import (
    OptionLegAction,
    SignalDirection,
)
from nse_algo_trader.strategy_engine.zero_dte_option_structures import (
    build_directional_long_option,
    build_long_straddle,
    build_short_premium_iron_fly,
)
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)
from datetime import date

LOT = 50


def _opt(token: int, strike: float, right: OptionRight) -> Instrument:
    return Instrument(
        instrument_token=token,
        trading_symbol=f"NIFTY{int(strike)}{right.value}",
        exchange_segment=ExchangeSegment.NSE_FO,
        kind=InstrumentKind.INDEX_OPTION,
        lot_size=LOT,
        tick_size=0.05,
        underlying_symbol="NIFTY",
        strike_price=strike,
        option_right=right,
        expiry_date=date(2026, 7, 28),
    )


def _ladder() -> list[Instrument]:
    strikes = [19800, 19900, 20000, 20100, 20200]
    ladder = []
    t = 1
    for k in strikes:
        ladder.append(_opt(t, k, OptionRight.CALL)); t += 1
        ladder.append(_opt(t, k, OptionRight.PUT)); t += 1
    return ladder


def _premia(ladder, value=100.0) -> dict[int, float]:
    # give wings lower premium than ATM so the fly earns a credit
    prem = {}
    for o in ladder:
        distance = abs(o.strike_price - 20000) / 100
        prem[o.instrument_token] = max(value - distance * 30, 5.0)
    return prem


def test_directional_long_buys_atm_call_for_long():
    ladder = _ladder()
    r = build_directional_long_option(ladder, 20000.0, SignalDirection.LONG, _premia(ladder))
    assert r.abstain_reason is None
    assert len(r.legs) == 1
    leg = r.legs[0]
    assert leg.action is OptionLegAction.BUY
    assert leg.instrument.option_right is OptionRight.CALL
    assert leg.instrument.strike_price == 20000
    assert r.defined_risk_per_lot == 100.0 * LOT  # ATM premium × lot


def test_directional_long_buys_put_for_short():
    ladder = _ladder()
    r = build_directional_long_option(ladder, 20000.0, SignalDirection.SHORT, _premia(ladder))
    assert r.legs[0].instrument.option_right is OptionRight.PUT


def test_straddle_buys_both_atm_legs():
    ladder = _ladder()
    r = build_long_straddle(ladder, 20000.0, _premia(ladder))
    assert r.abstain_reason is None
    assert {leg.instrument.option_right for leg in r.legs} == {OptionRight.CALL, OptionRight.PUT}
    assert all(leg.action is OptionLegAction.BUY for leg in r.legs)
    assert r.defined_risk_per_lot == (100.0 + 100.0) * LOT


def test_iron_fly_sells_atm_buys_wings_and_is_defined_risk():
    ladder = _ladder()
    r = build_short_premium_iron_fly(ladder, 20000.0, _premia(ladder), wing_steps=2)
    assert r.abstain_reason is None
    actions = {(leg.instrument.option_right, leg.action) for leg in r.legs}
    assert (OptionRight.CALL, OptionLegAction.SELL) in actions
    assert (OptionRight.PUT, OptionLegAction.SELL) in actions
    assert (OptionRight.CALL, OptionLegAction.BUY) in actions
    assert (OptionRight.PUT, OptionLegAction.BUY) in actions
    # wing width 200, ATM credit 200 gross − wings; risk is bounded and non-negative
    assert r.defined_risk_per_lot >= 0.0


def test_iron_fly_abstains_when_no_wing_available():
    ladder = _ladder()
    r = build_short_premium_iron_fly(ladder, 20000.0, _premia(ladder), wing_steps=9)
    assert r.abstain_reason is not None


def test_directional_abstains_on_missing_premium():
    ladder = _ladder()
    r = build_directional_long_option(ladder, 20000.0, SignalDirection.LONG, {})
    assert r.abstain_reason is not None
