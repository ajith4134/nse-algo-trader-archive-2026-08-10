"""Tests for the portfolio supervisor — netting, arbitration, and the assembled cycle."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationResult
from nse_algo_trader.portfolio_supervisor.net_exposure_netting_layer import NetExposureNettingLayer
from nse_algo_trader.portfolio_supervisor.portfolio_supervisor import (
    PortfolioRiskBudget,
    PortfolioSupervisor,
)
from nse_algo_trader.portfolio_supervisor.proposal_arbiter import ArbitrationOutcome, ProposalArbiter
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    BotCompetency,
    MarketSegment,
    OptionStructureKind,
    OptionStructurePlan,
    TradeProposal,
    TradeSide,
)


def _proposal(bot, underlying, side, lots, net_delta, expiry_epoch=1e12, expectancy=0.05) -> TradeProposal:
    plan = OptionStructurePlan(OptionStructureKind.IRON_CONDOR, underlying, "2026-08-07", (),
                               is_defined_risk=True, net_delta=net_delta, net_vega=-1.0, net_theta=1.0)
    return TradeProposal(
        segment=MarketSegment.INDEX_OPTION, bot_name=bot, underlying=underlying, side=side, structure=plan,
        size_hint_lots=lots, conviction=0.8, calibrated_prob=0.6, expected_expectancy=expectancy,
        loss_tail_estimate=0.05, signal_expiry_epoch=expiry_epoch, regime_label="calm",
    )


# ---- netting layer ----
def test_netting_cancels_opposite_sides_and_flags_conflict():
    layer = NetExposureNettingLayer()
    props = [_proposal("botA", "NIFTY", TradeSide.LONG, 5, +1.0),
             _proposal("botB", "NIFTY", TradeSide.SHORT, 3, -1.0)]
    net = layer.net(props)["NIFTY"]
    assert net.is_conflicting
    assert net.net_delta_lots == pytest.approx(2.0)  # 5 long - 3 short
    assert net.gross_delta_lots == pytest.approx(8.0)  # 5 + 3
    assert set(net.contributing_bots) == {"botA", "botB"}


def test_netting_same_side_adds_and_no_conflict():
    layer = NetExposureNettingLayer()
    net = layer.net([_proposal("a", "BANKNIFTY", TradeSide.LONG, 4, +1.0),
                     _proposal("b", "BANKNIFTY", TradeSide.LONG, 6, +1.0)])["BANKNIFTY"]
    assert not net.is_conflicting and net.net_delta_lots == pytest.approx(10.0)


# ---- arbiter ----
def test_arbiter_vetoes_expired_and_zero_allocation():
    arbiter = ProposalArbiter()
    live = _proposal("a", "NIFTY", TradeSide.LONG, 5, +1.0, expiry_epoch=2000.0)
    expired = _proposal("a", "NIFTY", TradeSide.LONG, 5, +1.0, expiry_epoch=500.0)
    net = NetExposureNettingLayer().net([live])
    orders = arbiter.arbitrate([live, expired], {id(live): 5, id(expired): 5}, net,
                               max_net_delta_lots_per_underlying=100.0, now_epoch=1000.0)
    by_id = {id(o.proposal): o for o in orders}
    assert by_id[id(expired)].outcome == ArbitrationOutcome.VETO
    assert by_id[id(live)].outcome == ArbitrationOutcome.ACCEPT and by_id[id(live)].approved_lots == 5


def test_arbiter_resizes_to_per_name_cap():
    arbiter = ProposalArbiter()
    p = _proposal("a", "NIFTY", TradeSide.LONG, 20, +1.0)
    net = NetExposureNettingLayer().net([p])  # gross 20
    orders = arbiter.arbitrate([p], {id(p): 20}, net, max_net_delta_lots_per_underlying=10.0, now_epoch=0.0)
    assert orders[0].outcome == ArbitrationOutcome.RESIZE and orders[0].approved_lots == 10  # capped to 10


# ---- assembled supervisor with an injected (earned) allocator (Rule J) ----
@dataclass
class _FakeBot:
    name: str
    segment: MarketSegment
    _proposals: list

    def competency(self):
        return BotCompetency(level=5, closed_trades=300, rolling_sharpe=1.0, calibration_error=0.05, is_earned=True)

    def propose(self, now_epoch):
        return list(self._proposals)

    def learn_from_closed_trades(self):
        pass


class _FakeOptimizer:
    """Injected allocator that grants each candidate 4 lots and a benign CVaR — exercises orchestration."""

    is_performance_earned = True

    def allocate(self, candidates, account_capital, benchmark=None):
        return AllocationResult(
            weights={c.candidate_id: 1.0 / len(candidates) for c in candidates},
            capital={c.candidate_id: account_capital / len(candidates) for c in candidates},
            lots={c.candidate_id: 4 for c in candidates},
            objective_mode_used="mean_cvar", solver_status="optimal",
            portfolio_cvar=0.03, portfolio_vol=0.1, is_earned=True, fell_back=False,
            active_count=len(candidates), turnover=0.0, scenario_count=0,
        )


def test_supervisor_cycle_allocates_nets_and_arbitrates():
    prop = _proposal("index_option_bot", "NIFTY", TradeSide.NEUTRAL, 8, 0.0)
    bot = _FakeBot("index_option_bot", MarketSegment.INDEX_OPTION, [prop])
    sup = PortfolioSupervisor([bot], optimizer=_FakeOptimizer(), budget=PortfolioRiskBudget())
    decision = sup.run_cycle(account_capital=1_000_000.0, now_epoch=1e9)
    assert decision.total_proposals == 1
    assert decision.accepted_orders == 1
    assert decision.orders[0].approved_lots == 4  # min(allocator 4, hint 8)
    assert decision.solver_status == "optimal"


def test_supervisor_reports_per_bot_heartbeat():
    """The per-bot breakdown that feeds each dashboard tile's own live pulse (not the shared pod pulse)."""
    idx = _FakeBot("index_option_bot", MarketSegment.INDEX_OPTION,
                   [_proposal("index_option_bot", "NIFTY", TradeSide.LONG, 4, 0.4),
                    _proposal("index_option_bot", "BANKNIFTY", TradeSide.LONG, 4, 0.4)])
    cash = _FakeBot("cash_intraday_bot", MarketSegment.CASH_INTRADAY,
                    [_proposal("cash_intraday_bot:SBIN", "SBIN", TradeSide.LONG, 4, 0.4)])  # per-instrument suffix
    sup = PortfolioSupervisor([idx, cash], optimizer=_FakeOptimizer(), budget=PortfolioRiskBudget())
    decision = sup.run_cycle(account_capital=1_000_000.0, now_epoch=1e9)
    assert decision.proposals_by_bot == {"index_option_bot": 2, "cash_intraday_bot": 1}  # suffix stripped
    assert sum(decision.accepted_by_bot.values()) == decision.accepted_orders


def test_per_bot_heartbeat_empty_when_no_proposals():
    bot = _FakeBot("stock_option_bot", MarketSegment.STOCK_OPTION, [])
    sup = PortfolioSupervisor([bot], optimizer=_FakeOptimizer(), budget=PortfolioRiskBudget())
    decision = sup.run_cycle(account_capital=1_000_000.0, now_epoch=1e9)
    assert decision.proposals_by_bot == {}  # no-live path still returns a (empty) breakdown


def test_supervisor_hard_cvar_stop_scales_everything_down():
    class _FatTailOptimizer(_FakeOptimizer):
        def allocate(self, candidates, account_capital, benchmark=None):
            import dataclasses

            r = super().allocate(candidates, account_capital)
            # portfolio CVaR 12% of capital, well over the 6% budget → hard stop ~0.5×
            return dataclasses.replace(r, lots={c.candidate_id: 10 for c in candidates}, portfolio_cvar=0.12)

    prop = _proposal("index_option_bot", "NIFTY", TradeSide.NEUTRAL, 10, 0.0)
    bot = _FakeBot("index_option_bot", MarketSegment.INDEX_OPTION, [prop])
    sup = PortfolioSupervisor([bot], optimizer=_FatTailOptimizer(),
                              budget=PortfolioRiskBudget(max_portfolio_cvar_fraction=0.06))
    decision = sup.run_cycle(account_capital=1_000_000.0, now_epoch=1e9)
    assert decision.hard_stop_scale < 1.0
    assert decision.orders[0].approved_lots < 10  # scaled down by the portfolio-CVaR stop


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_every_option_name_gets_funded_no_squeeze():
    """User directive: NO acceptance limit on option paper trades — every proposing index/stock option name
    is funded (≥1 lot), even when hundreds of cash candidates would otherwise crowd them out (Rule L)."""
    idx = _FakeBot("index_option_bot", MarketSegment.INDEX_OPTION, [
        _proposal("index_option_bot", u, TradeSide.NEUTRAL, 4, 0.4)
        for u in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50")])

    stock_props = [_proposal("stock_option_bot", f"S{i}", TradeSide.NEUTRAL, 4, 0.4) for i in range(12)]
    for p in stock_props:  # the _proposal helper defaults to INDEX_OPTION — retag these as STOCK_OPTION
        object.__setattr__(p, "segment", MarketSegment.STOCK_OPTION)
    stock = _FakeBot("stock_option_bot", MarketSegment.STOCK_OPTION, stock_props)
    # many cash names that would dominate a single pooled allocation
    cash_props = [_proposal("cash_intraday_bot", f"C{i}", TradeSide.LONG, 4, 0.4) for i in range(50)]
    for p in cash_props:
        object.__setattr__(p, "segment", MarketSegment.CASH_INTRADAY)
    cash = _FakeBot("cash_intraday_bot", MarketSegment.CASH_INTRADAY, cash_props)

    sup = PortfolioSupervisor([idx, stock, cash], optimizer=_FakeOptimizer(), budget=PortfolioRiskBudget())
    decision = sup.run_cycle(account_capital=1_000_000.0, now_epoch=1e9)
    accepted = {o.proposal.underlying for o in decision.orders if o.approved_lots > 0}
    for u in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"):
        assert u in accepted, f"index {u} was squeezed out"  # ALL 5 indices funded
    assert sum(1 for o in decision.orders if o.approved_lots > 0
               and o.proposal.segment == MarketSegment.STOCK_OPTION) == 12  # every stock option funded


def test_option_lots_are_capital_sized_to_max_capital_per_trade():
    """Each option trade's lots fit the max-capital-per-trade cap by its defined-risk max_loss (not a flat 1)."""
    props = [_proposal("index_option_bot", u, TradeSide.NEUTRAL, 8, 0.0) for u in ("NIFTY", "BANKNIFTY")]
    # NIFTY per-lot risk ₹5k → 100k/5k = 20 lots; BANKNIFTY per-lot risk ₹120k > cap → 1 lot (min tradeable)
    object.__setattr__(props[0], "feature_provenance", {"max_loss": 5000.0})
    object.__setattr__(props[1], "feature_provenance", {"max_loss": 120000.0})
    bot = _FakeBot("index_option_bot", MarketSegment.INDEX_OPTION, props)
    sup = PortfolioSupervisor([bot], optimizer=_FakeOptimizer(), budget=PortfolioRiskBudget(
        max_net_delta_lots_per_underlying=1000.0))
    decision = sup.run_cycle(account_capital=1e10, now_epoch=1e9,
                             min_capital_per_trade=40000.0, max_capital_per_trade=100000.0,
                             max_risk_per_trade_fraction=0.02)
    by_name = {o.proposal.underlying: o.approved_lots for o in decision.orders}
    assert by_name["NIFTY"] == 20   # 100k / 5k
    assert by_name["BANKNIFTY"] == 1  # single lot exceeds cap → min tradeable


def test_no_config_falls_back_to_single_lot_floor():
    prop = _proposal("index_option_bot", "NIFTY", TradeSide.NEUTRAL, 4, 0.0)  # no max_loss provenance
    bot = _FakeBot("index_option_bot", MarketSegment.INDEX_OPTION, [prop])
    sup = PortfolioSupervisor([bot], optimizer=_FakeOptimizer(), budget=PortfolioRiskBudget())
    decision = sup.run_cycle(account_capital=1e6, now_epoch=1e9)  # no capital config
    assert decision.orders[0].approved_lots >= 1  # still funded (fallback)
