"""B32 (hermetic, Rule J): the 0-DTE live path opens multi-leg structures through the gate cascade,
marks P&L per leg with the right sign, and closes on time-stop / stop / square-off. The Rule-F live
expiry-day pass stays an open blocker (BACKLOG B32)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.broker_oms.order_types import OrderExecutionResult, OrderLifecycleState
from nse_algo_trader.paper_trading.zero_dte_expiry_day_live_path import (
    manage_open_zero_dte_positions,
    open_zero_dte_position,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    OptionLegAction,
    OptionLegIntent,
)
from nse_algo_trader.strategy_engine.zero_dte_entry_planner import ZeroDtePlannedEntry
from nse_algo_trader.strategy_engine.zero_dte_regime_router import ZeroDteStructure
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

IST = ZoneInfo("Asia/Kolkata")
LOT = 50


def _opt(token: int, strike: float, right: OptionRight) -> Instrument:
    return Instrument(
        instrument_token=token, trading_symbol=f"NIFTY{int(strike)}{right.value}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=LOT, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=strike, option_right=right, expiry_date=date(2026, 7, 28),
    )


class _FakeBroker:
    def __init__(self, reject_token: int | None = None):
        self.reject_token = reject_token
        self.orders: list = []

    def update_market_price(self, token, price):  # noqa: D401
        pass

    def place_order(self, order_intent) -> OrderExecutionResult:
        self.orders.append(order_intent)
        state = (OrderLifecycleState.REJECTED
                 if order_intent.instrument.instrument_token == self.reject_token
                 else OrderLifecycleState.COMPLETE)
        return OrderExecutionResult(
            broker_order_id="x", state=state,
            filled_quantity=order_intent.quantity, average_fill_price=1.0,
        )


@dataclass
class _FakeState:
    simulated_broker: _FakeBroker
    allow_gates: bool = True
    zero_dte_risk_state: object = None
    open_zero_dte_positions: object = None
    closed_zero_dte_positions: object = None

    def constitution_permits_order(self, segment, is_option): return self.allow_gates
    def oversight_permits_autonomous_order(self, wp, is_option, risk_amount=None, account_capital=None):
        return self.allow_gates
    def convergence_limiter_permits_order(self): return self.allow_gates
    def homeostat_permits_order(self): return self.allow_gates
    def power_budget_permits_order(self, now): return self.allow_gates


def _straddle_plan() -> ZeroDtePlannedEntry:
    call = _opt(1, 20000, OptionRight.CALL)
    put = _opt(2, 20000, OptionRight.PUT)
    return ZeroDtePlannedEntry(
        underlying_symbol="NIFTY", structure=ZeroDteStructure.LONG_STRADDLE, direction=None,
        legs=(OptionLegIntent(call, OptionLegAction.BUY, 1), OptionLegIntent(put, OptionLegAction.BUY, 1)),
        defined_risk_per_lot=200.0 * LOT, trigger="volatility_expansion", reason="test",
    )


def _at(hour, minute=0):
    return datetime(2026, 7, 28, hour, minute, tzinfo=IST)


def test_opens_multi_leg_straddle_and_registers_risk_state():
    state = _FakeState(_FakeBroker())
    plan = _straddle_plan()
    ok = open_zero_dte_position(state, plan, {1: 100.0, 2: 100.0}, _at(11, 0))
    assert ok is True
    assert len(state.open_zero_dte_positions) == 1
    assert state.zero_dte_risk_state.open_position_count() == 1
    assert len(state.simulated_broker.orders) == 2  # two legs placed


def test_governance_block_prevents_opening():
    state = _FakeState(_FakeBroker(), allow_gates=False)
    ok = open_zero_dte_position(state, _straddle_plan(), {1: 100.0, 2: 100.0}, _at(11, 0))
    assert ok is False
    assert not state.open_zero_dte_positions


def test_rejected_leg_flattens_and_opens_nothing():
    state = _FakeState(_FakeBroker(reject_token=2))  # second leg rejected
    ok = open_zero_dte_position(state, _straddle_plan(), {1: 100.0, 2: 100.0}, _at(11, 0))
    assert ok is False
    assert not state.open_zero_dte_positions


def test_long_straddle_pnl_rises_when_premia_rise():
    state = _FakeState(_FakeBroker())
    open_zero_dte_position(state, _straddle_plan(), {1: 100.0, 2: 100.0}, _at(11, 0))
    position = next(iter(state.open_zero_dte_positions.values()))
    # both premia +20 → long legs each gain 20 × 1 lot × 50 = 1000 → total 2000
    assert position.unrealized_pnl({1: 120.0, 2: 120.0}) == 2000.0


def test_time_stop_closes_the_position():
    state = _FakeState(_FakeBroker())
    open_zero_dte_position(state, _straddle_plan(), {1: 100.0, 2: 100.0}, _at(10, 0))
    # default time-stop 45 min → at 11:00 it is past due
    closed = manage_open_zero_dte_positions(state, {1: 100.0, 2: 100.0}, _at(11, 0))
    assert closed == 1
    assert not state.open_zero_dte_positions
    assert state.closed_zero_dte_positions[-1].exit_reason == "time_stop"


def test_square_off_window_closes_regardless_of_pnl():
    state = _FakeState(_FakeBroker())
    open_zero_dte_position(state, _straddle_plan(), {1: 100.0, 2: 100.0}, _at(14, 45))
    closed = manage_open_zero_dte_positions(
        state, {1: 100.0, 2: 100.0}, _at(15, 16), is_square_off_window=True
    )
    assert closed == 1
    assert state.closed_zero_dte_positions[-1].exit_reason == "square_off"


def test_daily_loss_cap_blocks_new_entry_after_big_loss():
    from nse_algo_trader.paper_trading.zero_dte_risk_state import ZeroDteRiskConfig, ZeroDteRiskState
    state = _FakeState(_FakeBroker())
    state.zero_dte_risk_state = ZeroDteRiskState(ZeroDteRiskConfig(daily_loss_cap_rupees=500.0))
    # record a big prior loss for the day
    state.zero_dte_risk_state.register_opened("prior", _at(9, 30))
    state.zero_dte_risk_state.record_closed("prior", realized_pnl=-600.0, now=_at(9, 45))
    ok = open_zero_dte_position(state, _straddle_plan(), {1: 100.0, 2: 100.0}, _at(11, 0))
    assert ok is False
