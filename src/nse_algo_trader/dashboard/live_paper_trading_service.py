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
    information_diet: dict | None = None  # InformationDiet as a dict
    # §53 slice 3a: live-vs-replay experience mix, so over-reliance on 24/7
    # replay is visible ({"live": n, "replay_faithful": m}). Empty until replay
    # experiences accrue.
    experiment_count_by_provenance: dict | None = None
    # §53 slice 3b-ii: running forecast skill (log-loss/Brier) overall + split
    # live vs replay ({"overall":{...}, "live":{...}, "replay_faithful":{...}}).
    prequential_forecast_score: dict | None = None

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
        high_fidelity_replay=None,
        breeze_session_token_store=None,
        breeze_historical_source_builder=None,
        autonomous_breeze_replay_call_budget=5000,
        record_live_market_depth=False,
        market_depth_focus_size=100,
        market_depth_recorder=None,
    ) -> None:
        self._kite_client = authenticated_kite_client
        # §53 slice 4 P4a-wire: optional HighFidelityReplayConfig — when injected,
        # the market-closed replay is built from a higher-fidelity source (Breeze
        # 1-second) for a bounded focus set instead of the stored 5-minute bars.
        # None (default) keeps the store path exactly as before (no regression).
        self._high_fidelity_replay = high_fidelity_replay
        # §53 slice 4 task #7: autonomous self-activation seams (default real). When
        # no explicit high_fidelity_replay is passed AND a valid Breeze session
        # token is stored, start() builds a rate-limited 1s config itself.
        self._breeze_session_token_store = breeze_session_token_store
        self._breeze_historical_source_builder = breeze_historical_source_builder
        self._autonomous_breeze_replay_call_budget = autonomous_breeze_replay_call_budget
        # §53 slice 4 P4b: record live order-book depth forward (the only path to
        # historical depth). Default OFF (no load/behaviour change); enable to start
        # accumulating. The store is built lazily in the writer thread (SQLite is
        # single-thread). market_depth_recorder is a DI seam for tests.
        self._record_live_market_depth = record_live_market_depth
        self._market_depth_focus_size = market_depth_focus_size
        self._market_depth_recorder = market_depth_recorder
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
        if self._high_fidelity_replay is None:
            self._maybe_activate_autonomous_breeze_replay()  # §53 task #7
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
        if self._high_fidelity_replay is not None:
            self._build_high_fidelity_replay_feed()  # §53 P4a-wire (Breeze 1s)
            return
        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.paper_trading.historical_archive_replay_planner import (
            HistoricalArchiveReplayPlanner,
        )
        from nse_algo_trader.paper_trading.point_in_time_universe_resolver import (
            PointInTimeUniverseResolver,
        )
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
            # Slice-2 wiring (research/62 P2): keep each bar only if its
            # instrument was in the REAL cash universe on that bar's own date
            # (survivorship-free, §11.1) — not merely in today's universe.
            # Pass-through for dates with no ingested bhavcopy, so replay never
            # idles for want of a point-in-time universe.
            archive_replay_planner = HistoricalArchiveReplayPlanner(
                PointInTimeUniverseResolver(store)
            )
            bars_by_token = archive_replay_planner.filter_bars_to_point_in_time_universe(
                bars_by_token,
                {
                    inst.instrument_token: inst.trading_symbol
                    for inst in self._cash_universe
                },
            )
        finally:
            store.close()
        self._replay_feed = ReplayUniverseFeed(
            bars_by_token,
            corporate_action_adjustment_engine=(
                self._build_corporate_action_adjustment_engine(bars_by_token)
            ),
        )
        self._replay_timestamps = self._replay_feed.stored_session_timestamps()
        self._replay_cursor = 0

    def _build_high_fidelity_replay_feed(self) -> None:
        """§53 slice 4 P4a-wire: build the market-closed replay feed from the
        injected higher-fidelity source (Breeze 1-second) for the config's focus
        instruments over one session (09:15–15:30 IST), instead of the stored
        5-minute bars. Same `ReplayUniverseFeed` the loop already consumes."""
        from zoneinfo import ZoneInfo

        from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (  # noqa: E501
            build_replay_bars_by_token_from_source,
        )
        from nse_algo_trader.paper_trading.replay_universe_feed import (
            ReplayUniverseFeed,
        )

        config = self._high_fidelity_replay
        ist = ZoneInfo("Asia/Kolkata")
        session_open = datetime(
            config.session_date.year, config.session_date.month,
            config.session_date.day, 9, 15, tzinfo=ist,
        )
        session_close = datetime(
            config.session_date.year, config.session_date.month,
            config.session_date.day, 15, 30, tzinfo=ist,
        )
        bars_by_token = build_replay_bars_by_token_from_source(
            config.bar_source, config.focus_instruments,
            config.bar_interval, session_open, session_close,
        )
        self._replay_feed = ReplayUniverseFeed(bars_by_token)
        self._replay_timestamps = self._replay_feed.stored_session_timestamps()
        self._replay_cursor = 0

    def _maybe_activate_autonomous_breeze_replay(self) -> None:
        """§53 slice 4 task #7: when a valid daily Breeze session token is stored,
        self-build a rate-limited 1-second `HighFidelityReplayConfig` so the loop
        runs 1s replay UNATTENDED. Best-effort — no token / no creds / network
        error leaves `high_fidelity_replay` None → the store-5m path, so the
        always-on service always starts."""
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        from nse_algo_trader.market_data import BarInterval
        from nse_algo_trader.broker_sessions.breeze_session_token_store import (
            BreezeSessionTokenFileStore,
        )
        from nse_algo_trader.paper_trading.breeze_replay_focus_planner import (
            plan_breeze_replay_focus,
        )
        from nse_algo_trader.paper_trading.historical_source_replay_feed_builder import (  # noqa: E501
            HighFidelityReplayConfig,
        )
        from nse_algo_trader.paper_trading.historical_trading_day_walker import (
            HistoricalTradingDayWalker,
        )

        try:
            token_store = (
                self._breeze_session_token_store or BreezeSessionTokenFileStore()
            )
            token_record = token_store.load_if_still_valid()
            if token_record is None:
                return  # no fresh manual token -> stay on store-5m replay
            source_builder = (
                self._breeze_historical_source_builder
                or _build_authenticated_breeze_historical_source
            )
            bar_source = source_builder(token_record.session_token)
            session_date = HistoricalTradingDayWalker(
                self._clock
            ).most_recent_trading_day_on_or_before(
                datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=1)
            )
            focus_instruments = plan_breeze_replay_focus(
                self._liquidity_ranked_cash_universe(),
                self._autonomous_breeze_replay_call_budget,
                BarInterval.SECOND_1,
            )
            if not focus_instruments:
                return
            self._high_fidelity_replay = HighFidelityReplayConfig(
                bar_source=bar_source,
                focus_instruments=focus_instruments,
                session_date=session_date,
                bar_interval=BarInterval.SECOND_1,
            )
        except Exception:
            self._high_fidelity_replay = None  # never break startup

    @staticmethod
    def _build_corporate_action_adjustment_engine(bars_by_token):
        """Real NSE split/bonus actions over the replayed window so the replay
        lookback series stays continuous across ex-dates (research/62 P3, §11.2).
        Best-effort: any fetch failure or empty result → None (identity), so
        replay never breaks on a corporate-action data hiccup."""
        from nse_algo_trader.market_data.nse_corporate_action_source import (
            NseLibCorporateActionSource,
        )
        from nse_algo_trader.paper_trading.corporate_action_adjustment import (
            CorporateActionAdjustmentEngine,
        )

        bar_dates = [
            bar.timestamp.date()
            for bars in bars_by_token.values()
            for bar in bars
        ]
        if not bar_dates:
            return None
        try:
            actions_by_symbol = NseLibCorporateActionSource().corporate_actions_by_symbol(
                min(bar_dates), max(bar_dates)
            )
        except Exception:  # network / nselib / parse hiccup — never break replay
            return None
        if not actions_by_symbol:
            return None
        return CorporateActionAdjustmentEngine(actions_by_symbol)

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
                    self._record_market_depth_best_effort()  # §53 P4b (forward)
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

    def _liquidity_ranked_cash_universe(self) -> list:
        """Cash universe ordered most-liquid-first by the latest stored cash
        bhavcopy turnover (§53 task #8), so the rate-limited 1s replay focus is
        spent on the names that matter. Best-effort — falls back to the existing
        (option-underlyings-first) order if no bhavcopy is stored."""
        from nse_algo_trader.paper_trading.breeze_replay_focus_planner import (
            rank_instruments_by_liquidity,
        )

        try:
            store = MarketDataSqliteStore()
            try:
                latest_date = store.latest_cash_bhavcopy_trade_date()
                if latest_date is None:
                    return self._cash_universe
                turnover_by_symbol = {
                    row.symbol: row.turnover_lakhs
                    for row in store.load_cash_bhavcopy_delivery_rows(latest_date)
                }
            finally:
                store.close()
            return rank_instruments_by_liquidity(
                self._cash_universe, turnover_by_symbol
            )
        except Exception:
            return self._cash_universe

    def _record_market_depth_best_effort(self) -> None:
        """§53 P4b: snapshot + store the focus set's order book this live pass.
        Best-effort — depth recording must NEVER disturb trading. The store is built
        lazily HERE (writer thread) because SQLite objects are single-thread."""
        if not self._record_live_market_depth:
            return
        try:
            if self._market_depth_recorder is None:
                from nse_algo_trader.market_data.kite_market_depth_source import (
                    KiteMarketDepthSource,
                )
                from nse_algo_trader.market_data.market_depth_snapshot_store import (
                    MarketDepthSnapshotStore,
                )
                from nse_algo_trader.paper_trading.live_market_depth_recorder import (
                    LiveMarketDepthRecorder,
                )

                self._market_depth_recorder = LiveMarketDepthRecorder(
                    KiteMarketDepthSource(self._kite_client),
                    MarketDepthSnapshotStore(),
                )
            focus_tokens = [
                instrument.instrument_token
                for instrument in self._cash_universe[: self._market_depth_focus_size]
            ]
            self._market_depth_recorder.record_once(focus_tokens)
        except Exception:
            pass  # never let depth recording break the trading loop

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

    def _current_data_provenance(self) -> str:
        """Provenance of the data the loop is trading on right now — the active
        feed's stamp in replay, "live" otherwise (research/53 §8.2). A trade
        opens and squares off within one session/mode, so this drain-time read
        equals the trade's provenance. Consumes the slice-1 watermark (Rule G)."""
        from nse_algo_trader.paper_trading.replay_experience_provenance import (
            DataProvenance,
        )

        if self._replay_feed is not None and self._feed is self._replay_feed:
            return self._replay_feed.provenance_stamp().provenance.value
        return DataProvenance.LIVE.value

    def _drain_closed_experiments_into_memory(self) -> None:
        """Record each closed §9 experiment the loop emitted into Layer-10
        ExperienceMemory (Rule G wiring). Runs in the writer thread; the store
        is opened lazily here so its SQLite connection lives in this thread.
        Best-effort — a memory hiccup must never stall the trading loop."""
        events = self._state.closed_experiment_events
        try:
            if self._experience_memory is None:
                self._experience_memory = SqliteExperienceMemory()
            data_provenance = self._current_data_provenance()
            while events:
                graded, closed_trade, instrument_kind = events.pop(0)
                self._experience_memory.record_closed_experiment(
                    build_closed_experiment(
                        graded, closed_trade, instrument_kind, data_provenance
                    )
                )
            # Refresh the antibody veto set (Layer 10 slice 3): mechanisms the
            # memory has statistically refuted stop taking new entries.
            from nse_algo_trader.memory_reflection import (
                learn_mechanism_recalibrations,
                vetoed_mechanisms,
            )

            vetoed = vetoed_mechanisms(self._experience_memory)
            # research/51: learn win-probability bias offsets + hard-veto no-edge
            # (resolution≈0) mechanisms — the memory acting on its own diagnosis.
            offsets, no_edge = learn_mechanism_recalibrations(self._experience_memory)
            self._state.recalibration_offset_by_mechanism = offsets
            self._state.vetoed_mechanisms = vetoed | no_edge
        except Exception:
            pass

    def _information_diet_dict(self) -> dict:
        """Aggregate the loop's decision-input counters into the §10 information
        diet + health read (research/52)."""
        from dataclasses import asdict

        from nse_algo_trader.paper_trading.information_diet import (
            read_information_diet,
        )

        state = self._state
        # §53 slice 3b-i: feed the live-vs-replay experience mix so the diet warns
        # on over-reliance on 24/7 replay.
        by_provenance = self._memory_experiment_count_by_provenance()
        return asdict(
            read_information_diet(
                decisions_considered=state.entry_decisions_considered,
                positioning_deferred=state.positioning_deferred_count,
                antibody_vetoed=state.vetoed_entry_count,
                memory_recalibrated=state.recalibrated_entry_count,
                shadow_probes=state.shadow_entry_count,
                live_experience_count=by_provenance.get("live", 0),
                replay_experience_count=by_provenance.get("replay_faithful", 0),
            )
        )

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
            experiment_count_by_provenance=self._memory_experiment_count_by_provenance(),
            prequential_forecast_score=self._memory_prequential_forecast_score(),
            calibration_board=self._memory_calibration_board(),
            assumption_verdicts=self._memory_assumption_verdicts(),
            vetoed_mechanism_count=len(self._state.vetoed_mechanisms),
            vetoed_entry_count=self._state.vetoed_entry_count,
            shadow_entry_count=self._state.shadow_entry_count,
            opponent_ledger=self._opponent_ledger_reading,
            positioning_deferred_count=self._state.positioning_deferred_count,
            information_diet=self._information_diet_dict(),
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

    def _memory_experiment_count_by_provenance(self) -> dict:
        """The live-vs-replay experience mix (§53 slice 3a) — so the dashboard can
        show whether the brain is over-relying on 24/7 replay vs real live sessions
        (writer thread — owns the memory's SQLite connection)."""
        try:
            return (
                self._experience_memory.experiment_count_by_provenance()
                if self._experience_memory
                else {}
            )
        except Exception:
            return {}

    def _memory_prequential_forecast_score(self) -> dict:
        """Running forecast skill (log-loss/Brier) overall + split live vs replay
        (§53 slice 3b-ii; writer thread owns the memory's SQLite connection)."""
        if self._experience_memory is None:
            return {}
        try:
            from dataclasses import asdict

            return {
                "overall": asdict(self._experience_memory.prequential_forecast_score()),
                "live": asdict(
                    self._experience_memory.prequential_forecast_score(
                        data_provenance="live"
                    )
                ),
                "replay_faithful": asdict(
                    self._experience_memory.prequential_forecast_score(
                        data_provenance="replay_faithful"
                    )
                ),
            }
        except Exception:
            return {}

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
            mean_logarithmic_score=score.mean_logarithmic_score,
        )

    def published_snapshot(self) -> LivePaperPublishedSnapshot:
        with self._publish_lock:
            return self._published


def _build_authenticated_breeze_historical_source(session_token: str):
    """§53 task #7 default source builder: compose a real authenticated Breeze
    1-second source — creds → client (#6a) → ICICI stock-code resolver (#6b) →
    adapter. Network + the `breeze_connect` import happen ONLY here, so the rest of
    the service (and tests, which inject a fake builder) stay import-clean."""
    from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
        BrokerName,
        load_broker_api_credentials,
        load_env_file_into_environ,
    )
    from nse_algo_trader.broker_sessions.breeze_authenticated_client_builder import (
        build_authenticated_breeze_client,
    )
    from nse_algo_trader.market_data.breeze_historical_bar_source import (
        BreezeHistoricalBarSource,
    )
    from nse_algo_trader.market_data.icici_security_master_stock_code_resolver import (
        IciciSecurityMasterStockCodeResolver,
        download_icici_nse_scrip_master_text,
    )

    load_env_file_into_environ()
    credentials = load_broker_api_credentials(BrokerName.ICICI_BREEZE)
    client = build_authenticated_breeze_client(credentials, session_token)
    resolver = IciciSecurityMasterStockCodeResolver.from_nse_scrip_master_text(
        download_icici_nse_scrip_master_text()
    )
    return BreezeHistoricalBarSource(client, stock_code_resolver=resolver)
