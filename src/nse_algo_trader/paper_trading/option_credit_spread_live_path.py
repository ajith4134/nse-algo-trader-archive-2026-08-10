"""The options credit-spread half of the live paper loop.

Wires the previously-orphaned options path (docs/research/39) into the
running loop: per option underlying, the ADX regime gate routes RANGE_BOUND
names to a defined-risk credit spread — sell premium with a bought hedge,
never naked. Uses L3 IV inversion, L4 leg selector + regime gate, L5 risk
gate, and L6 atomic multi-leg executor — un-orphaning all of them.

Held open intraday, marked on both legs' live premium, and flattened by
Layer 8 at 15:15 (BUY-to-cover the short before selling the hedge). Paper
only: simulated fills, virtual capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nse_algo_trader.broker_oms import (
    SimulatedBrokerClient,
    build_order_intents_for_credit_spread,
    execute_multi_leg_order_atomically,
)
from nse_algo_trader.indicators import compute_implied_volatility
from nse_algo_trader.indicators.black_scholes_implied_volatility import (
    OptionRightForPricing,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.paper_trading.live_universe_paper_loop import (
    _regime_adx_warmed_at,
)
from nse_algo_trader.risk_management import (
    RiskBudgetConfig,
    evaluate_credit_spread_signal,
)
from nse_algo_trader.strategy_engine import (
    CreditSpreadBias,
    OptionLegAction,
    V1SessionStrategyChoice,
    choose_v1_session_strategy,
    select_credit_spread_legs,
)
from nse_algo_trader.universe_registry import Instrument, InstrumentKind

# Capture target / stop on the net credit (fraction of the credit received).
_PROFIT_TARGET_CREDIT_FRACTION = 0.5
_STOP_LOSS_CREDIT_MULTIPLE = 2.0


@dataclass
class OpenOptionSpreadPosition:
    underlying_symbol: str
    bias: str
    short_leg: Instrument
    hedge_leg: Instrument
    lots: int
    lot_size: int
    entry_net_credit_per_unit: float
    opened_at: datetime
    strategy_tag: str
    assigned_table: str

    def current_net_premium_per_unit(self, price_by_token: dict) -> float | None:
        short_px = price_by_token.get(self.short_leg.instrument_token)
        hedge_px = price_by_token.get(self.hedge_leg.instrument_token)
        if short_px is None or hedge_px is None:
            return None
        return short_px - hedge_px

    def unrealized_pnl(self, price_by_token: dict) -> float | None:
        current = self.current_net_premium_per_unit(price_by_token)
        if current is None:
            return None
        # Credit spread profits as the net premium decays below entry credit.
        return (self.entry_net_credit_per_unit - current) * self.lots * self.lot_size


def _intraday_drift_bias(spot_bars) -> CreditSpreadBias:
    """Mild up-drift → sell a put spread (bullish); down-drift → sell a call
    spread (bearish) — the range-bound premium-collection play either way."""
    today = [b for b in spot_bars if b.timestamp.date() == spot_bars[-1].timestamp.date()]
    if len(today) >= 2 and today[-1].close_price >= today[0].open_price:
        return CreditSpreadBias.BULLISH_SELL_PUT_SPREAD
    return CreditSpreadBias.BEARISH_SELL_CALL_SPREAD


def _atm_call_implied_volatility(
    option_ladder, underlying_symbol, spot_price, price_by_token, now
) -> float | None:
    calls = [
        o for o in option_ladder
        if o.underlying_symbol == underlying_symbol and o.option_right.value == "CE"
    ]
    if not calls:
        return None
    atm = min(calls, key=lambda o: abs(o.strike_price - spot_price))
    ltp = price_by_token.get(atm.instrument_token)
    if ltp is None or ltp <= 0:
        return None
    days_to_expiry = max((atm.expiry_date - now.date()).days, 1)
    return compute_implied_volatility(
        ltp, spot_price, atm.strike_price, days_to_expiry / 365,
        OptionRightForPricing.CALL,
    )


def _assigned_table_for_regime(adx_value: float) -> str:
    # A cleaner range (lower ADX) is a more confident premium-decay play.
    if adx_value <= 15.0:
        return "confident_win"
    if adx_value <= 18.0:
        return "uncertain"
    return "confident_loss"


def try_open_credit_spread_for_underlying(
    state,
    underlying_symbol: str,
    spot_instrument: Instrument,
    option_ladder: list,
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    banned_underlying_symbols: frozenset = frozenset(),
) -> bool:
    """Regime-gate one underlying and, if RANGE_BOUND, open a defined-risk
    credit spread. Returns True if a spread was opened."""
    state.seeded_option_underlyings.add(underlying_symbol)
    spot_bars = live_universe_feed.recent_intraday_bars(
        spot_instrument, now, bar_interval=BarInterval.MINUTE_5
    )
    if len(spot_bars) < 28:
        return False
    adx_value = _regime_adx_warmed_at(spot_bars, spot_bars[-1].timestamp)
    if choose_v1_session_strategy(adx_value) is not V1SessionStrategyChoice.CREDIT_SPREAD:
        return False

    spot_price = spot_bars[-1].close_price
    underlying_options = [o for o in option_ladder if o.underlying_symbol == underlying_symbol]
    price_by_token = live_universe_feed.latest_price_by_token(underlying_options)
    atm_iv = _atm_call_implied_volatility(
        option_ladder, underlying_symbol, spot_price, price_by_token, now
    )
    if atm_iv is None:
        return False

    bias = _intraday_drift_bias(spot_bars)
    signal = select_credit_spread_legs(
        underlying_options, underlying_symbol, spot_price, atm_iv, bias, now.date()
    )
    if signal is None:
        return False
    decision = evaluate_credit_spread_signal(
        signal, banned_underlying_symbols, risk_budget
    )
    if not decision.approved:
        return False

    lots = 1
    short_px = price_by_token.get(signal.short_leg.instrument.instrument_token)
    hedge_px = price_by_token.get(signal.hedge_leg.instrument.instrument_token)
    if short_px is None or hedge_px is None:
        return False
    net_credit = short_px - hedge_px
    if net_credit <= 0:
        return False  # a real credit spread must collect net premium

    # Open atomically (hedge BUY first) on the sim broker with real prices.
    for leg in (signal.short_leg, signal.hedge_leg):
        px = price_by_token.get(leg.instrument.instrument_token)
        state.simulated_broker.update_market_price(leg.instrument.instrument_token, px)
    intents = build_order_intents_for_credit_spread(signal, lots)
    report = execute_multi_leg_order_atomically(intents, state.simulated_broker)
    if not report.all_legs_executed:
        return False

    lot_size = signal.short_leg.instrument.lot_size
    state.open_option_spreads[underlying_symbol] = OpenOptionSpreadPosition(
        underlying_symbol=underlying_symbol,
        bias=bias.value,
        short_leg=signal.short_leg.instrument,
        hedge_leg=signal.hedge_leg.instrument,
        lots=lots,
        lot_size=lot_size,
        entry_net_credit_per_unit=net_credit,
        opened_at=now,
        strategy_tag=signal.strategy_tag,
        assigned_table=_assigned_table_for_regime(adx_value),
    )
    return True


def manage_open_credit_spreads(state, live_universe_feed, now: datetime) -> int:
    """Mark each open spread on both legs' live premium and exit on the
    capture-target or stop. Returns how many closed this pass."""
    if not state.open_option_spreads:
        return 0
    leg_instruments = []
    for spread in state.open_option_spreads.values():
        leg_instruments.extend([spread.short_leg, spread.hedge_leg])
    price_by_token = live_universe_feed.latest_price_by_token(leg_instruments)
    closed = 0
    for underlying_symbol, spread in list(state.open_option_spreads.items()):
        current = spread.current_net_premium_per_unit(price_by_token)
        if current is None:
            continue
        target = spread.entry_net_credit_per_unit * (1 - _PROFIT_TARGET_CREDIT_FRACTION)
        stop = spread.entry_net_credit_per_unit * _STOP_LOSS_CREDIT_MULTIPLE
        if current <= target or current >= stop:
            _close_spread(state, spread, current, now)
            closed += 1
    return closed


def advance_option_credit_spread_pass(
    state,
    tradable_universe,
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    max_new_underlying_seeds_per_pass: int = 8,
    is_square_off_window: bool = False,
    banned_underlying_symbols: frozenset = frozenset(),
) -> dict:
    """One options pass: manage open spreads, then either flatten all (15:15)
    or seed a bounded batch of un-seeded underlyings into new spreads."""
    closed = manage_open_credit_spreads(state, live_universe_feed, now)
    if is_square_off_window:
        square_off_all_open_spreads(state, live_universe_feed, now)
        return {"opened": 0, "closed": closed, "open": len(state.open_option_spreads)}

    option_ladder = list(tradable_universe.option_ladder_instruments)
    spot_by_underlying = tradable_universe.spot_instrument_by_option_underlying or {}
    opened = 0
    seeded_this_pass = 0
    for underlying_symbol in sorted(spot_by_underlying):
        if seeded_this_pass >= max_new_underlying_seeds_per_pass:
            break
        if underlying_symbol in state.seeded_option_underlyings:
            continue
        if underlying_symbol in state.open_option_spreads:
            continue
        seeded_this_pass += 1
        try:
            if try_open_credit_spread_for_underlying(
                state, underlying_symbol,
                spot_by_underlying[underlying_symbol], option_ladder,
                live_universe_feed, risk_budget, now, banned_underlying_symbols,
            ):
                opened += 1
        except Exception as spread_error:
            print(
                f"[option-spread] {underlying_symbol} seed error: {spread_error!r}",
                flush=True,
            )
            state.seeded_option_underlyings.add(underlying_symbol)
    return {"opened": opened, "closed": closed, "open": len(state.open_option_spreads)}


def _close_spread(state, spread, exit_net_premium, now) -> None:
    realized = (
        (spread.entry_net_credit_per_unit - exit_net_premium)
        * spread.lots * spread.lot_size
    )
    state.realized_option_spread_pnl += realized
    state.closed_option_spreads.append((spread, realized))
    del state.open_option_spreads[spread.underlying_symbol]


def square_off_all_open_spreads(state, live_universe_feed, now: datetime) -> None:
    """Flatten every open spread through Layer 8 at 15:15 — BUY-to-cover each
    short leg before selling its hedge, never a naked leg."""
    from nse_algo_trader.session_management import (
        OpenPositionLeg,
        execute_intraday_square_off,
    )

    if not state.open_option_spreads:
        return
    leg_instruments = []
    for spread in state.open_option_spreads.values():
        leg_instruments.extend([spread.short_leg, spread.hedge_leg])
    price_by_token = live_universe_feed.latest_price_by_token(leg_instruments)

    open_legs = []
    for spread in state.open_option_spreads.values():
        qty = spread.lots * spread.lot_size
        open_legs.append(OpenPositionLeg(spread.short_leg, -qty, spread.strategy_tag))
        open_legs.append(OpenPositionLeg(spread.hedge_leg, +qty, spread.strategy_tag))
        for leg in (spread.short_leg, spread.hedge_leg):
            px = price_by_token.get(leg.instrument_token)
            if px is not None:
                state.simulated_broker.update_market_price(leg.instrument_token, px)
    execute_intraday_square_off(open_legs, state.simulated_broker)
    for underlying_symbol, spread in list(state.open_option_spreads.items()):
        current = spread.current_net_premium_per_unit(price_by_token)
        _close_spread(
            state, spread,
            current if current is not None else spread.entry_net_credit_per_unit,
            now,
        )
