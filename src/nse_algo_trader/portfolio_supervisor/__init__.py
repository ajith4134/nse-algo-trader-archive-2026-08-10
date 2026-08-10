"""Portfolio supervisor — the pod frame above the segment bots (redesign 2026-08-03, slice 6).

Consumes ``TradeProposal``s from every ``SegmentBot``, allocates capital across the sleeves (competency-
weighted, on the existing CVXPY ``CapitalAllocationOptimizer``), nets correlated exposure per underlying,
enforces ONE portfolio risk budget, and arbitrates — the single place a trade is accepted, resized, or
vetoed (crypto Feature-Catalogue §03b). This is the decision consumer the segment bots propose into.
"""

from nse_algo_trader.portfolio_supervisor.cross_bot_crowding_monitor import (
    CrossBotCrowdingMonitor,
    CrowdingAssessment,
)
from nse_algo_trader.portfolio_supervisor.dispersion_overlay import (
    DispersionOverlay,
    DispersionSignal,
    ImpliedCorrelationStore,
)
from nse_algo_trader.portfolio_supervisor.net_exposure_netting_layer import (
    NetExposure,
    NetExposureNettingLayer,
)
from nse_algo_trader.portfolio_supervisor.portfolio_supervisor import (
    PortfolioRiskBudget,
    PortfolioSupervisor,
    SupervisorDecision,
)
from nse_algo_trader.portfolio_supervisor.pod_order_router import (
    InstrumentResolver,
    PlacedPodOrder,
    PodOrderRouter,
)
from nse_algo_trader.portfolio_supervisor.proposal_arbiter import (
    ArbitratedOrder,
    ArbitrationOutcome,
    ProposalArbiter,
)

__all__ = [
    "ArbitratedOrder",
    "ArbitrationOutcome",
    "CrossBotCrowdingMonitor",
    "CrowdingAssessment",
    "DispersionOverlay",
    "DispersionSignal",
    "ImpliedCorrelationStore",
    "InstrumentResolver",
    "PlacedPodOrder",
    "PodOrderRouter",
    "NetExposure",
    "NetExposureNettingLayer",
    "PortfolioRiskBudget",
    "PortfolioSupervisor",
    "ProposalArbiter",
    "SupervisorDecision",
]
