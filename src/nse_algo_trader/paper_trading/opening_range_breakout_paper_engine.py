"""The paper engine — runs the ORB directional strategy over replayed bars.

This is the loop-closing component (Rule G): it wires Layer 4 (signal) →
Layer 5 (risk gate) → Layer 6 (SimulatedBrokerClient) → the paper ledger,
driven by Layer 7's replayed real bars. One session in, one paper-trade
outcome out, with intraday stop/target management and a hard square-off
at session end (the no-overnight non-negotiable).

Scope of this slice: the cash-equity ORB path (the directional half of
the v1 shortlist). The credit-spread paper path is a later slice — it
needs intraday option bars, which the store does not yet hold. The
prediction-labeled tables lab (PLAN §9) attaches on top of this engine.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from enum import Enum

from nse_algo_trader.broker_oms import (
    OrderIntent,
    OrderSide,
    SimulatedBrokerClient,
    build_order_intent_for_opening_range_breakout,
)
from nse_algo_trader.market_data import PriceBar
from nse_algo_trader.paper_trading.paper_trading_ledger import PaperTradingLedger
from nse_algo_trader.risk_management import (
    RiskBudgetConfig,
    evaluate_opening_range_breakout_signal,
)
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutConfig,
    SignalDirection,
    detect_opening_range_breakout,
)
from nse_algo_trader.universe_registry import Instrument


class PaperSessionOutcome(str, Enum):
    NO_SIGNAL = "no_signal"
    RISK_REJECTED = "risk_rejected"
    EXITED_TARGET = "exited_target"
    EXITED_STOP = "exited_stop"
    SQUARED_OFF_AT_CLOSE = "squared_off_at_close"


@dataclass(frozen=True)
class PaperSessionResult:
    session_date: date
    outcome: PaperSessionOutcome
    direction: SignalDirection | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: int = 0
    realized_pnl: float = 0.0


def group_bars_into_sessions(bars: list[PriceBar]) -> dict[date, list[PriceBar]]:
    sessions: dict[date, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        sessions[bar.timestamp.date()].append(bar)
    return dict(sessions)


def run_opening_range_breakout_paper_session(
    single_session_bars: list[PriceBar],
    instrument: Instrument,
    simulated_broker: SimulatedBrokerClient,
    risk_budget: RiskBudgetConfig,
    ledger: PaperTradingLedger,
    strategy_config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
) -> PaperSessionResult:
    session_date = single_session_bars[0].timestamp.date()
    signal = detect_opening_range_breakout(
        single_session_bars, instrument, strategy_config
    )
    if signal is None:
        return PaperSessionResult(session_date, PaperSessionOutcome.NO_SIGNAL)

    risk_decision = evaluate_opening_range_breakout_signal(signal, risk_budget)
    if not risk_decision.approved:
        return PaperSessionResult(
            session_date, PaperSessionOutcome.RISK_REJECTED, signal.direction
        )

    entry_side = (
        OrderSide.BUY if signal.direction is SignalDirection.LONG else OrderSide.SELL
    )
    exit_side = OrderSide.SELL if entry_side is OrderSide.BUY else OrderSide.BUY
    quantity = risk_decision.approved_quantity

    # Enter at the breakout bar's close.
    simulated_broker.update_market_price(
        instrument.instrument_token, signal.breakout_close_price
    )
    entry_intent = build_order_intent_for_opening_range_breakout(signal, quantity)
    entry_fill = simulated_broker.place_order(entry_intent)
    ledger.record_fill(
        instrument.instrument_token, entry_side, quantity, entry_fill.average_fill_price
    )

    bars_after_entry = [
        bar for bar in single_session_bars if bar.timestamp > signal.triggered_at
    ]
    for bar in bars_after_entry:
        exit_price, outcome = _stop_or_target_hit(bar, signal)
        if exit_price is not None:
            return _close_session(
                simulated_broker, ledger, instrument, exit_side, quantity,
                exit_price, session_date, signal.direction, entry_fill.average_fill_price,
                outcome,
            )

    # Never hit stop or target -> square off at the last bar's close.
    square_off_price = single_session_bars[-1].close_price
    return _close_session(
        simulated_broker, ledger, instrument, exit_side, quantity, square_off_price,
        session_date, signal.direction, entry_fill.average_fill_price,
        PaperSessionOutcome.SQUARED_OFF_AT_CLOSE,
    )


def _stop_or_target_hit(bar: PriceBar, signal) -> tuple[float | None, PaperSessionOutcome | None]:
    if signal.direction is SignalDirection.LONG:
        if bar.low_price <= signal.stop_loss_price:
            return signal.stop_loss_price, PaperSessionOutcome.EXITED_STOP
        if bar.high_price >= signal.target_price:
            return signal.target_price, PaperSessionOutcome.EXITED_TARGET
    else:
        if bar.high_price >= signal.stop_loss_price:
            return signal.stop_loss_price, PaperSessionOutcome.EXITED_STOP
        if bar.low_price <= signal.target_price:
            return signal.target_price, PaperSessionOutcome.EXITED_TARGET
    return None, None


def _close_session(
    simulated_broker, ledger, instrument, exit_side, quantity, exit_price,
    session_date, direction, entry_price, outcome,
) -> PaperSessionResult:
    simulated_broker.update_market_price(instrument.instrument_token, exit_price)
    exit_fill = simulated_broker.place_order(
        OrderIntent(instrument, exit_side, quantity, "opening_range_breakout_v1")
    )
    recorded = ledger.record_fill(
        instrument.instrument_token, exit_side, quantity, exit_fill.average_fill_price
    )
    return PaperSessionResult(
        session_date=session_date,
        outcome=outcome,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_fill.average_fill_price,
        quantity=quantity,
        realized_pnl=recorded.realized_pnl_from_this_fill,
    )
