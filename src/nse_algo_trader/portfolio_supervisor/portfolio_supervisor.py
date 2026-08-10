"""Portfolio supervisor — assembles allocation + netting + arbitration over the segment bots (slice 6).

Each cycle: collect every bot's proposals → drop expired → price-reconciliation guard (choice-B: sanity-
check that bots agree on a shared underlying's price before netting) → competency-weight each proposal's
edge → solve capital allocation on the existing CVXPY ``CapitalAllocationOptimizer`` → net exposure per
underlying → arbitrate to final orders → apply the ONE hard portfolio-CVaR stop that overrides every bot.

The supervisor is the decision consumer the segment bots propose into (Rule G): a bot's proposal only
becomes an order here. It reuses the real allocator + society consensus rather than hand-rolling either.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate
from nse_algo_trader.capital_allocation.capital_allocation_optimizer import (
    CapitalAllocationOptimizer,
)
from nse_algo_trader.portfolio_supervisor.cross_bot_crowding_monitor import (
    CrossBotCrowdingMonitor,
    CrowdingAssessment,
)
from nse_algo_trader.portfolio_supervisor.net_exposure_netting_layer import (
    NetExposure,
    NetExposureNettingLayer,
)
from nse_algo_trader.portfolio_supervisor.proposal_arbiter import (
    ArbitratedOrder,
    ArbitrationOutcome,
    ProposalArbiter,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    MarketSegment,
    SegmentBot,
    TradeProposal,
    TradeSide,
)

_SEGMENT_TO_ALLOCATOR = {
    MarketSegment.CASH_INTRADAY: "cash_equity",
    MarketSegment.INDEX_OPTION: "index_option",
    MarketSegment.STOCK_OPTION: "stock_option",
}
_NOMINAL_LOT_NOTIONAL = 100_000.0  # ₹ nominal per lot for capital→lots (real margin/price is a refinement)
_WARMUP_WEIGHT = 1.0 / 6.0  # cold-start paper weight for an unearned bot (= a level-0 earned bot's weight)


def _base_bot_name(bot_name: str) -> str:
    """The owning bot for a proposal — strips the per-instrument suffix (e.g. ``cash_intraday_bot:SBIN``)."""
    return str(bot_name).split(":", 1)[0]


def _count_by_bot(bot_names) -> dict:
    """Tally an iterable of proposal ``bot_name``s into {base bot name → count} for the per-bot heartbeat."""
    counts: dict[str, int] = {}
    for name in bot_names:
        base = _base_bot_name(name)
        counts[base] = counts.get(base, 0) + 1
    return counts


@dataclass(frozen=True)
class PortfolioRiskBudget:
    """The ONE portfolio-level budget the supervisor enforces over all sleeves."""

    max_portfolio_cvar_fraction: float = 0.06  # hard stop: portfolio tail loss ≤ 6% of capital
    max_net_delta_lots_per_underlying: float = 20.0  # per-name gross exposure cap (netting)
    price_reconciliation_tolerance: float = 0.01  # 1% — bots must agree on a shared underlying's price


@dataclass(frozen=True)
class SupervisorDecision:
    """The supervisor's full output for one cycle."""

    orders: tuple[ArbitratedOrder, ...]
    portfolio_cvar_fraction: float
    allocation_mode: str
    solver_status: str
    hard_stop_scale: float  # <1.0 means the portfolio-CVaR stop scaled everything down
    net_exposures: dict[str, NetExposure]
    price_divergence_alarms: tuple[str, ...]  # underlyings where bots disagreed on price (choice-B guard)
    total_proposals: int
    accepted_orders: int
    crowding: CrowdingAssessment | None = None
    field_notes: dict = field(default_factory=dict)
    proposals_by_bot: dict = field(default_factory=dict)  # base bot name → proposals this cycle
    accepted_by_bot: dict = field(default_factory=dict)  # base bot name → accepted orders this cycle


class PortfolioSupervisor:
    """Coordinates the segment bots into one risk-budgeted, netted, arbitrated order set."""

    def __init__(
        self,
        bots: list[SegmentBot],
        optimizer: CapitalAllocationOptimizer | None = None,
        budget: PortfolioRiskBudget | None = None,
    ):
        self._bots = bots
        self._optimizer = optimizer or CapitalAllocationOptimizer()
        self._budget = budget or PortfolioRiskBudget()
        self._netting = NetExposureNettingLayer()
        self._arbiter = ProposalArbiter()
        self._crowding = CrossBotCrowdingMonitor()

    def run_cycle(self, account_capital: float, now_epoch: float,
                  min_capital_per_trade: float | None = None, max_capital_per_trade: float | None = None,
                  max_risk_per_trade_fraction: float | None = None) -> SupervisorDecision:
        competency_by_bot = {bot.name: bot.competency() for bot in self._bots}
        proposals: list[TradeProposal] = []
        for bot in self._bots:
            proposals.extend(bot.propose(now_epoch))
        live = [p for p in proposals if not p.is_expired(now_epoch)]

        price_alarms = self._reconcile_prices(live)

        if not live:
            return SupervisorDecision((), 0.0, "trivial", "trivial", 1.0, {}, tuple(price_alarms),
                                      len(proposals), 0, crowding=None,
                                      field_notes={"reason": "no live proposals"},
                                      proposals_by_bot=_count_by_bot(p.bot_name for p in proposals))

        candidates = [self._to_candidate(p, competency_by_bot) for p in live]
        result = self._optimizer.allocate(candidates, account_capital=account_capital)  # portfolio-level metadata + CVaR

        # Rule L (segments EQUAL): allocate each segment within an EQUAL capital slice, so index options / stock
        # options / cash each get funded — otherwise the 400+ cash candidates crowd out the 5 index names and
        # NIFTY & co. never win a slot. Acceptance uses these segment-fair lots; the portfolio CVaR/metadata
        # above still views the whole book.
        # each option trade's lots are CAPITAL-MEASURED to the min/max-capital-per-trade config (not a flat 1)
        effective_max = self._effective_max_capital(account_capital, max_capital_per_trade,
                                                    max_risk_per_trade_fraction)
        allocation_lots = self._segment_fair_lots(live, candidates, account_capital,
                                                  min_capital_per_trade, effective_max)

        net_exposures = self._netting.net(live)
        orders = self._arbiter.arbitrate(
            live, allocation_lots, net_exposures,
            self._budget.max_net_delta_lots_per_underlying, now_epoch,
        )

        # ONE hard portfolio-CVaR stop — overrides every bot absolutely (crypto §03b rule 5)
        cvar_fraction = self._portfolio_cvar_fraction(result, account_capital)
        hard_scale = 1.0
        if cvar_fraction > self._budget.max_portfolio_cvar_fraction > 0:
            hard_scale = self._budget.max_portfolio_cvar_fraction / cvar_fraction
            orders = self._apply_hard_stop(orders, hard_scale)

        # §8b cross-bot crowding: shrink gross risk when the sleeves converge (before the drawdown)
        crowding = self._crowding.assess(live)
        if crowding.recommended_gross_scale < 1.0:
            orders = self._apply_hard_stop(orders, crowding.recommended_gross_scale)

        accepted = sum(1 for o in orders if o.outcome != ArbitrationOutcome.VETO and o.approved_lots > 0)
        accepted_orders = [o for o in orders if o.outcome != ArbitrationOutcome.VETO and o.approved_lots > 0]
        return SupervisorDecision(
            orders=tuple(orders),
            portfolio_cvar_fraction=cvar_fraction,
            allocation_mode=result.objective_mode_used,
            solver_status=result.solver_status,
            hard_stop_scale=hard_scale,
            net_exposures=net_exposures,
            price_divergence_alarms=tuple(price_alarms),
            total_proposals=len(proposals),
            accepted_orders=accepted,
            crowding=crowding,
            field_notes={"is_allocation_earned": result.is_earned, "fell_back": result.fell_back},
            proposals_by_bot=_count_by_bot(p.bot_name for p in proposals),
            accepted_by_bot=_count_by_bot(o.proposal.bot_name for o in accepted_orders),
        )

    def _segment_fair_lots(self, live, candidates, account_capital: float,
                           min_capital_per_trade: float | None = None,
                           max_capital_per_trade: float | None = None) -> dict:
        """Allocate each SEGMENT within an equal capital slice (Rule L) → {id(proposal): lots}.

        Runs the CVXPY allocator once per segment so index/stock/cash each get funded. For OPTION segments there
        is NO acceptance limit (every proposing name trades) and each trade's lots are CAPITAL-MEASURED to the
        min/max-capital-per-trade config (sized to its defined-risk max-loss), not a flat 1 lot.
        """
        by_segment: dict = {}
        for proposal, candidate in zip(live, candidates, strict=False):
            by_segment.setdefault(proposal.segment, []).append((proposal, candidate))
        slice_capital = account_capital / max(len(by_segment), 1)
        lots: dict = {}
        for segment, items in by_segment.items():
            seg_candidates = [c for _, c in items]
            seg_result = self._optimizer.allocate(seg_candidates, account_capital=slice_capital)
            seg_lots = {int(cid): n for cid, n in seg_result.lots.items() if n}
            is_option = segment in (MarketSegment.INDEX_OPTION, MarketSegment.STOCK_OPTION)
            for proposal, _ in items:
                allocated = seg_lots.get(id(proposal), seg_result.lots.get(str(id(proposal)), 0))
                if is_option:
                    sized = self._capital_sized_lots(
                        proposal, min_capital_per_trade, max_capital_per_trade, fallback=max(int(allocated), 1))
                    # the arbiter clamps to size_hint_lots — make the capital-measured size the intended size
                    # so it isn't clipped back to the bot's small default (frozen proposal → set in place).
                    object.__setattr__(proposal, "size_hint_lots", sized)
                    lots[id(proposal)] = sized
                else:
                    lots[id(proposal)] = int(allocated)  # cash keeps allocator selection (no floor)
        return lots

    @staticmethod
    def _effective_max_capital(account_capital: float, max_capital_per_trade: float | None,
                               max_risk_per_trade_fraction: float | None) -> float | None:
        """The binding per-trade capital cap = min(max-capital-per-trade, max-risk-fraction × account)."""
        caps = [c for c in (max_capital_per_trade,
                            (max_risk_per_trade_fraction * account_capital
                             if max_risk_per_trade_fraction else None)) if c and c > 0]
        return min(caps) if caps else None

    @staticmethod
    def _capital_sized_lots(proposal, min_capital: float | None, max_capital: float | None, fallback: int) -> int:
        """Lots sized so the trade's capital-at-risk (defined-risk max loss) fits the max-capital cap.

        per-lot capital = the synthesized structure's max_loss (from the payoff optimizer, one contract lot).
        lots = floor(effective_max / per_lot), min 1 (a single lot is the smallest tradeable, even if it alone
        exceeds the cap). Falls back to the allocator lots when there is no max_loss to size against.
        """
        if not max_capital or max_capital <= 0:
            return fallback
        provenance = getattr(proposal, "feature_provenance", {}) or {}
        per_lot_risk = provenance.get("max_loss")
        if not per_lot_risk or per_lot_risk <= 0:
            return fallback  # no defined-risk estimate (template structure) → allocator fallback
        lots = int(max_capital // float(per_lot_risk))
        return max(1, lots)

    # -- helpers --------------------------------------------------------------------------------------
    def _to_candidate(self, proposal: TradeProposal, competency_by_bot: dict) -> AllocationCandidate:
        competency = competency_by_bot.get(proposal.bot_name)
        # Rule-Q warm-up: an unearned bot gets a small non-zero paper weight (floor) so it can open the paper
        # trades that earn its competency — instead of a 0.0 deadlock. Earned bots ladder up by level. LIVE
        # capital still gates on earned competency at the live-execution seam (this is the paper pod).
        if competency and competency.is_earned:
            weight = (competency.level + 1) / 6.0
        else:
            weight = _WARMUP_WEIGHT  # cold-start paper participation
        direction = "short" if proposal.side == TradeSide.SHORT else "long"
        per_unit_risk = max(proposal.loss_tail_estimate, 1e-4)
        return AllocationCandidate(
            candidate_id=str(id(proposal)),
            segment=_SEGMENT_TO_ALLOCATOR[proposal.segment],
            underlying=proposal.underlying,
            direction=direction,
            instrument_kind=_SEGMENT_TO_ALLOCATOR[proposal.segment],
            expected_edge_mu=proposal.expected_expectancy * weight,  # competency-weighted edge
            per_unit_risk=per_unit_risk,
            entry_price=_NOMINAL_LOT_NOTIONAL,
            lot_or_tick_size=1,
            est_margin_per_unit=per_unit_risk * _NOMINAL_LOT_NOTIONAL,
        )

    def _reconcile_prices(self, proposals: list[TradeProposal]) -> list[str]:
        """Choice-B guard: if two bots report different spots for one underlying, raise a divergence alarm."""
        spots: dict[str, list[float]] = {}
        for p in proposals:
            spot = p.feature_provenance.get("spot") if isinstance(p.feature_provenance, dict) else None
            if spot:
                spots.setdefault(p.underlying, []).append(float(spot))
        alarms = []
        for underlying, values in spots.items():
            if len(values) >= 2 and (max(values) - min(values)) / max(values) > self._budget.price_reconciliation_tolerance:
                alarms.append(underlying)
        return alarms

    @staticmethod
    def _portfolio_cvar_fraction(result, account_capital: float) -> float:
        if account_capital <= 0:
            return 0.0
        # portfolio_cvar is a positive loss magnitude (₹ or fraction depending on the optimizer's scaling)
        cvar = float(result.portfolio_cvar)
        return cvar if 0.0 <= cvar <= 1.0 else max(0.0, cvar / account_capital)

    @staticmethod
    def _apply_hard_stop(orders: list[ArbitratedOrder], scale: float) -> list[ArbitratedOrder]:
        scaled = []
        for o in orders:
            if o.outcome == ArbitrationOutcome.VETO or o.approved_lots <= 0:
                scaled.append(o)
                continue
            new_lots = int(max(0, round(o.approved_lots * scale)))
            outcome = ArbitrationOutcome.RESIZE if new_lots < o.approved_lots else o.outcome
            note = o.rationale + f" | portfolio-CVaR hard stop ×{scale:.2f}"
            scaled.append(ArbitratedOrder(o.proposal, new_lots, outcome, note))
        return scaled
