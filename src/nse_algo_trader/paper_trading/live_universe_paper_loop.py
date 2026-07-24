"""The universe-wide live paper loop — positions open and stay OPEN.

Unlike the replay engine (`opening_range_breakout_paper_engine`), which
force-closes every trade at the last bar because the session is already
over, this loop runs *during* the open session: it opens positions and
holds them OPEN across scan passes, managing each against the live price
until its stop/target hits — or until 15:15, when Layer 8 flattens
everything (safe-ordered, never a naked leg). That is why the dashboard
was showing no "open" trades: nothing was ever held open. (docs/research/38)

One scan pass (`run_live_universe_scan_pass`) does, in order:
1. Price the whole universe (one batched-LTP call via the live feed).
2. Manage every open position against its live price -> exit on stop/target.
3. Seed a bounded batch of not-yet-seeded cash instruments: fetch today's
   bars, run the real ORB detector, and either open a held position or —
   if the breakout already stopped/targeted earlier today — record it as a
   completed trade (the per-instrument replay-to-live catch-up).
4. From 15:15 IST, square off every open position through Layer 8.

Paper only: fills are simulated, capital is virtual. The live/real-money
consumer is a separate, market-gated path (PLAN §1.4) not built here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

from nse_algo_trader.broker_oms import OrderSide, SimulatedBrokerClient
from nse_algo_trader.indicators.average_directional_index import (
    compute_average_directional_index,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.opening_range_breakout_paper_engine import (
    PaperSessionOutcome,
)
from nse_algo_trader.paper_trading.paper_trading_ledger import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import (
    PredictionTableScoreboard,
    build_orb_prediction_record,
    grade_prediction,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    TradePredictionRecord,
)
from nse_algo_trader.risk_management import (
    RiskBudgetConfig,
    evaluate_opening_range_breakout_signal,
)
from nse_algo_trader.session_management import (
    IntradaySquareOffSchedule,
    OpenPositionLeg,
    execute_intraday_square_off,
)
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutConfig,
    SignalDirection,
    detect_opening_range_breakout,
)
from nse_algo_trader.universe_registry import Instrument

_FORCED_SQUARE_OFF_TIME_IST = time(15, 15)


@dataclass
class OpenPaperPosition:
    instrument: Instrument
    direction: SignalDirection
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    opened_at: datetime
    strategy_tag: str
    prediction_record: TradePredictionRecord

    def has_hit_stop_or_target(self, price: float) -> PaperSessionOutcome | None:
        if self.direction is SignalDirection.LONG:
            if price <= self.stop_loss_price:
                return PaperSessionOutcome.EXITED_STOP
            if price >= self.target_price:
                return PaperSessionOutcome.EXITED_TARGET
        else:
            if price >= self.stop_loss_price:
                return PaperSessionOutcome.EXITED_STOP
            if price <= self.target_price:
                return PaperSessionOutcome.EXITED_TARGET
        return None


@dataclass
class ClosedPaperTrade:
    instrument: Instrument
    direction: SignalDirection
    quantity: int
    entry_price: float
    exit_price: float
    realized_pnl: float
    outcome: PaperSessionOutcome
    opened_at: datetime
    closed_at: datetime


@dataclass
class LiveUniversePaperState:
    """All mutable state of the loop, so a scan pass is a pure step over it."""

    ledger: PaperTradingLedger
    scoreboard: PredictionTableScoreboard
    simulated_broker: SimulatedBrokerClient = field(
        default_factory=SimulatedBrokerClient
    )
    open_positions: dict[int, OpenPaperPosition] = field(default_factory=dict)
    closed_trades: list[ClosedPaperTrade] = field(default_factory=list)
    seeded_cash_tokens: set[int] = field(default_factory=set)
    # Positions Layer 8 could NOT flatten (surfaced CRITICAL, never dropped).
    unflattened_square_off_positions: list[OpenPaperPosition] = field(
        default_factory=list
    )
    # Seeded cash names with no breakout YET — watched for a later intraday
    # breakout of their cached opening range (token -> WatchedOpeningRange).
    watched_opening_ranges: dict = field(default_factory=dict)
    # Options credit-spread path (one spread per underlying at a time).
    open_option_spreads: dict = field(default_factory=dict)
    seeded_option_underlyings: set = field(default_factory=set)
    closed_option_spreads: list = field(default_factory=list)
    realized_option_spread_pnl: float = 0.0
    # Directional long-option path (trending underlyings; one per underlying).
    open_directional_options: dict = field(default_factory=dict)
    closed_directional_options: list = field(default_factory=list)
    realized_directional_option_pnl: float = 0.0

    def open_position_count(self) -> int:
        return len(self.open_positions)

    def open_positions_snapshot(self) -> list[OpenPaperPosition]:
        return list(self.open_positions.values())


@dataclass
class ScanPassReport:
    scanned_price_count: int
    newly_seeded_count: int
    newly_opened_count: int
    closed_this_pass_count: int
    open_position_count: int
    squared_off_at_close: bool


def _regime_adx_warmed_at(recent_bars: list[PriceBar], at_timestamp) -> float:
    """ADX at (or just before) the breakout, warmed over the whole multi-day
    window — ADX needs ~2×period bars, which today's ~20 intraday bars alone
    cannot supply. Returns 0.0 if still unwarmed."""
    if len(recent_bars) < 28:
        return 0.0
    adx_series = compute_average_directional_index(recent_bars)
    warmed_before = [
        adx_series.adx[index]
        for index, bar in enumerate(recent_bars)
        if bar.timestamp <= at_timestamp and adx_series.adx[index] is not None
    ]
    return warmed_before[-1] if warmed_before else 0.0


def _open_position_from_signal(
    state: LiveUniversePaperState,
    signal,
    quantity: int,
    prediction_record: TradePredictionRecord,
    opened_at: datetime,
) -> None:
    entry_side = (
        OrderSide.BUY if signal.direction is SignalDirection.LONG else OrderSide.SELL
    )
    state.simulated_broker.update_market_price(
        signal.instrument.instrument_token, signal.breakout_close_price
    )
    state.ledger.record_fill(
        signal.instrument.instrument_token,
        entry_side,
        quantity,
        signal.breakout_close_price,
    )
    state.open_positions[signal.instrument.instrument_token] = OpenPaperPosition(
        instrument=signal.instrument,
        direction=signal.direction,
        quantity=quantity,
        entry_price=signal.breakout_close_price,
        stop_loss_price=signal.stop_loss_price,
        target_price=signal.target_price,
        opened_at=opened_at,
        strategy_tag=signal.strategy_tag,
        prediction_record=prediction_record,
    )


def _close_position(
    state: LiveUniversePaperState,
    position: OpenPaperPosition,
    exit_price: float,
    outcome: PaperSessionOutcome,
    closed_at: datetime,
) -> None:
    exit_side = (
        OrderSide.SELL if position.direction is SignalDirection.LONG else OrderSide.BUY
    )
    recorded = state.ledger.record_fill(
        position.instrument.instrument_token, exit_side, position.quantity, exit_price
    )
    state.closed_trades.append(
        ClosedPaperTrade(
            instrument=position.instrument,
            direction=position.direction,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            realized_pnl=recorded.realized_pnl_from_this_fill,
            outcome=outcome,
            opened_at=position.opened_at,
            closed_at=closed_at,
        )
    )
    state.scoreboard.add_graded_prediction(
        grade_prediction(position.prediction_record, recorded.realized_pnl_from_this_fill)
    )
    del state.open_positions[position.instrument.instrument_token]


def _manage_open_positions_against_prices(
    state: LiveUniversePaperState,
    latest_price_by_token: dict[int, float],
    now: datetime,
) -> int:
    closed_count = 0
    for token, position in list(state.open_positions.items()):
        price = latest_price_by_token.get(token)
        if price is None:
            continue
        outcome = position.has_hit_stop_or_target(price)
        if outcome is None:
            continue
        exit_price = (
            position.stop_loss_price
            if outcome is PaperSessionOutcome.EXITED_STOP
            else position.target_price
        )
        _close_position(state, position, exit_price, outcome, now)
        closed_count += 1
    return closed_count


@dataclass
class WatchedOpeningRange:
    instrument: Instrument
    opening_range_high: float
    opening_range_low: float
    regime_adx: float
    target_risk_reward_ratio: float


def _cache_opening_range_for_watch(
    state, instrument, session_bars, recent_bars, strategy_config, now
) -> None:
    """Cache the opening-range high/low of a seeded-no-signal name so later
    passes can catch an intraday breakout from live LTP."""
    from datetime import timedelta

    session_open = session_bars[0].timestamp
    range_end = session_open + timedelta(minutes=strategy_config.opening_range_minutes)
    opening_bars = [b for b in session_bars if b.timestamp < range_end]
    if len(opening_bars) < 1:
        return
    # Past the latest-entry cutoff -> no point watching.
    if now.timetz().replace(tzinfo=None) >= strategy_config.latest_entry_time_ist:
        return
    state.watched_opening_ranges[instrument.instrument_token] = WatchedOpeningRange(
        instrument=instrument,
        opening_range_high=max(b.high_price for b in opening_bars),
        opening_range_low=min(b.low_price for b in opening_bars),
        regime_adx=_regime_adx_warmed_at(recent_bars, recent_bars[-1].timestamp),
        target_risk_reward_ratio=strategy_config.target_risk_reward_ratio,
    )


def check_watched_names_for_live_breakout(
    state: LiveUniversePaperState,
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    strategy_config: OpeningRangeBreakoutConfig,
) -> int:
    """Each pass: price the watched names and open a position on any that
    have now broken their cached opening range (live-LTP breakout). Returns
    the number opened."""
    if not state.watched_opening_ranges:
        return 0
    if now.timetz().replace(tzinfo=None) >= strategy_config.latest_entry_time_ist:
        state.watched_opening_ranges.clear()
        return 0
    watched = list(state.watched_opening_ranges.values())
    price_by_token = live_universe_feed.latest_price_by_token(
        [w.instrument for w in watched]
    )
    opened = 0
    for watch in watched:
        token = watch.instrument.instrument_token
        if token in state.open_positions:
            state.watched_opening_ranges.pop(token, None)
            continue
        ltp = price_by_token.get(token)
        if ltp is None:
            continue
        direction = None
        if ltp > watch.opening_range_high:
            direction = SignalDirection.LONG
        elif ltp < watch.opening_range_low:
            direction = SignalDirection.SHORT
        if direction is None:
            continue
        if _open_watched_breakout(state, watch, direction, ltp, risk_budget, now):
            opened += 1
        state.watched_opening_ranges.pop(token, None)
    return opened


def _open_watched_breakout(state, watch, direction, ltp, risk_budget, now) -> bool:
    from nse_algo_trader.strategy_engine import OpeningRangeBreakoutSignal

    stop = watch.opening_range_low if direction is SignalDirection.LONG else watch.opening_range_high
    risk_per_unit = abs(ltp - stop)
    if risk_per_unit <= 0:
        return False
    target = (
        ltp + watch.target_risk_reward_ratio * risk_per_unit
        if direction is SignalDirection.LONG
        else ltp - watch.target_risk_reward_ratio * risk_per_unit
    )
    signal = OpeningRangeBreakoutSignal(
        instrument=watch.instrument,
        direction=direction,
        triggered_at=now,
        breakout_close_price=ltp,
        opening_range_high=watch.opening_range_high,
        opening_range_low=watch.opening_range_low,
        stop_loss_price=stop,
        target_price=target,
        strategy_tag="opening_range_breakout_v1",
    )
    risk_decision = evaluate_opening_range_breakout_signal(signal, risk_budget)
    if not risk_decision.approved or risk_decision.approved_quantity <= 0:
        return False
    prediction_record = build_orb_prediction_record(
        signal=signal, adx_value=watch.regime_adx, session_date=now.date(),
        target_reward_multiple=watch.target_risk_reward_ratio,
    )
    _open_position_from_signal(
        state, signal, risk_decision.approved_quantity, prediction_record, now
    )
    return True


def _seed_cash_instrument_from_orb(
    state: LiveUniversePaperState,
    instrument: Instrument,
    recent_bars: list[PriceBar],
    risk_budget: RiskBudgetConfig,
    strategy_config: OpeningRangeBreakoutConfig,
    now: datetime,
) -> bool:
    """Run the ORB detector over TODAY's bars (a slice of `recent_bars`),
    with the regime ADX warmed over the whole multi-day window. If a
    breakout fires and passes the risk gate, either open a held position or
    — if it already stopped/targeted earlier today — record the completed
    trade. Returns True if a position was opened (still open)."""
    state.seeded_cash_tokens.add(instrument.instrument_token)
    today = now.astimezone(recent_bars[0].timestamp.tzinfo).date()
    session_bars = [bar for bar in recent_bars if bar.timestamp.date() == today]
    if not session_bars:
        return False
    signal = detect_opening_range_breakout(session_bars, instrument, strategy_config)
    if signal is None:
        # No breakout at seed time -> cache the opening range and watch live
        # LTP for a later intraday breakout (post-seed breakout watch).
        _cache_opening_range_for_watch(
            state, instrument, session_bars, recent_bars, strategy_config, now
        )
        return False
    risk_decision = evaluate_opening_range_breakout_signal(signal, risk_budget)
    if not risk_decision.approved or risk_decision.approved_quantity <= 0:
        return False

    prediction_record = build_orb_prediction_record(
        signal=signal,
        adx_value=_regime_adx_warmed_at(recent_bars, signal.triggered_at),
        session_date=session_bars[0].timestamp.date(),
        target_reward_multiple=strategy_config.target_risk_reward_ratio,
    )
    _open_position_from_signal(
        state, signal, risk_decision.approved_quantity, prediction_record, signal.triggered_at
    )
    position = state.open_positions[instrument.instrument_token]

    # Catch up on the part of today already elapsed: if the breakout already
    # hit stop/target in a later bar, close it there instead of holding.
    for bar in session_bars:
        if bar.timestamp <= signal.triggered_at:
            continue
        outcome = None
        if position.direction is SignalDirection.LONG:
            if bar.low_price <= position.stop_loss_price:
                outcome = PaperSessionOutcome.EXITED_STOP
            elif bar.high_price >= position.target_price:
                outcome = PaperSessionOutcome.EXITED_TARGET
        else:
            if bar.high_price >= position.stop_loss_price:
                outcome = PaperSessionOutcome.EXITED_STOP
            elif bar.low_price <= position.target_price:
                outcome = PaperSessionOutcome.EXITED_TARGET
        if outcome is not None:
            exit_price = (
                position.stop_loss_price
                if outcome is PaperSessionOutcome.EXITED_STOP
                else position.target_price
            )
            _close_position(state, position, exit_price, outcome, bar.timestamp)
            return False
    return True


def square_off_all_open_positions(
    state: LiveUniversePaperState,
    latest_price_by_token: dict[int, float],
    now: datetime,
) -> None:
    """Flatten every open position through Layer 8 — safe-ordered
    (BUY-to-cover before SELL-to-close), never a naked leg. This is the
    loop that finally consumes Layer 8 (Rule G)."""
    if not state.open_positions:
        return
    open_legs = []
    for position in state.open_positions.values():
        signed_quantity = (
            position.quantity
            if position.direction is SignalDirection.LONG
            else -position.quantity
        )
        open_legs.append(
            OpenPositionLeg(position.instrument, signed_quantity, position.strategy_tag)
        )
        exit_price = latest_price_by_token.get(
            position.instrument.instrument_token, position.entry_price
        )
        state.simulated_broker.update_market_price(
            position.instrument.instrument_token, exit_price
        )
    report = execute_intraday_square_off(open_legs, state.simulated_broker)
    # Honor Layer 8's guarantee: only book positions that ACTUALLY flattened.
    # A leg Layer 8 could not flatten stays OPEN and is surfaced as unflattened
    # (never silently booked closed) — the exact failure mode L8 exists to catch.
    unflattened_tokens = {
        leg.instrument.instrument_token for leg in report.unflattened_legs
    }
    for position in list(state.open_positions.values()):
        if position.instrument.instrument_token in unflattened_tokens:
            state.unflattened_square_off_positions.append(position)
            continue
        exit_price = latest_price_by_token.get(
            position.instrument.instrument_token, position.entry_price
        )
        _close_position(
            state, position, exit_price, PaperSessionOutcome.SQUARED_OFF_AT_CLOSE, now
        )


def run_live_universe_scan_pass(
    state: LiveUniversePaperState,
    cash_universe: list[Instrument],
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    max_new_cash_seeds_per_pass: int = 300,
    strategy_config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
    square_off_schedule: IntradaySquareOffSchedule = IntradaySquareOffSchedule(
        forced_square_off_time_ist=_FORCED_SQUARE_OFF_TIME_IST
    ),
    market_clock=None,
) -> ScanPassReport:
    # Only open positions need live prices (for stop/target management and
    # square-off); ORB entry reads today's bars, not LTP. Pricing just the
    # held set keeps each pass cheap so a background thread never stalls.
    open_instruments = [
        position.instrument for position in state.open_positions.values()
    ]
    latest_price_by_token = (
        live_universe_feed.latest_price_by_token(open_instruments)
        if open_instruments
        else {}
    )

    closed_this_pass = _manage_open_positions_against_prices(
        state, latest_price_by_token, now
    )

    # Post-seed breakout watch: open any watched name that has now broken its
    # cached opening range on live LTP.
    check_watched_names_for_live_breakout(
        state, live_universe_feed, risk_budget, now, strategy_config
    )

    # Force square-off window: flatten everything, seed nothing more.
    should_square_off = (
        market_clock is not None
        and square_off_schedule.should_force_square_off_now(now, market_clock)
    )
    if should_square_off:
        square_off_all_open_positions(state, latest_price_by_token, now)
        return ScanPassReport(
            scanned_price_count=len(latest_price_by_token),
            newly_seeded_count=0,
            newly_opened_count=0,
            closed_this_pass_count=closed_this_pass,
            open_position_count=state.open_position_count(),
            squared_off_at_close=True,
        )

    newly_seeded = 0
    newly_opened = 0
    for instrument in cash_universe:
        if newly_seeded >= max_new_cash_seeds_per_pass:
            break
        if instrument.instrument_token in state.seeded_cash_tokens:
            continue
        if instrument.instrument_token in state.open_positions:
            continue
        recent_bars = live_universe_feed.recent_intraday_bars(
            instrument, now, bar_interval=BarInterval.MINUTE_5
        )
        newly_seeded += 1
        if not recent_bars:
            continue
        opened = _seed_cash_instrument_from_orb(
            state, instrument, recent_bars, risk_budget, strategy_config, now
        )
        if opened:
            newly_opened += 1

    return ScanPassReport(
        scanned_price_count=len(latest_price_by_token),
        newly_seeded_count=newly_seeded,
        newly_opened_count=newly_opened,
        closed_this_pass_count=closed_this_pass,
        open_position_count=state.open_position_count(),
        squared_off_at_close=False,
    )
