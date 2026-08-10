"""Pod runner — the live-loop tick that drives the segment-bot pod end to end (wiring, Rule G).

One call = one pod cycle: assemble the three bots on the production market-store adapters + the supervisor +
the order router, run the supervisor cycle (proposals → capital allocation → netting → arbitration → hard
CVaR stop), route the accepted ``ArbitratedOrder``s to the broker, and persist the resulting
``SupervisorDecision`` so the ``/pod`` board renders the real cycle. Designed to be invoked on the live
paper-loop cadence; until that hook is registered it is callable on demand (real STORED data — the LIVE
intraday feed is the open blocker, Rule K).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nse_algo_trader.broker_oms.simulated_broker_client import SimulatedBrokerClient
from nse_algo_trader.portfolio_supervisor.dispersion_overlay import (
    DispersionOverlay,
    ImpliedCorrelationStore,
)
from nse_algo_trader.portfolio_supervisor.market_store_data_adapters import (
    CashBhavcopyUniverseAdapter,
    MarketStoreInstrumentResolver,
    MarketStoreOptionAdapter,
)
from nse_algo_trader.portfolio_supervisor.pod_order_router import PlacedPodOrder, PodOrderRouter
from nse_algo_trader.portfolio_supervisor.pod_paper_lifecycle import PodPaperLifecycleEngine
from nse_algo_trader.portfolio_supervisor.portfolio_supervisor import (
    PortfolioSupervisor,
    SupervisorDecision,
)
from nse_algo_trader.segment_bots.cash_intraday_bot.cash_intraday_bot import CashIntradayBot
from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import IndexOptionBot
from nse_algo_trader.segment_bots.segment_bot_protocol import SegmentBot
from nse_algo_trader.segment_bots.stock_option_bot.stock_option_bot import StockOptionBot

_POD_STORE_ROOT = Path.home() / ".nse_algo_trader" / "segment_bot_pod"
_NIFTY_CONSTITUENTS = (
    "RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK",
    "BHARTIARTL", "HINDUNILVR", "BAJFINANCE", "MARUTI", "SUNPHARMA",
)


@dataclass
class PodCycleResult:
    bots: list
    decision: SupervisorDecision
    placed_orders: list[PlacedPodOrder]


class PodRunner:
    """Assembles the pod on production adapters and runs one route-through cycle per call."""

    def __init__(
        self,
        db_path: Path | None = None,
        store_root: Path | None = None,
        broker_client=None,
        account_capital: float = 1_000_000.0,
    ):
        self._root = store_root or _POD_STORE_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        from nse_algo_trader.market_data.live_option_chain_source import MultiBrokerLiveOptionChainSource
        live_chain = MultiBrokerLiveOptionChainSource()  # today's real index chain (Kite NFO/BFO; multi-broker)
        index_adapter = MarketStoreOptionAdapter(db_path, index=True, live_chain_source=live_chain)
        # widen the stock-option universe (user directive: as many as it can) — capped for per-cycle time /
        # Kite rate limits; full ~210 F&O coverage via per-cycle rotation is the queued follow-up (Rule K).
        stock_adapter = MarketStoreOptionAdapter(db_path, index=False, max_underlyings=60,
                                                 live_chain_source=live_chain)
        cash_adapter = CashBhavcopyUniverseAdapter(db_path)
        self._cash_adapter = cash_adapter
        # scale the option bots' per-structure defined-risk cap to the configured account (falls back to the
        # constructor capital) so real capital can afford normal structures; the supervisor capital-sizes below.
        risk_notional = float(self._trading_control_config().get("account", account_capital))
        self._bots: list[SegmentBot] = [
            IndexOptionBot(index_adapter, self._root / "index_option", risk_account_notional=risk_notional),
            StockOptionBot(stock_adapter, self._root / "stock_option", risk_account_notional=risk_notional),
            CashIntradayBot(cash_adapter, self._root / "cash_intraday"),
        ]
        self._supervisor = PortfolioSupervisor(self._bots)
        self._broker = broker_client or SimulatedBrokerClient()
        self._resolver = MarketStoreInstrumentResolver(db_path)
        self._router = PodOrderRouter(self._broker, self._resolver, live_instrument_resolver=live_chain)
        self._capital = account_capital
        self._index_adapter = index_adapter
        self._stock_adapter = stock_adapter
        self._dispersion = DispersionOverlay(ImpliedCorrelationStore(self._root / "dispersion"))
        from nse_algo_trader.option_alpha.option_leg_marker import OptionLegMarker
        self._lifecycle = PodPaperLifecycleEngine(
            self._root / "lifecycle", {b.name: b for b in self._bots},
            option_marker=OptionLegMarker(live_chain))  # real per-leg option P&L from the live chain (slice 4)
        from nse_algo_trader.market_data.underlying_intraday_price_source import UnderlyingIntradayPriceSource
        self._intraday_prices = UnderlyingIntradayPriceSource(db_path)
        from nse_algo_trader.option_alpha.option_book_risk_engine import OptionBookRiskEngine
        self._book_risk = OptionBookRiskEngine()  # portfolio net-greeks/CVaR + CVXPY live-sizing (non-capping)
        self._last_closes: list = []

    def _trading_control_config(self) -> dict:
        """Load the live min/max capital-per-trade + account from the dashboard control config (best-effort)."""
        try:
            from nse_algo_trader.dashboard.trading_control_config import load_trading_control_config

            c = load_trading_control_config()
            return {"account": float(c.account_virtual_capital), "min_capital": float(c.min_capital_per_trade),
                    "max_capital": float(c.max_capital_per_trade),
                    "max_risk_fraction": float(c.max_risk_per_trade_fraction)}
        except Exception:  # noqa: BLE001 — fall back to defaults if the config can't be read
            return {}

    def _lifecycle_open_count(self) -> list:
        return self._lifecycle._store.load()

    def _compute_book_risk(self) -> dict:
        """Portfolio net-greeks + CVaR over the open option book (diagnostic; never caps paper)."""
        try:
            from dataclasses import asdict

            positions = [asdict(p) for p in self._lifecycle._store.load()]
            risk = self._book_risk.assess(positions, self._price_of)
            return {"net_delta": risk.net_delta, "net_gamma": risk.net_gamma, "net_vega": risk.net_vega,
                    "net_theta": risk.net_theta, "expected_pnl": risk.expected_pnl,
                    "portfolio_cvar": risk.portfolio_cvar, "n_structures": risk.n_structures}
        except Exception:  # noqa: BLE001 — a diagnostic must never break the cycle
            return {}

    def _price_of(self, underlying: str) -> float | None:
        """Live mark for a pod position: the LATEST intraday 5m bar (moves through the session) first, then
        the stored cash last-price, then the option-underlying spot — so the dashboard LTP actually moves."""
        try:
            live = self._intraday_prices.close_series(underlying)
            if len(live):
                return float(live.iloc[-1])
        except Exception:  # noqa: BLE001 — fall through to the stored marks
            pass
        try:
            cash_price = self._cash_adapter.last_price(underlying)
            if cash_price and cash_price > 0:
                return float(cash_price)
        except Exception:  # noqa: BLE001 — fall through to the option-underlying spot
            pass
        try:
            return self._resolver.reference_spot(underlying)
        except Exception:  # noqa: BLE001 — a missing mark holds the position, never crashes the tick
            return None

    @property
    def bots(self) -> list[SegmentBot]:
        return self._bots

    def run_cycle(self, now_epoch: float, force_square_off: bool = False,
                  allow_opens: bool = True) -> PodCycleResult:
        # after the intraday square-off / when the market is closed, run a CLOSE-ONLY cycle: no supervisor, no
        # new orders — just mark + force-exit every open position so nothing is carried past the session.
        if allow_opens:
            cfg = self._trading_control_config()  # live min/max capital-per-trade sizing from the dashboard controls
            decision = self._supervisor.run_cycle(
                account_capital=cfg.get("account", self._capital), now_epoch=now_epoch,
                min_capital_per_trade=cfg.get("min_capital"), max_capital_per_trade=cfg.get("max_capital"),
                max_risk_per_trade_fraction=cfg.get("max_risk_fraction"))
            placed = self._router.route(list(decision.orders))
        else:
            decision = self._supervisor_trivial(now_epoch)
            placed = []
        # lifecycle: mark+exit prior opens then record this cycle's opens (none when close-only)
        self._last_closes = self._lifecycle.on_cycle(placed, now_epoch, self._price_of, force_square_off)
        self._persist(decision, placed, self._compute_dispersion())
        return PodCycleResult(self._bots, decision, placed)

    def _supervisor_trivial(self, now_epoch: float):
        """A no-proposal decision for close-only cycles (no supervisor run → no new trades)."""
        from nse_algo_trader.portfolio_supervisor.portfolio_supervisor import SupervisorDecision

        return SupervisorDecision((), 0.0, "closed", "closed", 1.0, {}, (), 0, 0,
                                  crowding=None, field_notes={"reason": "close-only cycle"})

    def _compute_dispersion(self) -> dict:
        """§8b dispersion: back out NIFTY implied correlation from real ATM IVs (index vs its constituents)."""
        try:
            index_iv = self._index_adapter.implied_atm_vol("NIFTY")
            raw = {s: self._stock_adapter.implied_atm_vol(s) for s in _NIFTY_CONSTITUENTS}
            constituents: dict[str, float] = {s: float(v) for s, v in raw.items() if v}
            if not index_iv or len(constituents) < 5:
                return {"action": "abstain", "reason": "insufficient real ATM IVs"}
            sig = self._dispersion.assess("NIFTY", index_iv, constituents)
            return {"action": sig.action, "implied_correlation": sig.implied_correlation,
                    "index_iv": sig.index_iv, "basket_iv": sig.basket_iv, "conviction": sig.conviction}
        except Exception:  # noqa: BLE001 — dispersion is an overlay; its failure must not break the tick
            return {"action": "abstain", "reason": "error"}

    def _per_bot_heartbeat(self, decision: SupervisorDecision) -> dict:
        """Per-bot breakdown for the dashboard's per-tile pulse: proposals + accepted + competency, this cycle."""
        heartbeat: dict[str, dict] = {}
        for bot in self._bots:
            competency = bot.competency()
            heartbeat[bot.name] = {
                "segment": bot.segment.value,
                "proposals": int(decision.proposals_by_bot.get(bot.name, 0)),
                "accepted": int(decision.accepted_by_bot.get(bot.name, 0)),
                "closed_trades": competency.closed_trades,
                "competency_level": competency.level,
                "is_earned": competency.is_earned,
            }
        return heartbeat

    def _persist(self, decision: SupervisorDecision, placed: list[PlacedPodOrder], dispersion: dict) -> None:
        snapshot = {
            "dispersion": dispersion,
            "total_proposals": decision.total_proposals,
            "accepted_orders": decision.accepted_orders,
            "by_bot": self._per_bot_heartbeat(decision),
            "closed_this_cycle": len(self._last_closes),
            "open_positions": len(self._lifecycle_open_count()),
            "book_risk": self._compute_book_risk(),
            "allocation_mode": decision.allocation_mode,
            "solver_status": decision.solver_status,
            "portfolio_cvar_fraction": decision.portfolio_cvar_fraction,
            "hard_stop_scale": decision.hard_stop_scale,
            "crowding_level": decision.crowding.level if decision.crowding else "—",
            "crowding_score": decision.crowding.crowding_score if decision.crowding else 0.0,
            "price_divergence_alarms": list(decision.price_divergence_alarms),
            "orders_placed": sum(len(p.results) for p in placed),
            "orders": [
                {"underlying": o.proposal.underlying, "structure": o.proposal.structure.kind.value,
                 "side": o.proposal.side.value, "lots": o.approved_lots, "outcome": o.outcome.value}
                for o in decision.orders
            ],
        }
        (self._root / "last_cycle.json").write_text(json.dumps(snapshot, indent=1))

    @staticmethod
    def load_last_cycle(store_root: Path | None = None) -> dict | None:
        path = (store_root or _POD_STORE_ROOT) / "last_cycle.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
