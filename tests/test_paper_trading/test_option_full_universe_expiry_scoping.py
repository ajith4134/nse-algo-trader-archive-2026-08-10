"""B34 — the option arms must stay same-expiry-correct on the FULL option universe.

The tradable universe now carries every strike × every expiry (`select_full_option_universe`).
Before B34 the arms received only a near-expiry ATM±3 ladder, so an ATM pick over the raw
per-underlying list was safe. With the full mixed-expiry universe, an unscoped `min(..., key=abs(
strike-spot))` could return an arbitrary-expiry contract (a hidden calendar mix). These pin that the
expiry-scoping helper collapses each underlying to its OWN nearest expiry before any ATM/IV pick.
"""

from datetime import date, datetime

from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
    _atm_call_implied_volatility,
    _nearest_expiry_options_for_underlying,
)
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

NEAR = date(2026, 8, 4)
FAR = date(2026, 8, 25)


def _opt(underlying, strike, right, expiry, token):
    return Instrument(
        instrument_token=token,
        trading_symbol=f"{underlying}{strike}{right.value}{expiry:%d%b}",
        exchange_segment=ExchangeSegment.NSE_FO,
        kind=InstrumentKind.INDEX_OPTION,
        lot_size=75,
        tick_size=0.05,
        underlying_symbol=underlying,
        strike_price=float(strike),
        option_right=right,
        expiry_date=expiry,
    )


def _full_two_expiry_chain():
    chain = []
    token = 1
    for expiry in (FAR, NEAR):  # deliberately FAR first so ordering can't hide a bug
        for strike in (23400, 23500, 23600, 23700, 23800):
            for right in (OptionRight.CALL, OptionRight.PUT):
                chain.append(_opt("NIFTY", strike, right, expiry, token))
                token += 1
    return chain


def test_nearest_expiry_helper_collapses_to_own_soonest_expiry():
    chain = _full_two_expiry_chain()
    scoped = _nearest_expiry_options_for_underlying(chain, "NIFTY")
    assert scoped, "expected the nearest-expiry slice to be non-empty"
    assert {o.expiry_date for o in scoped} == {NEAR}  # FAR dropped
    assert len(scoped) == 10  # 5 strikes × 2 rights, one expiry


def test_nearest_expiry_helper_is_per_underlying_independent():
    chain = _full_two_expiry_chain()
    # RELIANCE lists ONLY the far expiry -> its own nearest is FAR, not NIFTY's NEAR.
    chain += [_opt("RELIANCE", 1250, OptionRight.CALL, FAR, 9001)]
    assert {o.expiry_date for o in _nearest_expiry_options_for_underlying(chain, "NIFTY")} == {NEAR}
    assert {o.expiry_date for o in _nearest_expiry_options_for_underlying(chain, "RELIANCE")} == {FAR}


def test_atm_iv_reads_off_the_nearest_expiry_not_a_far_contract():
    chain = _full_two_expiry_chain()
    spot = 23590.0  # ATM strike = 23600
    # Price ONLY the near-expiry contracts. If the ATM pick leaked to a far-expiry contract, its
    # token would be absent from price_by_token and IV would come back None.
    near = _nearest_expiry_options_for_underlying(chain, "NIFTY")
    price_by_token = {o.instrument_token: 120.0 for o in near}
    iv = _atm_call_implied_volatility(chain, "NIFTY", spot, price_by_token, datetime(2026, 8, 1, 10, 0))
    assert iv is not None and iv > 0.0
