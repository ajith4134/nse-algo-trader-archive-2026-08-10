"""B32 · 0-DTE expiry-day live path — open, carry, and close the multi-leg 0-DTE structures.

The planner (`zero_dte_entry_planner`) decides WHAT to trade; this module TRADES it: it runs the same
governance-gate cascade the other option paths use, places every leg through the simulated broker,
tracks the multi-leg position, drives the `ZeroDteRiskState` (time-stop + daily loss cap), and closes
on target/stop, time-stop, or the end-of-day square-off window.

0-DTE structures are MULTI-LEG (straddle = 2 longs; iron fly = 2 shorts + 2 protective longs), so a
new `OpenZeroDtePosition` carries them together — a single-leg position type cannot represent the
defined-risk relationship between a short leg and its wing. P&L is computed per leg with the correct
sign (long leg gains when its premium rises; short leg gains when its premium falls).

The `state` argument is the live loop's state object; this module uses only the same interface the
existing option paths do (`simulated_broker`, the five `*_permits_order` gates, and tracking dicts),
so it is exercised hermetically with a lightweight fake in tests (Rule J) — the Rule-F live expiry-day
pass stays the open blocker until an expiry session runs post-wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nse_algo_trader.paper_trading.zero_dte_risk_state import ZeroDteRiskState
from nse_algo_trader.strategy_engine.strategy_signal_types import (
    OptionLegAction,
    OptionLegIntent,
)
from nse_algo_trader.strategy_engine.zero_dte_entry_planner import ZeroDtePlannedEntry
from nse_algo_trader.strategy_engine.zero_dte_regime_router import ZeroDteStructure


@dataclass(frozen=True)
class _EnteredLeg:
    """One placed leg and the premium it was entered at (per share)."""

    leg: OptionLegIntent
    entry_premium: float


@dataclass
class OpenZeroDtePosition:
    """A live multi-leg 0-DTE structure, carried as one position with a defined max loss."""

    position_id: str
    underlying_symbol: str
    structure: ZeroDteStructure
    entered_legs: list[_EnteredLeg]
    lots: int
    lot_size: int
    defined_risk_per_lot: float
    opened_at: datetime
    strategy_tag: str
    assigned_table: str

    def unrealized_pnl(self, price_by_token: dict[int, float]) -> float:
        """Mark-to-market P&L across all legs (rupees). A BUY leg profits as its premium rises; a
        SELL leg profits as its premium falls. Legs with no current mark contribute 0 (never guessed)."""
        total = 0.0
        contracts = self.lots * self.lot_size
        for entered in self.entered_legs:
            token = entered.leg.instrument.instrument_token
            mark = price_by_token.get(token)
            if mark is None:
                continue
            move = mark - entered.entry_premium
            if entered.leg.action is OptionLegAction.SELL:
                move = -move
            total += move * contracts
        return total

    @property
    def max_loss_rupees(self) -> float:
        return self.defined_risk_per_lot * self.lots


@dataclass
class ClosedZeroDtePosition:
    position: OpenZeroDtePosition
    realized_pnl: float
    closed_at: datetime
    exit_reason: str


#: the five governance gates every option order must clear, in the same order the other paths use.
_GATE_METHOD_NAMES = (
    "constitution_permits_order",
    "oversight_permits_autonomous_order",
    "convergence_limiter_permits_order",
    "homeostat_permits_order",
    "power_budget_permits_order",
)


def _governance_permits_order(
    state, segment: str, win_probability: float, now: datetime,
    risk_amount: float | None = None, account_capital: float | None = None,
) -> bool:
    """Run the shared governance cascade. Any gate that refuses blocks the order (fail-closed).
    Passes `risk_amount` + `account_capital` to the oversight gate so a defined-risk 0-DTE spread is
    scored by MONEY AT RISK (B16), not by instrument class — otherwise every option entry defers as
    'high-stakes + low-confidence' regardless of how small its capped loss is."""
    if not state.constitution_permits_order(segment, is_option=True):
        return False
    if not state.oversight_permits_autonomous_order(
        win_probability, is_option=True,
        risk_amount=risk_amount, account_capital=account_capital,
    ):
        return False
    if not state.convergence_limiter_permits_order():
        return False
    if not state.homeostat_permits_order():
        return False
    return bool(state.power_budget_permits_order(now))


def open_zero_dte_position(
    state,
    planned_entry: ZeroDtePlannedEntry,
    price_by_token: dict[int, float],
    now: datetime,
    win_probability: float = 0.5,
) -> bool:
    """Place a planned 0-DTE structure: gate → place every leg → track → register the risk-state.
    Returns True iff a position opened. Refuses (no order) when the daily loss cap is breached, the
    governance cascade blocks, or any leg is rejected (already-placed legs are flattened to avoid a
    naked partial fill)."""
    if not planned_entry.is_actionable:
        return False
    risk_state = _risk_state(state)
    if not risk_state.permits_new_entry(now):
        return False
    lots = _first_leg_lots(planned_entry)
    segment = _segment_for(planned_entry)
    # Stakes = the structure's capped loss vs account capital (B16 money-at-risk measure), so a small
    # defined-risk 0-DTE spread is not deferred as if it were a high-stakes bet.
    risk_amount = planned_entry.defined_risk_per_lot * lots
    account_capital = getattr(getattr(state, "ledger", None), "starting_virtual_cash", None)
    if not _governance_permits_order(
        state, segment, win_probability, now, risk_amount, account_capital
    ):
        return False
    entered: list[_EnteredLeg] = []
    from nse_algo_trader.broker_oms import OrderIntent, OrderLifecycleState, OrderSide

    for leg in planned_entry.legs:
        premium = price_by_token.get(leg.instrument.instrument_token)
        if premium is None or premium <= 0.0:
            _flatten_entered_legs(state, entered, price_by_token, now)
            return False
        state.simulated_broker.update_market_price(leg.instrument.instrument_token, premium)
        side = OrderSide.BUY if leg.action is OptionLegAction.BUY else OrderSide.SELL
        fill = state.simulated_broker.place_order(
            OrderIntent(leg.instrument, side, lots * leg.instrument.lot_size, planned_entry.trigger)
        )
        if fill.state is OrderLifecycleState.REJECTED:
            _flatten_entered_legs(state, entered, price_by_token, now)
            return False
        entered.append(_EnteredLeg(leg=leg, entry_premium=premium))

    position = OpenZeroDtePosition(
        position_id=_position_id(planned_entry.underlying_symbol, now),
        underlying_symbol=planned_entry.underlying_symbol,
        structure=planned_entry.structure,
        entered_legs=entered,
        lots=lots,
        lot_size=planned_entry.legs[0].instrument.lot_size,
        defined_risk_per_lot=planned_entry.defined_risk_per_lot,
        opened_at=now,
        strategy_tag=f"zero_dte_{planned_entry.structure.value}",
        assigned_table=_assigned_table_for(planned_entry, win_probability),
    )
    _open_positions(state)[position.position_id] = position
    risk_state.register_opened(position.position_id, now)
    print(
        f"[zero-dte] OPENED {position.structure.value} on {position.underlying_symbol} "
        f"({len(position.entered_legs)} legs, {lots} lot, defined-risk Rs{position.max_loss_rupees:.0f}) "
        f"trigger={planned_entry.trigger}",
        flush=True,
    )
    return True


def manage_open_zero_dte_positions(
    state,
    price_by_token: dict[int, float],
    now: datetime,
    is_square_off_window: bool = False,
) -> int:
    """Close 0-DTE positions that hit their target, defined-risk stop, time-stop, or the square-off
    window. Returns the number closed this pass. Called every scan pass by the loop (part 6)."""
    risk_state = _risk_state(state)
    time_stopped = set(risk_state.time_stopped_position_ids(now))
    closed = 0
    for position_id, position in list(_open_positions(state).items()):
        pnl = position.unrealized_pnl(price_by_token)
        reason = None
        if is_square_off_window:
            reason = "square_off"
        elif position_id in time_stopped:
            reason = "time_stop"
        elif pnl <= -position.max_loss_rupees:
            reason = "defined_risk_stop"
        elif pnl >= position.max_loss_rupees:  # symmetric target at +1R of defined risk
            reason = "target"
        if reason is not None:
            _close_zero_dte_position(state, position, price_by_token, now, reason)
            closed += 1
    return closed


def _close_zero_dte_position(
    state, position: OpenZeroDtePosition, price_by_token: dict[int, float],
    now: datetime, exit_reason: str,
) -> None:
    realized = position.unrealized_pnl(price_by_token)
    from nse_algo_trader.broker_oms import OrderIntent, OrderSide

    for entered in position.entered_legs:
        mark = price_by_token.get(entered.leg.instrument.instrument_token)
        if mark is not None:
            state.simulated_broker.update_market_price(entered.leg.instrument.instrument_token, mark)
        # flatten: the opposite side of how the leg was entered
        exit_side = OrderSide.SELL if entered.leg.action is OptionLegAction.BUY else OrderSide.BUY
        state.simulated_broker.place_order(
            OrderIntent(entered.leg.instrument, exit_side,
                        position.lots * entered.leg.instrument.lot_size, f"zero_dte_exit_{exit_reason}")
        )
    _open_positions(state).pop(position.position_id, None)
    _closed_positions(state).append(
        ClosedZeroDtePosition(position=position, realized_pnl=realized,
                              closed_at=now, exit_reason=exit_reason)
    )
    _risk_state(state).record_closed(position.position_id, realized, now)


def _flatten_entered_legs(state, entered: list[_EnteredLeg], price_by_token, now) -> None:
    """Unwind partially-entered legs when a later leg is rejected — never leave a naked short leg."""
    if not entered:
        return
    from nse_algo_trader.broker_oms import OrderIntent, OrderSide
    for e in entered:
        exit_side = OrderSide.SELL if e.leg.action is OptionLegAction.BUY else OrderSide.BUY
        state.simulated_broker.place_order(
            OrderIntent(e.leg.instrument, exit_side, e.leg.instrument.lot_size, "zero_dte_unwind")
        )


# -- state accessors (the loop's state owns these; created lazily so wiring is a small change) -----

def _risk_state(state) -> ZeroDteRiskState:
    if getattr(state, "zero_dte_risk_state", None) is None:
        state.zero_dte_risk_state = ZeroDteRiskState()
    return state.zero_dte_risk_state


def _open_positions(state) -> dict:
    if getattr(state, "open_zero_dte_positions", None) is None:
        state.open_zero_dte_positions = {}
    return state.open_zero_dte_positions


def _closed_positions(state) -> list:
    if getattr(state, "closed_zero_dte_positions", None) is None:
        state.closed_zero_dte_positions = []
    return state.closed_zero_dte_positions


def _segment_for(planned_entry: ZeroDtePlannedEntry) -> str:
    kind = planned_entry.legs[0].instrument.kind
    from nse_algo_trader.universe_registry.instrument_types import InstrumentKind
    return "nse_index_options" if kind is InstrumentKind.INDEX_OPTION else "nse_stock_options"


def _first_leg_lots(planned_entry: ZeroDtePlannedEntry) -> int:
    return max(planned_entry.legs[0].lots, 1)


def _position_id(underlying_symbol: str, now: datetime) -> str:
    return f"zero_dte:{underlying_symbol}:{now.isoformat()}"


def _implied_volatility_by_token(
    underlying_options, spot_price: float, price_by_token: dict[int, float], now: datetime,
) -> dict[int, float]:
    """Per-strike IV inverted from each option's live premium (Kite carries no IV field). Skips a
    strike with no premium rather than guessing. On expiry day time-to-expiry floors at 1 day/365,
    matching the existing option path's convention."""
    from nse_algo_trader.indicators.black_scholes_implied_volatility import (
        OptionRightForPricing,
        compute_implied_volatility,
    )
    from nse_algo_trader.universe_registry.instrument_types import OptionRight

    iv_by_token: dict[int, float] = {}
    for option in underlying_options:
        premium = price_by_token.get(option.instrument_token)
        if premium is None or premium <= 0.0 or option.strike_price is None or option.expiry_date is None:
            continue
        days_to_expiry = max((option.expiry_date - now.date()).days, 1)
        right = (OptionRightForPricing.CALL if option.option_right is OptionRight.CALL
                 else OptionRightForPricing.PUT)
        value = compute_implied_volatility(
            premium, spot_price, option.strike_price, days_to_expiry / 365, right
        )
        if value is not None and value > 0.0:
            iv_by_token[option.instrument_token] = value
    return iv_by_token


def try_open_zero_dte_for_underlying(
    state, underlying_symbol: str, spot_instrument, option_ladder: list, live_universe_feed, now: datetime,
) -> bool:
    """Assemble the planner's inputs for one 0-DTE underlying from the live feed and open the routed
    structure. Returns True iff a position opened. The caller has already confirmed this underlying's
    nearest expiry is TODAY (routed here exclusively, so it is never also traded by the other arms)."""
    from nse_algo_trader.market_data.market_data_types import BarInterval
    from nse_algo_trader.strategy_engine.zero_dte_entry_planner import plan_zero_dte_entry

    spot_bars = live_universe_feed.recent_intraday_bars(
        spot_instrument, now, bar_interval=BarInterval.MINUTE_5
    )
    if len(spot_bars) < 28:
        return False
    spot_price = spot_bars[-1].close_price
    underlying_options = [
        o for o in option_ladder
        if o.underlying_symbol == underlying_symbol and o.expiry_date == now.date()
    ]
    if not underlying_options:
        return False
    price_by_token = live_universe_feed.latest_price_by_token(underlying_options)
    open_interest_by_token = live_universe_feed.latest_open_interest_by_token(underlying_options)
    implied_volatility_by_token = _implied_volatility_by_token(
        underlying_options, spot_price, price_by_token, now
    )
    # historical_atm_iv_by_date left empty until the IV-history reader is wired (Rule-Q: the IV-rank
    # signal abstains, the router still trades on GEX/ADX/momentum/ORB) — tracked in BACKLOG B32.
    plan = plan_zero_dte_entry(
        underlying_symbol, spot_instrument, spot_price, spot_bars, underlying_options,
        price_by_token, open_interest_by_token, implied_volatility_by_token, {}, now,
    )
    return open_zero_dte_position(state, plan, price_by_token, now)


def manage_open_zero_dte_positions_via_feed(
    state, live_universe_feed, now: datetime, is_square_off_window: bool = False,
) -> int:
    """Feed adapter for `manage_open_zero_dte_positions`: fetch live premia for every open 0-DTE leg,
    then run the target/stop/time-stop/square-off management. Called each pass by the options loop."""
    positions = _open_positions(state)
    if not positions:
        return 0
    instruments = [
        entered.leg.instrument for position in positions.values() for entered in position.entered_legs
    ]
    price_by_token = live_universe_feed.latest_price_by_token(instruments) if instruments else {}
    return manage_open_zero_dte_positions(state, price_by_token, now, is_square_off_window)


def _assigned_table_for(planned_entry: ZeroDtePlannedEntry, win_probability: float) -> str:
    """A directional/straddle entry opened to profit → confident_win when the read is strong, else
    uncertain; a short-premium pin is a defined-edge win thesis. Confident-loss probes are not opened
    here (this path only trades theses it believes in)."""
    if win_probability >= 0.6:
        return "confident_win"
    return "uncertain"
