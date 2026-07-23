from datetime import date

import pytest

from nse_algo_trader.broker_oms import (
    OrderIntent,
    OrderSide,
    OrderType,
    build_order_intent_for_opening_range_breakout,
    build_order_intents_for_credit_spread,
)
from nse_algo_trader.strategy_engine import (
    CreditSpreadBias,
    CreditSpreadSignal,
    OptionLegAction,
    OptionLegIntent,
)
from tests.test_broker_oms.broker_oms_test_fixtures import (
    CASH_INSTRUMENT,
    make_orb_signal,
    make_put_instrument,
)


def _bull_put_signal(lot_size: int = 65) -> CreditSpreadSignal:
    return CreditSpreadSignal(
        underlying_symbol="NIFTY",
        bias=CreditSpreadBias.BULLISH_SELL_PUT_SPREAD,
        short_leg=OptionLegIntent(
            make_put_instrument(23750.0, lot_size), OptionLegAction.SELL, 1
        ),
        hedge_leg=OptionLegIntent(
            make_put_instrument(23650.0, lot_size), OptionLegAction.BUY, 1
        ),
        short_leg_estimated_delta=0.24,
    )


class TestOrderIntentValidation:
    def test_zero_quantity_rejected(self):
        with pytest.raises(ValueError, match="at least 1 share"):
            OrderIntent(CASH_INSTRUMENT, OrderSide.BUY, 0, "tag")

    def test_limit_order_requires_price(self):
        with pytest.raises(ValueError, match="limit_price"):
            OrderIntent(
                CASH_INSTRUMENT, OrderSide.BUY, 10, "tag",
                order_type=OrderType.LIMIT,
            )


class TestSignalToOrderIntents:
    def test_orb_long_becomes_buy_with_approved_quantity_and_tag(self):
        intent = build_order_intent_for_opening_range_breakout(
            make_orb_signal(entry=103.0, stop=98.0), risk_approved_share_quantity=2000
        )
        assert intent.side is OrderSide.BUY
        assert intent.quantity == 2000
        assert intent.strategy_tag == "opening_range_breakout_v1"

    def test_credit_spread_hedge_buy_comes_first_and_lots_become_shares(self):
        intents = build_order_intents_for_credit_spread(
            _bull_put_signal(lot_size=65), risk_approved_lots=2
        )
        assert [intent.side for intent in intents] == [OrderSide.BUY, OrderSide.SELL]
        assert intents[0].instrument.strike_price == 23650.0  # the hedge
        assert all(intent.quantity == 2 * 65 for intent in intents)
        assert all(intent.strategy_tag == "credit_spread_v1" for intent in intents)
