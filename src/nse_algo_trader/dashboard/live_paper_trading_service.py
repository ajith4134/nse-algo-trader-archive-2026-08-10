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

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)


class LivePaperTradingService:
    def __init__(
        self,
        authenticated_kite_client,
        account_virtual_capital: float,
        scan_interval_seconds: float = 5.0,
        max_new_cash_seeds_per_pass: int = 40,
        max_new_option_seeds_per_pass: int = 12,
    ) -> None:
        self._kite_client = authenticated_kite_client
        self._feed = KiteLiveUniverseFeed(authenticated_kite_client)
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
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._run_forever, name="live-paper-loop", daemon=True
        )
        self._writer_thread.start()

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
            now = datetime.now(_INDIA_MARKET_TIMEZONE)
            try:  # never let one bad pass or publish kill the loop
                if self._clock.is_market_open(now):
                    self._advance_one_pass(now)
                self._publish(now)
            except Exception as loop_error:
                import traceback

                print(
                    f"[live-paper-loop] pass error: {loop_error!r}", flush=True
                )
                traceback.print_exc()
                # still publish status so the dashboard reflects liveness
                try:
                    self._publish(now, price_open_positions=False)
                except Exception:
                    pass
            time_module.sleep(self._scan_interval_seconds)

    def _advance_one_pass(self, now: datetime) -> None:
        # Honor the dashboard control plane each pass: risk budget follows the
        # configured capital/risk, and turning cash ORB off stops opening NEW
        # positions (existing open risk is still managed + squared off — never
        # abandoned). Config is re-read live so a phone toggle takes effect.
        control_config = load_trading_control_config()
        risk_budget = map_control_config_to_risk_budget(control_config)
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
        # defined-risk, atomic, squared off at 15:15 by Layer 8.
        if self._tradable_universe is None:
            return
        options_enabled = control_config.is_segment_enabled(
            TradableSegment.NSE_INDEX_OPTION
        ) or control_config.is_segment_enabled(TradableSegment.NSE_STOCK_OPTION)
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
                ledger.realized_pnl + self._state.realized_option_spread_pnl
            ),
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
        return tuple(rows)

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
