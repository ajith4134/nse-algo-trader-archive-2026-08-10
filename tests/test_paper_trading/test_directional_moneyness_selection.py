"""research/171 — moneyness strike selection for the directional ladder (ITM/ATM/OTM × CE/PE)."""

from datetime import date

from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
    directional_moneyness_for_conviction,
    select_directional_strike,
)
from nse_algo_trader.strategy_engine import OptionMoneyness
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

_STRIKES = [24400.0, 24500.0, 24600.0, 24700.0, 24800.0]
_SPOT = 24600.0


def _opt(strike: float, right: OptionRight) -> Instrument:
    return Instrument(
        instrument_token=int(strike) + (1 if right is OptionRight.CALL else 2),
        trading_symbol=f"NIFTY{int(strike)}{'CE' if right is OptionRight.CALL else 'PE'}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=75, tick_size=0.05, underlying_symbol="NIFTY", strike_price=strike,
        option_right=right, expiry_date=date(2026, 8, 6),
    )


def _calls():
    return [_opt(s, OptionRight.CALL) for s in _STRIKES]


def _puts():
    return [_opt(s, OptionRight.PUT) for s in _STRIKES]


class TestCallLadder:
    def test_atm_is_nearest_to_spot(self):
        assert select_directional_strike(_calls(), _SPOT, "CE", OptionMoneyness.AT_THE_MONEY).strike_price == 24600.0

    def test_call_itm_is_below_spot(self):
        # A CALL is in-the-money when the strike is BELOW spot.
        assert select_directional_strike(_calls(), _SPOT, "CE", OptionMoneyness.IN_THE_MONEY).strike_price == 24500.0

    def test_call_otm_is_above_spot(self):
        assert select_directional_strike(_calls(), _SPOT, "CE", OptionMoneyness.OUT_OF_THE_MONEY).strike_price == 24700.0


class TestPutLadder:
    def test_put_itm_is_above_spot(self):
        # A PUT is in-the-money when the strike is ABOVE spot — the inverse of a call.
        assert select_directional_strike(_puts(), _SPOT, "PE", OptionMoneyness.IN_THE_MONEY).strike_price == 24700.0

    def test_put_otm_is_below_spot(self):
        assert select_directional_strike(_puts(), _SPOT, "PE", OptionMoneyness.OUT_OF_THE_MONEY).strike_price == 24500.0

    def test_put_atm_is_nearest(self):
        assert select_directional_strike(_puts(), _SPOT, "PE", OptionMoneyness.AT_THE_MONEY).strike_price == 24600.0


class TestGuards:
    def test_empty_candidates_returns_none(self):
        assert select_directional_strike([], _SPOT, "CE", OptionMoneyness.AT_THE_MONEY) is None

    def test_clamps_when_ladder_runs_out(self):
        # Only strikes AT/above spot for a CALL → ITM (below) clamps to the lowest available.
        only_high = [_opt(s, OptionRight.CALL) for s in (24600.0, 24700.0, 24800.0)]
        chosen = select_directional_strike(only_high, _SPOT, "CE", OptionMoneyness.IN_THE_MONEY)
        assert chosen.strike_price == 24600.0  # clamped, never an index error


class TestConvictionPolicy:
    def test_strong_trend_takes_otm(self):
        assert directional_moneyness_for_conviction(32.0) is OptionMoneyness.OUT_OF_THE_MONEY

    def test_moderate_trend_takes_atm(self):
        assert directional_moneyness_for_conviction(28.0) is OptionMoneyness.AT_THE_MONEY

    def test_weak_trend_takes_itm(self):
        assert directional_moneyness_for_conviction(20.0) is OptionMoneyness.IN_THE_MONEY
