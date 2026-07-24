"""Always-on background service that runs the live universe paper loop.

The dashboard OBSERVES this; it does not drive it. A single writer thread
advances `run_live_universe_scan_pass` continuously during market hours —
seeding more of the universe each pass and managing open positions on live
prices — and after each pass publishes an immutable snapshot of the current
open positions + scoreboard. The dashboard reads only that published
snapshot, so the slow historical-seeding pass never blocks a page load, and
there is exactly one mutator of the loop state (no read/write races).

Paper only: simulated fills, virtual capital (PLAN §1.4). When the market is
closed the loop idles here (replay-when-closed is a later slice); live
real-money trading is a separate, market-gated consumer, not this service.
"""

from __future__ import annotations

import threading
import time as time_module
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.config_enforced_paper_run import (
    is_orb_cash_trading_enabled,
    map_control_config_to_risk_budget,
)
from nse_algo_trader.dashboard.dashboard_read_model import (
    PaperTradingSummary,
    PredictionTableSummary,
    StrategyReadinessSummary,
)
from nse_algo_trader.memory_reflection import (
    SqliteExperienceMemory,
    build_closed_experiment,
)
from nse_algo_trader.paper_trading.combinatorial_purged_cross_validation import (
    CpcvConfig,
    evaluate_strategy_with_cpcv_gate,
)
from nse_algo_trader.paper_trading.strategy_promotion_gate import (
    StrategyPromotionConfig,
)
from nse_algo_trader.dashboard.trading_control_config import (
    TradableSegment,
    load_trading_control_config,
)
from nse_algo_trader.market_data import KiteLiveUniverseFeed, MarketDataSqliteStore
from nse_algo_trader.paper_trading import (
    LiveUniversePaperState,
    PaperTradingLedger,
    run_live_universe_scan_pass,
)
from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock
from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
    advance_option_credit_spread_pass,
)
from nse_algo_trader.session_management import IntradaySquareOffSchedule
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictionLabeledTable,
)
from nse_algo_trader.universe_registry import fetch_live_tradable_universe

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class OpenPositionView:
    trading_symbol: str
    direction: str
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    last_price: float | None
    unrealized_pnl: float | None
    assigned_table: str
    segment: str = "cash"  # cash | index_option | stock_option


@dataclass(frozen=True)
class SegmentBoard:
    segment: str
    open_count: int
    unrealized_pnl: float


@dataclass(frozen=True)
class ClosedTradeView:
    segment: str
    trading_symbol: str
    direction: str
    realized_pnl: float
    outcome: str
    closed_at: str


@dataclass(frozen=True)
class LivePaperPublishedSnapshot:
    open_positions: tuple[OpenPositionView, ...]
    closed_trade_count: int
    cash_universe_size: int
    seeded_count: int
    last_pass_at: str | None
    is_market_open: bool
    # Summaries computed in the writer thread (sole mutator) so request
    # threads never read the mutating ledger/scoreboard — no race.
    paper_trading_summary: PaperTradingSummary | None = None
    prediction_table_summaries: tuple[PredictionTableSummary, ...] = ()
    confident_win_beats_confident_loss: bool | None = None
    segment_boards: tuple[SegmentBoard, ...] = ()
    recent_closed_trades: tuple[ClosedTradeView, ...] = ()
    combined_realized_pnl: float = 0.0
    strategy_readiness: tuple[StrategyReadinessSummary, ...] = ()
    memory_experiment_count: int = 0
    calibration_board: tuple = ()  # tuple[CalibrationBoardRow, ...]
    assumption_verdicts: tuple = ()  # tuple[AssumptionVerdict, ...]
    vetoed_mechanism_count: int = 0
    vetoed_entry_count: int = 0
    shadow_entry_count: int = 0
    opponent_ledger: dict | None = None  # OpponentLedgerReading as a dict
    positioning_deferred_count: int = 0

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)


# The promotion gate needs enough trades for CPCV to form groups AND to clear
# the Deflated-Sharpe minimum-trades bar; below this we report "gathering".
_MIN_TRADES_FOR_PROMOTION_GATE = StrategyPromotionConfig().minimum_trades
_PROMOTION_CPCV_CONFIG = CpcvConfig()


def _per_trade_return_fractions_by_strategy(state) -> dict[str, list[float]]:
    """Realized per-trade return fractions for each live strategy, from the
    closed trades — the input series the Deflated-Sharpe/CPCV gate scores."""
    returns_by_strategy: dict[str, list[float]] = {
        "ORB cash": [], "Directional options": [], "Credit spreads": []
    }
    for trade in state.closed_trades:
        basis = trade.entry_price * trade.quantity
        if basis > 0:
            returns_by_strategy["ORB cash"].append(trade.realized_pnl / basis)
    for position, realized in state.closed_directional_options:
        basis = position.entry_premium * position.lots * position.lot_size
        if basis > 0:
            returns_by_strategy["Directional options"].append(realized / basis)
    for spread, realized in state.closed_option_spreads:
        basis = abs(spread.entry_net_credit_per_unit * spread.lots * spread.lot_size)
        if basis > 0:
            returns_by_strategy["Credit spreads"].append(realized / basis)
    return returns_by_strategy


def _strategy_readiness_summaries(state) -> tuple[StrategyReadinessSummary, ...]:
    """Run the Deflated-Sharpe + CPCV promotion gate per strategy (research/41
    wiring). Under the minimum trade count it reports 'gathering' rather than
    forcing the gate on too little data."""
    summaries = []
    for strategy, returns in _per_trade_return_fractions_by_strategy(state).items():
        if len(returns) < _MIN_TRADES_FOR_PROMOTION_GATE:
            summaries.append(
                StrategyReadinessSummary(
                    strategy=strategy, trade_count=len(returns),
                    per_trade_sharpe_ratio=None, deflated_sharpe_ratio=None,
                    outcome="gathering_trades", promoted=False,
                )
            )
            continue
        try:
            decision = evaluate_strategy_with_cpcv_gate(
                returns, _PROMOTION_CPCV_CONFIG,
                StrategyPromotionConfig(minimum_trades=_MIN_TRADES_FOR_PROMOTION_GATE),
            )
            summaries.append(
                StrategyReadinessSummary(
                    strategy=strategy, trade_count=decision.trade_count,
                    per_trade_sharpe_ratio=decision.per_trade_sharpe_ratio,
                    deflated_sharpe_ratio=decision.deflated_sharpe_ratio,
                    outcome=decision.outcome.value, promoted=decision.promoted,
                )
            )
        except Exception:
            summaries.append(
                StrategyReadinessSummary(
                    strategy=strategy, trade_count=len(returns),
                    per_trade_sharpe_ratio=None, deflated_sharpe_ratio=None,
                    outcome="gathering_trades", promoted=False,
                )
            )
    return tuple(summaries)


class LivePaperTradingService:
    # Multi-day FII-net trend window (slice 3): trading days of participant OI
    # history walked back to trend FII index-futures net.
    _FII_NET_TREND_WINDOW = 5

    def __init__(
        self,
        authenticated_kite_client,
        account_virtual_capital: float,
        scan_interval_seconds: float = 5.0,
        max_new_cash_seeds_per_pass: int = 30,
        max_new_option_seeds_per_pass: int = 25,
        participant_positioning_source=None,
    ) -> None:
        self._kite_client = authenticated_kite_client
        # Layer 10 §10 opponent ledger — real NSE archive fetcher by default;
        # injectable (DI seam) so tests pass an in-memory fake. Fetched once per
        # trade date in the writer thread and cached.
        if participant_positioning_source is None:
            from nse_algo_trader.participant_positioning.nse_participant_positioning_source import (  # noqa: E501
                NseParticipantPositioningSource,
            )

            participant_positioning_source = NseParticipantPositioningSource()
        self._participant_positioning_source = participant_positioning_source
        self._opponent_ledger_reading = None
        self._opponent_ledger_fetched_for = None  # the date last attempted
        # persist_todays_bars=True so the replay-when-closed store grows with
        # each live session the loop trades (research/41).
        self._live_feed = KiteLiveUniverseFeed(
            authenticated_kite_client, persist_todays_bars=True
        )
        self._feed = self._live_feed  # active feed pointer (live or replay)
        self._replay_feed = None  # market-CLOSED replay half (built in start())
        self._replay_timestamps: list = []
        self._replay_cursor = 0
        self._clock = NseMarketClock()
        self._square_off_schedule = IntradaySquareOffSchedule()
        self._max_new_option_seeds_per_pass = max_new_option_seeds_per_pass
        self._tradable_universe = None
        self._banned_underlying_symbols: frozenset = frozenset()
        self._state = LiveUniversePaperState(
            ledger=PaperTradingLedger(account_virtual_capital),
            scoreboard=PredictionTableScoreboard(),
        )
        self._scan_interval_seconds = scan_interval_seconds
        self._max_new_cash_seeds_per_pass = max_new_cash_seeds_per_pass

        self._cash_universe: list = []
        self._publish_lock = threading.Lock()
        self._published = LivePaperPublishedSnapshot(
            open_positions=(), closed_trade_count=0, cash_universe_size=0,
            seeded_count=0, last_pass_at=None, is_market_open=False,
        )
        self._writer_thread: threading.Thread | None = None
        self._running = False
        # Layer 10 experience memory — opened lazily in the writer thread
        # (per-thread SQLite), fed the closed §9 experiments the loop emits.
        self._experience_memory = None

    @property
    def scoreboard(self) -> PredictionTableScoreboard:
        return self._state.scoreboard

    @property
    def ledger(self) -> PaperTradingLedger:
        return self._state.ledger

    def start(self) -> None:
        """Assemble the universe (F&O-liquid first so trades appear soonest —
        ordering, not sampling) and launch the writer thread."""
        universe = fetch_live_tradable_universe(self._kite_client)
        self._tradable_universe = universe
        liquid_underlyings = set(universe.option_underlying_symbols())
        self._cash_universe = sorted(
            universe.cash_equity_instruments,
            key=lambda instrument: (
                instrument.trading_symbol not in liquid_underlyings,
                instrument.trading_symbol,
            ),
        )
        self._banned_underlying_symbols = self._load_fo_ban_list()
        self._build_replay_feed_from_store()  # market-CLOSED replay data
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._run_forever, name="live-paper-loop", daemon=True
        )
        self._writer_thread.start()

    def _build_replay_feed_from_store(self) -> None:
        """Pre-load stored intraday bars (main thread — no cross-thread SQLite)
        into a ReplayUniverseFeed so the loop can run on replay when the market
        is closed. Only cash instruments in the tradable universe are replayed;
        the feed is empty (and replay simply idles) until bars accumulate."""
        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.paper_trading.replay_universe_feed import (
            ReplayUniverseFeed,
        )

        instrument_by_token = {
            inst.instrument_token: inst for inst in self._cash_universe
        }
        bars_by_token: dict = {}
        store = MarketDataSqliteStore()
        try:
            for token in self._stored_bar_tokens(store):
                if token not in instrument_by_token:
                    continue
                bars = store.load_price_bars(token, BarInterval.MINUTE_5)
                if bars:
                    bars_by_token[token] = bars
        finally:
            store.close()
        self._replay_feed = ReplayUniverseFeed(bars_by_token)
        self._replay_timestamps = self._replay_feed.stored_session_timestamps()
        self._replay_cursor = 0

    @staticmethod
    def _stored_bar_tokens(store) -> list:
        """Distinct instrument tokens that have stored intraday bars."""
        cursor = store._connection.execute(
            "SELECT DISTINCT instrument_token FROM price_bars"
        )
        return [row[0] for row in cursor.fetchall()]

    def stop(self) -> None:
        self._running = False

    def _load_fo_ban_list(self) -> frozenset:
        """Today's F&O ban list from the store (empty if not ingested) — fed
        to the credit-spread risk gate so banned underlyings are refused."""
        try:
            store = MarketDataSqliteStore()
            report = store.load_fo_ban_list_report(
                datetime.now(_INDIA_MARKET_TIMEZONE).date()
            )
            store.close()
            if report is not None:
                return frozenset(report.banned_underlying_symbols)
        except Exception:
            pass
        return frozenset()

    def _run_forever(self) -> None:
        while self._running:
            real_now = datetime.now(_INDIA_MARKET_TIMEZONE)
            try:  # never let one bad pass or publish kill the loop
                if self._clock.is_market_open(real_now):
                    # LIVE half: real Kite feed, wall-clock now.
                    self._feed = self._live_feed
                    self._advance_one_pass(real_now)
                elif self._replay_feed is not None and self._replay_feed.has_data():
                    # CLOSED -> REPLAY half (PLAN §1.4): step the replay clock
                    # through stored history so paper never idles.
                    self._advance_replay_pass()
                self._drain_closed_experiments_into_memory()  # Layer 10
                self._refresh_opponent_ledger(real_now)  # Layer 10 §10
                self._publish(real_now)
            except Exception as loop_error:
                import traceback

                print(
                    f"[live-paper-loop] pass error: {loop_error!r}", flush=True
                )
                traceback.print_exc()
                try:
                    self._publish(real_now, price_open_positions=False)
                except Exception:
                    pass
            time_module.sleep(self._scan_interval_seconds)

    def _advance_replay_pass(self) -> None:
        """One replay step: advance the replay clock to the next stored bar
        timestamp (looping) and run the loop against the replay feed with that
        timestamp as 'now'. A new replay day resets the per-session seeded
        state so each replayed day is a fresh session."""
        replay_now = self._replay_timestamps[self._replay_cursor]
        previous_index = (self._replay_cursor - 1) % len(self._replay_timestamps)
        previous_now = self._replay_timestamps[previous_index]
        if replay_now.date() != previous_now.date():
            self._state.seeded_cash_tokens.clear()
            self._state.watched_opening_ranges.clear()
        self._replay_cursor = (self._replay_cursor + 1) % len(self._replay_timestamps)
        self._replay_feed.set_replay_as_of(replay_now)
        self._feed = self._replay_feed
        self._advance_one_pass(replay_now, replay_mode=True)

    def _drain_closed_experiments_into_memory(self) -> None:
        """Record each closed §9 experiment the loop emitted into Layer-10
        ExperienceMemory (Rule G wiring). Runs in the writer thread; the store
        is opened lazily here so its SQLite connection lives in this thread.
        Best-effort — a memory hiccup must never stall the trading loop."""
        events = self._state.closed_experiment_events
        try:
            if self._experience_memory is None:
                self._experience_memory = SqliteExperienceMemory()
            while events:
                graded, closed_trade, instrument_kind = events.pop(0)
                self._experience_memory.record_closed_experiment(
                    build_closed_experiment(graded, closed_trade, instrument_kind)
                )
            # Refresh the antibody veto set (Layer 10 slice 3): mechanisms the
            # memory has statistically refuted stop taking new entries.
            from nse_algo_trader.memory_reflection import vetoed_mechanisms

            self._state.vetoed_mechanisms = vetoed_mechanisms(self._experience_memory)
        except Exception:
            pass

    def _refresh_opponent_ledger(self, now: datetime) -> None:
        """Fetch NSE participant-wise OI at most once per calendar date and
        cache the opponent-ledger reading (Layer 10 §10, Rule G wiring). Walks
        back over holidays/before-publish 404s to collect the most recent report
        plus a window of prior trading days for the multi-day FII-net trend
        (slice 3). Best-effort — a fetch hiccup must never stall the loop."""
        today = now.date()
        if self._opponent_ledger_fetched_for == today:
            return
        self._opponent_ledger_fetched_for = today
        try:
            from datetime import timedelta

            from nse_algo_trader.participant_positioning import read_opponent_ledger
            from nse_algo_trader.participant_positioning.participant_positioning_source import (  # noqa: E501
                ParticipantCategory,
            )

            # History walk: collect up to _FII_NET_TREND_WINDOW trading-day OI
            # snapshots (newest first), tolerating weekend/holiday 404s.
            dated_snapshots: list = []
            probe_date = today
            for _ in range(self._FII_NET_TREND_WINDOW + 8):
                if len(dated_snapshots) >= self._FII_NET_TREND_WINDOW:
                    break
                snapshot = self._participant_positioning_source.positioning_on(
                    probe_date
                )
                if snapshot is not None:
                    dated_snapshots.append((probe_date, snapshot))
                probe_date -= timedelta(days=1)

            if not dated_snapshots:
                return
            newest_date, newest_snapshot = dated_snapshots[0]
            # Recent FII index-futures net, oldest→newest (today last).
            recent_fii_nets = [
                row.future_index_net_long
                for _, snap in reversed(dated_snapshots)
                if (row := snap.row_for(ParticipantCategory.FII)) is not None
            ]
            volume_snapshot = self._participant_positioning_source.volume_on(
                newest_date
            )
            reading = read_opponent_ledger(
                newest_snapshot, volume_snapshot, recent_fii_nets
            )
            if reading is not None:
                from dataclasses import asdict

                self._opponent_ledger_reading = asdict(reading)
                self._state.market_positioning_bias = reading
        except Exception:
            # Retry on the next calendar date, not this pass.
            pass

    def _advance_one_pass(self, now: datetime, replay_mode: bool = False) -> None:
        # Honor the dashboard control plane each pass: risk budget follows the
        # configured capital/risk, and turning cash ORB off stops opening NEW
        # positions (existing open risk is still managed + squared off — never
        # abandoned). Config is re-read live so a phone toggle takes effect.
        control_config = load_trading_control_config()
        risk_budget = map_control_config_to_risk_budget(control_config)
        # Enforce the min/max capital-per-trade knobs on the live path
        # (research/41 L9): the loop clamps risk-sized qty to these each pass.
        self._state.max_capital_per_trade = control_config.max_capital_per_trade
        self._state.min_capital_per_trade = control_config.min_capital_per_trade
        seeds_this_pass = (
            self._max_new_cash_seeds_per_pass
            if is_orb_cash_trading_enabled(control_config)
            else 0
        )
        run_live_universe_scan_pass(
            self._state,
            self._cash_universe,
            self._feed,
            risk_budget,
            now,
            max_new_cash_seeds_per_pass=seeds_this_pass,
            market_clock=self._clock,
        )
        # Options credit-spread half (index + stock options): regime-gated,
        # defined-risk, atomic, squared off at 15:15 by Layer 8. Skipped in
        # replay mode — the replay store holds cash bars only (no option chain).
        if replay_mode or self._tradable_universe is None:
            return
        options_enabled = control_config.is_segment_enabled(
            TradableSegment.NSE_INDEX_OPTIONS
        ) or control_config.is_segment_enabled(TradableSegment.NSE_STOCK_OPTIONS)
        is_square_off = self._square_off_schedule.should_force_square_off_now(
            now, self._clock
        )
        advance_option_credit_spread_pass(
            self._state,
            self._tradable_universe,
            self._feed,
            risk_budget,
            now,
            max_new_underlying_seeds_per_pass=(
                self._max_new_option_seeds_per_pass if options_enabled else 0
            ),
            is_square_off_window=is_square_off,
            banned_underlying_symbols=self._banned_underlying_symbols,
        )

    def _publish(self, now: datetime, price_open_positions: bool = True) -> None:
        open_instruments = [
            position.instrument for position in self._state.open_positions.values()
        ]
        price_by_token: dict[int, float] = {}
        if price_open_positions and open_instruments:
            try:
                price_by_token = self._feed.latest_price_by_token(open_instruments)
            except Exception:
                price_by_token = {}  # show positions without a live mark
        views = []
        for position in self._state.open_positions.values():
            last_price = price_by_token.get(position.instrument.instrument_token)
            unrealized = None
            if last_price is not None:
                direction_sign = 1 if position.direction.value == "long" else -1
                unrealized = (
                    (last_price - position.entry_price)
                    * direction_sign
                    * position.quantity
                )
            views.append(
                OpenPositionView(
                    trading_symbol=position.instrument.trading_symbol,
                    direction=position.direction.value,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    stop_loss_price=position.stop_loss_price,
                    target_price=position.target_price,
                    last_price=last_price,
                    unrealized_pnl=unrealized,
                    assigned_table=position.prediction_record.assigned_table.value,
                    segment="cash",
                )
            )
        # Option credit spreads -> one synthetic row each (flows into the 3
        # §9 tables alongside cash; segment tags it index/stock option).
        views.extend(self._option_spread_views(price_open_positions))
        views.sort(key=lambda view: -(view.unrealized_pnl or 0.0))
        segment_boards = self._segment_boards(views)
        recent_closed = self._recent_closed_trades()
        ledger = self._state.ledger
        paper_summary = PaperTradingSummary(
            starting_virtual_cash=ledger.starting_virtual_cash,
            realized_pnl=ledger.realized_pnl,
            fill_count=len(ledger.recorded_fills),
            is_flat=ledger.is_flat(),
        )
        table_summaries = tuple(
            self._summarize_prediction_table(table)
            for table in PredictionLabeledTable
        )
        snapshot = LivePaperPublishedSnapshot(
            open_positions=tuple(views),
            closed_trade_count=len(self._state.closed_trades),
            cash_universe_size=len(self._cash_universe),
            seeded_count=len(self._state.seeded_cash_tokens),
            last_pass_at=now.isoformat(),
            is_market_open=self._clock.is_market_open(now),
            paper_trading_summary=paper_summary,
            prediction_table_summaries=table_summaries,
            confident_win_beats_confident_loss=(
                self._state.scoreboard.confident_win_beats_confident_loss()
            ),
            segment_boards=segment_boards,
            recent_closed_trades=recent_closed,
            combined_realized_pnl=(
                ledger.realized_pnl
                + self._state.realized_option_spread_pnl
                + self._state.realized_directional_option_pnl
            ),
            strategy_readiness=_strategy_readiness_summaries(self._state),
            memory_experiment_count=self._memory_experiment_count(),
            calibration_board=self._memory_calibration_board(),
            assumption_verdicts=self._memory_assumption_verdicts(),
            vetoed_mechanism_count=len(self._state.vetoed_mechanisms),
            vetoed_entry_count=self._state.vetoed_entry_count,
            shadow_entry_count=self._state.shadow_entry_count,
            opponent_ledger=self._opponent_ledger_reading,
            positioning_deferred_count=self._state.positioning_deferred_count,
        )
        with self._publish_lock:
            self._published = snapshot

    _INDEX_UNDERLYINGS = frozenset(
        {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
    )

    def _option_spread_views(self, price: bool) -> list[OpenPositionView]:
        spreads = list(self._state.open_option_spreads.values())
        if not spreads:
            return []
        price_by_token: dict[int, float] = {}
        if price:
            legs = [leg for sp in spreads for leg in (sp.short_leg, sp.hedge_leg)]
            try:
                price_by_token = self._feed.latest_price_by_token(legs)
            except Exception:
                price_by_token = {}
        rows = []
        for spread in spreads:
            segment = (
                "index_option"
                if spread.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            current = spread.current_net_premium_per_unit(price_by_token)
            rows.append(
                OpenPositionView(
                    trading_symbol=f"{spread.underlying_symbol} {spread.bias}",
                    direction="spread",
                    quantity=spread.lots * spread.lot_size,
                    entry_price=round(spread.entry_net_credit_per_unit, 2),
                    stop_loss_price=round(spread.entry_net_credit_per_unit * 2, 2),
                    target_price=round(spread.entry_net_credit_per_unit * 0.5, 2),
                    last_price=None if current is None else round(current, 2),
                    unrealized_pnl=spread.unrealized_pnl(price_by_token),
                    assigned_table=spread.assigned_table,
                    segment=segment,
                )
            )
        rows.extend(self._directional_option_views(price))
        return rows

    def _directional_option_views(self, price: bool) -> list[OpenPositionView]:
        positions = list(self._state.open_directional_options.values())
        if not positions:
            return []
        price_by_token: dict[int, float] = {}
        if price:
            try:
                price_by_token = self._feed.latest_price_by_token(
                    [p.option for p in positions]
                )
            except Exception:
                price_by_token = {}
        rows = []
        for pos in positions:
            segment = (
                "index_option"
                if pos.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            ltp = price_by_token.get(pos.option.instrument_token)
            rows.append(
                OpenPositionView(
                    trading_symbol=pos.option.trading_symbol,
                    direction="long",  # a bought option is a BUY
                    quantity=pos.lots * pos.lot_size,
                    entry_price=round(pos.entry_premium, 2),
                    stop_loss_price=round(pos.entry_premium * 0.5, 2),
                    target_price=round(pos.entry_premium * 2, 2),
                    last_price=None if ltp is None else round(ltp, 2),
                    unrealized_pnl=pos.unrealized_pnl(price_by_token),
                    assigned_table=pos.assigned_table,
                    segment=segment,
                )
            )
        return rows

    def _segment_boards(self, views: list[OpenPositionView]) -> tuple[SegmentBoard, ...]:
        boards = []
        for segment in ("cash", "index_option", "stock_option"):
            in_segment = [v for v in views if v.segment == segment]
            boards.append(
                SegmentBoard(
                    segment=segment,
                    open_count=len(in_segment),
                    unrealized_pnl=sum(v.unrealized_pnl or 0.0 for v in in_segment),
                )
            )
        return tuple(boards)

    def _recent_closed_trades(self) -> tuple[ClosedTradeView, ...]:
        rows = []
        for trade in self._state.closed_trades[-30:][::-1]:
            rows.append(
                ClosedTradeView(
                    segment="cash",
                    trading_symbol=trade.instrument.trading_symbol,
                    direction=trade.direction.value,
                    realized_pnl=trade.realized_pnl,
                    outcome=trade.outcome.value,
                    closed_at=trade.closed_at.isoformat(),
                )
            )
        for spread, realized in self._state.closed_option_spreads[-15:][::-1]:
            segment = (
                "index_option"
                if spread.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            rows.append(
                ClosedTradeView(
                    segment=segment,
                    trading_symbol=f"{spread.underlying_symbol} {spread.bias}",
                    direction="spread",
                    realized_pnl=realized,
                    outcome="closed",
                    closed_at=spread.opened_at.isoformat(),
                )
            )
        for pos, realized in self._state.closed_directional_options[-15:][::-1]:
            segment = (
                "index_option"
                if pos.underlying_symbol in self._INDEX_UNDERLYINGS
                else "stock_option"
            )
            rows.append(
                ClosedTradeView(
                    segment=segment,
                    trading_symbol=pos.option.trading_symbol,
                    direction="long",
                    realized_pnl=realized,
                    outcome="closed",
                    closed_at=pos.opened_at.isoformat(),
                )
            )
        return tuple(rows)

    def _memory_experiment_count(self) -> int:
        try:
            return self._experience_memory.experiment_count() if self._experience_memory else 0
        except Exception:
            return 0

    def _memory_calibration_board(self) -> tuple:
        """The reflection surface: per-mechanism predicted-vs-actual calibration
        (writer thread — same thread that owns the memory's SQLite connection)."""
        if self._experience_memory is None:
            return ()
        try:
            return tuple(self._experience_memory.calibration_board(minimum_experiments=3))
        except Exception:
            return ()

    def _memory_assumption_verdicts(self) -> tuple:
        """Layer-10 slice 2: significance-tested assumption tripwires over the
        experience memory (writer thread — owns the SQLite connection)."""
        if self._experience_memory is None:
            return ()
        try:
            from nse_algo_trader.memory_reflection import evaluate_trading_assumptions

            return tuple(evaluate_trading_assumptions(self._experience_memory))
        except Exception:
            return ()

    def _summarize_prediction_table(self, table) -> PredictionTableSummary:
        score = self._state.scoreboard.score_for_table(table)
        if score is None:
            return PredictionTableSummary(table.value, 0, None, None, None, None)
        return PredictionTableSummary(
            table=table.value,
            trade_count=score.prediction_count,
            prediction_hit_rate=score.prediction_hit_rate,
            mean_win_probability=score.mean_win_probability,
            actual_win_rate=score.actual_win_rate,
            brier_score=score.brier_score,
        )

    def published_snapshot(self) -> LivePaperPublishedSnapshot:
        with self._publish_lock:
            return self._published
