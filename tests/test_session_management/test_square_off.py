from datetime import date, datetime, time

import pytest

from nse_algo_trader.broker_oms import (
    OrderExecutionResult,
    OrderLifecycleState,
    OrderSide,
)
from nse_algo_trader.paper_trading import INDIA_MARKET_TIMEZONE, NseMarketClock
from nse_algo_trader.session_management import (
    IntradaySquareOffSchedule,
    OpenPositionLeg,
    SquareOffConfig,
    build_square_off_order_intents,
    execute_intraday_square_off,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

CASH = Instrument(
    instrument_token=408065, trading_symbol="INFY",
    exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
    lot_size=1, tick_size=0.05, underlying_symbol=None, strike_price=None,
    option_right=None, expiry_date=None,
)
SHORT_PUT = Instrument(
    instrument_token=101, trading_symbol="NIFTY23750PE",
    exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
    lot_size=65, tick_size=0.05, underlying_symbol="NIFTY",
    strike_price=23750.0, option_right=OptionRight.PUT, expiry_date=date(2026, 7, 28),
)
HEDGE_PUT = Instrument(
    instrument_token=102, trading_symbol="NIFTY23650PE",
    exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
    lot_size=65, tick_size=0.05, underlying_symbol="NIFTY",
    strike_price=23650.0, option_right=OptionRight.PUT, expiry_date=date(2026, 7, 28),
)


def _ist(*a):
    return datetime(*a, tzinfo=INDIA_MARKET_TIMEZONE)


class TestSquareOffSchedule:
    def test_triggers_inside_window_before_close(self):
        schedule = IntradaySquareOffSchedule()
        clock = NseMarketClock()
        assert schedule.should_force_square_off_now(_ist(2026, 7, 22, 15, 20), clock)

    def test_not_before_window(self):
        schedule = IntradaySquareOffSchedule()
        clock = NseMarketClock()
        assert not schedule.should_force_square_off_now(_ist(2026, 7, 22, 11, 0), clock)

    def test_not_on_weekend(self):
        schedule = IntradaySquareOffSchedule()
        clock = NseMarketClock()
        assert not schedule.should_force_square_off_now(_ist(2026, 7, 25, 15, 20), clock)


class TestSafeLegOrdering:
    def test_credit_spread_covers_short_before_selling_hedge(self):
        # short put (-65) + long hedge put (+65) — the classic naked-leg trap
        legs = [
            OpenPositionLeg(SHORT_PUT, -65, "credit_spread_v1"),  # short
            OpenPositionLeg(HEDGE_PUT, +65, "credit_spread_v1"),  # protective long
        ]
        intents = build_square_off_order_intents(legs)
        # first order MUST be the BUY-to-cover of the short leg
        assert intents[0].instrument is SHORT_PUT
        assert intents[0].side is OrderSide.BUY
        # only then the SELL of the hedge
        assert intents[1].instrument is HEDGE_PUT
        assert intents[1].side is OrderSide.SELL

    def test_long_cash_position_is_sold_to_close(self):
        intents = build_square_off_order_intents(
            [OpenPositionLeg(CASH, +100, "orb")]
        )
        assert intents[0].side is OrderSide.SELL
        assert intents[0].quantity == 100

    def test_zero_quantity_legs_are_ignored(self):
        assert build_square_off_order_intents(
            [OpenPositionLeg(CASH, 0, "orb")]
        ) == []


class _RejectingThenFillingBroker:
    """Rejects each leg's first `reject_first_n` attempts, then fills."""

    def __init__(self, reject_first_n=0, always_reject_tokens=frozenset()):
        self.reject_first_n = reject_first_n
        self.always_reject_tokens = always_reject_tokens
        self.attempts_by_token: dict[int, int] = {}
        self.placed_order_sequence: list[tuple[int, str]] = []

    def place_order(self, order_intent):
        token = order_intent.instrument.instrument_token
        self.attempts_by_token[token] = self.attempts_by_token.get(token, 0) + 1
        self.placed_order_sequence.append((token, order_intent.side.value))
        if token in self.always_reject_tokens:
            return OrderExecutionResult("", OrderLifecycleState.REJECTED, 0, None, "RMS")
        if self.attempts_by_token[token] <= self.reject_first_n:
            return OrderExecutionResult("", OrderLifecycleState.REJECTED, 0, None, "net drop")
        return OrderExecutionResult("SIM", OrderLifecycleState.COMPLETE, order_intent.quantity, 1.0)

    def fetch_order_result(self, broker_order_id):
        raise NotImplementedError

    def cancel_order(self, broker_order_id):
        raise NotImplementedError


class TestForcedSquareOffResilience:
    def test_all_legs_flatten_cleanly(self):
        broker = _RejectingThenFillingBroker()
        report = execute_intraday_square_off(
            [OpenPositionLeg(SHORT_PUT, -65, "s"), OpenPositionLeg(HEDGE_PUT, +65, "s")],
            broker,
        )
        assert report.all_positions_flat
        assert not report.unflattened_legs

    def test_transient_outage_at_square_off_is_retried_until_flat(self):
        # PLAN §5 Layer 8 test: a broker drop right at square-off -> retry -> flat
        broker = _RejectingThenFillingBroker(reject_first_n=2)  # 2 drops then OK
        report = execute_intraday_square_off(
            [OpenPositionLeg(CASH, +100, "orb")], broker,
            SquareOffConfig(max_attempts_per_leg=3),
        )
        assert report.all_positions_flat
        assert report.leg_outcomes[0].attempts_used == 3

    def test_persistent_failure_is_reported_critical_never_silent(self):
        broker = _RejectingThenFillingBroker(always_reject_tokens={CASH.instrument_token})
        report = execute_intraday_square_off(
            [OpenPositionLeg(CASH, +100, "orb")], broker,
        )
        assert not report.all_positions_flat
        assert len(report.unflattened_legs) == 1  # surfaced, not dropped

    def test_short_leg_is_covered_first_even_under_retries(self):
        broker = _RejectingThenFillingBroker(reject_first_n=1)
        execute_intraday_square_off(
            [OpenPositionLeg(HEDGE_PUT, +65, "s"), OpenPositionLeg(SHORT_PUT, -65, "s")],
            broker, SquareOffConfig(max_attempts_per_leg=3),
        )
        # the very first order placed must be a BUY (covering the short)
        assert broker.placed_order_sequence[0][1] == "buy"
        assert broker.placed_order_sequence[0][0] == SHORT_PUT.instrument_token
