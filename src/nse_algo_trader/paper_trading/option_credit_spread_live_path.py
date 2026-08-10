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

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime

from nse_algo_trader.broker_oms import (
    build_order_intents_for_credit_spread,
    execute_multi_leg_order_atomically,
)
from nse_algo_trader.indicators import compute_implied_volatility
from nse_algo_trader.indicators.black_scholes_implied_volatility import (
    OptionRightForPricing,
)
from nse_algo_trader.market_data.market_data_types import BarInterval
from nse_algo_trader.paper_trading.live_universe_paper_loop import (
    ClosedPaperTrade,
    _regime_adx_warmed_at,
)
from nse_algo_trader.paper_trading.opening_range_breakout_paper_engine import (
    PaperSessionOutcome,
)
from nse_algo_trader.paper_trading.prediction_lab import grade_prediction
from nse_algo_trader.paper_trading.prediction_lab.option_prediction_records import (
    build_credit_spread_prediction_record,
    build_directional_option_prediction_record,
)
from nse_algo_trader.paper_trading.indian_trading_cost_model import (
    estimate_round_trip_cost,
)
from nse_algo_trader.paper_trading.position_excursion_tracker import (
    PositionProfitExcursion,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    TradePredictionRecord,
)
from nse_algo_trader.paper_trading.profit_trail_lock_engine import (
    ProfitTrailState,
    trail_exit_triggered,
    update_profit_trail,
)
from nse_algo_trader.risk_management import (
    RiskBudgetConfig,
    compose_size_down_multipliers,
    evaluate_credit_spread_signal,
    size_defined_risk_spread_lots,
    size_down_discrete_lots,
)
from nse_algo_trader.strategy_engine import (
    CreditSpreadBias,
    OpeningRangeBreakoutConfig,
    SignalDirection,
    choose_v1_session_strategy,
    detect_opening_range_breakout,
    select_credit_spread_legs,
)
from nse_algo_trader.universe_registry import Instrument, InstrumentKind
from nse_algo_trader.universe_registry.nse_index_options_reference import (
    NSE_INDEX_OPTION_UNDERLYING_SYMBOLS,
)

#: B18: the two option arms that already exist in code. The selector chooses between them per
#: (index, regime) cell; more arms (IV-rank, trained model) plug in here as they are built.
OPTION_ARM_DIRECTIONAL = "directional_atm_option"
OPTION_ARM_CREDIT_SPREAD = "defined_risk_credit_spread"
#: task #4: the 5 NSE index-option underlyings — the ones whose per-look entry OUTCOME is logged each
#: pass so the live journal shows exactly which gate blocks index options. Stocks are not logged (flood).
_INDEX_OPTION_UNDERLYING_SYMBOLS_FOR_LOG = frozenset(NSE_INDEX_OPTION_UNDERLYING_SYMBOLS)
OPTION_ARM_NAMES: tuple[str, ...] = (OPTION_ARM_DIRECTIONAL, OPTION_ARM_CREDIT_SPREAD)

# Directional long-option exits, as a fraction of premium paid.
_DIRECTIONAL_TARGET_GAIN_FRACTION = 1.0  # +100% premium
_DIRECTIONAL_STOP_LOSS_FRACTION = 0.5  # -50% premium

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
    prediction_record: TradePredictionRecord | None = None
    #: B23: excursion + ratcheting profit lock. The SIGN TRAP lives here: a credit spread profits as
    #: the net premium FALLS, so `unrealized_pnl` below is already the correct profit-space value and
    #: the trail needs no per-type direction handling.
    excursion: PositionProfitExcursion = dc_field(default_factory=PositionProfitExcursion)
    profit_trail: ProfitTrailState = dc_field(default_factory=ProfitTrailState)

    def observe_and_advance_trail(self, price_by_token: dict) -> None:
        profit = self.unrealized_pnl(price_by_token)
        self.excursion.observe_unrealised_profit(profit)
        self.profit_trail = update_profit_trail(
            self.profit_trail,
            peak_profit=self.excursion.maximum_favourable_profit,
            # Max loss on a defined-risk spread is the strike width less the credit taken; the
            # credit collected is the cleanest risk proxy available on this object.
            initial_risk_amount=abs(self.entry_net_credit_per_unit) * self.lots * self.lot_size,
            entry_notional=abs(self.entry_net_credit_per_unit) * self.lots * self.lot_size,
        )

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


@dataclass
class OpenDirectionalOptionPosition:
    underlying_symbol: str
    option: Instrument  # the long CE/PE bought
    breakout_direction: str  # "long" (bought CE) | "short" (bought PE)
    lots: int
    lot_size: int
    entry_premium: float
    opened_at: datetime
    strategy_tag: str
    assigned_table: str
    prediction_record: TradePredictionRecord | None = None
    #: B23: excursion + ratcheting profit lock (a bought option profits as the premium RISES).
    excursion: PositionProfitExcursion = dc_field(default_factory=PositionProfitExcursion)
    profit_trail: ProfitTrailState = dc_field(default_factory=ProfitTrailState)
    #: research/171: ITM/ATM/OTM — the moneyness of THIS strike, so the ladder coexists per underlying
    #: (the position store is keyed by underlying|moneyness) and each moneyness earns its own edge verdict.
    moneyness: str = "ATM"

    def unrealized_pnl(self, price_by_token: dict) -> float | None:
        ltp = price_by_token.get(self.option.instrument_token)
        if ltp is None:
            return None
        return (ltp - self.entry_premium) * self.lots * self.lot_size

    def observe_and_advance_trail(self, price_by_token: dict) -> None:
        self.excursion.observe_unrealised_profit(self.unrealized_pnl(price_by_token))
        self.profit_trail = update_profit_trail(
            self.profit_trail,
            peak_profit=self.excursion.maximum_favourable_profit,
            # Max loss on a bought option IS the premium paid — an exact, not approximate, 1R.
            initial_risk_amount=self.entry_premium * self.lots * self.lot_size,
            entry_notional=self.entry_premium * self.lots * self.lot_size,
        )


def option_arm_trade_id(underlying_symbol: str, opened_at: datetime) -> str:
    """B18 step 6: a trade key that exists at OPEN time (the experiment id needs the CLOSE time).

    One open option position per underlying is enforced upstream, so underlying+open-instant is
    unique. It must be reproducible from the position object at close, which is why it is derived
    rather than random.
    """
    return f"{underlying_symbol}|{opened_at.isoformat()}"


def _intraday_drift_bias(spot_bars) -> CreditSpreadBias:
    """Mild up-drift → sell a put spread (bullish); down-drift → sell a call
    spread (bearish) — the range-bound premium-collection play either way."""
    today = [b for b in spot_bars if b.timestamp.date() == spot_bars[-1].timestamp.date()]
    if len(today) >= 2 and today[-1].close_price >= today[0].open_price:
        return CreditSpreadBias.BULLISH_SELL_PUT_SPREAD
    return CreditSpreadBias.BEARISH_SELL_CALL_SPREAD


def _nearest_expiry_options_for_underlying(
    option_ladder, underlying_symbol: str
) -> list:
    """The subset of one underlying's contracts on its OWN nearest listed expiry.

    B34: the tradable universe now carries EVERY expiry (`select_full_option_universe`), so any ATM
    pick over the raw per-underlying list would compare strikes across DIFFERENT expiries and could
    return an arbitrary-expiry contract (a hidden calendar mix). Scoping to the single nearest expiry
    first keeps every ATM/IV pick same-expiry-correct on the full universe. The credit-spread leg
    selector already does its own nearest-expiry scoping; this gives the ATM/directional helpers the
    same guarantee."""
    underlying_options = [
        o for o in option_ladder
        if o.underlying_symbol == underlying_symbol and o.expiry_date is not None
    ]
    if not underlying_options:
        return []
    nearest_expiry = min(o.expiry_date for o in underlying_options)
    return [o for o in underlying_options if o.expiry_date == nearest_expiry]


def _atm_call_implied_volatility(
    option_ladder, underlying_symbol, spot_price, price_by_token, now
) -> float | None:
    # B34: scope to the underlying's nearest expiry BEFORE the ATM pick — the full universe holds
    # many expiries, and IV must be read off one coherent expiry (its own days_to_expiry).
    calls = [
        o for o in _nearest_expiry_options_for_underlying(option_ladder, underlying_symbol)
        if o.option_right.value == "CE"
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


#: B8: how long before an option underlying is worth examining again. A full sweep of the ~215
#: underlyings takes ~7 min at 25 looks/pass, so a 5-minute cooldown yields continuous, roughly
#: non-overlapping re-looking — ~10+ looks per underlying across a 6.25h session instead of ONE.
#: The old behaviour (a permanent skip set) spent every underlying's single look in the first ~7
#: minutes after the open, when no opening-range breakout can exist yet.
OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS: float = 300.0


def select_option_underlyings_due_for_look(
    candidate_underlying_symbols: Iterable[str],
    last_look_at_by_underlying: Mapping[str, datetime],
    underlyings_with_open_positions: AbstractSet[str],
    now: datetime,
    maximum_looks_this_pass: int,
    relook_interval_seconds: float = OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS,
) -> list[str]:
    """Which option underlyings should be examined this pass — LEAST-RECENTLY-LOOKED first.

    Pure, so the scheduling policy is testable without a feed, a clock, or a broker.

    Ordering matters as much as the cooldown: the previous code walked `sorted(...)`, so with a
    per-pass budget of 25 against ~215 underlyings a naive repeat scheme would keep re-examining the
    A-names and starve the tail — the same starvation shape as the cash-scanner deadlock (B1), just
    in a different disguise. Least-recently-looked-first makes the sweep round-robin: every
    underlying is examined once before any is examined twice. Never-looked underlyings sort first;
    ties break alphabetically so the order is deterministic.
    """
    due: list[tuple[float, str]] = []
    for underlying_symbol in candidate_underlying_symbols:
        if underlying_symbol in underlyings_with_open_positions:
            continue  # already holding risk in this underlying — never re-seed it
        last_look_at = last_look_at_by_underlying.get(underlying_symbol)
        if last_look_at is None:
            due.append((float("-inf"), underlying_symbol))  # never looked at — highest priority
            continue
        seconds_since_look = (now - last_look_at).total_seconds()
        if seconds_since_look < relook_interval_seconds:
            continue  # examined too recently — respect the fetch budget
        due.append((-seconds_since_look, underlying_symbol))

    due.sort(key=lambda staleness_and_symbol: (staleness_and_symbol[0], staleness_and_symbol[1]))
    return [underlying_symbol for _, underlying_symbol in due[:max(0, maximum_looks_this_pass)]]


def try_open_option_position_for_underlying(
    state,
    underlying_symbol: str,
    spot_instrument: Instrument,
    option_ladder: list,
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    banned_underlying_symbols: frozenset = frozenset(),
) -> bool:
    """Regime-dispatch one underlying: RANGE_BOUND → defined-risk credit
    spread; TRENDING → directional ATM long option on an ORB breakout;
    INDECISIVE → stand aside. Returns True if any option position opened.

    B8: this no longer marks the underlying as seeded — the caller records the look BEFORE
    dispatching, so the mark survives an early return or an exception.
    """
    spot_bars = live_universe_feed.recent_intraday_bars(
        spot_instrument, now, bar_interval=BarInterval.MINUTE_5
    )
    if len(spot_bars) < 28:
        state.record_option_entry_outcome(
            underlying_symbol, "insufficient_bars", f"{len(spot_bars)} bars", now
        )
        return False
    adx_value = _regime_adx_warmed_at(spot_bars, spot_bars[-1].timestamp)
    if adx_value is None:
        # B31: the regime is UNMEASURED, not range-bound. Trading here would file the outcome under
        # a fabricated regime — which is the selector's context key, so it would poison the very
        # evidence the selector accumulates. Abstain; this underlying is re-looked next cycle (B8).
        state.entries_skipped_for_unmeasured_regime_count += 1
        state.record_option_entry_outcome(underlying_symbol, "regime_unmeasured", "", now)
        return False
    choice = choose_v1_session_strategy(adx_value)
    # B34: the universe now carries EVERY expiry. This (non-0-DTE) arm always trades the underlying's
    # nearest expiry — the credit-spread selector's `minimum_calendar_days_to_expiry=1` excludes only
    # today's expiry (0-DTE underlyings are routed away upstream), so the nearest listed expiry always
    # qualifies. Scoping the look to that one expiry keeps ATM/IV/leg picks same-expiry-correct AND
    # bounds pricing to ~one strike chain (e.g. ~248 NIFTY contracts, not all ~1,558 across 18
    # expiries) — the full chain of the nearest expiry, so the credit-spread hedge is finally
    # reachable (the old ATM±3 ladder was too short to place the bought hedge).
    underlying_options = _nearest_expiry_options_for_underlying(option_ladder, underlying_symbol)
    if not underlying_options:
        state.record_option_entry_outcome(underlying_symbol, "no_nearest_expiry_chain", "", now)
        return False
    price_by_token = live_universe_feed.latest_price_by_token(underlying_options)
    # B18.1b: record TODAY's ATM IV for EVERY underlying we look at, BEFORE the regime branch.
    # Recording it only inside the credit-spread branch would build a history sampled exclusively
    # from range-bound sessions — a biased series that makes "IV rank" meaningless, since trending
    # days (typically higher IV) would never enter the distribution. The inversion is computed here
    # anyway; it was previously discarded entirely.
    state.record_daily_atm_implied_volatility(
        underlying_symbol,
        now.date(),
        _atm_call_implied_volatility(
            underlying_options, underlying_symbol, spot_bars[-1].close_price, price_by_token, now
        ),
    )
    # B18 step 6: the ADX regime is now CONTEXT for the selector, not the router.
    # Two arms already exist in code — the directional ATM option and the defined-risk credit
    # spread. Rather than letting the regime hard-dispatch between them, the selector learns from
    # realised, cost-net outcomes which structure actually works in each (index, regime) cell. The
    # regime still constrains WHICH arms are eligible (a credit spread needs a non-trending tape),
    # so this widens the choice without inventing an unsupported one.
    selected_arm = state.select_option_arm(underlying_symbol, choice, now)
    if selected_arm == OPTION_ARM_DIRECTIONAL:
        return _try_open_directional_option(
            state, underlying_symbol, spot_instrument, spot_bars, underlying_options,
            price_by_token, adx_value, now, risk_budget,
        )
    if selected_arm != OPTION_ARM_CREDIT_SPREAD:
        state.record_option_entry_outcome(
            underlying_symbol, "no_eligible_arm", f"regime={choice.name}", now
        )
        return False

    spot_price = spot_bars[-1].close_price
    atm_iv = _atm_call_implied_volatility(
        underlying_options, underlying_symbol, spot_price, price_by_token, now
    )
    if atm_iv is None:
        state.record_option_entry_outcome(underlying_symbol, "credit_no_atm_iv", "", now)
        return False

    bias = _intraday_drift_bias(spot_bars)
    signal = select_credit_spread_legs(
        underlying_options, underlying_symbol, spot_price, atm_iv, bias, now.date()
    )
    if signal is None:
        state.record_option_entry_outcome(underlying_symbol, "credit_no_signal", "", now)
        return False
    decision = evaluate_credit_spread_signal(
        signal, banned_underlying_symbols, risk_budget
    )
    if not decision.approved:
        state.record_option_entry_outcome(
            underlying_symbol, "credit_risk_rejected",
            ",".join(r.name for r in decision.rejection_reasons), now,
        )
        return False

    # B7: the risk gate already sized this spread against the real budget — use it. The previous
    # hard-coded `lots = 1` discarded that and guaranteed the size-down levers floored it to zero.
    lots = decision.approved_quantity
    short_px = price_by_token.get(signal.short_leg.instrument.instrument_token)
    hedge_px = price_by_token.get(signal.hedge_leg.instrument.instrument_token)
    if short_px is None or hedge_px is None:
        state.record_option_entry_outcome(underlying_symbol, "credit_leg_price_missing", "", now)
        return False
    net_credit = short_px - hedge_px
    if net_credit <= 0:
        state.record_option_entry_outcome(
            underlying_symbol, "credit_net_credit_nonpositive", f"{net_credit:.2f}", now
        )
        return False  # a real credit spread must collect net premium

    # §9 record + antibody veto BEFORE placing any leg (Layer 10 slice 3).
    prediction_record = build_credit_spread_prediction_record(
        signal.short_leg.instrument, bias.value, adx_value, now.date()
    )
    prediction_record = state.apply_recalibration(prediction_record)
    if state.entry_decision_for_mechanism(prediction_record.mechanism_name) == "veto":
        state.record_option_entry_outcome(
            underlying_symbol, "credit_mechanism_vetoed", prediction_record.mechanism_name, now
        )
        return False
    # B16: the opponent ledger sizes down instead of refusing (it blocked every bullish entry).
    # B7: compose every size-down lever ONCE and apply it ONCE to the indivisible lot count.
    # Applying them stepwise with int() floored a 1-lot order to zero and blocked 100% of option
    # entries (docs/research/live_session_diagnosis_2026-07-27.md §7a).
    # task #4: keep every lever's value so a FLOOR is diagnosable per underlying (which lever, how much).
    is_index_option = signal.short_leg.instrument.kind is InstrumentKind.INDEX_OPTION
    positioning_multiplier = state.positioning_size_down(  # B16: graded opponent-ledger lever
        entry_is_bullish=bias is CreditSpreadBias.BULLISH_SELL_PUT_SPREAD,
        instrument_kind="index_option" if is_index_option else "stock_option",
    )
    debate_multiplier = state.debate_risk_size_multiplier(prediction_record.mechanism_name)
    index_level_multiplier = state.index_level_size_multiplier(underlying_symbol, spot_price)
    vitality_multiplier = state.organism_vitality_multiplier()
    workspace_multiplier = state.counted_workspace_caution_multiplier()
    composed_multiplier = compose_size_down_multipliers(
        positioning_multiplier, debate_multiplier, index_level_multiplier,
        vitality_multiplier, workspace_multiplier,
    )
    size_down_decision = size_down_discrete_lots(
        base_lots=lots, composed_multiplier=composed_multiplier,
    )
    size_down_detail = (
        f"base_lots={lots} composed={composed_multiplier:.3f} "
        f"[positioning={positioning_multiplier:.2f} debate={debate_multiplier:.2f} "
        f"index_level={index_level_multiplier:.2f} vitality={vitality_multiplier:.2f} "
        f"workspace={workspace_multiplier:.2f}]"
    )
    if not size_down_decision.permits_order:
        state.record_option_size_down_stand_aside(
            underlying_symbol, size_down_decision.stood_aside_reason
        )
        state.record_option_entry_outcome(
            underlying_symbol, "sized_down_to_zero", size_down_detail, now
        )
        return False
    lots = size_down_decision.granted_lots
    spread_segment = "nse_index_options" if is_index_option else "nse_stock_options"
    if not state.constitution_permits_order(spread_segment, is_option=True):
        state.record_option_entry_outcome(underlying_symbol, "gate_constitution", "", now)
        return False  # Trunk VII.6 constitutional Referee: order violates the constitution
    if not state.oversight_permits_autonomous_order(
        prediction_record.win_probability, is_option=True
    ):
        state.record_option_entry_outcome(
            underlying_symbol, "gate_oversight", f"wp={prediction_record.win_probability:.2f}", now
        )
        return False  # Trunk VII scalable oversight: beyond autonomous competence, escalated
    if not state.convergence_limiter_permits_order():
        state.record_option_entry_outcome(underlying_symbol, "gate_convergence", "", now)
        return False  # Trunk VII instrumental-convergence limiter: sprawl / off-switch dominance
    if not state.homeostat_permits_order():
        state.record_option_entry_outcome(underlying_symbol, "gate_homeostat", "", now)
        return False  # Trunk X: a VITAL organ has acutely failed
    if not state.power_budget_permits_order(now):
        state.record_option_entry_outcome(underlying_symbol, "gate_power_budget", "", now)
        return False  # Trunk VII power budget: daily action-throughput budget spent
    if not state.cost_gate_permits_credit_spread(
        spread_segment, short_px, hedge_px, signal.short_leg.instrument.lot_size, lots,
    ):
        state.record_option_entry_outcome(
            underlying_symbol, "gate_cost_below_breakeven", f"credit={net_credit:.2f}", now
        )
        return False  # REDESIGN L1 cost gate: net credit below both-leg round-trip breakeven

    # Open atomically (hedge BUY first) on the sim broker with real prices.
    for leg in (signal.short_leg, signal.hedge_leg):
        px = price_by_token.get(leg.instrument.instrument_token)
        state.simulated_broker.update_market_price(leg.instrument.instrument_token, px)
    intents = build_order_intents_for_credit_spread(signal, lots)
    report = execute_multi_leg_order_atomically(intents, state.simulated_broker)
    if not report.all_legs_executed:
        state.record_option_entry_outcome(underlying_symbol, "execution_incomplete", "", now)
        return False

    state.record_option_arm_trade_opened(
        option_arm_trade_id(underlying_symbol, now), OPTION_ARM_CREDIT_SPREAD,
        underlying_symbol, "credit_spread", now,
    )
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
        assigned_table=prediction_record.assigned_table.value,
        prediction_record=prediction_record,
    )
    state.record_option_entry_outcome(
        underlying_symbol, "opened_credit_spread", f"{lots}lot {bias.value}", now
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
    for _underlying_symbol, spread in list(state.open_option_spreads.items()):
        current = spread.current_net_premium_per_unit(price_by_token)
        if current is None:
            continue
        spread.observe_and_advance_trail(price_by_token)  # B23
        target = spread.entry_net_credit_per_unit * (1 - _PROFIT_TARGET_CREDIT_FRACTION)
        stop = spread.entry_net_credit_per_unit * _STOP_LOSS_CREDIT_MULTIPLE
        if not (current <= target or current >= stop) and trail_exit_triggered(
            spread.profit_trail, spread.unrealized_pnl(price_by_token)
        ):
            # B23: the trail only ever fires once armed, so it can never exit earlier than the
            # existing stop would have.
            _close_spread(
                state, spread, current, now, PaperSessionOutcome.EXITED_TARGET,
                exited_on_profit_trail=True,
            )
            closed += 1
            continue
        if current <= target or current >= stop:
            outcome = (
                PaperSessionOutcome.EXITED_TARGET if current <= target
                else PaperSessionOutcome.EXITED_STOP
            )
            _close_spread(state, spread, current, now, outcome)
            closed += 1
    return closed


def select_directional_strike(candidates, spot_price, want_right, moneyness, ladder_steps=1):
    """Pick ONE strike off the ladder by moneyness (research/171). ATM = nearest to spot; ITM =
    `ladder_steps` toward the money, OTM = away — direction depends on the right (CE: ITM below spot / OTM
    above; PE: ITM above / OTM below). Clamps to the available strikes; None if no candidates."""
    from nse_algo_trader.strategy_engine import OptionMoneyness

    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda o: o.strike_price)
    atm_index = min(range(len(ordered)), key=lambda i: abs(ordered[i].strike_price - spot_price))
    if moneyness is OptionMoneyness.AT_THE_MONEY:
        return ordered[atm_index]
    toward_money = -1 if want_right == "CE" else +1  # CE ITM = lower strike; PE ITM = higher strike
    step = toward_money if moneyness is OptionMoneyness.IN_THE_MONEY else -toward_money
    index = max(0, min(len(ordered) - 1, atm_index + step * max(1, ladder_steps)))
    return ordered[index]


def directional_moneyness_for_conviction(adx_value):
    """Moneyness by trend conviction (reuses the 27/30 ADX bands, no new thresholds): a stronger trend
    justifies the cheaper, more-leveraged OTM; a weaker trend takes the delta-safer ITM; the middle takes
    ATM. Spreads directional buys across ITM/ATM/OTM organically by each underlying's own trend strength."""
    from nse_algo_trader.strategy_engine import OptionMoneyness

    if adx_value >= 30.0:
        return OptionMoneyness.OUT_OF_THE_MONEY
    if adx_value >= 27.0:
        return OptionMoneyness.AT_THE_MONEY
    return OptionMoneyness.IN_THE_MONEY


def _try_open_directional_option(
    state, underlying_symbol, spot_instrument, spot_bars, underlying_options,
    price_by_token, adx_value, now, risk_budget: RiskBudgetConfig,
) -> bool:
    """Trending underlying: on an ORB breakout of the spot, BUY an ATM option
    in the breakout direction (CE up / PE down). Defined-risk = premium paid.
    This is what gives trending indices (and stocks) option trades."""
    today = [b for b in spot_bars if b.timestamp.date() == spot_bars[-1].timestamp.date()]
    if not today:
        state.record_option_entry_outcome(underlying_symbol, "directional_no_today_bars", "", now)
        return False
    signal = detect_opening_range_breakout(
        today, spot_instrument, OpeningRangeBreakoutConfig()
    )
    if signal is None:
        # The trending-underlying arm is armed but the tape has not broken its opening range yet —
        # the single most common reason a trending INDEX shows no option trade early in a session.
        state.record_option_entry_outcome(underlying_symbol, "directional_no_breakout", "", now)
        return False
    want_right = "CE" if signal.direction is SignalDirection.LONG else "PE"
    spot_price = today[-1].close_price
    # B34: the full universe carries every expiry, so scope to the underlying's nearest expiry
    # before the ATM pick — a bought directional option must be one concrete expiry, not the closest
    # strike across a mixed-expiry list (which could buy a far-dated contract by accident).
    candidates = [
        o for o in _nearest_expiry_options_for_underlying(underlying_options, underlying_symbol)
        if o.option_right.value == want_right
    ]
    if not candidates:
        state.record_option_entry_outcome(underlying_symbol, "directional_no_candidates", "", now)
        return False
    from nse_algo_trader.strategy_engine import OptionMoneyness

    # research/171: trade the FULL moneyness ladder per breakout — ITM + ATM + OTM, both CE (up) and PE
    # (down), across index AND stock options. Each rung is a separate gated PAPER position keyed by
    # (underlying|moneyness) so all three coexist; validation decides which moneyness ever earns capital.
    opened_any = False
    for moneyness in (
        OptionMoneyness.IN_THE_MONEY, OptionMoneyness.AT_THE_MONEY, OptionMoneyness.OUT_OF_THE_MONEY,
    ):
        chosen = select_directional_strike(candidates, spot_price, want_right, moneyness)
        if chosen is None:
            continue
        if _open_one_directional_strike(
            state, underlying_symbol, chosen, signal, spot_price, adx_value, now, risk_budget,
            price_by_token, moneyness.value,
        ):
            opened_any = True
    if not opened_any:
        state.record_option_entry_outcome(underlying_symbol, "directional_no_strike_opened", "", now)
    return opened_any


def _open_one_directional_strike(
    state, underlying_symbol, chosen_option, signal, spot_price, adx_value, now, risk_budget,
    price_by_token, moneyness_label,
) -> bool:
    """Open ONE directional long option at `chosen_option` through every gate (research/171). Keyed by
    (underlying|moneyness) so the ITM/ATM/OTM ladder coexists per underlying. A per-rung gate failure
    returns False (that rung is skipped); the other rungs still try. Returns True iff this rung opened.

    Max loss on a bought option IS the premium paid, so the premium outlay per lot is both the risk and the
    margin for sizing."""
    premium = price_by_token.get(chosen_option.instrument_token)
    if premium is None or premium <= 0:
        return False
    premium_outlay_per_lot = premium * chosen_option.lot_size
    risk_approved_option_lots = size_defined_risk_spread_lots(
        worst_case_structural_loss_per_lot=premium_outlay_per_lot,
        estimated_margin_per_lot=premium_outlay_per_lot,
        config=risk_budget,
    )
    if risk_approved_option_lots < 1:
        return False
    prediction_record = build_directional_option_prediction_record(
        chosen_option, signal.direction.value, adx_value, now.date(),
        OpeningRangeBreakoutConfig().target_risk_reward_ratio,
    )
    prediction_record = state.apply_recalibration(prediction_record)
    if state.entry_decision_for_mechanism(prediction_record.mechanism_name) == "veto":
        return False
    is_index_option = chosen_option.kind is InstrumentKind.INDEX_OPTION
    composed_multiplier = compose_size_down_multipliers(
        state.positioning_size_down(
            entry_is_bullish=signal.direction is SignalDirection.LONG,
            instrument_kind="index_option" if is_index_option else "stock_option",
        ),
        state.debate_risk_size_multiplier(prediction_record.mechanism_name),
        state.index_level_size_multiplier(underlying_symbol, spot_price),
        state.organism_vitality_multiplier(),
        state.counted_workspace_caution_multiplier(),
    )
    size_down_decision = size_down_discrete_lots(
        base_lots=risk_approved_option_lots, composed_multiplier=composed_multiplier,
    )
    if not size_down_decision.permits_order:
        return False
    gated_option_lots = size_down_decision.granted_lots
    segment = "nse_index_options" if is_index_option else "nse_stock_options"
    if not state.constitution_permits_order(segment, is_option=True):
        return False
    if not state.oversight_permits_autonomous_order(prediction_record.win_probability, is_option=True):
        return False
    if not state.convergence_limiter_permits_order():
        return False
    if not state.homeostat_permits_order():
        return False
    if not state.power_budget_permits_order(now):
        return False
    state.simulated_broker.update_market_price(chosen_option.instrument_token, premium)
    from nse_algo_trader.broker_oms import OrderIntent, OrderLifecycleState, OrderSide

    fill = state.simulated_broker.place_order(
        OrderIntent(chosen_option, OrderSide.BUY, gated_option_lots * chosen_option.lot_size,
                    "directional_option_orb_v1")
    )
    if fill.state is OrderLifecycleState.REJECTED:
        return False
    position_key = f"{underlying_symbol}|{moneyness_label}"
    state.record_option_arm_trade_opened(
        option_arm_trade_id(position_key, now), OPTION_ARM_DIRECTIONAL,
        underlying_symbol, "opening_range_breakout", now,
    )
    state.open_directional_options[position_key] = OpenDirectionalOptionPosition(
        underlying_symbol=underlying_symbol,
        option=chosen_option,
        breakout_direction=signal.direction.value,
        lots=gated_option_lots,
        lot_size=chosen_option.lot_size,
        entry_premium=premium,
        opened_at=now,
        strategy_tag="directional_option_orb_v1",
        assigned_table=prediction_record.assigned_table.value,
        prediction_record=prediction_record,
        moneyness=moneyness_label,
    )
    state.record_option_entry_outcome(
        underlying_symbol, "opened_directional",
        f"{gated_option_lots}lot {signal.direction.value} {moneyness_label}", now,
    )
    return True


def _directional_assigned_table(adx_value: float) -> str:
    # A stronger trend (higher ADX) is a more confident directional play.
    if adx_value >= 30.0:
        return "confident_win"
    if adx_value >= 27.0:
        return "uncertain"
    return "confident_loss"


def manage_open_directional_options(state, live_universe_feed, now) -> int:
    if not state.open_directional_options:
        return 0
    options = [pos.option for pos in state.open_directional_options.values()]
    price_by_token = live_universe_feed.latest_price_by_token(options)
    closed = 0
    for _underlying_symbol, pos in list(state.open_directional_options.items()):
        ltp = price_by_token.get(pos.option.instrument_token)
        if ltp is None:
            continue
        pos.observe_and_advance_trail(price_by_token)  # B23
        target = pos.entry_premium * (1 + _DIRECTIONAL_TARGET_GAIN_FRACTION)
        stop = pos.entry_premium * (1 - _DIRECTIONAL_STOP_LOSS_FRACTION)
        if not (ltp >= target or ltp <= stop) and trail_exit_triggered(
            pos.profit_trail, pos.unrealized_pnl(price_by_token)
        ):
            _close_directional(
                state, pos, ltp, now, PaperSessionOutcome.EXITED_TARGET,
                exited_on_profit_trail=True,
            )
            closed += 1
            continue
        if ltp >= target or ltp <= stop:
            outcome = (
                PaperSessionOutcome.EXITED_TARGET if ltp >= target
                else PaperSessionOutcome.EXITED_STOP
            )
            _close_directional(state, pos, ltp, now, outcome)
            closed += 1
    return closed


def _record_option_experiment(
    state, prediction_record, instrument, quantity, entry_price, exit_price,
    realized, outcome, opened_at, closed_at, excursion=None, on_trail=False,
) -> None:
    """Grade the option's §9 prediction and emit a closed experiment (so option
    trades feed the §9 scoreboard AND Layer-10 memory, like cash — Rule I).

    B23c: `excursion` carries the position's MFE/MAE into the memory node. Without it the
    learning layer sees 0/0 for every option trade and cannot answer "do we exit too early?"
    for the options book at all — which is exactly what the first B23c deploy revealed."""
    if prediction_record is None:
        return
    graded = grade_prediction(prediction_record, realized)
    state.scoreboard.add_graded_prediction(graded)
    closed_trade = ClosedPaperTrade(
        instrument=instrument, direction=prediction_record.direction,
        quantity=quantity, entry_price=entry_price, exit_price=exit_price,
        realized_pnl=realized, outcome=outcome,
        opened_at=opened_at, closed_at=closed_at,
        maximum_favourable_profit=(
            excursion.maximum_favourable_profit if excursion is not None else 0.0
        ),
        maximum_adverse_profit=(
            excursion.maximum_adverse_profit if excursion is not None else 0.0
        ),
        exited_on_profit_trail=on_trail,
        total_fees=estimate_round_trip_cost(
            entry_price=entry_price, exit_price=exit_price, quantity=quantity,
            segment=(
                "nse_index_options"
                if instrument.kind is InstrumentKind.INDEX_OPTION
                else "nse_stock_options"
            ),
            # A credit spread is SOLD to open (credit received) and a bought option is BOUGHT to
            # open — the STT leg differs, so the direction must be passed, not assumed.
            opened_short=prediction_record.direction is not SignalDirection.LONG,
            trade_date=opened_at.date(),  # point-in-time option STT (0.10% pre-Apr-2026)
        ).total_cost,
    )
    state.closed_experiment_events.append(
        (graded, closed_trade, instrument.kind.value.lower())
    )


def _close_directional(
    state, pos, exit_premium, now,
    outcome=PaperSessionOutcome.SQUARED_OFF_AT_CLOSE,
    exited_on_profit_trail: bool = False,
) -> None:
    realized = (exit_premium - pos.entry_premium) * pos.lots * pos.lot_size
    state.realized_directional_option_pnl += realized
    state.closed_directional_options.append((pos, realized))
    state.resolve_option_arm_trade_closed(
        option_arm_trade_id(pos.underlying_symbol, pos.opened_at),
        realized - estimate_round_trip_cost(
            entry_price=pos.entry_premium, exit_price=exit_premium,
            quantity=pos.lots * pos.lot_size,
            segment=("nse_index_options" if pos.option.kind is InstrumentKind.INDEX_OPTION
                     else "nse_stock_options"),
            opened_short=False,  # a bought option is BOUGHT to open
            trade_date=pos.opened_at.date(),  # point-in-time option STT
        ).total_cost,
        now,
    )
    _record_option_experiment(
        state, pos.prediction_record, pos.option, pos.lots * pos.lot_size,
        pos.entry_premium, exit_premium, realized, outcome, pos.opened_at, now,
        excursion=pos.excursion, on_trail=exited_on_profit_trail,
    )
    del state.open_directional_options[f"{pos.underlying_symbol}|{pos.moneyness}"]


def square_off_all_directional_options(state, live_universe_feed, now) -> None:
    """Flatten every long option at 15:15 (a long option is sold to close —
    no naked-leg concern, but routed for consistency)."""
    if not state.open_directional_options:
        return
    options = [pos.option for pos in state.open_directional_options.values()]
    price_by_token = live_universe_feed.latest_price_by_token(options)
    for _underlying_symbol, pos in list(state.open_directional_options.items()):
        ltp = price_by_token.get(pos.option.instrument_token, pos.entry_premium)
        _close_directional(state, pos, ltp, now)


def _underlying_nearest_expiry_is_today(option_ladder, underlying_symbol: str, now) -> bool:
    """True iff this underlying's soonest listed option expiry is today (it is a 0-DTE underlying).
    Uses the same per-underlying nearest-expiry logic as the B9 ladder (each underlying independent)."""
    expiries = [
        o.expiry_date for o in option_ladder
        if o.underlying_symbol == underlying_symbol and o.expiry_date is not None
    ]
    return bool(expiries) and min(expiries) == now.date()


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
    from nse_algo_trader.paper_trading.zero_dte_expiry_day_live_path import (
        manage_open_zero_dte_positions_via_feed,
        try_open_zero_dte_for_underlying,
    )

    closed = manage_open_credit_spreads(state, live_universe_feed, now)
    closed += manage_open_directional_options(state, live_universe_feed, now)
    closed += manage_open_zero_dte_positions_via_feed(state, live_universe_feed, now)
    if is_square_off_window:
        square_off_all_open_spreads(state, live_universe_feed, now)
        square_off_all_directional_options(state, live_universe_feed, now)
        manage_open_zero_dte_positions_via_feed(
            state, live_universe_feed, now, is_square_off_window=True
        )
        return {"opened": 0, "closed": closed,
                "open": (len(state.open_option_spreads) + len(state.open_directional_options)
                         + len(state.open_zero_dte_positions))}

    option_ladder = list(tradable_universe.option_ladder_instruments)
    spot_by_underlying = tradable_universe.spot_instrument_by_option_underlying or {}
    opened = 0
    due_underlyings = select_option_underlyings_due_for_look(
        candidate_underlying_symbols=spot_by_underlying,
        last_look_at_by_underlying=state.last_option_look_at_by_underlying,
        underlyings_with_open_positions=(
            set(state.open_option_spreads) | set(state.open_directional_options)
        ),
        now=now,
        maximum_looks_this_pass=max_new_underlying_seeds_per_pass,
    )
    for underlying_symbol in due_underlyings:
        # B8: record the look in the PASS LOOP, before dispatching. A mark buried inside a function
        # that early-returns is a mark that does not happen (the B1 lesson) — and here it must also
        # survive an exception, or a raising underlying would be retried every pass forever.
        state.last_option_look_at_by_underlying[underlying_symbol] = now
        state.seeded_option_underlyings.add(underlying_symbol)
        state.option_underlying_look_count += 1
        # B32: an underlying whose NEAREST expiry is today is 0-DTE — route it EXCLUSIVELY to the
        # 0-DTE expiry-day engine (defined-risk structures across regimes), never also to the ORB /
        # credit-spread arms, so it is not traded twice on the same tape.
        is_zero_dte_underlying = _underlying_nearest_expiry_is_today(
            option_ladder, underlying_symbol, now
        )
        try:
            if is_zero_dte_underlying:
                if try_open_zero_dte_for_underlying(
                    state, underlying_symbol, spot_by_underlying[underlying_symbol],
                    option_ladder, live_universe_feed, now,
                ):
                    opened += 1
            elif try_open_option_position_for_underlying(
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
        # task #4: log the outcome for the 5 INDEX underlyings each look, so the live journal shows
        # exactly WHICH gate blocks index options (stocks fire, indices don't) — the diagnosis this
        # instrumentation exists for. Stock outcomes stay in-state only (would flood the log).
        if underlying_symbol in _INDEX_OPTION_UNDERLYING_SYMBOLS_FOR_LOG:
            outcome = state.option_entry_outcome_by_underlying.get(underlying_symbol, {})
            print(
                f"[option-entry] INDEX {underlying_symbol}: {outcome.get('reason','?')} "
                f"{outcome.get('detail','')}".rstrip(),
                flush=True,
            )
    return {"opened": opened, "closed": closed,
            "open": (len(state.open_option_spreads) + len(state.open_directional_options)
                     + len(state.open_zero_dte_positions))}


def _close_spread(
    state, spread, exit_net_premium, now,
    outcome=PaperSessionOutcome.SQUARED_OFF_AT_CLOSE,
    exited_on_profit_trail: bool = False,
) -> None:
    realized = (
        (spread.entry_net_credit_per_unit - exit_net_premium)
        * spread.lots * spread.lot_size
    )
    state.realized_option_spread_pnl += realized
    state.closed_option_spreads.append((spread, realized))
    # B18 step 6: the reward the selector learns from is COST-NET (B28), not gross.
    state.resolve_option_arm_trade_closed(
        option_arm_trade_id(spread.underlying_symbol, spread.opened_at),
        realized - estimate_round_trip_cost(
            entry_price=spread.entry_net_credit_per_unit, exit_price=exit_net_premium,
            quantity=spread.lots * spread.lot_size,
            segment=("nse_index_options"
                     if spread.short_leg.kind is InstrumentKind.INDEX_OPTION
                     else "nse_stock_options"),
            opened_short=True,   # a credit spread is SOLD to open
            trade_date=spread.opened_at.date(),  # point-in-time option STT
        ).total_cost,
        now,
    )
    _record_option_experiment(
        state, spread.prediction_record, spread.short_leg,
        spread.lots * spread.lot_size, spread.entry_net_credit_per_unit,
        exit_net_premium, realized, outcome, spread.opened_at, now,
        excursion=spread.excursion, on_trail=exited_on_profit_trail,
    )
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
    for _underlying_symbol, spread in list(state.open_option_spreads.items()):
        current = spread.current_net_premium_per_unit(price_by_token)
        _close_spread(
            state, spread,
            current if current is not None else spread.entry_net_credit_per_unit,
            now,
        )
