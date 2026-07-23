from datetime import date

import pytest

from nse_algo_trader.indicators import OptionRightForPricing, compute_black_scholes_delta
from nse_algo_trader.strategy_engine import (
    CreditSpreadBias,
    CreditSpreadSelectionConfig,
    MarketRegime,
    V1SessionStrategyChoice,
    choose_v1_session_strategy,
    classify_adx_market_regime,
    select_credit_spread_legs,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    CreditSpreadSignal,
    OptionLegAction,
    OptionLegIntent,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

TRADE_DATE = date(2026, 7, 22)
NEAR_EXPIRY = date(2026, 7, 28)
FAR_EXPIRY = date(2026, 8, 25)


def _nifty_option(strike: float, right: OptionRight, expiry: date) -> Instrument:
    right_code = "CE" if right is OptionRight.CALL else "PE"
    return Instrument(
        instrument_token=int(strike) * 10 + (1 if right is OptionRight.CALL else 2),
        trading_symbol=f"NIFTY{strike:.0f}{right_code}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=75, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=strike, option_right=right, expiry_date=expiry,
    )


NIFTY_CHAIN = [
    _nifty_option(strike, right, expiry)
    for strike in range(23000, 27001, 100)
    for right in (OptionRight.CALL, OptionRight.PUT)
    for expiry in (NEAR_EXPIRY, FAR_EXPIRY)
]


class TestAdxRegimeGate:
    def test_threshold_classification(self):
        assert classify_adx_market_regime(30.0) is MarketRegime.TRENDING
        assert classify_adx_market_regime(25.0) is MarketRegime.TRENDING
        assert classify_adx_market_regime(22.0) is MarketRegime.INDECISIVE
        assert classify_adx_market_regime(20.0) is MarketRegime.RANGE_BOUND
        assert classify_adx_market_regime(10.0) is MarketRegime.RANGE_BOUND

    def test_warmup_none_never_trades(self):
        assert classify_adx_market_regime(None) is MarketRegime.INDECISIVE
        assert choose_v1_session_strategy(None) is V1SessionStrategyChoice.STAND_ASIDE

    def test_strategy_choice_mapping(self):
        assert choose_v1_session_strategy(30.0) is V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT
        assert choose_v1_session_strategy(15.0) is V1SessionStrategyChoice.CREDIT_SPREAD


class TestCreditSpreadLegSelector:
    def test_bull_put_selects_otm_puts_near_target_delta_with_hedge_below(self):
        signal = select_credit_spread_legs(
            NIFTY_CHAIN, "NIFTY", spot_price=25000.0, atm_implied_volatility=0.15,
            bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD, trade_date=TRADE_DATE,
        )
        assert signal.short_leg.action is OptionLegAction.SELL
        assert signal.hedge_leg.action is OptionLegAction.BUY
        short, hedge = signal.short_leg.instrument, signal.hedge_leg.instrument
        assert short.option_right is OptionRight.PUT and hedge.option_right is OptionRight.PUT
        assert short.expiry_date == NEAR_EXPIRY == hedge.expiry_date
        assert short.strike_price < 25000.0
        assert hedge.strike_price == short.strike_price - 200  # 2 steps x 100
        # the chosen strike's BS delta really is the closest to 0.25
        tte = (NEAR_EXPIRY - TRADE_DATE).days / 365.0
        chosen_delta_gap = abs(abs(compute_black_scholes_delta(
            25000.0, short.strike_price, tte, 0.15, OptionRightForPricing.PUT)) - 0.25)
        for strike in range(23000, 25000, 100):
            other_gap = abs(abs(compute_black_scholes_delta(
                25000.0, float(strike), tte, 0.15, OptionRightForPricing.PUT)) - 0.25)
            assert chosen_delta_gap <= other_gap + 1e-12
        assert signal.short_leg_estimated_delta == pytest.approx(0.25, abs=0.10)

    def test_bear_call_mirrors_above_spot(self):
        signal = select_credit_spread_legs(
            NIFTY_CHAIN, "NIFTY", spot_price=25000.0, atm_implied_volatility=0.15,
            bias=CreditSpreadBias.BEARISH_SELL_CALL_SPREAD, trade_date=TRADE_DATE,
        )
        short, hedge = signal.short_leg.instrument, signal.hedge_leg.instrument
        assert short.option_right is OptionRight.CALL
        assert short.strike_price > 25000.0
        assert hedge.strike_price == short.strike_price + 200

    def test_expiry_day_chain_is_skipped_to_next_expiry(self):
        signal = select_credit_spread_legs(
            NIFTY_CHAIN, "NIFTY", spot_price=25000.0, atm_implied_volatility=0.15,
            bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD, trade_date=NEAR_EXPIRY,
        )
        assert signal.short_leg.instrument.expiry_date == FAR_EXPIRY

    def test_ladder_too_short_for_hedge_returns_none_not_naked(self):
        stub_ladder = [
            _nifty_option(24900.0, OptionRight.PUT, NEAR_EXPIRY),
        ]
        assert select_credit_spread_legs(
            stub_ladder, "NIFTY", spot_price=25000.0, atm_implied_volatility=0.15,
            bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD, trade_date=TRADE_DATE,
        ) is None

    def test_unknown_underlying_returns_none(self):
        assert select_credit_spread_legs(
            NIFTY_CHAIN, "BANKNIFTY", spot_price=57000.0, atm_implied_volatility=0.15,
            bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD, trade_date=TRADE_DATE,
        ) is None


class TestCreditSpreadSignalInvariants:
    def test_short_leg_must_sell_and_lots_must_match(self):
        put_short = _nifty_option(24800.0, OptionRight.PUT, NEAR_EXPIRY)
        put_hedge = _nifty_option(24600.0, OptionRight.PUT, NEAR_EXPIRY)
        with pytest.raises(ValueError, match="short leg must be a SELL"):
            CreditSpreadSignal(
                underlying_symbol="NIFTY", bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD,
                short_leg=OptionLegIntent(put_short, OptionLegAction.BUY, 1),
                hedge_leg=OptionLegIntent(put_hedge, OptionLegAction.BUY, 1),
                short_leg_estimated_delta=0.25,
            )
        with pytest.raises(ValueError, match="equal lots"):
            CreditSpreadSignal(
                underlying_symbol="NIFTY", bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD,
                short_leg=OptionLegIntent(put_short, OptionLegAction.SELL, 2),
                hedge_leg=OptionLegIntent(put_hedge, OptionLegAction.BUY, 1),
                short_leg_estimated_delta=0.25,
            )
