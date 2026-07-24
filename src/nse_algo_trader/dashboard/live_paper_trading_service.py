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
    load_trading_control_config,
)
from nse_algo_trader.market_data import KiteLiveUniverseFeed
from nse_algo_trader.paper_trading import (
    LiveUniversePaperState,
    PaperTradingLedger,
    run_live_universe_scan_pass,
)
from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock
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
    ) -> None:
        self._kite_client = authenticated_kite_client
        self._feed = KiteLiveUniverseFeed(authenticated_kite_client)
        self._clock = NseMarketClock()
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
        liquid_underlyings = set(universe.option_underlying_symbols())
        self._cash_universe = sorted(
            universe.cash_equity_instruments,
            key=lambda instrument: (
                instrument.trading_symbol not in liquid_underlyings,
                instrument.trading_symbol,
            ),
        )
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._run_forever, name="live-paper-loop", daemon=True
        )
        self._writer_thread.start()

    def stop(self) -> None:
        self._running = False

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
                )
            )
        views.sort(key=lambda view: -(view.unrealized_pnl or 0.0))
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
        )
        with self._publish_lock:
            self._published = snapshot

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
